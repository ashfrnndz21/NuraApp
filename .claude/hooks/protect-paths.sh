#!/usr/bin/env bash
# PreToolUse hook: block edits to protected paths unless NURA_ALLOW_PROTECTED=1.
input=$(cat)
path=$(echo "$input" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path") or d.get("tool_input",{}).get("path") or "")')
case "$path" in
  */.github/*|*/.claude/*|*/CLAUDE.md|*/backend/app/keys/*|*/backend/app/safety/*|*/backend/alembic/versions/*)
    if [ "${NURA_ALLOW_PROTECTED:-0}" != "1" ]; then echo "Blocked: $path is a protected path. Open a risk:high PR and ask a human." >&2; exit 2; fi;;
esac
exit 0
