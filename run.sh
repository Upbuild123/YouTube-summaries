#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  run.sh — YouTube playlist → Google Doc pipeline
#
#  This script handles everything:
#    • Auto-installs system prerequisites if missing
#        - Homebrew (macOS)
#        - Python 3.11+ (3.13 by default)
#        - ffmpeg (for audio conversion)
#        - Node.js >=20 (for yt-dlp's JS challenge solver)
#    • Creates the virtual environment on first run
#    • Installs / updates Python dependencies
#    • Validates your .env file
#    • Checks that Google credentials exist
#    • Runs pipeline.py with any arguments you pass
#
#  Usage
#  -----
#    ./run.sh                # run all four steps (CLI)
#    ./run.sh --app          # launch the Streamlit web UI
#    ./run.sh --step 2       # run only step 2
#    ./run.sh --steps 1,3    # run steps 1 and 3
#    ./run.sh --steps 2-4    # run steps 2 through 4
#    ./run.sh --list         # show per-episode progress table
#    ./run.sh --setup-only   # install dependencies and exit (no pipeline run)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
ENV_FILE="$SCRIPT_DIR/.env"
CREDS_FILE="$SCRIPT_DIR/credentials/credentials.json"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${BLUE}[run.sh]${NC} $*"; }
ok()   { echo -e "${GREEN}[run.sh]${NC} ✓ $*"; }
warn() { echo -e "${YELLOW}[run.sh]${NC} ⚠ $*"; }
die()  { echo -e "${RED}[run.sh]${NC} ✗ $*" >&2; exit 1; }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. PREREQUISITES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

log "Checking prerequisites…"

# ── Detect OS so we know which package manager to use ────────────────────────
OS="$(uname -s)"
case "$OS" in
    Darwin)  PLATFORM="macos" ;;
    Linux)   PLATFORM="linux" ;;
    *)       PLATFORM="other" ;;
esac

# Ask the user before installing system software.  Returns 0 if they agree.
_confirm_install() {
    local what="$1"
    echo ""
    read -r -p "       Install $what now? [Y/n] " reply
    [[ -z "$reply" || "$reply" =~ ^[Yy]$ ]]
}

