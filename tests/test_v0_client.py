"""Run the V0 owner adapter's built-in Node contract tests in the normal suite."""
import shutil
import subprocess
from pathlib import Path


def test_RULE_02_RULE_06_RULE_10_v0_owner_caller():
    node = shutil.which('node')
    assert node, 'Node is required for the executable V0 owner caller tests'
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, '--test', 'tests/v0_client.test.mjs'],
                            cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
