#!/bin/bash
# T4 activation — apply the conversation-layer migrations, load the 7-year
# legacy series, run the first panel+baselines build. One run, ~3 minutes.
set -euo pipefail
cd ~/PERSONAL_OS_V2
for m in 0026 0027 0029 0030; do
  PYTHONPATH=. python3 tools/run_migration.py --core core --ops ops --only $m --commit
done
PYTHONPATH=. python3 tools/parsers/legacy_daily.py
PYTHONPATH=. python3 tools/run_analysis.py
echo "=== DONE. Refresh the app: Today + Timeline are live over 7 years. ==="
