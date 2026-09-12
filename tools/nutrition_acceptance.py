#!/usr/bin/env python3
"""The nutrition cascade's acceptance cases, as a runnable command (B12 §D.2/D.3).

    python3 tools/nutrition_acceptance.py
    python3 tools/nutrition_acceptance.py --verbose

Seven behaviours decide whether the nutrition path is finished. They are asserted in
`tests/test_nutrition_usda.py`, and a passing pytest run is evidence — but it is evidence that
has to be read out of a test runner's output by someone who knows which test names matter. This
command executes the same seven against a throwaway PostgreSQL server and prints what happened,
so the claim "nutrition resolution works" can be checked by running one thing and reading a
table. It follows `tools/reconstruction_acceptance.py`, which exists for the same reason.

  1. A cache hit issues no external call.
  2. A cache miss reaches the configured cascade.
  3. A reference result becomes a traced interval, never a point.
  4. A correction from Joe outranks every source.
  5. Failure and ambiguity produce an accurate unresolved status, distinguishing five outcomes.
  6. Persistence and retrieval preserve unit, method and provenance.
  7. Repeated processing duplicates nothing.

WHAT THIS DOES NOT SHOW. Every source response here is a payload this file constructs and hands
to an injected transport. **No request reaches api.data.gov or Open Food Facts, and nothing
here is evidence that the live USDA client works.** That check needs an api.data.gov key and is
listed as pending. A run of this command proves the code path, the arithmetic and the storage —
not the network.

The server is built by `initdb` in a temporary directory, listens on a Unix socket with TCP
disabled, is loaded from migration DDL, and every case runs inside a transaction that is rolled
back (RULE-01's ADR-0022 exception). No production credential is read and no production table is
touched: `SUPABASE_DB_URL` is explicitly removed from the environment this process builds.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CORE, OPS, CONFIG = "core_accept", "ops_accept", "config_accept"
SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql", "0011_ops.sql")
DAY, WHEN = "2026-09-11", "2026-09-11 12:30:00+00"
KEY_ENV = {"USDA_FDC_API_KEY": "SYNTHETICKEYNOTREAL"}       # synthetic; not a key


# ---------------------------------------------------------------- the disposable server

def pg_bin():
    located = shutil.which("initdb")
    candidates = ([str(Path(located).parent)] if located else []) + [
        "/opt/homebrew/opt/postgresql@17/bin", "/usr/local/opt/postgresql@17/bin"]
    for base in candidates:
        binary = Path(base) / "initdb"
        if binary.exists():
            version = subprocess.run([str(binary), "--version"], check=True,
                                     capture_output=True, text=True).stdout
            if re.search(r"\(PostgreSQL\) 17[. ]", version):
                return Path(base)
    raise RuntimeError("PostgreSQL 17 binaries are required; install them before running this.")


class Disposable:
    """A temporary PostgreSQL 17 server, stopped on exit.

    The data directory is RETAINED rather than force-deleted. `tools/test_local_sql.py` removes
    it, and does so only after proving the server stopped; this command leaves it either way
    and prints the path, because a recursive delete of a directory whose server state is
    uncertain is the one operation that can destroy data nobody meant to lose.
    """

    def __enter__(self):
        binaries = pg_bin()
        self.root = Path(tempfile.mkdtemp(prefix="personal-os-nutrition-accept-", dir="/tmp"))
        data, sockets = self.root / "data", self.root / "socket"
        sockets.mkdir(mode=0o700)
        subprocess.run([str(binaries / "initdb"), "-D", str(data), "--auth-local=trust",
                        "--auth-host=reject", "--encoding=UTF8", "--no-locale"],
                       check=True, stdout=subprocess.DEVNULL)
        self.control = [str(binaries / "pg_ctl"), "-D", str(data)]
        subprocess.run([*self.control, "-l", str(self.root / "server.log"), "-o",
                        # `-c timezone=UTC` matches tools/test_local_sql.py and is NOT
                        # cosmetic. A server left on the machine's local zone shifts every
                        # server-side `timestamptz::date` by the UTC offset, which moves day
                        # counts by one. Three tests in test_resolve_watches.py fail exactly
                        # that way under a server without it — found by running this project's
                        # own harness against a server that omitted the flag.
                        f"-k {sockets} -p 55434 -c listen_addresses='' -c timezone=UTC",
                        "start"],
                       check=True, stdout=subprocess.DEVNULL)
        self.socket = sockets / ".s.PGSQL.55434"
        return self

    def __exit__(self, *exc):
        subprocess.run([*self.control, "-m", "fast", "stop"], stdout=subprocess.DEVNULL)
        print(f"\nserver stopped; temporary directory retained at {self.root}")
        return False

    def connect(self):
        import getpass

        import pg8000.dbapi
        return pg8000.dbapi.connect(user=getpass.getuser(), database="postgres",
                                    unix_sock=str(self.socket), timeout=10)


def world(cur):
    """Migration 0050 verbatim over the spine, in disposable schemas."""
    from tests._import_fixture import _statements
    from tools.run_migration import split_statements

    for schema in (CORE, OPS, CONFIG):
        cur.execute(f"CREATE SCHEMA {schema}")
    for name in SPINE:
        for stmt in _statements(name, CORE, OPS):
            cur.execute(stmt)
    cur.execute(f"CREATE TABLE {CONFIG}.strings (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                f"note TEXT)")
    # 0071 REVOKEs on `anon`/`authenticated`, which Supabase supplies and a bare PostgreSQL 17
    # cluster does not. Created idempotently exactly as `tests/_import_fixture.build_spine`
    # does; without them the chain dies on `role "anon" does not exist` and every test in the
    # file fails for a reason that has nothing to do with what it is testing.
    for role in ("anon", "authenticated", "service_role"):
        cur.execute(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
            END IF;
        END $$""")
    # The nutrition migrations IN ORDER. 0071 adds `food_aliases`, which REQ-NUT-001 step (1)
    # reads and REQ-NUT-004 writes.
    for migration in ("0050_nutrition.sql", "0071_food_and_portion_aliases.sql"):
        body = (ROOT / "migrations" / migration).read_text() \
            .replace("__CORE__", CORE).replace("__OPS__", OPS).replace("config.", f"{CONFIG}.")
        for stmt in split_statements(body):
            cur.execute(stmt)
    return cur


