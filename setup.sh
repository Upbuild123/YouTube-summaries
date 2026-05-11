#!/usr/bin/env bash
# Creates a virtual environment and installs all dependencies.
# Run once before using any pipeline scripts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# Pick the newest available Python (>=3.11). yt-dlp no longer supports 3.9.
PYTHON3=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON3="$(command -v "$candidate")"
        break
    fi
done
if [[ -z "$PYTHON3" ]]; then
    echo "No python3 found. Install Python 3.11+ (e.g. 'brew install python@3.13')." >&2
    exit 1
fi

echo "==> Creating virtual environment at $VENV_DIR (using $PYTHON3)"
"$PYTHON3" -m venv "$VENV_DIR"

echo "==> Activating virtual environment"
source "$VENV_DIR/bin/activate"

echo "==> Upgrading pip"
pip install --upgrade pip

echo "==> Installing dependencies from requirements.txt"
pip install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "==> Setup complete."
echo ""
echo "Next steps:"
echo "  1. Copy .env.example to .env and fill in your API keys and playlist URL."
echo "  2. Place your Google OAuth credentials.json in the credentials/ folder."
echo "     (See README.md for how to get these.)"
echo "  3. Activate the venv before running scripts:"
echo "       source venv/bin/activate"
echo "  4. Run the full pipeline:"
echo "       python run_all.py"
echo "     Or run each step individually:"
echo "       python 01_download_audio.py"
echo "       python 02_get_transcripts.py"
echo "       python 03_generate_descriptions.py"
echo "       python 04_write_google_doc.py"
