#!/usr/bin/env python3
"""The drop folder: exported files become captures and atoms (B13, ADR-0057).

    PYTHONPATH=. python3 tools/import_drop.py                      # inspect only, no writes
    PYTHONPATH=. python3 tools/import_drop.py --since 2026-07-28   # bound the window
    PYTHONPATH=. python3 tools/import_drop.py --since 2026-07-28 --commit

**Why this exists.** On 2026-07-28 the device-side capture path stopped and the samples for
every day since were never ingested. They still exist on the phone (Apple Health) and in
Google's export. This is the path that recovers them, and thereafter the path that keeps
working when a live feed breaks again.

**The model.** Joe drops `export.zip` (Apple Health), a bank `*.csv`/`*.qfx`, or
`Takeout*.zip` into `~/PersonalOS_Drop/`. Each *file* becomes exactly one
`core.raw_captures` row (`source='file_import'`) whose payload carries the file's SHA-256,
its record count and the period it covers. Every atom from that file points at that row, so
INV-1 holds by construction: each derived row traces to a capture. The file itself is never
stored in the database — it stays on the Mac, and nothing personal is committed anywhere
(RULE-29).

**Idempotency.** A file whose SHA-256 is already present is skipped whole (ADR-0057; this is
REQ-FIN-011/012's `raw_documents` rule expressed in the spine's vocabulary — the capture row
*is* the document row). Within a file, an atom whose (kind, metric_key, instant, value) is
already stored is not written again, so re-exporting an overlapping window is a no-op rather
than a doubling. Nothing is ever updated or deleted: raw_captures and atoms are append-only
(RULE-02), and the drop file is moved to `_done/`, never removed.

**Default is read-only.** Without `--commit` the whole transaction is rolled back and only
counts are printed. Counts, never contents: this command prints how many atoms a file would
produce and never a value, a merchant, a title or a URL.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

from lib import db
from tools.importers import apple_health, bank, takeout
from tools.importers.common import (SUBJECT_DAY_RULE_VERSION, file_sha256, in_range,
                                    quantise, redact, utc_key)
from tools.importers.apple_health import Counters

DROP_DIR = Path(os.environ.get("PERSONAL_OS_DROP", Path.home() / "PersonalOS_Drop"))
DONE_DIR = DROP_DIR / "_done"
BATCH = 500

# The kinds each importer writes, used to bound the dedupe key load.
IMPORTER_KINDS = {
    "apple_health": ("vital_sample", "heart_rate_variability", "body_measurement",
                     "activity_sample", "environment_sample", "sleep"),
    "bank": ("transaction",),
    "takeout": ("web_visit", "media_play"),
}


def classify(path: Path):
    """Which importer owns this file. Returns an importer name or None."""
    n = path.name.lower()
    if n.endswith(".zip") and n.startswith("takeout"):
        return "takeout"
    if n == "export.zip" or n == "export.xml" or n.endswith("_export.xml"):
        return "apple_health"
    if n.endswith((".csv", ".qfx", ".ofx", ".qbo")):
        return "bank"
    if n.endswith(".zip"):
        # An Apple Health export is a zip containing export.xml; a Takeout zip was caught
        # above by name. Look inside rather than guess from the extension.
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
            if any(x.rsplit("/", 1)[-1] == "export.xml" for x in names):
                return "apple_health"
            if any(x.rsplit("/", 1)[-1] in (takeout.CHROME_MEMBER, takeout.YOUTUBE_MEMBER)
                   for x in names):
                return "takeout"
        except Exception:
            return None
    return None


def open_apple_export(path: Path):
    """Apple exports a zip containing `apple_health_export/export.xml`. Return a file object
    positioned at the XML, streamed from inside the zip — the archive is never unpacked to
    disk, so no copy of the health export is left lying around."""
    import zipfile
    if path.suffix.lower() == ".xml":
        return open(path, "rb")
    z = zipfile.ZipFile(path)
    for name in z.namelist():
        if name.rsplit("/", 1)[-1] == "export.xml":
            return z.open(name)
    raise ValueError(f"{path.name}: no export.xml inside")


def registry_ranges(cur, schema):
    """metric_key -> (plausible_low, plausible_high) from the registry.

    The instrument range that decides whether a sample is credible is stored configuration,
    never a constant in the importer — the migration says so and this is what makes that true.
    """
    cur.execute(f"select metric_key, plausible_low, plausible_high from {schema}.metric_registry")
    return {k: (None if lo is None else float(lo), None if hi is None else float(hi))
            for k, lo, hi in cur.fetchall()}


def bounded(specs, ranges, counters):
    """Drop any atom whose value falls outside its registry range, and count it.

    RULE-01 / RULE-06: an implausible reading is a documented gap, never the nearest legal
    value — a clamped reading is a fabricated one. The bounds are stored configuration
    (`core.metric_registry.plausible_low/high`), never constants in an importer.

    **This is the only place the check happens, deliberately.** The first version put it
    inside the Apple Health parser, defaulted it off, and therefore applied it to quantity
    records only — sleep segments and bank transactions were never checked at all, and every
    database test called the importer without bounds and stored a 9999 bpm heart rate. One
    choke point that every importer's output passes through cannot be forgotten by an importer.
    """
    for s in specs:
        if s.value is not None and s.metric_key is not None:
            lo, hi = ranges.get(s.metric_key, (None, None))
            if not in_range(float(s.value), lo, hi):
                counters.bump(f"out_of_range:{s.metric_key}")
                continue
        yield s


def specs_for(importer, path, since, until, counters, ranges):
    if importer == "apple_health":
        fp = open_apple_export(path)
        try:
            yield from bounded(
                apple_health.parse(fp, since=since, until=until, counters=counters),
                ranges, counters)
        finally:
            fp.close()
    elif importer == "bank":
        yield from bounded(bank.parse(path, since=since, until=until, counters=counters),
                           ranges, counters)
    elif importer == "takeout":
        yield from bounded(takeout.parse(path, since=since, until=until, counters=counters),
                           ranges, counters)
    else:
        raise ValueError(f"unknown importer {importer!r}")


def already_imported(cur, schema, sha, since, until):
    """The capture for this exact file AND this exact window, or None.

    Keying on the hash alone was wrong and would have bitten on the documented primary use
    case: recovering the 2026-07-28 gap with `--since` writes only the windowed atoms, and a
    hash-only key then refuses to ever read the rest of that seven-year export again — leaving
    no remedy except deleting a `raw_captures` row, which RULE-02 forbids. The window is part
    of what was imported, so it is part of the identity of the import. Re-running the same
    file with the same window is still a no-op, and a widened window is safe because the
    per-atom dedupe stops anything already stored from being written twice.
    """
    cur.execute(
        f"""select capture_id from {schema}.raw_captures
             where payload->>'file_sha256' = %s
               and coalesce(payload->'window_requested'->>0,'') = %s
               and coalesce(payload->'window_requested'->>1,'') = %s
             limit 1""",
        (sha, since.isoformat() if since else "", until.isoformat() if until else ""))
    r = cur.fetchone()
    return r[0] if r else None


def load_dedupe_keys(cur, schema, kinds, since, until):
    """Existing atoms of these kinds, as dedupe keys.

    Bounded by the [since, until] subject-day window when one is given. Without a window
    this loads every atom of those kinds, which is fine at today's size and is not fine at
    seven years of history — which is why `--since` exists and why the loaded count is
    printed rather than hidden.
    """
    where = ["kind = any(%s)"]
    params = [list(kinds)]
    if since:
        where.append("subject_day >= %s"); params.append(since)
    if until:
        where.append("subject_day <= %s"); params.append(until)
    cur.execute(
        f"""select kind, metric_key, occurred_at, lower(valid_interval), upper(valid_interval),
                   round(coalesce(value_point, value_low), 6), evidence_span
              from {schema}.atoms where {' and '.join(where)}""", params)
    keys = set()
    for kind, mk, occ, lo, hi, val, ev in cur.fetchall():
        # utc_key on both sides: pg8000 renders a timestamptz in the session's TimeZone, which
        # is UTC on Supabase and the local zone on a developer's machine. Rendering the raw
        # value here would make the key depend on who is asking.
        keys.add((kind, mk, utc_key(occ), utc_key(lo), utc_key(hi), quantise(val), ev))
    return keys


def insert_atoms(cur, schema, capture_id, batch, code_version):
    """One multi-row INSERT per batch. pg8000's executemany issues a statement per row, which
    turns a large import into an hour of round trips."""
    if not batch:
        return 0
    cols = ("raw_capture_id, kind, metric_key, occurred_at, time_precision, valid_interval, "
            "subject_day, subject_day_rule_version, presence, value_low, value_point, "
            "value_high, estimate_method, unit, state_class, trust_level, provenance, "
            "evidence_span, code_version")
    rows, params = [], []
    for s in batch:
        rows.append("(%s,%s,%s,%s,%s::" + schema + ".time_precision,"
                    "case when %s::timestamptz is null then null "
                    "else tstzrange(%s::timestamptz, %s::timestamptz, '[)') end,"
                    "%s,%s,%s::" + schema + ".presence,%s,%s,%s,%s,%s,"
                    "%s::" + schema + ".state_class,%s::" + schema + ".trust_level,"
                    "%s::" + schema + ".provenance,%s,%s)")
        v = None if s.value is None else float(s.value)
        params += [
            capture_id, s.kind, s.metric_key, s.occurred_at, s.time_precision,
            s.interval_start, s.interval_start, s.interval_end,
            s.subject_day, SUBJECT_DAY_RULE_VERSION, s.presence,
            # RULE-05 / atoms_measured_is_point: a measured value is a point, so low, point
            # and high are the same number. It is not a fake interval; it is the constraint's
            # own statement that this reading was measured, not resolved.
            v, v, v,
            s.estimate_method, s.unit, s.state_class, "trusted", "extracted",
            s.evidence_span, code_version,
        ]
    cur.execute(f"insert into {schema}.atoms ({cols}) values " + ",".join(rows), params)
    return len(batch)


def import_file(cur, schema, path, importer, since, until, code_version, ranges):
    """Returns a dict of counts. Caller owns commit/rollback.

    `ranges` is required, not optional. It was optional once and every caller omitted it,
    which turned range rejection off everywhere it mattered while the ADR said otherwise.
    Pass `registry_ranges(cur, schema)`.
    """
    sha = file_sha256(path)
    existing = already_imported(cur, schema, sha, since, until)
    if existing:
        return {"file": path.name, "importer": importer, "status": "skipped_duplicate_file",
                "capture_id": str(existing), "atoms_written": 0}

    counters = Counters()

    # Pass 1 — count and find the period. raw_captures is append-only (RULE-02), so its
    # payload has to be right when it is written; there is no second chance to correct
    # records_parsed. Counting first is what buys that, at the cost of reading the file twice.
    n = 0
    lo = hi = None
    for s in specs_for(importer, path, since, until, counters, ranges):
        n += 1
        d = s.subject_day
        lo = d if lo is None or d < lo else lo
        hi = d if hi is None or d > hi else hi

    capture_id = uuid.uuid4()
    payload = {
        "kind": "import",
        "importer": importer,
        "file_name": path.name,
        "file_sha256": sha,
        "file_bytes": path.stat().st_size,
        "records_parsed": n,
        "period": [lo.isoformat() if lo else None, hi.isoformat() if hi else None],
        "window_requested": [since.isoformat() if since else None,
                             until.isoformat() if until else None],
    }
    # `captured_at` is the moment the exported file was produced. The file's mtime is the
    # best available evidence of that; `recorded_at` (defaulted) is when this system learned
    # it. Two timestamps, as RULE-03 requires.
    captured_at = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
    # 'enriched' is the terminal state of the lifecycle in 0004 (received ->
    # pending_enrichment -> enriched | failed). A file import is fully extracted in the same
    # transaction that lands the capture, so it is never 'received': there is no later pass
    # to run, and raw_captures is append-only, so the status it is written with is the status
    # it keeps.
    cur.execute(
        f"""insert into {schema}.raw_captures
              (capture_id, captured_at, source, trust_level, payload, processing_status)
            values (%s, %s, 'file_import', 'trusted', %s, 'enriched')""",
        (capture_id, captured_at, json.dumps(payload)))

    if n == 0:
        return {"file": path.name, "importer": importer, "status": "no_records_in_window",
                "capture_id": str(capture_id), "atoms_written": 0,
                "counters": dict(counters)}

    seen = load_dedupe_keys(cur, schema, IMPORTER_KINDS[importer], since or lo, until or hi)
    keys_preloaded = len(seen)

    # Pass 2 — write.
    written = duplicates = 0
    batch = []
    counters2 = Counters()
    for s in specs_for(importer, path, since, until, counters2, ranges):
        k = s.dedupe_key
        if k in seen:
            duplicates += 1
            continue
        seen.add(k)                 # also dedupes a file against itself
        batch.append(s)
        if len(batch) >= BATCH:
            written += insert_atoms(cur, schema, capture_id, batch, code_version)
            batch = []
    written += insert_atoms(cur, schema, capture_id, batch, code_version)

    return {"file": path.name, "importer": importer, "status": "imported",
            "capture_id": str(capture_id), "records_parsed": n,
            "atoms_written": written, "duplicates_skipped": duplicates,
            "dedupe_keys_preloaded": keys_preloaded,
            "period": payload["period"], "counters": dict(counters2)}


def code_version_for(importer):
    return {"apple_health": apple_health.CODE_VERSION,
            "bank": bank.CODE_VERSION,
            "takeout": takeout.CODE_VERSION}[importer]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drop", default=str(DROP_DIR), help="drop folder (default ~/PersonalOS_Drop)")
    ap.add_argument("--since", help="earliest subject day to import, YYYY-MM-DD")
    ap.add_argument("--until", help="latest subject day to import, YYYY-MM-DD")
    ap.add_argument("--schema", default="core", choices=("core", "core_dryrun"))
    ap.add_argument("--commit", action="store_true",
                    help="write. Without it the transaction is rolled back and nothing changes.")
    ap.add_argument("--file", help="import exactly this file instead of scanning the folder")
    a = ap.parse_args(argv)

    since = dt.date.fromisoformat(a.since) if a.since else None
    until = dt.date.fromisoformat(a.until) if a.until else None
    drop = Path(a.drop)

    if a.file:
        files = [Path(a.file)]
    else:
        if not drop.is_dir():
            print(f"drop folder does not exist: {drop}", file=sys.stderr)
            return 2
        files = sorted(p for p in drop.iterdir() if p.is_file() and not p.name.startswith("."))

    if not files:
        print(f"nothing to import in {drop}")
        return 0

    conn = db.connect()
    cur = conn.cursor()
    results, failures = [], []
    try:
        # Everything from here down is inside one guarded block. The registry load, the
        # SAVEPOINT statements and the ops.runs write all sit OUTSIDE the per-file try, and an
        # error in any of them previously escaped `main()` as a raw, unredacted traceback —
        # including the ops.runs write, which is the very statement the per-file SAVEPOINT
        # work exists to protect.
        ranges = registry_ranges(cur, a.schema)
        for n, p in enumerate(files):
            imp = classify(p)
            if imp is None:
                # An entry is appended for EVERY file, in order, so `results` stays index-
                # aligned with `files` for the move step below.
                results.append({"file": p.name, "status": "unrecognised_file_type"})
                continue
            # A SAVEPOINT per file. Without one, a single Postgres error leaves the whole
            # transaction in a failed state, so the ops.runs write below raises 25P02, the
            # exception escapes main(), and Joe gets a traceback instead of the per-file report
            # — losing every file that had already succeeded. That is today's behaviour if
            # migration 0051 has not been applied, which is exactly when it would first be hit.
            sp = f"sp_import_{n}"
            cur.execute(f"SAVEPOINT {sp}")
            try:
                r = import_file(cur, a.schema, p, imp, since, until, code_version_for(imp),
                                ranges)
                cur.execute(f"RELEASE SAVEPOINT {sp}")
                results.append(r)
            except bank.QuarantineError as e:
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                # REQ-FIN-015: quarantined, not parsed, no transaction row.
                results.append({"file": p.name, "status": "quarantined", "reason": str(e)})
                failures.append(p.name)
            except Exception as e:
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                results.append({"file": p.name, "status": "failed", "error": redact(e)})
                failures.append(p.name)

        total = sum(r.get("atoms_written", 0) for r in results)
        cur.execute(
            f"""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                values ('import_drop', now(), %s, %s, %s)""",
            ("ok" if not failures else "error", total,
             json.dumps({"files": len(files), "atoms": total, "failed": failures,
                         "committed": bool(a.commit)})))

        if a.commit:
            conn.commit()
        else:
            conn.rollback()
    except Exception as e:
        conn.rollback()
        print(f"import_drop: FAILED: {redact(e)}", file=sys.stderr)
        for r in results:
            print(json.dumps(r, default=str))
        return 2
    finally:
        conn.close()

    for r in results:
        print(json.dumps(r, default=str))
    print(f"\n{'COMMITTED' if a.commit else 'DRY RUN (rolled back)'}: "
          f"{sum(r.get('atoms_written', 0) for r in results)} atoms from {len(files)} file(s)")

    if a.commit:
        # Move the file that was actually imported. `DONE_DIR` is a module constant derived
        # from the default drop folder, and `drop / basename` resolves a bare name — together
        # they meant `--file /elsewhere/export.xml` moved a DIFFERENT file that happened to
        # share the name out of the default folder, and left the imported one in place.
        done_dir = (files[0].parent if a.file else drop) / "_done"
        moved = 0
        for r, src in zip(results, files):
            if r.get("status") in ("imported", "skipped_duplicate_file", "no_records_in_window"):
                if src.exists():
                    done_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(done_dir / src.name))
                    moved += 1
        if moved:
            print(f"{moved} processed file(s) moved to {done_dir}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
