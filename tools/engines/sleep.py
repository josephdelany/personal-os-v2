"""B21.2 — sleep timing measures (REQ-SLP, authored alongside; RULE-06/07/08, RULE-12).

Pure: no database, no clock, no model. Every function takes explicit intervals and an explicit
timezone, so a replay is reproducible and a daylight-saving change cannot move a midpoint.

THREE FACTS ABOUT ONE NIGHT THAT ARE NOT THE SAME FACT, and conflating any two is the OQ-48
family of error:

  * DURATION  — how long Joe was asleep: the union of the asleep segments (ADR-0089's
                `interval_union_minutes`, already in the panel). Awake-in-bed is excluded.
  * WINDOW    — onset to final wake. It CONTAINS the awake periods, so it is always >= duration
                and is not a sleep duration under another name.
  * MIDPOINT  — the centre of the window. It says WHEN Joe slept, not how much, and it is the
                input to regularity.

A night of 6h duration inside a 9h window is a different night from 6h inside a 6h window. Any
measure that reported one number for both would erase that.
"""
from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
METHOD_VERSION = "sleep-v1"

# RULE-12: ONE definition of where a sleep session ends. The importer already groups segments
# into sessions on a three-hour gap (ADR-0058) and this imports that constant rather than
# restating it, so the engine and the importer cannot come to disagree about what one night is.
from tools.importers.apple_health import SLEEP_SESSION_GAP  # noqa: E402

# REQ-SLP: below this a regularity figure is arithmetic on too little (RULE-06). Seven nights
# is the smallest window over which "usual bedtime" is a meaningful phrase at all, and it is a
# floor, not a target.
MIN_NIGHTS_FOR_REGULARITY = 7


@dataclass(frozen=True)
class Omission:
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class Night:
    onset: dt.datetime
    final_wake: dt.datetime
    window_min: float
    asleep_min: float
    # Naps, disclosed rather than merged into the night (RULE-06).
    other_sessions: int = 0
    other_asleep_min: float = 0.0

    @property
    def awake_in_window_min(self) -> float:
        """The gap the window contains and the duration does not. Never negative."""
        return round(max(self.window_min - self.asleep_min, 0.0), 1)

    @property
    def efficiency(self):
        """REQ-SLP. Asleep over window. `None` when the window is zero — a ratio with no
        denominator is not 100%, it is undefined (RULE-06)."""
        if self.window_min <= 0:
            return None
        return round(self.asleep_min / self.window_min, 3)


def merge(intervals):
    """Union of [start, end) pairs, so an overlapping segment is counted once (RULE-08)."""
    ordered = sorted((s, e) for s, e in intervals if s is not None and e is not None and s < e)
    out = []
    for start, end in ordered:
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def sessions(intervals, gap=SLEEP_SESSION_GAP):
    """Split merged segments into separate sleep SESSIONS on a gap.

    A subject day can hold a night AND a nap. Treating every segment in one day as a single
    period is not a rounding error: 2026-07-14 held two blocks 352 minutes apart, which became
    a 938-minute "window" with 586 minutes of sleep in it and a midpoint at 13:14 — an outlier
    that on its own pushed the regularity spread from plausible to 208 minutes. A nap must be
    visible as a nap, not as a night that went strangely.
    """
    out = []
    for start, end in merge(intervals):
        if out and start - out[-1][-1][1] <= gap:
            out[-1].append((start, end))
        else:
            out.append([(start, end)])
    return out


def night(intervals, gap=SLEEP_SESSION_GAP):
    """The MAIN sleep session's window and duration, or an Omission.

    "Main" is the longest session by time asleep. Other sessions in the same subject day are
    counted in `other_sessions` rather than folded in, so a nap is disclosed instead of
    inflating the night it sits beside.
    """
    grouped = sessions(intervals, gap)
    if not grouped:
        return Omission("no_segments", "no asleep interval for this night")
    def asleep_of(block):
        return sum((e - s).total_seconds() for s, e in block)
    main = max(grouped, key=asleep_of)
    onset, final_wake = main[0][0], main[-1][1]
    return Night(onset=onset, final_wake=final_wake,
                 window_min=round((final_wake - onset).total_seconds() / 60.0, 1),
                 asleep_min=round(asleep_of(main) / 60.0, 1),
                 other_sessions=len(grouped) - 1,
                 other_asleep_min=round(sum(asleep_of(b) for b in grouped
                                            if b is not main) / 60.0, 1))


def midpoint_minutes(n: Night, tz=ET):
    """Minutes past LOCAL midnight of the window's centre.

    Local, not UTC: a March clock change would otherwise move every midpoint by an hour and
    read as Joe's sleep shifting. Values are wrapped around noon, so 23:50 and 00:10 are ten
    minutes apart rather than twenty-three hours (REQ-SLP, RULE-12).
    """
    centre = n.onset + (n.final_wake - n.onset) / 2
    local = centre.astimezone(tz)
    minutes = local.hour * 60 + local.minute + local.second / 60.0
    # Anchor on noon so a night spanning midnight does not split the distribution in two.
    return round(minutes - 1440 if minutes >= 720 else minutes, 1)


def regularity(nights, tz=ET, min_nights=MIN_NIGHTS_FOR_REGULARITY):
    """REQ-SLP. The spread of sleep midpoints, or an Omission.

    A missing night is UNKNOWN, not "the usual" (RULE-07): it is absent from the input and
    absent from the statistic, and the count of nights actually used is returned so a caller
    can refuse a thin figure rather than presenting it as settled.
    """
    points = [midpoint_minutes(n, tz) for n in nights if isinstance(n, Night)]
    if len(points) < min_nights:
        return Omission("too_few_nights",
                        f"{len(points)} night(s) with sleep timing; regularity needs at least "
                        f"{min_nights} before 'usual bedtime' means anything")
    return dict(
        sd_minutes=round(statistics.stdev(points), 1),
        median_midpoint_minutes=round(statistics.median(points), 1),
        nights_used=len(points),
        method_version=METHOD_VERSION,
        # RULE-08: a spread is the measure here. A single "usual bedtime" would state a
        # precision a 23-night sample does not have.
        note="the spread of sleep midpoints in minutes; a smaller number is a more regular "
             "schedule, and it carries no target")
