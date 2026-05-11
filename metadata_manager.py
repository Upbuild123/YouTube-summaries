"""
Thread-safe read/write helpers for metadata.json.

metadata.json shape
-------------------
{
  "playlist_title": "...",
  "playlist_url":   "...",
  "google_doc_id":  null | "...",
  "episodes": [
    {
      "episode_number":   1,
      "video_id":         "abc123",
      "youtube_url":      "https://www.youtube.com/watch?v=abc123",
      "title":            "Episode Title",
      "duration_seconds": 600,
      "audio_file":       "audio/001_Episode_Title.mp3",
      "subtitle_file":    "audio/001_Episode_Title.en.vtt",   // may be null
      "transcript_file":  "transcripts/001_Episode_Title.txt",
      "description_file": "descriptions/001_Episode_Title.txt",
      "description":      null | "...",
      "transcript_source": null | "youtube_captions" | "whisper",
      "status": {
        "audio_downloaded":    false,
        "transcript_obtained": false,
        "description_generated": false,
        "google_doc_updated":  false
      },
      "errors": []
    }
  ]
}
"""

import json
import logging
import re
import threading
from pathlib import Path

from config import METADATA_FILE

logger = logging.getLogger(__name__)

_lock = threading.Lock()


# ── Filename helpers ───────────────────────────────────────────────────────────

def safe_filename(title: str, max_length: int = 80) -> str:
    """Return a filesystem-safe version of *title*."""
    # Keep letters, digits, spaces, hyphens; replace everything else
    safe = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    safe = re.sub(r"\s+", "_", safe.strip())
    return safe[:max_length]


def episode_stem(episode_number: int, title: str) -> str:
    return f"{episode_number:03d}_{safe_filename(title)}"


# ── Load / save ────────────────────────────────────────────────────────────────

def load() -> dict:
    with _lock:
        if not METADATA_FILE.exists():
            return {"playlist_title": "", "playlist_url": "", "google_doc_id": None, "episodes": []}
        try:
            with METADATA_FILE.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError as exc:
            logger.error("metadata.json is corrupt: %s", exc)
            raise


def save(data: dict) -> None:
    with _lock:
        tmp = METADATA_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        tmp.replace(METADATA_FILE)


# ── Episode helpers ────────────────────────────────────────────────────────────

def get_episode(data: dict, video_id: str) -> dict | None:
    for ep in data["episodes"]:
        if ep["video_id"] == video_id:
            return ep
    return None


def upsert_episode(data: dict, episode: dict) -> None:
    """Insert or replace an episode entry (matched by video_id)."""
    for i, ep in enumerate(data["episodes"]):
        if ep["video_id"] == episode["video_id"]:
            data["episodes"][i] = episode
            return
    data["episodes"].append(episode)


def new_episode(episode_number: int, video_id: str, title: str, youtube_url: str,
                duration_seconds: int = 0) -> dict:
    from config import AUDIO_FORMAT
    stem = episode_stem(episode_number, title)
    return {
        "episode_number":       episode_number,
        "video_id":             video_id,
        "youtube_url":          youtube_url,
        "title":                title,
        "duration_seconds":     duration_seconds,
        "audio_file":           f"audio/{stem}.{AUDIO_FORMAT}",
        "subtitle_file":        None,
        "transcript_file":      f"transcripts/{stem}.txt",
        "description_file":     f"descriptions/{stem}.txt",
        "description":          None,
        "transcript_source":    None,
        "status": {
            "audio_downloaded":      False,
            "transcript_obtained":   False,
            "description_generated": False,
            "google_doc_updated":    False,
        },
        "errors": [],
    }


def mark_status(data: dict, video_id: str, key: str, value: bool = True) -> None:
    ep = get_episode(data, video_id)
    if ep:
        ep["status"][key] = value


def add_error(data: dict, video_id: str, message: str) -> None:
    ep = get_episode(data, video_id)
    if ep:
        ep["errors"].append(message)
        logger.warning("[%s] error recorded: %s", video_id, message)
