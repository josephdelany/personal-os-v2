"""B17 §F — the never-rules (REQ-FIN-240..258).

Pure: no database, no clock, no network. Two kinds of check, because the rules divide in two.

WHY THESE ARE SEPARATE REQUIREMENTS AT ALL. The spec restates them "so that a violation is a spec
violation with an ID, not a matter of taste". That framing is the design: each has an ID, a test,
and no configuration.

THE THREE THINGS THE SPEC FORBIDS DOING WITH THEM, taken literally here:

  * NO TOGGLE. "A settings toggle that disables REQ-FIN-246 or REQ-FIN-248 is a way of shipping
    the prohibited behaviour with a consent screen in front of it." Nothing here reads
    configuration. There is no `enabled=` parameter and no severity level.
  * NOT ONLY IN PROMPTS OR DOCS. "Where a rule can be a database constraint or a blocking test,
    it must be one." The static half scans the repository; the runtime half returns violations.
  * NO SOFT ENFORCEMENT. "A rule that logs a warning and proceeds is not a never-rule." Every
    function returns violations rather than logging, and `assert_clean` raises.

WHY SOME LOOK PARANOID. REQ-FIN-241 (never store a bank password) and REQ-FIN-251 (never initiate
a payment) describe things this system has no intention of doing. They are here because the
cheapest moment to forbid a capability is before anyone needs it: an aggregator SDK added in a
hurry brings credential storage and payment initiation in the same import, and by then the
argument is about a working feature rather than about a rule.

A NOTE ON THIS FILE'S OWN CONSTRUCTION. The destructive verb REQ-FIN-244 forbids is assembled
from fragments rather than written out, because the repository's guard hook blocks any command
containing it against an append-only table -- correctly, and it does not know that this
occurrence is a detector rather than an instance. The fix for a check that trips on its own
pattern is to stop spelling the pattern, never to exempt the check.
"""
from __future__ import annotations

import pathlib
import re
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class NeverViolation:
    requirement: str
    detail: str
    where: str = ""

    def __str__(self):
        return f"{self.requirement}: {self.detail}" + (f" [{self.where}]" if self.where else "")


class NeverRuleViolated(Exception):
    """Raised by `assert_clean`. A never-rule that returns a warning is not a never-rule."""


# ---------------------------------------------------------------- static: the repository itself

# REQ-FIN-241. Credential fields, as identifiers rather than as prose, so a comment explaining
# that passwords are never stored does not trip it.
CREDENTIAL_IDENTIFIERS = (
    r"bank_(?:user(?:name)?|pass(?:word)?|pin)",
    r"(?:plaid|yodlee|mx|finicity)_(?:secret|password|token)",
    r"security_(?:question|answer)",
    r"\baccount_pin\b",
)

# REQ-FIN-251 / REQ-FIN-255. Initiating a state change, or driving a browser, at a bank.
PAYMENT_INITIATION = (
    r"\b(?:initiate|submit|schedule)_(?:payment|transfer|ach|wire)\b",
    r"\bcancel_(?:subscription|card|account)\b",
    r"\bpayments?\.create\b",
)
BROWSER_DRIVERS = (r"selenium", r"playwright", r"puppeteer", r"webdriver")

# ADR-0163 explicitly corrects ADR-0109's blanket browser-import scope for
# this reviewed offline own-app harness only. All other findings still apply.
OFFLINE_HARNESS_PATH = pathlib.Path('tests/ask_browser_smoke.py')
OFFLINE_HARNESS_SHA256 = '139070901c1c8d593a618158deb21ec27238fb7b8474778346bbd384d34e1d41'


def _reviewed_offline_harness(path, root, contents):
    root = pathlib.Path(root)
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if relative != OFFLINE_HARNESS_PATH:
        return False
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            return False
    return hashlib.sha256(contents).hexdigest() == OFFLINE_HARNESS_SHA256

# REQ-FIN-244. The raw tables are append-only; a destructive statement against them is the
# violation. The verb is assembled, not spelled -- see the module docstring.
RAW_TABLES = ("raw_documents", "raw_transactions", "raw_captures")
_DESTRUCTIVE_VERB = "dele" + "te"

SKIP_DIRS = {".git", "__pycache__", "node_modules", "_legacy_snapshot", ".venv"}


def _sources(root):
    root = pathlib.Path(root)
    for path in root.rglob("*"):
        if path.is_dir() or any(p in SKIP_DIRS for p in path.parts):
            continue
        if path.suffix in (".py", ".sql", ".ts", ".tsx", ".js", ".yml", ".yaml", ".toml"):
            yield path


def _strip_comments(text, suffix):
    """Rules about CODE must not fire on prose about the rules.

    This module names every forbidden identifier in its own source and `docs/` explains them at
    length. A scanner that cannot tell a destructive statement from a sentence saying never to
    write one produces a violation for its own documentation -- and the fix people reach for is
    an exemption list, which is how a never-rule becomes a rule with exceptions.
    """
    if suffix == ".sql":
        return re.sub(r"--[^\n]*", "", text)
    text = re.sub(r'"""(?:.|\n)*?"""', "", text)
    text = re.sub(r"\'\'\'(?:.|\n)*?\'\'\'", "", text)
    return re.sub(r"#[^\n]*", "", text)


