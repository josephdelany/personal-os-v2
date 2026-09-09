"""Bank / card statement files -> AtomSpec (B13, ADR-0059).

REQ-FIN-010 (CSV, OFX, QFX, QBO, no third-party network call), REQ-FIN-013 (OFX family is
parsed by `ofxtools`, never by its Direct-Connect client), REQ-FIN-014 (column semantics come
from a per-institution mapping file in the repository, never from a runtime heuristic),
REQ-FIN-015 (a file matching no mapping is quarantined and produces no transaction row),
REQ-FIN-016 (Apple Card, Venmo, PayPal and Cash App are first-class mappings),
REQ-FIN-040/042 (two distinct timestamps, and never writing the same value to both when a
distinct one was available).

The two-timestamp rule is the reason this module is more careful than a CSV reader needs to
be. `occurred_at` is the swipe and is what behaviour is analysed on; `posted_at` is
settlement and is what reconciliation reads. A statement that carries only one date carries
only `occurred_at` — `posted_at` is left NULL rather than filled with a copy, because a
copied settlement date is an invented fact (REQ-FIN-042, RULE-01), and a NULL is a gap that
a later posted observation can fill honestly.

Dedupe across the three arrival paths (alert -> pending -> posted) is REQ-FIN-043..048 and
belongs to B17's canonical-transaction engine. What happens here is narrower and stated
plainly: the same *file* imported twice is a no-op (ADR-0057 file hash), and an identical
(amount, occurred_at, descriptor) row already present as an atom is not written again.
"""
import csv
import datetime as dt
import io
import re
from pathlib import Path

import yaml

from tools.importers.common import AtomSpec

CODE_VERSION = "import-bank-v1"

MAPPING_DIR = Path(__file__).resolve().parents[2] / "config" / "institutions"


class QuarantineError(Exception):
    """REQ-FIN-015: the file is not parsed and no transaction row is created. The message
    carries the observed header, because that is exactly what is needed to write the mapping
    that would have matched it."""


def load_mappings(mapping_dir=None):
    """Every institution mapping in the repository, as dicts."""
    d = Path(mapping_dir or MAPPING_DIR)
    out = []
    for p in sorted(d.glob("*.yaml")):
        m = yaml.safe_load(p.read_text())
        if not m or "columns" not in m:
            continue
        m["_path"] = str(p)
        out.append(m)
    return out


def find_header(rows, mappings):
    """The first row that is a header for some mapping, and that mapping.

    Venmo's export puts preamble rows above the real header, so the header is *found*, not
    assumed to be row 0. Returns (row_index, mapping) or (None, None).

    A genuine tie — two mappings matching the same number of columns on the same row — raises
    QuarantineError rather than keeping whichever sorted first. Both the README and ADR-0059
    promise that, and the first version did not implement it: it used a strict `>`, so the tie
    silently went to the alphabetically-first file. Two mappings can disagree about
    `amount_sign`, so a silent tie-break is a coin flip on the sign of every amount in the file.
    """
    best_i, best_m, best_n, tied = None, None, -1, []
    for i, row in enumerate(rows[:40]):          # a header past row 40 is not a header
        present = {c.strip() for c in row if c is not None}
        for m in mappings:
            need = set(m["columns"].values())
            if not need or not need <= present:
                continue
            n = len(need)
            if n > best_n:
                best_i, best_m, best_n, tied = i, m, n, [m]
            elif n == best_n and i == best_i and m is not best_m:
                tied.append(m)
    if len(tied) > 1:
        names = sorted(m["institution"] for m in tied)
        raise QuarantineError(
            f"ambiguous_institution_mapping: {len(tied)} mappings match this file equally "
            f"({', '.join(names)}). Refusing to choose — they can disagree about the sign "
            "convention. Narrow one mapping's required columns.")
    return best_i, best_m


