"""Shared vocabulary for the file-drop importers (B13, ADR-0057).

The only thing every importer agrees on: what an atom-to-be looks like, and how a subject
day is assigned. Nothing here touches the database.
"""
import datetime as dt
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# ADR-0019: the subject day boundary is 04:00 local (ET). Assignment is by the *start*
# instant for everything except sleep, which ADR-0058 assigns by the WAKE instant — a night
# that begins at 23:40 on the 8th and ends at 07:10 on the 9th is the 9th's sleep, because
# that is the day it is a fact about.
SUBJECT_DAY_RULE_VERSION = "v1-2026-08-23"


def subject_day(ts: dt.datetime) -> dt.date:
    """The 04:00-ET subject day containing `ts`."""
    local = ts.astimezone(ET)
    d = local.date()
    if local.hour < 4:
        d -= dt.timedelta(days=1)
    return d


def current_subject_day(now: dt.datetime = None) -> dt.date:
    """The subject day in progress right now.

    Anything comparing a stored `subject_day` against "today" must use this and not the
    database server's `current_date`. The server keeps UTC; the subject day turns at 04:00 ET.
    Between 00:00 and 04:00 ET the two differ by a day in summer and, because the offset moves,
    a job scheduled at a fixed UTC time can sit on the correct side of the boundary in EDT and
    the wrong side in EST — which would inflate every metric's elapsed-day count by one for the
    whole winter and turn a freshness check permanently red.
    """
    return subject_day(now or dt.datetime.now(dt.timezone.utc))


def utc_key(ts) -> str:
    """An instant, rendered identically no matter which timezone the reader is in."""
    if ts is None:
        return None
    if ts.tzinfo is None:            # a naive value is not an instant; refuse to guess
        raise ValueError("dedupe key needs an aware datetime")
    return ts.astimezone(dt.timezone.utc).isoformat()


def quantise(value, places: int = 6):
    """Round to `places` half-away-from-zero, as Postgres `numeric` does, via Decimal.

    Used for the dedupe key on both sides of the comparison. `round()` on a Python float is
    banker's rounding and disagrees with Postgres on an exact tie, which would let one real
    duplicate through per tie.
    """
    if value is None:
        return None
    q = Decimal(1).scaleb(-places)
    return str(Decimal(str(float(value))).quantize(q, rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class AtomSpec:
    """One atom an importer wants written. `value` is None for an event atom (a web visit,
    a media play) that records that something happened and carries no quantity.

    An AtomSpec is deliberately not an atom: it has no raw_capture_id, no recorded_at and
    no id. Those belong to the writer, which is the only thing that knows the capture row.
    """
    kind: str
    metric_key: Optional[str]
    occurred_at: Optional[dt.datetime] = None
    interval_start: Optional[dt.datetime] = None
    interval_end: Optional[dt.datetime] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    state_class: Optional[str] = None
    estimate_method: Optional[str] = None
    time_precision: str = "exact"
    presence: str = "observed"
    evidence_span: Optional[str] = None
    # Sleep only (ADR-0058). Set by the importer once a whole sleep SESSION has been seen, to
    # the subject day of that session's final wake instant. It is an explicit value rather
    # than a rule applied per segment because a night is one fact: applying the 04:00 rule to
    # each segment's own end would file the segments that end before 04:00 on the previous
    # day and split a single night across two subject days — the exact misalignment the
    # wake-day rule exists to prevent.
    subject_day_override: Optional[dt.date] = None

    @property
    def subject_day(self) -> dt.date:
        if self.subject_day_override is not None:
            return self.subject_day_override
        anchor = self.occurred_at or self.interval_start
        if anchor is None:
            raise ValueError("AtomSpec has no instant to assign a subject day from")
        return subject_day(anchor)

    @property
    def dedupe_key(self) -> tuple:
        """What makes this atom the same fact as one already stored (B13 dedupe rule).

        A re-export overlaps every previously imported day, so this is the difference
        between an idempotent re-import and silently doubling seven years of samples.

        **`evidence_span` is part of the key, and has to be.** Without it, two genuinely
        distinct transactions on the same day for the same amount — a $20 payment to each of
        two people, two identical fares, two identical coffees — produce identical keys and
        the second is silently discarded as a duplicate. That is ordinary data, not an edge
        case. `evidence_span` is stable across re-exports (it carries the record type and
        source device for Apple Health, the merchant and descriptor for a statement, the
        domain or channel for Takeout), so including it does not weaken idempotency.

        Value is quantised with `Decimal` rather than `round(float(...))` so that this key
        and the SQL-side key in `import_drop.load_dedupe_keys` — which rounds a Postgres
        `numeric` half-away-from-zero — agree on a tie. Python's float `round` is
        banker's rounding, so the two disagreed at exactly the 7th decimal.

        **Every instant is rendered in UTC**, which is the half of this that actually mattered
        and which a first fix missed. Python renders an Apple timestamp with the offset the
        file carried (`-04:00`); pg8000 renders the same `timestamptz` in the *database
        session's* `TimeZone`, which is UTC on Supabase. The two strings can then never be
        equal, so nothing is ever recognised as a duplicate and every overlapping re-export
        writes its samples again — silently, reporting `duplicates_skipped: 0` as if that were
        good news. The tests did not catch it because this machine's session happened to be in
        the same zone as the fixture data; a UTC session (which is production, and which is
        every CI runner) fails. Normalising both sides to UTC makes the key a property of the
        instant rather than of whoever is looking at it.
        """
        return (
            self.kind,
            self.metric_key,
            utc_key(self.occurred_at),
            utc_key(self.interval_start),
            utc_key(self.interval_end),
            quantise(self.value),
            self.evidence_span,
        )


def file_sha256(path, chunk: int = 1 << 20) -> str:
    """The idempotency key for a dropped file (ADR-0057).

    REQ-CAP-006 asks for a UUIDv7 minted on the device. A file Joe exported has no device
    identity to mint one from, so the file's own content hash takes that role: the same
    export dropped twice is the same capture, and is skipped.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def redact(exc) -> str:
    """A driver error, with any echoed row content removed.

    Postgres attaches `DETAIL: Failing row contains (...)` to a constraint violation, and for
    these tables that row carries `evidence_span` — merchant names, page titles, video titles.
    Any command that promises counts and never contents must pass every driver error through
    here, including from paths that "cannot fail", because those are exactly the ones nobody
    remembers to guard.
    """
    text = str(exc)
    cut = len(text)
    for marker in ("DETAIL", "Failing row contains", "'D':"):
        i = text.find(marker)
        if i != -1:
            cut = min(cut, i)
    if cut < len(text):
        text = text[:cut] + "[detail withheld: may contain record content]"
    return text[:300]


def in_range(value: float, low, high) -> bool:
    """Instrument-range check. A value outside its registry range is DROPPED, never
    clamped: a clamped reading is a fabricated one (RULE-01), and a missing reading is a
    documented gap (RULE-06)."""
    if value is None:
        return False
    if low is not None and value < float(low):
        return False
    if high is not None and value > float(high):
        return False
    return True