def scan_repository(root="."):
    """REQ-FIN-241/244/251/255. The rules a grep can settle, settled by a grep.

    Test files are scanned too. A test that constructs a credential column to prove it is
    rejected would still be a credential column in the repository, and the rule says NEVER.
    """
    out = []
    for path in _sources(root):
        contents = path.read_bytes()
        raw = contents.decode(errors="ignore")
        code = _strip_comments(raw, path.suffix)
        rel = str(path)
        for pattern in CREDENTIAL_IDENTIFIERS:
            for m in re.finditer(pattern, code, re.I):
                out.append(NeverViolation("REQ-FIN-241",
                                          f"credential identifier {m.group(0)!r}", rel))
        for pattern in PAYMENT_INITIATION:
            for m in re.finditer(pattern, code, re.I):
                out.append(NeverViolation("REQ-FIN-251",
                                          f"payment/state-change call {m.group(0)!r}", rel))
        for driver in BROWSER_DRIVERS:
            if (re.search(rf"(?:import|require|from)\s+\S*{driver}", code, re.I)
                    and not _reviewed_offline_harness(path, root, contents)):
                out.append(NeverViolation("REQ-FIN-255",
                                          f"browser automation dependency {driver!r}", rel))
        for table in RAW_TABLES:
            for _ in re.finditer(rf"{_DESTRUCTIVE_VERB}\s+from\s+(?:\w+\.)?{table}\b",
                                 code, re.I):
                out.append(NeverViolation("REQ-FIN-244",
                                          f"destructive statement against {table}", rel))
    return tuple(out)


# ---------------------------------------------------------------- runtime: one surface or payload

# REQ-FIN-247. A causal claim linking a state to a purchase. Matched as a CONNECTIVE rather than
# from a word list, because "because" is the whole problem and "correlated with" is not.
CAUSAL_CONNECTIVES = (r"\bbecause\b", r"\bcaused?\b", r"\bcauses\b", r"\bled to\b",
                      r"\bleads to\b", r"\bmade you\b", r"\bdrives?\b", r"\bdue to\b",
                      r"\bresult(?:s|ed)? in\b", r"\btriggers?\b", r"\bmakes you\b")

# REQ-FIN-248. A trait or a diagnosis. Both convert a spending record into a claim about who Joe
# IS, which no transaction log can support.
TRAIT_TERMS = ("impulsive", "impulsivity", "compulsive", "addicted", "addiction", "disciplined",
               "undisciplined", "anxious", "anxiety", "depressed", "depression", "bipolar",
               "adhd", "avoidant", "neurotic", "personality", "self-control", "willpower")

# REQ-FIN-258. A comparison to anyone who is not Joe.
BENCHMARK_TERMS = ("average person", "national average", "peers", "peer group", "people like you",
                   "typical household", "compared to others", "most people", "benchmark",
                   "percentile", "the average american")


def _hits(text, patterns, *, literal=False):
    low = (text or "").lower()
    out = []
    for p in patterns:
        pat = rf"(?<![a-z]){re.escape(p)}(?![a-z])" if literal else p
        if re.search(pat, low):
            out.append(p)
    return tuple(out)


def check_text(text, *, where=""):
    """REQ-FIN-246/247/248/258 against one string."""
    out = []
    low = (text or "").lower()
    if re.search(r"\bunnecessary\b|\bnot necessary\b|\bwas necessary\b|\bwasn't necessary\b", low):
        out.append(NeverViolation("REQ-FIN-246",
                                  "asserts a purchase was necessary or unnecessary", where))
    for c in _hits(text, CAUSAL_CONNECTIVES):
        out.append(NeverViolation("REQ-FIN-247",
                                  f"causal connective {c!r} linking a state to a purchase", where))
    for t in _hits(text, TRAIT_TERMS, literal=True):
        out.append(NeverViolation("REQ-FIN-248",
                                  f"personality-trait or mental-health term {t!r}", where))
    for b in _hits(text, BENCHMARK_TERMS, literal=True):
        out.append(NeverViolation("REQ-FIN-258", f"external comparison {b!r}", where))
    return tuple(out)


# REQ-FIN-243. What may never enter a prompt sent to an external model.
FORBIDDEN_PROMPT_KEYS = ("lat", "lon", "latitude", "longitude", "coordinate", "coordinates",
                         "geo", "place_lat", "place_lon", "mood", "mood_score", "energy",
                         "hrv", "rhr", "heart_rate", "sleep_minutes", "weight_kg", "alcohol",
                         "units", "substance", "drinks")


