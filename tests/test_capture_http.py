"""Exercise the deployable Worker entrypoint via Node's standard Web APIs."""
from pathlib import Path
import os
import shutil
import subprocess
from tests.conftest import dependency_skip

def test_REQ_CAP_007_008_009_011_016_017_018_deployable_http_contract():
    node = shutil.which('node')
    if node is None:
        dependency_skip('Node 24', 'capture Worker behavioral tests')
    env = {k: v for k, v in os.environ.items() if k not in
           ('SUPABASE_DB_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_CAPTURE_JWT',
            'SUPABASE_ANON_KEY', 'CAPTURE_TOKEN')}
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, '--test', 'tests/capture_http.test.mjs',
                             'tests/capture_media_http.test.mjs'],
                            cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
