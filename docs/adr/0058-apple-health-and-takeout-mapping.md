# ADR-0058: Apple Health and Takeout — record mapping, the sleep wake-day rule, and one precedence flip

## Status
Accepted. Built by B13, migration 0051. Opens OQ-48.

## Date
2026-09-09

## 1. Sleep belongs to the day you wake up, and a night is one session

ADR-0019 assigns a subject day by applying an 04:00-local boundary to the **start** instant.
Sleep is the documented exception — `core.atoms.subject_day`'s own column comment already
says "EXCEPT sleep atoms which are assigned to the wake day". This ADR states how.

The naive reading — apply the 04:00 rule to each segment's **end** — is wrong, and the test
`test_ADR_0058_sleep_intervals_assign_subject_day_by_wake_day` was written to catch it. Apple
records a night as several stage segments. A night running 23:40 → 07:10 produces segments
that end at 01:40, 03:10 and 07:10. Under the per-segment reading the first two end before
04:00 and land on the previous day while the third lands on the next — **one night split
across two subject days**, which is a worse error than the one the wake-day rule was
introduced to fix.

**The rule.** Segments are grouped into **sessions**; a session ends when more than **3 hours**
separate one segment from the next. Every segment in a session takes the subject day of that
session's final wake instant, under the ordinary 04:00 rule. Three hours is comfortably above
intra-night gaps (Apple records wake periods as their own `Awake` segments, so real gaps are
minutes) and far below the twelve-plus hours between nights, so an afternoon nap stays its own
session rather than being folded into that night —
`test_ADR_0058_a_nap_is_its_own_session_and_does_not_join_the_following_night`.

Each stage segment is stored as its own atom with `valid_interval = [start, end)` and a value
in minutes, rather than as one pre-summed nightly total. The totals are recoverable by summing;
the segments are not recoverable from a total.

## 2. Units are read, never assumed

Apple writes the unit into every record, and it is locale-dependent: the same
`HKQuantityTypeIdentifierBodyMass` arrives as `lb` on one phone and `kg` on another. Every
conversion is keyed on the unit string Apple actually wrote, and each record type declares the
set of units it accepts. **A record whose unit is not in that set is dropped and counted, never
guessed at.** A locale change therefore surfaces as a reported `unconvertible_unit:` count
instead of as silently wrong numbers — which is the difference between a visible gap (RULE-06)
and a fabricated value (RULE-01).

Two conversions are worth naming because they are the ones that look like no-ops and are not:

- **HealthKit's percent unit is a 0..1 fraction**, so a record written with `unit="%"` is
  multiplied by 100 — **unconditionally, for every such type**. The first version branched per
  *value* ("if it is ≤ 1.0 treat it as a fraction"), justified by SpO2 physiology, and applied
  that branch to the walking percentages too. Review caught it: walking asymmetry is
  legitimately below 1%, so two adjacent readings of `0.8` and `1.2` landed as `80.0` and
  `1.2` — 78.8 apart, on two different scales, in one column, with nothing recording which
  branch had fired. A deterministic conversion plus range rejection is the correct shape.
- **Values outside the registry's plausible range are dropped, never clamped.** A clamped
  reading is an invented one; a dropped reading is an honest gap. The bounds are read from
  `core.metric_registry` and passed into the parser, so the instrument range is stored
  configuration rather than a constant in the importer.

  **This was claimed here before it was true.** The first version of this ADR, the migration's
  comment, the importer's own docstring and a test *named* for the behaviour all asserted
  range rejection while the predicate that implements it was never called from anywhere: a
  9999 bpm heart rate was stored as a measured atom. The test passed because it called the
  dead predicate directly and asserted four booleans. That is precisely the failure RULE-00
  exists to name — a green test standing in for an unbuilt gate — and it is recorded here
  rather than quietly fixed, because the mechanism that let it happen (a test asserting a
  helper instead of the behaviour) is more useful to remember than the bug.

Nothing here produces an interval-valued estimate: every sample is a device measurement, so
`estimate_method = 'measured'` and low = point = high, which is what the `atoms_measured_is_point`
constraint requires (RULE-05, RULE-08).

## 3. Takeout: two members are read, and location is refused by name

`Chrome/BrowserHistory.json` becomes `web_visit` atoms; `watch-history.json` becomes
`media_play` atoms. Both are **event atoms** — they carry no value, because what they record is
that something happened, and inventing a duration for a page visit would be a fabricated
quantity.

**Location history is refused by name (REQ-LOC-005, RULE-29).** Takeout carries
`Location History/Records.json` and the semantic-location files. A coordinate belongs only in
the restricted store B5 built, reached by B5's ingress. This importer therefore *declines* those
members explicitly and counts the refusals, rather than merely not asking for them — a refusal
is testable and an omission is not. `test_REQ_LOC_005_takeout_location_history_is_never_read`
puts location members in the archive and asserts that none of them is opened while the Chrome
member beside them still imports.

