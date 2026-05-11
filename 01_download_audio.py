#!/usr/bin/env python3
"""
Step 1 — Download audio (and auto-captions) for every episode in the playlist.

Resumable: episodes already marked audio_downloaded=true are skipped.

Outputs
-------
audio/<NNN>_<title>.mp3          — audio file
audio/<NNN>_<title>.en.vtt       — subtitle sidecar (if YouTube has captions)
metadata.json                    — updated with file paths + status
"""

import logging
import subprocess
import sys
import time
from pathlib import Path

from tqdm import tqdm

import metadata_manager as mm
from config import (
    AUDIO_DIR, AUDIO_FORMAT, AUDIO_QUALITY, LOG_FILE,
    MAX_RETRIES, METADATA_FILE, PLAYLIST_URL, RETRY_DELAY,
)

# ── Logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ── Playlist info extraction ───────────────────────────────────────────────────

def fetch_playlist_info(playlist_url: str) -> dict:
    """
    Use yt-dlp --flat-playlist to get the list of video IDs and titles without
    downloading anything.  Returns a dict with keys: title, entries.
    """
    import json as _json
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--quiet",
        playlist_url,
    ]
    logger.info("Fetching playlist metadata (this may take a moment)…")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{result.stderr}")
    return _json.loads(result.stdout)


# ── Single-episode download ────────────────────────────────────────────────────

def download_episode(video_id: str, output_template: str) -> bool:
    """
    Download audio + sidecar subtitles for a single video.
    Returns True on success, False on failure.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--extract-audio",
        "--audio-format", AUDIO_FORMAT,
        "--audio-quality", AUDIO_QUALITY,
        # Subtitles — try manual captions first, fall back to auto-generated
        "--write-sub",
        "--write-auto-sub",
        "--sub-lang", "en",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        # Output naming
        "-o", output_template,
        "--no-playlist",
        "--quiet",
        "--progress",
        url,
    ]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = subprocess.run(cmd, timeout=600)
            if result.returncode == 0:
                return True
            logger.warning(
                "yt-dlp returned code %d for %s (attempt %d/%d)",
                result.returncode, video_id, attempt, MAX_RETRIES,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Download timed out for %s (attempt %d/%d)", video_id, attempt, MAX_RETRIES)
        except Exception as exc:
            logger.warning("Unexpected error for %s: %s (attempt %d/%d)", video_id, exc, attempt, MAX_RETRIES)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    return False


# ── VTT sidecar detection ──────────────────────────────────────────────────────

def find_subtitle_file(stem: str) -> Path | None:
    """
    yt-dlp may write the subtitle as <stem>.en.vtt or <stem>.en-US.vtt etc.
    Try common variants and return the first that exists.
    """
    for suffix in (".en.vtt", ".en-US.vtt", ".en-GB.vtt"):
        candidate = AUDIO_DIR / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not PLAYLIST_URL:
        logger.error("PLAYLIST_URL is not set. Add it to your .env file.")
        sys.exit(1)

    # Load (or initialise) metadata
    data = mm.load()
    data["playlist_url"] = PLAYLIST_URL

    # ── Fetch playlist info ───────────────────────────────────────────────────
    playlist_info = fetch_playlist_info(PLAYLIST_URL)
    playlist_title = playlist_info.get("title", "YouTube Playlist")
    entries        = playlist_info.get("entries", [])

    if not entries:
        logger.error("Playlist returned no entries. Check the URL and try again.")
        sys.exit(1)

    data["playlist_title"] = playlist_title
    logger.info("Playlist: %s — %d episodes", playlist_title, len(entries))

    # ── Populate metadata for any new episodes ────────────────────────────────
    for idx, entry in enumerate(entries, start=1):
        video_id = entry.get("id") or entry.get("url", "").split("v=")[-1]
        title    = entry.get("title", f"Episode {idx}")
        url      = f"https://www.youtube.com/watch?v={video_id}"

        if mm.get_episode(data, video_id) is None:
            ep = mm.new_episode(idx, video_id, title, url, entry.get("duration", 0))
            # Set the concrete audio file path (format known at this point)
            stem = mm.episode_stem(idx, title)
            ep["audio_file"] = f"audio/{stem}.{AUDIO_FORMAT}"
            mm.upsert_episode(data, ep)

    mm.save(data)

    # ── Download loop ─────────────────────────────────────────────────────────
    to_download = [ep for ep in data["episodes"] if not ep["status"]["audio_downloaded"]]
    logger.info("%d episode(s) to download (skipping %d already done)",
                len(to_download), len(data["episodes"]) - len(to_download))

    for ep in tqdm(to_download, desc="Downloading", unit="ep"):
        video_id = ep["video_id"]
        stem     = mm.episode_stem(ep["episode_number"], ep["title"])

        # yt-dlp output template — no extension; it adds the right one
        output_template = str(AUDIO_DIR / stem) + ".%(ext)s"

        logger.info("[%03d] Downloading: %s", ep["episode_number"], ep["title"])
        success = download_episode(video_id, output_template)

        # Reload to avoid overwriting changes from a concurrent run (defensive)
        data = mm.load()
        ep   = mm.get_episode(data, video_id)

        if success:
            audio_path = AUDIO_DIR / f"{stem}.{AUDIO_FORMAT}"
            ep["audio_file"] = str(audio_path.relative_to(Path(__file__).parent))

            sub = find_subtitle_file(stem)
            if sub:
                ep["subtitle_file"] = str(sub.relative_to(Path(__file__).parent))
                logger.info("  ↳ subtitle sidecar found: %s", sub.name)

            ep["status"]["audio_downloaded"] = True
        else:
            mm.add_error(data, video_id, "Audio download failed after retries")
            logger.error("[%03d] FAILED: %s", ep["episode_number"], ep["title"])

        mm.save(data)

    downloaded = sum(1 for ep in data["episodes"] if ep["status"]["audio_downloaded"])
    logger.info("Done. %d/%d episodes have audio.", downloaded, len(data["episodes"]))


if __name__ == "__main__":
    main()
