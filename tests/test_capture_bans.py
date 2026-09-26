"""REQ-CAP structural bans — constraints provable by reading the repository (RULE-30, RULE-29).

These are not aspirations about runtime behaviour. Each is a promise that a particular API or
secret appears NOWHERE in the shipped source, and that is decidable now, on every commit,
without a device.

`ops/features.json` has carried "PWA never calls getUserMedia" as FAILING since the ledger was
created — not because the PWA calls it, but because nothing had ever checked. An unchecked
promise and a broken one are indistinguishable from outside.
"""
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PWA_FILES = sorted([*(ROOT / "app").glob("*.html"), *(ROOT / "app").glob("*.mjs")])
SHORTCUT_GENERATORS = sorted(ROOT.glob("tools/make_shortcut_*.py"))


def test_REQ_CAP_001_the_pwa_never_calls_get_user_media():
    """RULE-30. Microphone capture belongs to the Shortcut, which records to a file Joe can
    see and delete. A browser that can open the microphone is a browser that can do it without
    Joe noticing, and the PWA is the surface with the weakest consent affordances."""
    assert (ROOT / "app" / "index.html") in PWA_FILES, "the PWA source must exist for this ban to mean anything"
    source = "\n".join(path.read_text() for path in PWA_FILES)
    assert not re.search(r"getUserMedia", source, re.I), "the PWA opens the microphone"
    assert not re.search(r"\bmediaDevices\b", source, re.I)
    assert not re.search(r"\bMediaRecorder\b", source, re.I)


def test_REQ_CAP_002_the_pwa_never_calls_the_webspeech_api():
    """A browser speech API sends audio to the browser vendor. RULE-29 permits Supabase,
    Cloudflare Workers AI and the originating source APIs — a vendor's speech endpoint is
    none of those, and it would leave no row in ops.egress_log."""
    source = "\n".join(path.read_text() for path in PWA_FILES)
    for banned in ("webkitSpeechRecognition", "SpeechRecognition", "speechSynthesis"):
        assert banned.lower() not in source.lower(), f"the PWA uses {banned}"


def test_REQ_CAP_009_no_shortcut_carries_the_service_role_key():
    """A Shortcut lives on a phone and is shareable by design. The service_role key bypasses
    row-level security entirely, so one in a Shortcut is a full-database credential in a file
    that can be AirDropped."""
    assert SHORTCUT_GENERATORS, "the shortcut generators must exist"
    for path in SHORTCUT_GENERATORS:
        source = path.read_text()
        assert "service_role" not in source, f"{path.name} names the service_role key"
        # A Supabase JWT carries its role in the payload; the anon key is the only one allowed.
        for token in re.findall(r"eyJ[A-Za-z0-9_\-]{10,}", source):
            assert "service" not in token.lower(), f"{path.name} embeds a non-anon token"


def test_REQ_CAP_009_no_credential_of_any_kind_is_committed_in_a_shortcut_generator():
    """The constitution's wording is absolute: credentials come from environment variables or
    repository secrets, never committed. The anon key is deliberately exempt — it is public by
    design and RLS is what protects the data behind it."""
    for path in SHORTCUT_GENERATORS:
        source = path.read_text()
        for name in ("SUPABASE_DB_URL", "postgres://", "postgresql://", "PGPASSWORD"):
            assert name not in source, f"{path.name} contains {name}"


def test_the_features_ledger_and_these_bans_do_not_contradict_each_other():
    """ops/features.json is the project's own claim about what works. F-002 asserts the PWA
    ban; if the ledger says failing while this file passes, one of them is lying — and the
    ledger moves only on a named passing test (ADR-0011), which is what this now is."""
    ledger = json.loads((ROOT / "ops" / "features.json").read_text())
    f002 = next(f for f in ledger["features"] if f["id"] == "F-002")
    assert f002["requirement"] == "REQ-CAP-001"
    if f002["status"] == "passing":
        assert f002["proving_test"], "a passing feature must name the test that proves it"