Both readers are incremental. `BrowserHistory.json` is a single array holding years of visits;
`json.load` on it costs several times the file size in memory, so objects are pulled one at a
time with `raw_decode` over a sliding buffer — the same reason the Apple Health parser uses
`iterparse`. `test_ADR_0058_iterparse_handles_a_300mb_fixture_within_memory_limit` pins peak RSS
below 500 MB on a generated 300 MB export, measured **inside the child process** with
`RUSAGE_SELF`. (Measuring `RUSAGE_CHILDREN` from the parent, as the first version did, reads a
monotonic maximum over every reaped child that is never reset, so the reported figure collapses
to zero once any earlier subprocess in the suite has peaked higher — and one does.)

Three properties of the incremental JSON reader are load-bearing, and each was wrong first:

- **A malformed record raises, and does not truncate.** Treating every decode failure as "an
  object straddling the read boundary" meant one bad record part-way through a history file
  ended the iteration silently. `import_drop` then wrote a capture saying `n_records: 1`, moved
  the file to `_done/`, and — idempotency keying on the file hash — refused to ever read that
  archive again. Five thousand visits, lost with no error anywhere. Raising leaves the file
  re-importable, which is the entire point.
- **The array is found by a string-aware scan.** Anchoring on the first bare `[` finds one
  inside a string value; Takeout's own `{"note":"see [here]", "Browser History":[…]}` shape
  defeats it, and the reader then yields nothing at all, silently.
- **Bytes go through an incremental UTF-8 decoder.** Decoding each ~1 MiB chunk independently
  splits multibyte characters at the boundaries — roughly 200 of them in a 200 MB history —
  and `errors="replace"` writes U+FFFD into a title that is stored verbatim in
  `core.atoms.evidence_span`, indistinguishable from what the source actually said. Stored text
  must be what the source said.

## 4. One precedence flip in `panel.py`, and the two metrics it does NOT apply to

`panel.py`'s stated order is `signals > legacy_daily > atoms` — fresher provenance wins. The
`attention` stream in `public.signals` stopped on 2026-07-28, so once Takeout history is
imported the atoms are the live source and signals is the stale one. For **`chrome_events` and
`yt_events` only**, the order is flipped to atoms-first. `panel.py` expresses precedence as
insertion order plus `on conflict do nothing`, so this is a new step ahead of the signals pass.
`CODE_VERSION` moves to `panel-v2` so rows built under the old order stay identifiable (RULE-12).

**Correction after review: this is a FILL, not an override.** The build order asked for atoms
to *win* these two metrics. That is unsafe and was not done, for two reasons that appear only
where the two sources overlap:

- **The two sources use different day boundaries.** Atoms carry `subject_day` (04:00 ET,
  ADR-0019); the signals passes group by `ts::date`, the server's UTC calendar date. A visit at
  22:00 ET is one day under one rule and the previous day under the other, so an override would
  move every late-evening visit one day earlier across the overlap — a silent step in the middle
  of a series, which is exactly what this ADR refuses to accept for the `screen_*` metrics one
  paragraph below. The original text asserted an event count "means the same thing in both
  stacks"; that claim was unverifiable by this ADR's own admission that the old stack's code
  cannot be read, and it is false on the day-boundary axis regardless of what it counted.
- **Chrome expires local history at roughly 90 days**, so a Takeout archive covers about a
  quarter. Letting it win would replace complete historical values with partial ones.

Atoms are therefore inserted **after** the signals passes, filling only days signals never
covered. The join still carries the day-boundary difference; that is recorded as OQ-52 rather
than hidden.

**The four `screen_*` metrics are deliberately NOT re-derived.** `screen_active_hours`,
`screen_binge_min`, `screen_max_binge` and `screen_sessions` are session-level statistics whose
definitions — the inactivity gap that ends a session, the length that makes a session a binge —
live in the old stack's code, which is not in this repository and cannot be read. Re-deriving
them here would require inventing those thresholds, and the resulting series would step
silently at the changeover while continuing to carry the historical name. They therefore keep
coming from signals alone and go **visibly stale**, which is the honest failure.
`test_ADR_0058_session_level_screen_metrics_are_not_re_derived_from_atoms` exists to stop a
later change from quietly adding them. Recorded as **OQ-48**.

An event count has no such ambiguity: it is the number of events in the subject day, and it
means the same thing in both stacks. That is the whole reason the flip is limited to two metrics.

## Consequences

- Sleep analysis aligns to the morning it is about, and one night is one row-group, not two.
- A locale or firmware change that alters a unit produces a counted refusal, not bad data.
- Attention counts survive the old stack's death; the four session metrics do not, and say so.
- `web_visit` / `media_play` atoms carry no duration, so any future screen-time measure must
  define its own sessionization explicitly — which is the point.