# ---------------------------------------------------------------- synthetic payloads

def branded(fdc_id=999001, description="Synthetic Crunch Bar", brand_owner="Examplo Foods"):
    return {"fdcId": fdc_id, "description": description, "dataType": "Branded",
            "brandOwner": brand_owner, "servingSize": 40, "servingSizeUnit": "g",
            "foodNutrients": [{"nutrientId": 1008, "unitName": "KCAL", "value": 450.0},
                              {"nutrientId": 1003, "unitName": "G", "value": 8.0},
                              {"nutrientId": 1093, "unitName": "MG", "value": 300.0}]}


def foundation(fdc_id=999500, description="Synthetic Rolled Oats"):
    return {"fdcId": fdc_id, "description": description, "dataType": "Foundation",
            "foodNutrients": [{"nutrientId": 1008, "unitName": "KCAL", "value": 380.0},
                              {"nutrientId": 1003, "unitName": "G", "value": 13.0}]}


def transport_for(foods, log=None):
    def transport(url, headers, timeout):
        if log is not None:
            log.append(url)
        return json.dumps({"totalHits": len(foods), "foods": list(foods)}).encode()
    return transport


def forbidden(url, headers, timeout):
    raise AssertionError(f"a request was issued when none was permitted: {url}")


def failing(exc):
    def transport(url, headers, timeout):
        raise exc
    return transport


class Http429(Exception):
    code = 429


def cache_food(cur, name, source, nutrients, serving_g=None, brand=None, source_id=None):
    cur.execute(f"""insert into {CORE}.foods_cache
        (canonical_name, source, source_id, brand, nutrients_per_100g, serving_g)
        values (%s,%s,%s,%s,%s::jsonb,%s)""",
        (name, source, source_id or name, brand, json.dumps(nutrients), serving_g))


def capture(cur):
    cap_id = uuid.uuid4()
    cur.execute(
        f"""insert into {CORE}.raw_captures
              (capture_id, captured_at, source, trust_level, payload, processing_status)
            values (%s, %s, 'shortcut_text', 'trusted', %s::jsonb, 'enriched')""",
        (cap_id, WHEN, json.dumps({"kind": "food"})))
    return cap_id


def sources_for(cur, transport=None, env=None, quota=None):
    from tools.engines import nutrition
    return nutrition.build_sources(cur, schema=CORE, ops=OPS, config=CONFIG, off=False,
                                   usda_transport=transport, usda_quota=quota,
                                   usda_env=KEY_ENV if env is None else env)


def egress_count(cur):
    cur.execute(f"select count(*) from {OPS}.egress_log")
    return cur.fetchone()[0]


# ---------------------------------------------------------------- the seven cases

