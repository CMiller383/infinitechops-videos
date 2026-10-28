#!/usr/bin/env bash
# Daily job: post the next queued Reel to Instagram. Reads the token from ../secrets.txt (never committed).
# Run by the systemd user timer infinitechops-post.timer; run by hand with --check to test without posting.
set -uo pipefail
cd "$(dirname "$0")"
TOKEN_LINE=$(grep -m1 '^IG_ACCESS_TOKEN=' ../secrets.txt) || { echo "$(date -Is) no IG_ACCESS_TOKEN in ../secrets.txt" >> post.log; exit 1; }
export IG_ACCESS_TOKEN="${TOKEN_LINE#IG_ACCESS_TOKEN=}"
git pull -q --rebase >> post.log 2>&1 || true
echo "=== $(date -Is) $*" >> post.log
python3 post_next.py "$@" >> post.log 2>&1
status=$?
tail -n 6 post.log
exit $status
