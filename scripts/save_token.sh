#!/usr/bin/env bash
# One-time: saves your GitHub token into .env (git-ignored). Input is hidden.
set -euo pipefail
cd "$(dirname "$0")/.."
printf "Paste your GitHub token (hidden), then press Enter: "
read -rs TOK; echo
case "$TOK" in github_pat_*|ghp_*) ;; *) echo "That doesn't look like a GitHub token. Nothing saved."; exit 1;; esac
touch .env; chmod 600 .env
grep -v '^GITHUB_TOKEN=' .env > .env.tmp || true
echo "GITHUB_TOKEN=$TOK" >> .env.tmp && mv .env.tmp .env && chmod 600 .env
echo "Saved. You're done; Claude can now publish updates for you."
