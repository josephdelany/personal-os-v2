#!/usr/bin/env bash
# Blocks unrecoverable commands before they run. Exit 2 = block, and tell the model why.
# permissions.deny in settings.json is the first line; this catches constructions
# that pattern-matching misses (piped, quoted, chained).

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
block() { echo "BLOCKED by guard-destructive.sh: $1" >&2; exit 2; }

echo "$CMD" | grep -qiE '\b(drop|truncate)[[:space:]]+(table|schema|database)' \
  && block "DDL that destroys data. Write a forward-only migration instead."

echo "$CMD" | grep -qiE '\b(delete[[:space:]]+from|update)[[:space:]]+(public\.|core\.)?(atoms|raw_captures|entities|links|findings)' \
  && block "RULE-02: these tables are append-only. A correction is a new row with supersedes set."

echo "$CMD" | grep -qE 'push[[:space:]]+.*(--force|-f)\b' && block "Force push. Ask Joe first."
echo "$CMD" | grep -qE 'reset[[:space:]]+--hard' && block "Hard reset discards work irreversibly. Use git stash."

echo "$CMD" | grep -qE '\brm[[:space:]]+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)' \
  && block "Recursive force delete. Move files to _to_delete/ and tell Joe instead."

echo "$CMD" | grep -qiE '(cat|head|tail|less|echo).*(\.env|SUPABASE_(KEY|PASSWORD|SERVICE)|CLOUDFLARE_API)' \
  && block "Credentials come from env vars or repo secrets. Never into context, never echoed."

echo "$CMD" | grep -qE '\b(curl|wget|nc)\b' \
  && block "RULE-29: outbound requests go through the egress-logged client, not the shell."

exit 0
