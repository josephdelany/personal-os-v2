"""Google Takeout -> AtomSpec (B13, ADR-0058).

Two members of the archive are read and no others:

* `Chrome/BrowserHistory.json`  -> `web_visit` atoms
* `YouTube and YouTube Music/history/watch-history.json` -> `media_play` atoms

**Location history is never read here (REQ-LOC-005).** Takeout carries
`Location History/Records.json`, and a coordinate belongs only in the restricted store that
B5 built, reached by B5's ingress, never through a general importer whose output lands in
`core.atoms` (RULE-29: coordinates are stored restricted and never leak). This module
therefore refuses location members by name rather than merely not asking for them — a
refusal is testable, an omission is not. `test_REQ_LOC_005_takeout_location_history_is_never_read`
is that test.

**Memory.** `BrowserHistory.json` is a single JSON array with years of visits in it and can
run to hundreds of megabytes. `json.load` on that costs several times the file size in
resident memory. Objects are instead pulled one at a time with `raw_decode` over a sliding
buffer, so peak memory is a function of the largest single record, not of the file — the same
reason the Apple Health importer uses `iterparse`.
"""
import codecs
import datetime as dt
import json
import zipfile
from pathlib import Path

from tools.importers.common import AtomSpec

CODE_VERSION = "import-takeout-v1"

CHROME_MEMBER = "BrowserHistory.json"
YOUTUBE_MEMBER = "watch-history.json"

# Members this importer must never open. Matched case-insensitively against the whole path.
FORBIDDEN_MEMBER_MARKERS = (
    "location history",
    "location_history",
    "records.json",
    "semantic location history",
    "semantic_location_history",
    "timeline",
)


def is_forbidden_member(name: str) -> bool:
    """REQ-LOC-005 / RULE-29: location history is not this importer's to read."""
    low = name.lower()
    return any(marker in low for marker in FORBIDDEN_MEMBER_MARKERS)


class MalformedJSON(Exception):
    """The file is not the shape this reader can stream.

    Raised rather than returning what was read so far. The first version returned silently,
    and the consequence was severe: one malformed record part-way through
    `BrowserHistory.json` ended the iteration, `import_drop` recorded a capture whose payload
    said `n_records: 1`, moved the file to `_done/`, and — because idempotency keys on the
    file's SHA-256 — refused to ever import that archive again. Five thousand visits could be
    lost with no error anywhere. A loud failure leaves the file re-importable.
    """


def _find_array_start(text, key=None):
    """Index just past the `[` that opens the array of interest, or -1.

    Two things this must not do, both of which caused silent zero-record imports:

    * Anchor on a `[` inside a string value. Takeout's own
      `{"note":"see [here]", "Browser History":[...]}` shape defeats a naive scan.
    * Anchor on the WRONG array. `{"a":[], "Browser History":[...]}` has an earlier empty
      array, and anchoring there yields nothing at all, with no error — after which
      `import_drop` writes a capture, moves the archive to `_done/`, and refuses to import it
      again because the hash matches. When `key` is given the scan therefore locates that key
      first and takes the next `[` after it.
    """
    i, in_string, escaped, start_of_string = 0, False, False, -1
    seen_key = key is None
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
                if key is not None and not seen_key and text[start_of_string + 1:i] == key:
                    seen_key = True
        elif ch == '"':
            in_string, start_of_string = True, i
        elif ch == "[" and seen_key:
            return i + 1
        i += 1
    return -1


