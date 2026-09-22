#!/usr/bin/env python3
"""Local checkpoint monitor (ADR-0142), not a coding agent or release approver.

Run once with --write-status; --emit-launchd prints a 15-minute macOS job.
Reads only NEXT_SESSION; writes only ignored .local/backend_watchdog/status.json.
No database, network, model, credentials, subprocesses or feature-ledger writes.
"""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LABEL = "com.personalos.backend-watchdog"
INTERVAL_SECONDS = 900
STALE_SECONDS = 5400  # advisory checkpoint age, not a backend acceptance threshold
START = "<!-- backend-control:start -->"
END = "<!-- backend-control:end -->"
STATES = {"ready", "running", "held", "release_declared"}


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("checkpoint timestamps require timezone")
    return parsed


def read_control(text):
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("exactly one checkpoint control block required")
    block = text.split(START, 1)[1].split(END, 1)[0].strip()
    match = re.fullmatch(r"```json\s*\n(.*?)\n```", block, re.S)
    if not match:
        raise ValueError("checkpoint control block must be fenced JSON")
    state = json.loads(match.group(1))
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ValueError("unsupported checkpoint version")
    if state.get("status") not in STATES:
        raise ValueError("unsupported checkpoint state")
    for field in ("unit", "next_action", "updated_at", "last_progress_at"):
        if not isinstance(state.get(field), str) or not state[field].strip():
            raise ValueError("missing checkpoint field")
    updated = timestamp(state["updated_at"])
    progress = timestamp(state["last_progress_at"])
    if progress > updated:
        raise ValueError("progress cannot be later than checkpoint update")
    if state["status"] == "release_declared" and not state.get("release_evidence"):
        raise ValueError("release declaration requires evidence reference")
    return state


def inspect(root=ROOT, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    result = {"checked_at": now.isoformat(timespec="seconds"),
              "monitor": LABEL, "release_verified": False}
    try:
        state = read_control((root / "docs/NEXT_SESSION.md").read_text())
        updated = timestamp(state["updated_at"])
        progress = timestamp(state["last_progress_at"])
        if updated > now or progress > now:
            raise ValueError("checkpoint timestamp is in the future")
        checkpoint_age = int((now - updated).total_seconds())
        progress_age = int((now - progress).total_seconds())
        if state["status"] == "ready":
            outcome = "awaiting_goal"
        elif state["status"] == "held":
            outcome = "external_hold_recorded"
        elif state["status"] == "release_declared":
            outcome = "release_declaration_needs_review"
        elif checkpoint_age > STALE_SECONDS or progress_age > STALE_SECONDS:
            outcome = "checkpoint_needs_attention"
        else:
            outcome = "checkpoint_recent"
        result.update(outcome=outcome, checkpoint_state=state["status"],
                      checkpoint_age_seconds=checkpoint_age,
                      progress_age_seconds=progress_age)
    except (OSError, ValueError, TypeError, AttributeError):
        # Never copy malformed checkpoint text, paths or an exception into logs.
        result["outcome"] = "checkpoint_invalid_or_unreadable"
    return result


def write_status(root=ROOT):
    directory = root / ".local/backend_watchdog"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "monitor.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"outcome": "monitor_already_running", "release_verified": False}
        result = inspect(root)
        # Replace one bounded snapshot. No growing log and no partial JSON readers.
        fd, temporary = tempfile.mkstemp(prefix="status-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w") as target:
                json.dump(result, target, indent=2)
                target.write("\n")
            os.replace(temporary, directory / "status.json")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return result


def launchd(root=ROOT, python=None):
    return {"Label": LABEL,
            "ProgramArguments": [python or sys.executable,
                                 str(root / "ops/backend_watchdog.py"), "--write-status"],
            "WorkingDirectory": str(root),
            "StartInterval": INTERVAL_SECONDS,
            "RunAtLoad": True,
            "ProcessType": "Background"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write-status", action="store_true")
    mode.add_argument("--emit-launchd", action="store_true")
    args = parser.parse_args()
    if args.emit_launchd:
        sys.stdout.buffer.write(plistlib.dumps(launchd()))
        return 0
    result = write_status() if args.write_status else inspect()
    print(json.dumps(result, sort_keys=True))
    return 1 if result["outcome"] in {
        "checkpoint_invalid_or_unreadable", "checkpoint_needs_attention"} else 0


if __name__ == "__main__":
    sys.exit(main())
