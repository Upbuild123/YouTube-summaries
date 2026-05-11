"""
Central configuration for the YouTube playlist pipeline.
All scripts import from here so settings only need to change in one place.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Directory layout ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent

AUDIO_DIR        = BASE_DIR / "audio"
TRANSCRIPTS_DIR  = BASE_DIR / "transcripts"
DESCRIPTIONS_DIR = BASE_DIR / "descriptions"
LOGS_DIR         = BASE_DIR / "logs"
CREDENTIALS_DIR  = BASE_DIR / "credentials"

METADATA_FILE = BASE_DIR / "metadata.json"
LOG_FILE      = LOGS_DIR  / "pipeline.log"

# Create dirs on import so every script can safely write to them.
for _d in (AUDIO_DIR, TRANSCRIPTS_DIR, DESCRIPTIONS_DIR, LOGS_DIR, CREDENTIALS_DIR):
    _d.mkdir(exist_ok=True)

# ── API keys ──────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")  # Optional — Whisper fallback

# ── Playlist ──────────────────────────────────────────────────────────────────

PLAYLIST_URL = os.getenv("PLAYLIST_URL", "")

# ── Google Docs ───────────────────────────────────────────────────────────────

GOOGLE_CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"
GOOGLE_TOKEN_FILE       = CREDENTIALS_DIR / "token.json"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

# ── AI model ──────────────────────────────────────────────────────────────────

ANTHROPIC_MODEL        = "claude-opus-4-7"
DESCRIPTION_MAX_TOKENS = 600

# Max words of transcript to send to Claude (controls cost; 3000 ≈ ~10 min episode)
TRANSCRIPT_MAX_WORDS = 3000

# ── Audio download ────────────────────────────────────────────────────────────

AUDIO_FORMAT  = "mp3"
AUDIO_QUALITY = "128"  # kbps

# ── Transcript strategy ───────────────────────────────────────────────────────

# Try YouTube captions first (free, instant).
PREFER_YOUTUBE_CAPTIONS = True

# Fall back to OpenAI Whisper API if no captions exist.
# Requires OPENAI_API_KEY.  Set False to skip fallback (episodes will be marked
# transcript_unavailable instead of failing the whole run).
USE_OPENAI_WHISPER_FALLBACK = True

# ── Retry / rate-limit settings ───────────────────────────────────────────────

MAX_RETRIES  = 3
RETRY_DELAY  = 5   # seconds between retries

# Seconds to pause between Google Docs API batchUpdate calls to stay under
# the 300-requests/min quota.
GDOCS_INTER_EPISODE_DELAY = 0.4
