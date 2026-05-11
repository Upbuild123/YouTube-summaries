#!/usr/bin/env python3
"""
Step 3 — Generate a 2-5 sentence SEO-optimised podcast description for each
episode using the Claude API.

Resumable: episodes already marked description_generated=true are skipped.

Outputs
-------
descriptions/<NNN>_<title>.txt   — plain-text description
metadata.json                    — updated with description text + status
"""

import logging
import sys
import time
from pathlib import Path

from tqdm import tqdm

import metadata_manager as mm
from config import (
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL, DESCRIPTION_MAX_TOKENS,
    LOG_FILE, MAX_RETRIES, RETRY_DELAY, TRANSCRIPT_MAX_WORDS,
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


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert podcast content writer who specialises in
SEO-optimised show notes and episode descriptions. You write copy that ranks
well in search engines while sounding natural and engaging to human readers."""

def build_user_prompt(title: str, transcript_excerpt: str) -> str:
    return f"""Write a podcast episode description for the episode below.

Requirements:
- Exactly 2 to 5 sentences (no more, no less).
- Incorporate the most relevant SEO keywords and phrases from the transcript
  naturally — do NOT keyword-stuff; every keyword must fit the sentence.
- Accurately summarise the main topics, key insights, and takeaways.
- Sound professional and compelling — make the reader want to listen.
- Suitable for use as podcast show notes and on a podcast platform.

Episode title: {title}

Transcript excerpt:
---
{transcript_excerpt}
---

Write only the description. No preamble, no labels, no quotes around it."""


# ── Transcript truncation ─────────────────────────────────────────────────────

def truncate_transcript(text: str, max_words: int = TRANSCRIPT_MAX_WORDS) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + " [...]"


# ── Claude API call ───────────────────────────────────────────────────────────

def generate_description(title: str, transcript: str) -> str | None:
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)

    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    excerpt = truncate_transcript(transcript)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            message = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=DESCRIPTION_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": build_user_prompt(title, excerpt)}
                ],
            )
            return message.content[0].text.strip()

        except Exception as exc:
            logger.warning(
                "Claude API attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
        sys.exit(1)

    data = mm.load()

    to_process = [
        ep for ep in data["episodes"]
        if ep["status"]["transcript_obtained"] and not ep["status"]["description_generated"]
    ]
    skipped = sum(1 for ep in data["episodes"] if ep["status"]["description_generated"])
    logger.info(
        "%d episode(s) need descriptions (skipping %d already done)",
        len(to_process), skipped,
    )

    for ep in tqdm(to_process, desc="Descriptions", unit="ep"):
        video_id = ep["video_id"]
        logger.info("[%03d] Generating description: %s", ep["episode_number"], ep["title"])

        transcript_path = BASE_DIR / ep["transcript_file"]
        if not transcript_path.exists():
            logger.warning("  ↳ Transcript file missing — skipping")
            continue

        transcript = transcript_path.read_text(encoding="utf-8")
        description = generate_description(ep["title"], transcript)

        data = mm.load()
        ep   = mm.get_episode(data, video_id)

        if description:
            out_path = BASE_DIR / ep["description_file"]
            out_path.write_text(description, encoding="utf-8")

            ep["description"] = description
            ep["status"]["description_generated"] = True
            logger.info("  ↳ %d chars written", len(description))
        else:
            mm.add_error(data, video_id, "Description generation failed after retries")
            logger.error("[%03d] FAILED to generate description", ep["episode_number"])

        mm.save(data)

    done = sum(1 for ep in data["episodes"] if ep["status"]["description_generated"])
    logger.info("Done. %d/%d episodes have descriptions.", done, len(data["episodes"]))


if __name__ == "__main__":
    main()