def iter_json_objects(fp, chunk=1 << 20, key=None):
    """Yield each object of the first JSON array in `fp`, without holding the whole array.

    Works for both shapes Takeout uses: a bare top-level array (YouTube) and an object whose
    single value is the array (Chrome's `{"Browser History": [...]}`).

    Bytes are fed through an **incremental** UTF-8 decoder. Decoding each raw chunk
    independently splits multibyte characters across the ~1 MiB read boundaries — about 200 of
    them in a 200 MB history — and `errors="replace"` then writes U+FFFD into a title that is
    stored verbatim in `core.atoms.evidence_span`, indistinguishable from what the source
    actually said. Stored text must be what the source said.
    """
    dec = json.JSONDecoder()
    decoder = codecs.getincrementaldecoder("utf-8")()
    buf = ""
    started = False
    eof = False
    closed = False
    while True:
        block = fp.read(chunk)
        if block:
            if isinstance(block, bytes):
                block = decoder.decode(block)
            buf += block
        else:
            eof = True
            if isinstance(getattr(fp, "read", None), object):
                tail = decoder.decode(b"", final=True)
                if tail:
                    buf += tail
        if not started:
            i = _find_array_start(buf, key)
            if i == -1:
                if eof:
                    raise MalformedJSON(
                        f"no JSON array found for {key!r}" if key else "no JSON array found")
                continue
            buf = buf[i:]
            started = True
        while True:
            rest = buf.lstrip()
            if not rest:
                buf = rest
                break
            if rest[0] == ",":
                buf = rest[1:]
                continue
            if rest[0] == "]":
                closed = True
                return
            try:
                obj, end = dec.raw_decode(rest)
            except ValueError:
                # Either an object straddling the read boundary — read more — or genuinely
                # malformed. Only EOF distinguishes them, so the decision is deferred to EOF.
                buf = rest
                break
            yield obj
            buf = rest[end:]
        if eof:
            leftover = buf.strip()
            if leftover and not leftover.startswith("]"):
                raise MalformedJSON(
                    f"unparseable JSON after {len(buf)} remaining characters; "
                    "the archive was NOT imported so it can be re-dropped once corrected")
            if not closed:
                # Reaching the end of the file without ever seeing the array's closing bracket
                # means the file is truncated — an interrupted download, or a cut on an object
                # boundary where every object read so far happened to be well-formed. Returning
                # here would report a short but entirely plausible import.
                raise MalformedJSON(
                    "the array is not closed: this file is truncated. Nothing was imported, "
                    "so the archive can be re-downloaded and re-dropped")
            return


def _from_usec(usec):
    try:
        return dt.datetime.fromtimestamp(int(usec) / 1_000_000, tz=dt.timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _from_iso(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _domain(url):
    if not url:
        return ""
    s = str(url)
    for prefix in ("https://", "http://"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s.split("/", 1)[0].split("?", 1)[0][:255]


def parse(path, since=None, until=None, counters=None):
    """Yield AtomSpec from a Takeout zip, or from an already-extracted directory."""
    from tools.importers.apple_health import Counters
    c = counters if counters is not None else Counters()
    p = Path(path)
    if zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if is_forbidden_member(name):
                    c.bump("location_member_refused_REQ_LOC_005")
                    continue
                base = name.rsplit("/", 1)[-1]
                if base == CHROME_MEMBER:
                    with z.open(name) as fp:
                        yield from _chrome(fp, since, until, c)
                elif base == YOUTUBE_MEMBER:
                    with z.open(name) as fp:
                        yield from _youtube(fp, since, until, c)
    else:
        for f in sorted(p.rglob("*.json")):
            rel = str(f.relative_to(p))
            if is_forbidden_member(rel):
                c.bump("location_member_refused_REQ_LOC_005")
                continue
            if f.name == CHROME_MEMBER:
                with open(f, "rb") as fp:
                    yield from _chrome(fp, since, until, c)
            elif f.name == YOUTUBE_MEMBER:
                with open(f, "rb") as fp:
                    yield from _youtube(fp, since, until, c)


def _emit(spec, since, until, c):
    d = spec.subject_day
    if (since and d < since) or (until and d > until):
        c.bump("outside_window")
        return None
    return spec


CHROME_KEY = "Browser History"


def _chrome(fp, since, until, c):
    for rec in iter_json_objects(fp, key=CHROME_KEY):
        ts = _from_usec(rec.get("time_usec"))
        if ts is None:
            c.bump("chrome_row_without_time")
            continue
        url = rec.get("url") or ""
        title = (rec.get("title") or "").replace("\n", " ")[:500]
        spec = AtomSpec(
            kind="web_visit",
            metric_key=None,          # an event atom: it records that a visit happened
            occurred_at=ts,
            time_precision="exact",
            evidence_span=f"takeout:chrome;domain={_domain(url)};title={title}",
        )
        got = _emit(spec, since, until, c)
        if got is not None:
            yield got


def _youtube(fp, since, until, c):
    for rec in iter_json_objects(fp):
        ts = _from_iso(rec.get("time"))
        if ts is None:
            c.bump("youtube_row_without_time")
            continue
        subs = rec.get("subtitles") or []
        channel = (subs[0].get("name") if subs and isinstance(subs[0], dict) else "") or ""
        title = (rec.get("title") or "").replace("\n", " ")[:500]
        spec = AtomSpec(
            kind="media_play",
            metric_key=None,
            occurred_at=ts,
            time_precision="exact",
            evidence_span=f"takeout:youtube;channel={channel};title={title}",
        )
        got = _emit(spec, since, until, c)
        if got is not None:
            yield got