# ── Homebrew (macOS only) ────────────────────────────────────────────────────
# We use brew to bootstrap python/ffmpeg/node on macOS.  On Linux we delegate
# to apt (debian/ubuntu) or dnf (fedora) and just warn if neither exists.
if [[ "$PLATFORM" == "macos" ]]; then
    if ! command -v brew &>/dev/null; then
        warn "Homebrew not found — needed to auto-install python/ffmpeg/node."
        echo    "       Homebrew is the standard macOS package manager."
        if _confirm_install "Homebrew"; then
            log "Installing Homebrew (this may prompt for your password)…"
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # The installer prints a hint to add brew to PATH.  Apply it now so
            # the rest of this script can find brew without a shell restart.
            if [[ -x /opt/homebrew/bin/brew ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [[ -x /usr/local/bin/brew ]]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
            ok "Homebrew installed"
        else
            die "Homebrew is required on macOS for auto-install. Install it from https://brew.sh and re-run."
        fi
    else
        ok "Homebrew $(brew --version | head -1 | awk '{print $2}')"
    fi
fi

# ── Python 3.11+ ─────────────────────────────────────────────────────────────
# Prefer the newest interpreter available.  yt-dlp dropped 3.9, so 3.11 is the
# floor.  If nothing suitable is found, install python@3.13 via brew on macOS.
_find_python() {
    PYTHON3=""
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" &>/dev/null; then
            local path; path="$(command -v "$candidate")"
            local major minor
            major="$("$path" -c 'import sys; print(sys.version_info[0])' 2>/dev/null || echo 0)"
            minor="$("$path" -c 'import sys; print(sys.version_info[1])' 2>/dev/null || echo 0)"
            if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
                PYTHON3="$path"
                PY_MAJOR="$major"
                PY_MINOR="$minor"
                return 0
            fi
        fi
    done
    return 1
}

if ! _find_python; then
    warn "No Python 3.11+ found."
    if [[ "$PLATFORM" == "macos" ]]; then
        if _confirm_install "Python 3.13 via brew"; then
            brew install python@3.13
            _find_python || die "Python install reported success but no python3.11+ on PATH."
        else
            die "Python 3.11+ required. Install manually then re-run."
        fi
    elif [[ "$PLATFORM" == "linux" ]]; then
        die "Python 3.11+ required. Install with your package manager (e.g. 'sudo apt install python3.11') then re-run."
    else
        die "Python 3.11+ required. Install from https://python.org then re-run."
    fi
fi
ok "Python $PY_MAJOR.$PY_MINOR ($PYTHON3)"

# ── ffmpeg ───────────────────────────────────────────────────────────────────
# Required by yt-dlp to convert downloaded audio to MP3.
if ! command -v ffmpeg &>/dev/null; then
    warn "ffmpeg not found — required for audio conversion."
    if [[ "$PLATFORM" == "macos" ]]; then
        if _confirm_install "ffmpeg via brew"; then
            brew install ffmpeg
        else
            die "ffmpeg is required for step 1. Install it then re-run."
        fi
    elif [[ "$PLATFORM" == "linux" ]] && command -v apt-get &>/dev/null; then
        if _confirm_install "ffmpeg via apt"; then
            sudo apt-get update && sudo apt-get install -y ffmpeg
        else
            die "ffmpeg is required for step 1. Install it then re-run."
        fi
    else
        die "ffmpeg not found and no supported package manager detected. Install it manually."
    fi
fi
ok "ffmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"

# ── Node.js >=20 ─────────────────────────────────────────────────────────────
# yt-dlp shells out to node to solve YouTube's JS "n-challenge".  Without it,
# only video thumbnails are downloadable.
_node_ok() {
    command -v node &>/dev/null || return 1
    local ver major
    ver="$(node -v 2>/dev/null | sed 's/^v//')"
    major="${ver%%.*}"
    [[ -n "$major" && "$major" -ge 20 ]]
}

if ! _node_ok; then
    if command -v node &>/dev/null; then
        warn "node $(node -v) is too old — need >=20."
    else
        warn "node not found — yt-dlp can't solve YouTube's JS challenge without it."
    fi
    if [[ "$PLATFORM" == "macos" ]]; then
        if _confirm_install "Node.js via brew"; then
            brew install node || brew upgrade node
        else
            die "Node.js >=20 is required. Install it then re-run."
        fi
    elif [[ "$PLATFORM" == "linux" ]] && command -v apt-get &>/dev/null; then
        if _confirm_install "Node.js via apt"; then
            sudo apt-get update && sudo apt-get install -y nodejs npm
        else
            die "Node.js >=20 is required. Install it then re-run."
        fi
    else
        die "Node.js >=20 not found and no supported package manager detected. Install it manually."
    fi
    _node_ok || die "Node.js install reported success but 'node' is still missing or <20."
fi
ok "node $(node -v)"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. VIRTUAL ENVIRONMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if [[ ! -d "$VENV" ]]; then
    log "Creating virtual environment at $VENV …"
    "$PYTHON3" -m venv "$VENV"
    ok "Virtual environment created"
else
    ok "Virtual environment exists"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. INSTALL / UPDATE DEPENDENCIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Use a sentinel file to avoid running pip install on every run.
# It is re-touched whenever requirements.txt changes.
SENTINEL="$VENV/.deps_installed"
if [[ ! -f "$SENTINEL" ]] || [[ "$REQUIREMENTS" -nt "$SENTINEL" ]]; then
    log "Installing / updating Python dependencies…"
    "$PIP" install --upgrade pip --quiet
    "$PIP" install -r "$REQUIREMENTS" --quiet
    touch "$SENTINEL"
    ok "Dependencies installed"
else
    ok "Dependencies up to date"
fi

# yt-dlp must be kept current — YouTube changes its player frequently and
# stale yt-dlp builds break with "YouTube is no longer supported in this
# application or device".  Upgrade on every run; it's a fast no-op when current.
"$PIP" install --upgrade --quiet yt-dlp
ok "yt-dlp up to date"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. VALIDATE .env
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if [[ ! -f "$ENV_FILE" ]]; then
    warn ".env not found — creating one from .env.example"
    if [[ -f "$SCRIPT_DIR/.env.example" ]]; then
        cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
        echo ""
        echo -e "  ${BOLD}Action required:${NC} open .env and fill in your values:"
        echo    "    GEMINI_API_KEY  — from https://aistudio.google.com/app/apikey"
        echo    "    PLAYLIST_URL    — the YouTube playlist URL"
        echo    "    OPENAI_API_KEY  — optional (only for Whisper fallback)"
        echo ""
        die "Fill in .env then re-run ./run.sh"
    else
        die ".env file missing. Create it — see README.md for required variables."
    fi
fi

# Check required keys are non-empty in .env
_get_env_val() {
    local key="$1"
    grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs
}

GEMINI_VAL="$(_get_env_val GEMINI_API_KEY)"
PLAYLIST_VAL="$(_get_env_val PLAYLIST_URL)"
MISSING=0

if [[ -z "$GEMINI_VAL" || "$GEMINI_VAL" == AIza...* ]]; then
    warn "GEMINI_API_KEY is not set in .env"
    MISSING=1
fi
if [[ -z "$PLAYLIST_VAL" || "$PLAYLIST_VAL" == https://www.youtube.com/playlist?list=PLx* ]]; then
    warn "PLAYLIST_URL is not set in .env"
    MISSING=1
fi

if [[ "$MISSING" -eq 1 ]]; then
    echo ""
    echo    "  Open .env and set the missing values, then re-run ./run.sh"
    echo ""
    # Only block if step 1 or 3 would be needed — let --list pass through.
    # We check the args below; for now just warn and continue.
    :
fi

ok ".env present"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. GOOGLE CREDENTIALS REMINDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if [[ ! -f "$CREDS_FILE" ]]; then
    warn "credentials/credentials.json not found"
    echo ""
    echo    "  Step 4 (Google Doc) will fail without this file."
    echo    "  To set it up:"
    echo    "    1. Go to console.cloud.google.com"
    echo    "    2. Enable Google Docs API and Google Drive API"
    echo    "    3. Create an OAuth 2.0 Desktop App credential"
    echo    "    4. Download the JSON and save it as:"
    echo    "         credentials/credentials.json"
    echo    "  (See README.md for the full walkthrough.)"
    echo ""
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. HANDLE --setup-only / --app
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LAUNCH_APP=0
for arg in "$@"; do
    if [[ "$arg" == "--setup-only" ]]; then
        ok "Setup complete. Run ./run.sh to start the pipeline, or ./run.sh --app for the web UI."
        exit 0
    fi
    if [[ "$arg" == "--app" ]]; then
        LAUNCH_APP=1
    fi
done

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. RUN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if [[ "$LAUNCH_APP" -eq 1 ]]; then
    echo ""
    log "Launching Streamlit web UI…"
    echo ""
    exec "$VENV/bin/streamlit" run "$SCRIPT_DIR/app.py"
fi

# Filter out run.sh-specific flags before passing args to Python
PIPELINE_ARGS=()
for arg in "$@"; do
    [[ "$arg" != "--setup-only" && "$arg" != "--app" ]] && PIPELINE_ARGS+=("$arg")
done

echo ""
log "Starting pipeline…"
echo ""

exec "$PYTHON" "$SCRIPT_DIR/pipeline.py" ${PIPELINE_ARGS[@]+"${PIPELINE_ARGS[@]}"}
