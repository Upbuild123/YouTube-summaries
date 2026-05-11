#!/usr/bin/env python3
"""
Step 2 — Obtain a plain-text transcript for each downloaded episode.

Strategy (in order):
  1. youtube-transcript-api  — fetches captions directly from YouTube (no audio needed)
  2. VTT sidecar file        — parse the .vtt downloaded by yt-dlp in step 1
  3. OpenAI Whisper API      — sends the MP3 to OpenAI for transcription (paid fallback)

Resumable: episodes already marked transcript_obtained=true are skipped.

Outputs
-------
transcripts/<NNN>_<title>.txt   — plain-text transcript
metadata.json                   — updated with file path, source, and status
"""

import logging
import re
import sys
import time
from pathlib import Path

from tqdm import tqdm

import metadata_manager as mm
from config import (
    LOG_FILE, MAX_RETRIES, OPENAI_API_KEY, RETRY_DELAY,
    TRANSCRIPTS_DIR, USE_OPENAI_WHISPER_FALLBACK,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent


# ── VTT parser ────────────────────────────────────────────────────────────────

def parse_vtt(vtt_text: str) -> str:
    """
    Convert a WebVTT string to clean, deduplicated plain text.
    YouTube auto-captions repeat lines across overlapping cue windows, so we
    deduplicate consecutive identical lines after stripping cue headers and tags.
    """
    lines = vtt_text.replace("\r\n", "\n").split("\n")
    text_lines: list[str] = []
    skip_next = False

    for line in lines:
        stripped = line.strip()

        # Skip WEBVTT header, NOTE blocks, STYLE blocks, empty lines
        if not stripped or stripped.startswith("WEBVTT") or stripped.startswith("NOTE") \
                or stripped.startswith("STYLE") or stripped.startswith("REGION"):
            skip_next = False
            continue

        # Skip cue numeric identifiers ("1", "2", …)
        if re.match(r"^\d+$", stripped):
            continue

        # Skip timestamp lines (e.g. "00:00:01.000 --> 00:00:04.000 ...")
        if re.match(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->", stripped):
            skip_next = False
            continue

        # Remove inline tags like <00:00:01.000>, <c>, </c>
        clean = re.sub(r"<[^>]+>", "", stripped)
        # Remove VTT positioning markup like {\\an8}
        clean = re.sub(r"\{[^}]*\}", "", clean).strip()

        if not clean:
            continue

        # Deduplicate consecutive identical lines
        if text_lines and clean == text_lines[-1]:
            continue

        text_lines.append(clean)

    return " ".join(text_lines)


# ── Transcript source 1: youtube-transcript-api ───────────────────────────────

def get_youtube_transcript(video_id: str) -> str | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
    except ImportError:
        logger.warning("youtube-transcript-api not installed — skipping")
        return None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Prefer manually created en transcript; fall back to auto-generated
            transcript = None
            try:
                transcript = transcript_list.find_manually_created_transcript(["en"])
            except Exception:
                pass
            if transcript is None:
                try:
                    transcript = transcript_list.find_generated_transcript(["en"])
                except Exception:
                    pass
            if transcript is None:
                # Try any available transcript and translate to English
                for t in transcript_list:
                    transcript = t.translate("en") if t.language_code != "en" else t
                    break

            if transcript is None:
                return None

            segments = transcript.fetch()
            # Deduplicate and join
            words: list[str] = []
            for seg in segments:
                text = re.sub(r"\s+", " ", seg["text"]).strip()
                # Skip music/noise markers
                if re.match(r"^\[.*\]$", text):
                    continue
                words.append(text)

            return " ".join(words)

        except (TranscriptsDisabled, NoTranscriptFound):
            return None
        except Exception as exc:
            logger.warning("youtube-transcript-api attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    return None


# ── Transcript source 2: VTT sidecar file ────────────────────────────────────

def get_vtt_transcript(subtitle_file: str | None) -> str | None:
    if not subtitle_file:
        return None
    path = BASE_DIR / subtitle_file
    if not path.exists():
        return None
    try:
        return parse_vtt(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse VTT %s: %s", path, exc)
        return None


# ── Transcript source 3: OpenAI Whisper API ───────────────────────────────────

def get_whisper_transcript(audio_file: str) -> str | None:
    if not USE_OPENAI_WHISPER_FALLBACK:
        return None
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — cannot use Whisper fallback")
        return None

    path = BASE_DIR / audio_file
    if not path.exists():
        logger.warning("Audio file not found for Whisper: %s", path)
        return None

    # OpenAI Whisper API has a 25 MB file size limit
    file_size_mb = path.stat().st_size / (1024 * 1024)
    if file_size_mb > 24:
        logger.warning(
            "Audio file %.1f MB exceeds Whisper 25 MB limit: %s", file_size_mb, path.name
        )
        return None

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed — cannot use Whisper")
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("  ↳ Sending to Whisper API (%.1f MB)…", file_size_mb)
            with path.open("rb") as audio_fp:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_fp,
                    response_format="text",
                )
            return response if isinstance(response, str) else response.text
        except Exception as exc:
            logger.warning("Whisper attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    return None


# ── Transcript cleaning ────────────────────────────────────────────────────────

def clean_transcript(raw: str) -> str:
    """Collapse whitespace and remove common noise markers."""
    text = re.sub(r"\[(?:Music|Applause|Laughter|Inaudible|music|applause)\]", "", raw, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    data = mm.load()

    to_process = [
        ep for ep in data["episodes"]
        if ep["status"]["audio_downloaded"] and not ep["status"]["transcript_obtained"]
    ]

    skipped = sum(1 for ep in data["episodes"] if ep["status"]["transcript_obtained"])
    logger.info(
        "%d episode(s) need transcripts (skipping %d already done)",
        len(to_process), skipped,
    )

    for ep in tqdm(to_process, desc="Transcripts", unit="ep"):
        video_id = ep["video_id"]
        logger.info("[%03d] Transcribing: %s", ep["episode_number"], ep["title"])

        transcript: str | None = None
        source: str | None = None

        # 1. YouTube captions
        transcript = get_youtube_transcript(video_id)
        if transcript:
            source = "youtube_captions"
            logger.info("  ↳ Got YouTube captions")

        # 2. VTT sidecar
        if transcript is None:
            transcript = get_vtt_transcript(ep.get("subtitle_file"))
            if transcript:
                source = "vtt_sidecar"
                logger.info("  ↳ Parsed VTT sidecar")

        # 3. Whisper API
        if transcript is None:
            transcript = get_whisper_transcript(ep["audio_file"])
            if transcript:
                source = "whisper_api"
                logger.info("  ↳ Transcribed via Whisper")

        # ── Save or record failure ────────────────────────────────────────────
        data = mm.load()
        ep   = mm.get_episode(data, video_id)

        if transcript:
            transcript = clean_transcript(transcript)
            out_path = BASE_DIR / ep["transcript_file"]
            out_path.write_text(transcript, encoding="utf-8")

            ep["transcript_source"] = source
            ep["status"]["transcript_obtained"] = True
            logger.info("  ↳ Saved %d words", len(transcript.split()))
        else:
            mm.add_error(data, video_id, "No transcript source available")
            logger.warning("[%03d] No transcript available for: %s", ep["episode_number"], ep["title"])

        mm.save(data)

    done = sum(1 for ep in data["episodes"] if ep["status"]["transcript_obtained"])
    logger.info("Done. %d/%d episodes have transcripts.", done, len(data["episodes"]))


if __name__ == "__main__":
    main()
