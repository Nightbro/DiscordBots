#!/bin/bash
set -e
cd "$(dirname "$0")"

# ── Step 1: Set up Virtual Environment ───────
echo "[1/2] Setting up virtual environment..."
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created!"
else
    echo "Virtual environment already exists."
fi

source venv/bin/activate

echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing dependencies..."
pip install -r requirements.txt
echo "Dependencies ready!"

# ── Step 2: Check .env token ──────────────────
echo "[2/2] Checking configuration..."
if [ ! -f ".env" ]; then
    echo "[ERROR] .env file not found!"
    echo "Create a .env file in this folder with:"
    echo "  DISCORD_TOKEN=your_token_here"
    echo "  OWNER_ID=your_discord_user_id"
    exit 1
fi
if grep -q "paste_your_token_here" .env; then
    echo "[ERROR] You haven't set your DISCORD_TOKEN in the .env file!"
    exit 1
fi
echo "Configuration looks good!"

echo "============================================"
echo " Night Roller is starting..."
echo "============================================"
exec python bot.py