def parse_amount(text, amount_sign):
    """Statement text -> a signed amount in the ledger convention (money out is negative).

    Returns None for anything ambiguous. An amount that cannot be read unambiguously is a
    documented gap (RULE-06); guessing at it produces a plausible wrong number, which is the
    one failure this whole file is arranged against.

    **Parentheses negate within the STATEMENT's own convention, before `amount_sign` is
    applied.** `(12.34)` on an Apple Card statement is a refund: the statement writes charges
    positive, so a bracketed value is money *in*, and in the ledger convention that is
    `+12.34`. A previous "fix" here returned `-12.34` and carried a docstring whose causal
    story was backwards — it recorded the original behaviour as the bug and shipped the bug as
    the fix, with a test asserting the wrong value under a comment describing the right one.
    The ordering below is the whole content of that correction: parenthesis first, convention
    second.

    **Everything that is not a number is refused, not deleted.** Stripping every non-digit
    silently turned `$100.00 CR` (a credit) into `-100.0`, `--12.34` into `-12.34`, `1e3` into
    `13.0`, and an unbalanced `(12.34` into `+12.34`.
    """
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None

    # Balanced parentheses only; an unbalanced one means the cell is not what it looks like.
    opens, closes = raw.count("("), raw.count(")")
    if opens != closes or opens > 1:
        return None
    negative_by_parens = raw.startswith("(") and raw.endswith(")")
    body = raw[1:-1].strip() if negative_by_parens else raw
    if "(" in body or ")" in body:
        return None

    # A trailing minus is a real statement convention ("1234.56-").
    trailing_minus = body.endswith("-")
    if trailing_minus:
        body = body[:-1].strip()

    # Currency symbols and internal whitespace are decoration. A currency CODE or a
    # debit/credit marker (CR, DR) changes the meaning, so it is refused rather than dropped.
    body = re.sub(r"[\s$\u20ac\u00a3\u00a5]", "", body)
    if not re.fullmatch(r"[+-]?[0-9][0-9.,]*", body):
        return None
    if trailing_minus and body.startswith(("-", "+")):
        return None

    negative = body.startswith("-") or trailing_minus
    digits = body.lstrip("+-")

    has_dot, has_comma = "." in digits, "," in digits
    if has_dot and has_comma:
        # The LAST separator is the decimal one. A comma-decimal amount ("1.234,56") is a
        # European statement, which none of the shipped mappings declare — reading it as US
        # would turn 1,234.56 into 1.23. Refuse rather than guess (RULE-06).
        if digits.rindex(",") > digits.rindex("."):
            return None
        groups = digits.split(".")[0].split(",")
        if len(groups[0]) > 3 or any(len(g) != 3 for g in groups[1:]):
            return None
        digits = digits.replace(",", "")
    elif has_comma:
        parts = digits.split(",")
        # "1,234" and "1,234,567" are US thousands. "1,56" is a comma decimal — refuse.
        if len(parts) > 1 and all(len(g) == 3 for g in parts[1:]) and len(parts[0]) <= 3:
            digits = digits.replace(",", "")
        else:
            return None

    if digits.count(".") > 1 or not digits.replace(".", "").isdigit():
        return None

    try:
        v = float(digits)
    except ValueError:
        return None

    # 1. the sign the statement itself wrote, including a bracketed accounting negative
    if negative:
        v = -v
    if negative_by_parens:
        v = -abs(v)
    # 2. then translate the statement's convention into the ledger convention
    if amount_sign == "positive_is_outflow":
        v = -v
    return v


def _has_clock_time(text, formats):
    """Did the source string carry a real clock time, or only a date?

    A value of exactly midnight is treated as date-only. Institutions pad date columns into
    datetimes, and a literal `00:00:00` anchored as a real instant lands on the PREVIOUS
    subject day (the boundary is 04:00 ET) while claiming minute precision it does not have.
    A genuine midnight transaction loses four hours of precision by this rule and is filed on
    the day the statement names, which is the safer of the two errors.

    The first version read `(":" in s) and (...) or (":" in s)`, which is `A and B or A` — just
    `A`. The midnight check never executed at all.
    """
    d = parse_date(text, formats)
    if d is None or ":" not in str(text):
        return False
    return (d.hour, d.minute, d.second) != (0, 0, 0)


def parse_date(text, formats):
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    for f in formats:
        try:
            return dt.datetime.strptime(s, f)
        except ValueError:
            continue
    # ISO-8601 with an offset or a 'T', which strptime formats above may not cover.
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _localise(d, had_time):
    """Attach a timezone, and only invent a clock time when the source carried none.

    A date-only statement value is anchored at noon ET: midnight sits one hour from the 04:00
    subject-day boundary in one direction and twenty in the other, so a midnight anchor makes
    the subject day sensitive to a DST shift, while noon is unambiguous.

    **A source that DID carry a time keeps it.** Venmo and Cash App both export a real
    timestamp, and the first version overwrote it with noon for every row. That erased the only
    thing separating two same-day, same-amount payments and made them collide in the dedupe
    key — the second was discarded as a duplicate. Returns (datetime, time_precision).
    """
    from tools.importers.common import ET
    if d.tzinfo is None:
        d = d.replace(tzinfo=ET)
    if had_time:
        return d, "minute"
    return d.replace(hour=12, minute=0, second=0, microsecond=0), "day"


