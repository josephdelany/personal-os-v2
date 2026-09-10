#!/usr/bin/env python3
"""Produce the merchant review sheet, and read Joe's answers back (REQ-FIN-073/074, RULE-10).

WHY THIS EXISTS. 197 descriptors resolve to nothing above the fuzzy floor, so REQ-FIN-073
holds each as provisional and none becomes a fact. That is correct and it is also a dead end
until Joe can answer them. "197 descriptors await Joe" is not an action; a sheet with a
suggested answer on every line is.

A SUGGESTION IS ONLY OFFERED WHEN IT IS PLAUSIBLE. The cascade computes the three nearest
known merchants for every unresolved descriptor, but difflib returns the least-bad match even
when nothing is close: the first draft of this sheet offered "Msg Concessions New" and
"Interest Payment" for "$1.50 FRESH PIZZA #2 NEW YORK NY", and reported all 197 lines as "a
tick, not typing". Nonsense presented as a suggestion invites a wrong tick, and a wrong tick
becomes a HUMAN pattern that outranks every rule permanently (RULE-10) — the most expensive
kind of error this system can be handed. A candidate must reach PLAUSIBLE (0.60) to appear;
below that the columns are blank and the line asks for a name.

PRIVACY. A merchant descriptor is an observation about Joe: where he was and what he bought.
This writes OUTSIDE the repository and refuses to write inside it, because the repository is
public and `git add` is one keystroke away from a mistake that is permanent (RULE-29,
CLAUDE.md: public Git contains code, not personal data).

    PYTHONPATH=. python3 tools/review_merchants.py --out ~/merchant_review.tsv
    # ...Joe edits the `answer` column...
    PYTHONPATH=. python3 tools/review_merchants.py --apply ~/merchant_review.tsv          # dry
    PYTHONPATH=. python3 tools/review_merchants.py --apply ~/merchant_review.tsv --commit
"""
import argparse
import pathlib
import sys

from lib import db
from tools.engines.merchants import FUZZY_FLOOR, confirm, normalize
from tools.engines.resolve_merchants import build, read_descriptors

REPO = pathlib.Path(__file__).resolve().parents[1]
# Below the cascade's 0.80 assignment floor, but high enough that a human can recognise the
# merchant from the name. Between the two, a person decides; below it, nobody guesses.
PLAUSIBLE = 0.60
assert PLAUSIBLE < FUZZY_FLOOR, "a suggestion the cascade would have taken is not a suggestion"
HEADER = ("answer", "descriptor", "normalised", "charges", "suggestion_1", "suggestion_2",
          "suggestion_3")
INSTRUCTIONS = """\
# Merchant review. One line per descriptor this system could not identify.
#
# In the `answer` column put ONE of:
#     1 / 2 / 3   -- it is that numbered suggestion
#     <a name>    -- it is this merchant (type the name)
#     skip        -- not a merchant, or you do not want it identified
#     (blank)     -- decide later; the line is ignored
#
# Nothing here is guessed on your behalf. A blank line stays unresolved, and an unresolved
# charge is excluded from every merchant total rather than being attached to a likely shop.
"""


def outside_the_repo(path: pathlib.Path) -> pathlib.Path:
    resolved = path.expanduser().resolve()
    if REPO in resolved.parents or resolved == REPO:
        raise SystemExit(
            f"refusing to write personal data inside the repository ({resolved}).\n"
            "A merchant descriptor is an observation about Joe and this repo is public.\n"
            "Choose a path outside it, e.g. ~/merchant_review.tsv")
    return resolved


def sheet(cur):
    descriptors = read_descriptors(cur)
    location, _, resolutions, _ = build(descriptors)
    rows = []
    for raw, (norm, res, count) in resolutions.items():
        if not res.needs_review:
            continue
        names = [name for name, score in res.considered if score >= PLAUSIBLE][:3]
        names += [""] * (3 - len(names))
        rows.append(["", raw, norm.normalized, str(count), *names])
    rows.sort(key=lambda r: (-int(r[3]), r[1]))
    return rows, location


