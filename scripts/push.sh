#!/usr/bin/env bash
# Commits and pushes all changes using GITHUB_TOKEN from .env. Never prints or stores the token.
set -euo pipefail
cd "$(dirname "$0")/.."
TOK=$(grep '^GITHUB_TOKEN=' .env | cut -d= -f2-)
[ -n "$TOK" ] || { echo "No GITHUB_TOKEN in .env"; exit 1; }
AUTH=$(printf 'x-access-token:%s' "$TOK" | base64 | tr -d '\n')
git add -A
git diff --cached --quiet || git commit -q -m "${1:-update dashboard}"
git -c "http.extraheader=Authorization: Basic $AUTH" pull -q --rebase origin main
git -c "http.extraheader=Authorization: Basic $AUTH" push -q origin main
echo "Pushed. Live site rebuilds in ~2 minutes."
