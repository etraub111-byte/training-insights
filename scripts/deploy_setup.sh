#!/usr/bin/env bash
# One-time setup: puts this project on GitHub and turns on the auto-updating phone app.
# Needs the GitHub CLI: brew install gh && gh auth login
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${1:-training-insights}"

command -v gh >/dev/null || { echo "Install the GitHub CLI first: brew install gh"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Run: gh auth login"; exit 1; }
[ -f .env ] || { echo ".env not found"; exit 1; }
KEY="$(grep -m1 '^GARMIN_API_KEY=' .env | cut -d= -f2- | tr -d '"'"'"' \r')"
[ -n "$KEY" ] || { echo "GARMIN_API_KEY missing in .env"; exit 1; }

LOGIN="$(gh api user -q .login)"
echo "GitHub account: $LOGIN   repo: $NAME (public; your data and key stay private)"

while true; do
  read -rsp "Choose a page password (12+ characters, a few random words works well): " PW; echo
  read -rsp "Repeat it: " PW2; echo
  [ "$PW" = "$PW2" ] && [ "${#PW}" -ge 12 ] && break
  echo "Passwords differ or are under 12 characters. Try again."
done

[ -d .git ] || git init -q -b main
git config user.name >/dev/null || git config user.name "$LOGIN"
git config user.email >/dev/null || git config user.email "$LOGIN@users.noreply.github.com"
git add -A
git diff --cached --quiet || git commit -q -m "Training insights dashboard"

gh repo view "$LOGIN/$NAME" >/dev/null 2>&1 || gh repo create "$NAME" --public --source . --remote origin
printf %s "$KEY" | gh secret set GARMIN_API_KEY --repo "$LOGIN/$NAME"
printf %s "$PW"  | gh secret set PAGE_PASSWORD  --repo "$LOGIN/$NAME"
gh api -X POST "repos/$LOGIN/$NAME/pages" -f build_type=workflow >/dev/null 2>&1 \
  || gh api -X PUT "repos/$LOGIN/$NAME/pages" -f build_type=workflow >/dev/null 2>&1 \
  || echo "Could not enable Pages automatically. Do it in repo Settings > Pages > Source: GitHub Actions."

git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$LOGIN/$NAME.git"
git push -u origin main

echo
echo "Done. First build is running (the full Garmin backfill can take a few runs)."
echo "Watch it:  gh run watch --repo $LOGIN/$NAME"
echo "Your app:  https://$LOGIN.github.io/$NAME/"
echo "On iPhone: open that link in Safari > Share > Add to Home Screen."