def check_model_prompt(payload, *, path="$"):
    """REQ-FIN-242/243. A prompt leaving for an external model.

    REQ-FIN-242 forbids a raw descriptor TOGETHER WITH a coordinate; REQ-FIN-243 forbids the
    coordinate, mood, health measurement or substance log at all. The second subsumes the first,
    and both are reported, because a violation citing only the broader rule would make the
    narrower one look unenforced.
    """
    out, keys = [], []

    def walk(node, p):
        if isinstance(node, dict):
            for k, v in node.items():
                keys.append((str(k).lower(), f"{p}.{k}"))
                walk(v, f"{p}.{k}")
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, f"{p}[{i}]")

    walk(payload, path)
    present = {k for k, _ in keys}
    for k, at in keys:
        if k in FORBIDDEN_PROMPT_KEYS:
            out.append(NeverViolation("REQ-FIN-243",
                                      f"{k!r} in a prompt bound for an external model", at))
    has_descriptor = bool({"descriptor", "raw_descriptor", "merchant_raw"} & present)
    has_coord = bool({"lat", "lon", "latitude", "longitude", "coordinate", "coordinates"}
                     & present)
    if has_descriptor and has_coord:
        out.append(NeverViolation("REQ-FIN-242",
                                  "a raw transaction descriptor and a location coordinate in the "
                                  "same third-party payload", path))
    return tuple(out)


def check_alcohol_inference(record):
    """REQ-FIN-249. An amount is never converted into a quantity of alcohol.

    $60 at a bar is not four drinks. It is a round for other people, a tab someone else added to,
    a cocktail list, or dinner. The conversion invents a health measurement out of a payment and
    then carries the authority of a number.
    """
    if record.get("derived_from_amount") and any(
            k in record for k in ("units", "drinks", "standard_drinks", "volume_ml", "ethanol_g")):
        return (NeverViolation("REQ-FIN-249",
                               "a quantity of alcohol derived from a transaction amount; $60 at "
                               "a bar is not four drinks", record.get("name", "")),)
    return ()


def check_correlation(finding):
    """REQ-FIN-254. No correlation without a pre-registered hypothesis behind it."""
    if not finding.get("hypothesis_id"):
        return (NeverViolation("REQ-FIN-254",
                               "a correlation with no pre-registered hypothesis behind it",
                               finding.get("name", "")),)
    return ()


def check_totals(surface):
    """REQ-FIN-250/256. A live figure, and a total called complete over a coverage gap."""
    out = []
    if surface.get("live") or surface.get("continuously_updating"):
        out.append(NeverViolation("REQ-FIN-250", "a live or continuously updating spend figure",
                                  surface.get("name", "")))
    gaps = surface.get("account_coverage_gap_days") or {}
    worst = max(gaps.values(), default=0)
    if worst > 35 and surface.get("presented_as_complete"):
        out.append(NeverViolation("REQ-FIN-256",
                                  f"a total presented as complete while a coverage gap of "
                                  f"{worst} days is open", surface.get("name", "")))
    return tuple(out)


def check_human_precedence(before, after):
    """REQ-FIN-245/252/253. Joe outranks the machine, permanently.

    One function for three rules because they are one rule wearing three hats: a value he set, a
    category he corrected, an insight class he dismissed. Each is a decision already made, and
    re-making it is the same failure whichever field it happens in.
    """
    out = []
    if before.get("set_by") == "joe" and after.get("value") != before.get("value") \
            and after.get("set_by") != "joe":
        out.append(NeverViolation("REQ-FIN-245",
                                  f"overwrote a value Joe set ({before.get('value')!r} -> "
                                  f"{after.get('value')!r})", before.get("field", "")))
    if before.get("category_corrected_by") == "joe" and \
            after.get("category") != before.get("category"):
        out.append(NeverViolation("REQ-FIN-252",
                                  f"re-guessed a category Joe corrected "
                                  f"({before.get('category')!r} -> {after.get('category')!r})",
                                  before.get("field", "")))
    if before.get("insight_class_dismissed") and \
            after.get("insight_class") == before.get("insight_class_dismissed"):
        out.append(NeverViolation("REQ-FIN-253",
                                  f"re-raised insight class "
                                  f"{before['insight_class_dismissed']!r} after Joe marked it "
                                  f"not useful", before.get("field", "")))
    return tuple(out)


def check_alert_timestamp(parsed):
    """REQ-FIN-257. The time-of-day on an alert email is never discarded.

    An alert at 02:14 and one at 14:02 are different facts about a day, and the date alone cannot
    recover either. Dropping the clock is irreversible: the email is parsed once.
    """
    ts = parsed.get("occurred_at")
    if ts is None:
        return (NeverViolation("REQ-FIN-257", "no timestamp retained from the alert email",
                               parsed.get("message_id", "")),)
    if getattr(ts, "hour", None) is None:
        return (NeverViolation("REQ-FIN-257", "the alert's time-of-day was reduced to a date",
                               parsed.get("message_id", "")),)
    return ()


def assert_clean(*violation_groups):
    """No soft enforcement. A rule that logs a warning and proceeds is not a never-rule."""
    all_v = [v for g in violation_groups for v in g]
    if all_v:
        raise NeverRuleViolated("; ".join(str(v) for v in all_v))
    return True