REPO_ROOT = Path(__file__).resolve().parents[2]


def _looks_like_a_header(row):
    """A row of column names, as opposed to a row of data.

    Only header-shaped rows are written to the quarantine note. A data row carries amounts,
    dates and counterparty names; a header carries short labels. Getting this wrong writes
    someone's transactions to a file, so the test is deliberately strict: no cell may parse as
    a number or contain a currency symbol or an '@', every cell must be short, and at least
    two cells must be non-empty.
    """
    cells = [(c or "").strip() for c in row]
    non_empty = [c for c in cells if c]
    if len(non_empty) < 2:
        return False
    for c in non_empty:
        if len(c) > 40 or any(ch in c for ch in "$\u20ac\u00a3\u00a5@"):
            return False
        if re.fullmatch(r"[+-]?[0-9][0-9,./:\s-]*", c):
            return False
    return True


def _write_quarantine_note(path, rows):
    """Record the unmatched HEADER next to the drop folder, and return the path.

    Three constraints, each from a real failure mode:

    * **Only header-shaped rows are written.** The first version wrote `rows[:5]` verbatim —
      real transactions, merchants and amounts — to a file, and did so on a dry run too, which
      contradicts this tool's promise that without `--commit` nothing is written.
    * **Never inside the repository.** If `PERSONAL_OS_DROP` ever pointed into the working
      tree, a `.txt` of statement rows would be committable: `validate_layout.py` fails on a
      tracked `.parquet/.csv/.db/.sqlite` and would not notice this one (RULE-29).
    * **Failure to write is reported, not raised.** The quarantine itself is the important
      signal; losing the note must not lose it.
    """
    import os
    drop = Path(os.environ.get("PERSONAL_OS_DROP", Path.home() / "PersonalOS_Drop")).resolve()
    if REPO_ROOT == drop or REPO_ROOT in drop.parents:
        return ("(not written: the drop folder is inside the repository, and a file of "
                "statement rows must never be committable — RULE-29)")
    headers = [r for r in rows[:8] if _looks_like_a_header(r)]
    if not headers:
        return "(not written: no header-shaped row found in the first 8 rows)"
    out_dir = drop / "_quarantine"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        note = out_dir / f"{path.name}.header.txt"
        with open(note, "w") as f:
            f.write(f"# {path.name}: no institution mapping matched.\n")
            f.write("# Only header-shaped rows are reproduced below; data rows are omitted.\n")
            f.write("# Add a mapping under config/institutions/ naming these columns\n")
            f.write("# (see that directory's README).\n\n")
            for i, row in enumerate(headers):
                f.write(f"header candidate {i}: {[str(c).strip() for c in row]!r}\n")
        return str(note)
    except OSError as e:
        return f"(could not be written: {type(e).__name__})"


