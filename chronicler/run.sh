#!/bin/bash
set -e
cd "$(dirname "$0")"

# ── Step 1: Check Python ──────────────────────
# fpdf2 and Pillow both require 3.11. Without this check the failure surfaces
# as an opaque pip resolution error several steps later.
echo "[1/3] Checking Python version..."
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "[ERROR] Chronicler needs Python 3.11 or newer."
    echo "        Found: $(python3 --version 2>&1)"
    echo "        The PDF and image libraries require it."
    echo "        See LINUX_SETUP.md section 6.2 for the options."
    exit 1
fi
echo "Python $(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))') is fine."

# ── Step 2: Set up Virtual Environment ───────
echo "[2/3] Setting up virtual environment..."
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

# ── Step 3: Check .env token ──────────────────
echo "[3/3] Checking configuration..."
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
echo " Chronicler is starting..."
echo "============================================"
exec python bot.py
