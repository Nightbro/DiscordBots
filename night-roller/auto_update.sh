#!/bin/bash
# Polls GitHub for new commits. If there are any, pulls, reinstalls deps,
# and restarts the bot. Designed to run from cron every few minutes.

set -e
cd "$(dirname "$0")"

git fetch origin main

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0  # nothing new
fi

echo "[$(date)] New commits detected, updating..."
git pull origin main
source venv/bin/activate
pip install -q -r requirements.txt
sudo systemctl restart night-roller
echo "[$(date)] Update complete."