def parse(path, since=None, until=None, counters=None, mapping_dir=None):
    """A statement file -> AtomSpec. Raises QuarantineError when no mapping matches."""
    from tools.importers.apple_health import Counters
    c = counters if counters is not None else Counters()
    p = Path(path)
    if p.suffix.lower() in (".ofx", ".qfx", ".qbo"):
        yield from _parse_ofx(p, since, until, c)
        return

    text = p.read_text(encoding="utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    mappings = load_mappings(mapping_dir)
    idx, mapping = find_header(rows, mappings)
    if mapping is None:
        # REQ-FIN-015. The observed header is what is needed to write the mapping that would
        # have matched, but it must not be printed: a CSV's first row is not always a header
        # (Venmo's export opens with "Account Statement - (@joe)"), so it can be data, and this
        # command promises counts and never contents. It is written to a local file beside the
        # drop folder — Joe's own machine, no egress (RULE-29) — and only the path is reported.
        note = _write_quarantine_note(p, rows)
        raise QuarantineError(
            "no_institution_mapping: no mapping in config/institutions matches this file "
            f"({len(rows[0]) if rows else 0} columns in its first row). The observed header "
            f"was written to {note} — add a mapping naming those columns."
        )

    cols = mapping["columns"]
    formats = mapping.get("date_formats") or ["%Y-%m-%d"]
    sign = mapping.get("amount_sign", "negative_is_outflow")
    header = [h.strip() for h in rows[idx]]
    pos = {h: i for i, h in enumerate(header)}

    for row in rows[idx + 1:]:
        if not row or all((x or "").strip() == "" for x in row):
            continue
        def cell(key):
            src = cols.get(key)
            if src is None or src not in pos or pos[src] >= len(row):
                return None
            return row[pos[src]]

        amount = parse_amount(cell("amount"), sign)
        occurred = parse_date(cell("occurred_at"), formats)
        if amount is None or occurred is None:
            c.bump("bank_row_unparseable")
            continue
        posted = parse_date(cell("posted_at"), formats)
        # REQ-FIN-042: never write the same value to both. A statement carrying one date
        # carries one date; posted stays absent rather than being copied.
        if posted is not None and posted.date() == occurred.date():
            posted = None

        occurred, precision = _localise(occurred, _has_clock_time(cell("occurred_at"), formats))
        merchant = (cell("merchant") or "").strip()
        descriptor = (cell("descriptor") or "").strip()
        spec = AtomSpec(
            kind="transaction",
            metric_key="transaction_amount_usd",
            occurred_at=occurred,
            value=amount,
            unit="usd",
            state_class="total",
            estimate_method="measured",
            time_precision=precision,
            evidence_span=(
                f"bank:{mapping['institution']};merchant={merchant};descriptor={descriptor}"
                + (f";posted={posted.date().isoformat()}" if posted else "")
            ),
        )
        d = spec.subject_day
        if (since and d < since) or (until and d > until):
            c.bump("outside_window")
            continue
        yield spec


def _parse_ofx(path, since, until, c):
    """REQ-FIN-013: OFX/QFX/QBO are parsed by `ofxtools`, and never by its fetch client.

    `ofxtools` is not vendored. When it is absent this raises a QuarantineError naming the
    missing dependency instead of falling back to a hand-rolled SGML reader — a
    silently-different parser for a financial file is how amounts go quietly wrong.
    """
    try:
        from ofxtools.Parser import OFXTree
    except ImportError as e:
        raise QuarantineError(
            "ofx_parser_unavailable: REQ-FIN-013 requires ofxtools to read OFX/QFX/QBO. "
            "Install it (`python3 -m pip install ofxtools`; MIT, no account, no recurring "
            f"cost — ADR-0059) and re-run. Underlying: {e}"
        ) from e

    tree = OFXTree()
    tree.parse(str(path))
    ofx = tree.convert()
    for stmt in getattr(ofx, "statements", []):
        acct = getattr(getattr(stmt, "account", None), "acctid", "") or ""
        for txn in getattr(stmt, "transactions", []):
            amount = float(txn.trnamt)                    # OFX is already ledger convention
            # REQ-FIN-040/042: DTUSER is the transaction (swipe) date, DTPOSTED is settlement.
            # The first version wrote DTPOSTED into occurred_at, which is the settlement date
            # in the field the behavioural layer reads — precisely what REQ-FIN-042 forbids.
            posted = getattr(txn, "dtposted", None)
            user = getattr(txn, "dtuser", None)
            occurred = user or posted
            if occurred is None:
                c.bump("ofx_txn_without_date")
                continue
            if posted is not None and occurred is not None and posted.date() == occurred.date():
                posted = None            # one fact, recorded once
            spec = AtomSpec(
                kind="transaction",
                metric_key="transaction_amount_usd",
                occurred_at=occurred,
                value=amount,
                unit="usd",
                state_class="total",
                estimate_method="measured",
                time_precision="day" if user is None else "minute",
                evidence_span=(
                    f"bank:ofx;account={str(acct)[-4:]};"
                    f"merchant={getattr(txn, 'name', '') or ''};"
                    f"descriptor={getattr(txn, 'memo', '') or ''}"
                    + (f";posted={posted.date().isoformat()}" if posted else "")
                ),
            )
            d = spec.subject_day
            if (since and d < since) or (until and d > until):
                c.bump("outside_window")
                continue
            yield spec