def case_cache_hit(cur):
    """1. A cache hit issues no external call."""
    from tools.engines import nutrition
    cache_food(cur, "synthetic rolled oats", "usda_foundation", {"kcal": 380.0}, serving_g=50.0)
    sources = sources_for(cur, forbidden)
    result = nutrition.resolve_item(cur, "synthetic rolled oats", servings=1, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)
    assert result["from_cache"] is True
    assert result["source"] == "usda_foundation"
    assert sum(leg.calls for name, leg in sources.items() if name != "joe") == 0
    assert egress_count(cur) == 0
    return f"{result['canonical_name']!r} served from cache, 0 outbound calls logged"


def case_cache_miss(cur):
    """2. A cache miss reaches the configured cascade."""
    from tools.engines import nutrition
    log = []
    sources = sources_for(cur, transport_for([foundation()], log))
    result = nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)
    assert result["source"] == "usda_foundation" and result["from_cache"] is False
    assert result["food_id"] is not None, "REQ-NUT-003: the answer became a cache row"
    assert egress_count(cur) == 2, "branded asked first, then foundation"
    return (f"resolved via usda_foundation, fdcId stored, {egress_count(cur)} calls logged "
            f"to api.nal.usda.gov")


def case_interval(cur):
    """3. A reference result becomes a traced interval, never a point."""
    from tools.engines import nutrition
    sources = sources_for(cur, transport_for([foundation()]))
    result = nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=200, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)
    low, point, high = result["nutrients"]["kcal"]
    assert point == 760.0, f"380 kcal/100 g at 200 g should be 760, got {point}"
    assert low < point < high, "RULE-08: a point estimate is a lie about precision"
    widths = nutrition.interval_widths(cur, CONFIG)
    assert (low, point, high) == nutrition.apply_width(760.0, result["method"], widths)
    return (f"kcal {low} .. {point} .. {high}  method={result['method']} "
            f"estimate_method={result['estimate_method']}")


def case_correction(cur):
    """4. A correction from Joe outranks every source."""
    from tools.engines import nutrition
    cache_food(cur, "Synthetic Crunch Bar", "joe", {"kcal": 111.0}, serving_g=40.0)
    cache_food(cur, "Synthetic Crunch Bar", "usda_branded", {"kcal": 450.0}, serving_g=40.0,
               brand="Examplo Foods", source_id="999001")
    sources = sources_for(cur, forbidden)
    result = nutrition.resolve_item(cur, "Synthetic Crunch Bar", grams=100, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)
    assert result["source"] == "joe"
    assert result["nutrients"]["kcal"][1] == 111.0, "Joe's number, not the label's 450"
    return "joe=111 kcal won over usda_branded=450 kcal; no source was asked"


def case_failures(cur):
    """5. Failure and ambiguity produce an accurate unresolved status — five distinct ones."""
    from tools.engines import nutrition
    from tools.engines import nutrition_usda as usda
    seen = {}

    def attempt(label, **kw):
        try:
            nutrition.resolve_item(cur, "Synthetic Unknown Thing", grams=100,
                                   sources=sources_for(cur, **kw), schema=CORE,
                                   config=CONFIG, ops=OPS)
        except nutrition.Unresolved as e:
            reasons = [t.get("reason") for t in e.tried if t.get("reason")]
            outcomes = [t.get("outcome") for t in e.tried if t.get("outcome")]
            seen[label] = (e.reason, e.review_reason, reasons + outcomes)
        else:
            raise AssertionError(f"{label}: expected Unresolved")

    attempt("no key", transport=forbidden, env={})
    attempt("no match", transport=transport_for([]))
    attempt("ambiguous", transport=transport_for(
        [foundation(fdc_id=1, description="Synthetic Unknown Thing"),
         foundation(fdc_id=2, description="Synthetic Unknown Thing")]))
    attempt("rate limited", transport=failing(Http429()), quota=usda.Quota())
    attempt("malformed", transport=transport_for([{
        "fdcId": 7, "description": "Synthetic Unknown Thing", "dataType": "Foundation",
        "foodNutrients": [{"nutrientId": 1008, "unitName": "furlongs", "value": 5.0}]}]))

    # The point of this case is that the five do NOT collapse into one status.
    assert seen["no key"][0] == "no_source_available" and seen["no key"][1] is None
    assert seen["no match"][:2] == ("no_source_match", "no_source_match")
    assert "ambiguous_exact_match" in seen["ambiguous"][2]
    assert "rate_limited_now" in seen["rate limited"][2]
    assert "no_readable_nutrient" in seen["malformed"][2]
    assert seen["no key"][0] != seen["no match"][0], \
        "'could not look' and 'could not find' must not be the same status"
    return " | ".join(f"{k}: {v[0]}" for k, v in seen.items())