def read_answers(path):
    out = []
    for line in pathlib.Path(path).expanduser().read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cells = line.split("\t")
        if cells[:len(HEADER)] == list(HEADER):
            continue
        cells += [""] * (len(HEADER) - len(cells))
        answer = cells[0].strip()
        if not answer:
            continue
        if answer.lower() == "skip":
            out.append((cells[1], cells[2], None))
            continue
        if answer in ("1", "2", "3"):
            suggestion = cells[3 + int(answer)].strip()
            if not suggestion:
                raise SystemExit(f"line picks suggestion {answer} but it is empty: {cells[1]!r}")
            out.append((cells[1], cells[2], suggestion))
        else:
            out.append((cells[1], cells[2], answer))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--apply")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--core", default="core")
    a = ap.parse_args()
    if not (a.out or a.apply):
        raise SystemExit("give --out to produce the sheet or --apply to read it back")

    conn = db.connect()
    cur = conn.cursor()
    try:
        if a.out:
            path = outside_the_repo(pathlib.Path(a.out))
            rows, _ = sheet(cur)
            path.write_text(INSTRUCTIONS + "\t".join(HEADER) + "\n"
                            + "\n".join("\t".join(r) for r in rows) + "\n")
            with_suggestion = sum(1 for r in rows if r[4])
            print(f"wrote {len(rows)} descriptors to {path}")
            print(f"  {with_suggestion} carry a plausible suggestion (>= {PLAUSIBLE}) — tick a number")
            print(f"  {len(rows) - with_suggestion} have no plausible match and need a name; "
                  f"offering the nearest string anyway would invite a wrong tick, and a wrong "
                  f"tick becomes a human pattern that outranks every rule (RULE-10)")
            return 0

        answers = read_answers(a.apply)
        skipped = [d for d, _, c in answers if c is None]
        named = [(d, n, c) for d, n, c in answers if c]
        print(f"{len(answers)} answered: {len(named)} identified, {len(skipped)} skipped")
        if not a.commit:
            for d, n, c in named[:8]:
                print(f"  {d[:44]!r:<46} -> {c!r}")
            print("\nDRY RUN — nothing written.")
            return 0
        for descriptor, normalised, canonical in named:
            # RULE-10 / REQ-FIN-074. Joe's answer is a HUMAN pattern: it outranks every rule
            # permanently and the trigger in 0057 stops any later automated pass replacing it.
            p = confirm(normalised or normalize(descriptor).normalized, canonical)
            cur.execute("""INSERT INTO config.merchant_patterns
                           (pattern, canonical, is_regex, specificity, provenance)
                           VALUES (%s,%s,false,0,'human')
                           ON CONFLICT (pattern, is_regex)
                           DO UPDATE SET canonical = EXCLUDED.canonical,
                                         provenance = 'human'""", (p.pattern, p.canonical))
            cur.execute(f"""UPDATE {a.core}.merchant_review_queue SET status = 'confirmed'
                             WHERE alias = %s""", (p.pattern,))
            # And into the ALIAS LEDGER, which is where RULE-10 actually lives. Writing only
            # the pattern left `entity_aliases` with no human row anywhere in the system: the
            # resolver's cascade step 1 -- "the answer, and it outranks every rule permanently"
            # -- had no production caller, and the trigger enforcing RULE-10 guarded a table
            # nothing wrote to and nothing read. The guarantee was real in the schema and
            # unreachable in the code.
            #
            # RULE-02: this SUPERSEDES the current head rather than updating it. Re-confirming
            # the same canonical appends nothing.
            cur.execute(f"""SELECT alias_id, canonical, resolved_by
                              FROM {a.core}.entity_aliases al
                             WHERE al.alias = %s
                               AND NOT EXISTS (SELECT 1 FROM {a.core}.entity_aliases b
                                                WHERE b.supersedes = al.alias_id)""",
                        (p.pattern,))
            head = cur.fetchone()
            if not (head and head[1] == p.canonical and head[2] == 'human'):
                cur.execute(f"""INSERT INTO {a.core}.entity_aliases
                    (alias, raw_descriptor, canonical, resolved_by, confidence, supersedes)
                    VALUES (%s,%s,%s,'human',1.0,%s)""",
                            (p.pattern, descriptor, p.canonical, head[0] if head else None))
        for descriptor, normalised, _ in ((d, n, c) for d, n, c in answers if c is None):
            cur.execute(f"""UPDATE {a.core}.merchant_review_queue SET status = 'dismissed'
                             WHERE alias = %s""", (normalised or descriptor,))
        conn.commit()
        print(f"\nCOMMITTED {len(named)} human patterns, {len(skipped)} dismissed")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
