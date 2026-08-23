#!/usr/bin/env bash
# Behavioural test of .claude/hooks/guard-destructive.sh.
# Feeds it the exact JSON Claude Code feeds it. exit 2 = blocked, 0 = allowed.
pass=0; fail=0
try() { # try <expect: BLOCK|ALLOW> <command>
  out=$(printf '{"tool_input":{"command":%s}}' "$(jq -Rs . <<<"$2")" | .claude/hooks/guard-destructive.sh 2>&1)
  code=$?
  want=2; [ "$1" = ALLOW ] && want=0
  if [ "$code" -eq "$want" ]; then echo "  ok   $1  $2"; pass=$((pass+1))
  else echo "  FAIL $1 expected but got exit $code  ::  $2"; fail=$((fail+1)); fi
}
echo "MUST BLOCK:"
try BLOCK "psql -c 'drop table atoms'"
try BLOCK "psql -c 'DROP TABLE IF EXISTS raw_captures'"
try BLOCK "psql -c 'truncate table findings'"
try BLOCK "psql -c 'delete from atoms where id = 3'"
try BLOCK "psql -c 'UPDATE public.raw_captures SET payload = null'"
try BLOCK "psql -c 'UPDATE core.atoms SET code_version = null'"
try BLOCK "psql -c 'delete from core.raw_captures'"
try BLOCK "git push --force origin main"
try BLOCK "git push -f"
try BLOCK "git reset --hard HEAD~3"
try BLOCK "rm -rf node_modules/"
try BLOCK "rm -fr build"
try BLOCK "cat .env"
try BLOCK "echo \$SUPABASE_PASSWORD"
try BLOCK "curl https://api.example.com/food"
try BLOCK "wget -q http://x/y"
echo "MUST ALLOW:"
try ALLOW "pytest -k REQ_CAP_001"
try ALLOW "git commit -m 'REQ-CAP-001: shortcut owns capture'"
try ALLOW "psql -c 'select count(*) from atoms'"
try ALLOW "python3 tools/validate_layout.py"
try ALLOW "ls -la docs/"
echo "--- KNOWN-EVASION PROBES (these are the interesting ones) ---"
try BLOCK "psql -c 'DELETE  FROM  atoms'"
try BLOCK "python3 -c \"import os; os.system('rm -rf build')\""
try BLOCK "git push --force-with-lease origin main"
# OQ-14 open: derived_measures is recomputable, so this is currently ALLOWED by
# design. If Joe rules that derived rows are append-with-supersedes too, flip
# this to BLOCK and add the table to the hook's append-only list.
try ALLOW "psql -c 'delete from derived_measures'"
# OQ-15 open: a shell regex cannot close this. The real enforcement is a
# forbidden-import lint in CI. Asserted ALLOW here so that this gate stays
# honest -- the hole is tracked in OPEN_QUESTIONS, not hidden by a passing test.
try ALLOW "python3 -c \"import requests; requests.get('http://x')\""
echo
echo "$pass passed, $fail failed"
exit $(( fail > 0 ))