def case_persistence(cur):
    """6. Persistence and retrieval preserve unit, method and provenance."""
    from tools.engines import nutrition
    cap = capture(cur)
    sources = sources_for(cur, transport_for([branded()]))
    result = nutrition.resolve_item(cur, "Synthetic Crunch Bar", grams=40, brand="Examplo Foods",
                                    sources=sources, schema=CORE, config=CONFIG, ops=OPS)
    nutrition.persist_resolution(cur, result, raw_capture_id=cap, occurred_at=WHEN,
                                 subject_day=DAY, evidence_span="a synthetic crunch bar",
                                 schema=CORE)
    cur.execute(f"""select metric_key, value_low, value_point, value_high, estimate_method,
                           unit, provenance
                      from {CORE}.atoms_current
                     where kind = 'consume' and metric_key is not null order by metric_key""")
    rows = {r[0]: r for r in cur.fetchall()}
    assert rows["kcal"][4] == "labelled", "REQ-NUT-014's claim survived the write"
    assert rows["kcal"][5] == "kcal" and rows["sodium_mg"][5] == "mg", "units preserved"
    assert rows["kcal"][6] == "inferred", "RULE-05/INV-5: a nutrient is never observed"
    assert float(rows["kcal"][1]) < float(rows["kcal"][2]) < float(rows["kcal"][3])
    return (f"{len(rows)} atoms readable through atoms_current; "
            f"kcal method={rows['kcal'][4]} unit={rows['kcal'][5]} "
            f"provenance={rows['kcal'][6]}")


def case_idempotent(cur):
    """7. Repeated processing duplicates nothing."""
    from tools.engines import nutrition
    cap = capture(cur)
    sources = sources_for(cur, transport_for([foundation()]))
    result = nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)
    first = nutrition.persist_resolution(cur, result, raw_capture_id=cap, occurred_at=WHEN,
                                         subject_day=DAY, evidence_span="oats", schema=CORE)
    second = nutrition.persist_resolution(cur, result, raw_capture_id=cap, occurred_at=WHEN,
                                          subject_day=DAY, evidence_span="oats", schema=CORE)
    assert first and second == [], "the second persistence pass wrote something"

    calls_before = egress_count(cur)
    again = nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100,
                                   sources=sources_for(cur, forbidden), schema=CORE,
                                   config=CONFIG, ops=OPS)
    assert again["from_cache"] is True and egress_count(cur) == calls_before
    cur.execute(f"select count(*) from {CORE}.foods_cache "
                f"where canonical_name = 'Synthetic Rolled Oats'")
    assert cur.fetchone()[0] == 1, "a second cache row appeared for the same food"
    cur.execute(f"select count(*) from {CORE}.atoms_current where metric_key = 'kcal'")
    assert cur.fetchone()[0] == 1, "the day's calories were counted twice"
    return "second resolve served from cache; 1 cache row, 1 kcal atom, 0 extra calls"


CASES = (("cache hit avoids the network", case_cache_hit),
         ("cache miss reaches the cascade", case_cache_miss),
         ("result becomes a traced interval", case_interval),
         ("a correction outranks sources", case_correction),
         ("five failures stay distinct", case_failures),
         ("persistence preserves meaning", case_persistence),
         ("repeats duplicate nothing", case_idempotent))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verbose", action="store_true", help="print the full traceback on failure")
    args = ap.parse_args()

    # RULE-01: this process must not be able to reach production even by accident.
    os.environ.pop("SUPABASE_DB_URL", None)

    print("nutrition acceptance — B12 §D.2/D.3, against a disposable PostgreSQL 17 server")
    print("NO request reaches api.data.gov or Open Food Facts; every payload below is "
          "constructed by this file.\n")

    passed = failed = 0
    with Disposable() as server:
        for title, case in CASES:
            conn = server.connect()
            cur = conn.cursor()
            try:
                world(cur)
                detail = case(cur)
                print(f"  PASS  {title:<34}  {detail}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {title:<34}  {type(e).__name__}: {e}")
                failed += 1
                if args.verbose:
                    import traceback
                    traceback.print_exc()
            finally:
                conn.rollback()          # nothing is ever committed
                conn.close()

    print(f"\n{passed} of {len(CASES)} acceptance cases passed"
          + (f", {failed} FAILED" if failed else ""))
    print("PENDING (not shown by this command): a live api.data.gov lookup. It needs "
          "USDA_FDC_API_KEY and has not been run.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
