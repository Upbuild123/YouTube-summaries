#!/usr/bin/env python3
"""
pipeline.py — fully self-contained YouTube playlist → Google Doc pipeline.
No imports from config.py or metadata_manager.py required.

Usage (via run.sh — recommended)
---------------------------------
  ./run.sh                # setup + run all steps
  ./run.sh --step 2       # setup + run only step 2
  ./run.sh --list         # show per-episode progress

Usage (direct, venv already active)
-------------------------------------
  python pipeline.py              # all steps
  python pipeline.py --step 2
  python pipeline.py --steps 1,3
  python pipeline.py --steps 2-4
  python pipeline.py --list
"""

# Enables X | Y union syntax for type hints on Python 3.9
from __future__ import annotations

# ── Stdlib-only imports (safe before venv check) ──────────────────────────────
import argparse
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# .ENV LOADER  (no python-dotenv needed)
# ══════════════════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent

def _load_env() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

_load_env()

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG  (edit these constants to change behaviour)
# ══════════════════════════════════════════════════════════════════════════════

# Directories
AUDIO_DIR        = BASE_DIR / "audio"
TRANSCRIPTS_DIR  = BASE_DIR / "transcripts"
DESCRIPTIONS_DIR = BASE_DIR / "descriptions"
LOGS_DIR         = BASE_DIR / "logs"
CREDENTIALS_DIR  = BASE_DIR / "credentials"
METADATA_FILE    = BASE_DIR / "metadata.json"
LOG_FILE         = LOGS_DIR / "pipeline.log"

for _d in (AUDIO_DIR, TRANSCRIPTS_DIR, DESCRIPTIONS_DIR, LOGS_DIR, CREDENTIALS_DIR):
    _d.mkdir(exist_ok=True)

# API keys (loaded from .env)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")   # no longer used
PLAYLIST_URL   = os.getenv("PLAYLIST_URL", "")

# Browser to pull cookies from so yt-dlp can bypass YouTube's 403 / PO-token
# restriction.  Set to "chrome", "safari", "firefox", or "edge".
# Leave blank to skip (downloads may 403 on some videos).
BROWSER_FOR_COOKIES = os.getenv("BROWSER_FOR_COOKIES", "chrome")

# Google Docs OAuth
GOOGLE_CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"
GOOGLE_TOKEN_FILE       = CREDENTIALS_DIR / "token.json"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

# AI
OPENAI_DESCRIPTION_MODEL = "gpt-4o-mini"
DESCRIPTION_MAX_TOKENS   = 900
TRANSCRIPT_MAX_WORDS     = 3000   # words sent per episode (~10 min ≈ 1500 words)

# Audio
AUDIO_FORMAT  = "mp3"
AUDIO_QUALITY = "128"           # kbps

# Transcript
USE_OPENAI_WHISPER_FALLBACK = True   # set False to skip Whisper when no captions exist

# Reliability
MAX_RETRIES               = 3
RETRY_DELAY               = 5    # seconds between retries
GDOCS_INTER_EPISODE_DELAY = 0.4  # pause between Docs API calls (quota headroom)

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# METADATA  (tracks per-episode progress; written to metadata.json)
# ══════════════════════════════════════════════════════════════════════════════

_meta_lock = threading.Lock()

def _safe_filename(title: str, max_length: int = 80) -> str:
    safe = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    return re.sub(r"\s+", "_", safe.strip())[:max_length]

def _stem(num: int, title: str) -> str:
    return f"{num:03d}_{_safe_filename(title)}"

def _meta_load() -> dict:
    with _meta_lock:
        if not METADATA_FILE.exists():
            return {"playlist_title": "", "playlist_url": "", "google_doc_id": None, "episodes": []}
        with METADATA_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)

def _sanitize_strings(obj):
    """Recursively strip control characters from all string values before JSON serialisation."""
    if isinstance(obj, dict):
        return {k: _sanitize_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_strings(v) for v in obj]
    if isinstance(obj, str):
        # Remove control chars (0x00-0x1f) except \t \n \r which json.dumps handles fine
        import re as _re
        return _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', obj)
    return obj

def _meta_save(data: dict) -> None:
    with _meta_lock:
        tmp = METADATA_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(_sanitize_strings(data), fh, indent=2, ensure_ascii=False)
        tmp.replace(METADATA_FILE)

def _get_ep(data: dict, video_id: str) -> dict | None:
    return next((ep for ep in data["episodes"] if ep["video_id"] == video_id), None)

def _upsert_ep(data: dict, ep: dict) -> None:
    for i, e in enumerate(data["episodes"]):
        if e["video_id"] == ep["video_id"]:
            data["episodes"][i] = ep
            return
    data["episodes"].append(ep)

def _new_ep(num: int, video_id: str, title: str, url: str, duration: int = 0) -> dict:
    s = _stem(num, title)
    return {
        "episode_number":    num,
        "video_id":          video_id,
        "youtube_url":       url,
        "title":             title,
        "duration_seconds":  duration,
        "audio_file":        f"audio/{s}.{AUDIO_FORMAT}",
        "subtitle_file":     None,
        "transcript_file":   f"transcripts/{s}.txt",
        "description_file":  f"descriptions/{s}.txt",
        "description":       None,
        "transcript_source": None,
        "status": {
            "audio_downloaded":      False,
            "transcript_obtained":   False,
            "description_generated": False,
            "google_doc_updated":    False,
        },
        "errors": [],
    }

def _add_err(data: dict, video_id: str, msg: str) -> None:
    ep = _get_ep(data, video_id)
    if ep:
        ep["errors"].append(msg)
        logger.warning("[%s] %s", video_id, msg)

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — DOWNLOAD AUDIO
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_playlist_info(url: str) -> dict:
    cmd = [sys.executable, "-m", "yt_dlp",
           "--flat-playlist", "--dump-single-json", "--quiet",
           "--js-runtimes", "node", url]
    logger.info("Fetching playlist metadata…")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp playlist fetch failed:\n{r.stderr}")
    return json.loads(r.stdout)

def _download_audio(video_id: str, out_template: str) -> bool:
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--extract-audio",
        "--audio-format", AUDIO_FORMAT,
        "--audio-quality", AUDIO_QUALITY,
        "--write-sub", "--write-auto-sub",
        "--sub-lang", "en",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        # YouTube wraps stream URLs in a JS "n-challenge" that yt-dlp must solve
        # via an external runtime; without this, only thumbnails are reachable.
        # Requires Node.js >= 20 on PATH (and yt-dlp installed with [default]).
        "--js-runtimes", "node",
        "-o", out_template,
        "--no-playlist", "--quiet", "--progress",
        url,
    ]
    # Pass browser cookies so YouTube treats this as an authenticated request
    if BROWSER_FOR_COOKIES:
        cmd += ["--cookies-from-browser", BROWSER_FOR_COOKIES]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if subprocess.run(cmd, timeout=600).returncode == 0:
                return True
        except (subprocess.TimeoutExpired, Exception) as exc:
            logger.warning("Download attempt %d/%d failed for %s: %s", attempt, MAX_RETRIES, video_id, exc)
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
    return False

def _find_vtt(stem: str) -> Path | None:
    for sfx in (".en.vtt", ".en-US.vtt", ".en-GB.vtt"):
        p = AUDIO_DIR / f"{stem}{sfx}"
        if p.exists():
            return p
    return None

def step_download_audio() -> None:
    logger.info("━━━  STEP 1: DOWNLOAD AUDIO  ━━━")
    if not PLAYLIST_URL:
        logger.error("PLAYLIST_URL not set — add it to .env")
        sys.exit(1)

    data = _meta_load()
    data["playlist_url"] = PLAYLIST_URL
    info    = _fetch_playlist_info(PLAYLIST_URL)
    title   = info.get("title", "YouTube Playlist")
    entries = info.get("entries", [])
    if not entries:
        logger.error("Playlist returned no entries.")
        sys.exit(1)

    data["playlist_title"] = title
    logger.info("Playlist: %s — %d episodes", title, len(entries))

    for idx, entry in enumerate(entries, 1):
        vid = entry.get("id") or entry.get("url", "").split("v=")[-1]
        t   = entry.get("title", f"Episode {idx}")
        if _get_ep(data, vid) is None:
            _upsert_ep(data, _new_ep(idx, vid, t,
                                     f"https://www.youtube.com/watch?v={vid}",
                                     entry.get("duration", 0)))
    _meta_save(data)

    todo    = [ep for ep in data["episodes"] if not ep["status"]["audio_downloaded"]]
    done_ct = len(data["episodes"]) - len(todo)
    logger.info("%d to download, %d already done", len(todo), done_ct)

    for ep in todo:
        vid  = ep["video_id"]
        s    = _stem(ep["episode_number"], ep["title"])
        tmpl = str(AUDIO_DIR / s) + ".%(ext)s"
        logger.info("[%03d] %s", ep["episode_number"], ep["title"])

        ok = _download_audio(vid, tmpl)
        data = _meta_load()
        ep   = _get_ep(data, vid)

        if ok:
            ep["audio_file"] = f"audio/{s}.{AUDIO_FORMAT}"
            vtt = _find_vtt(s)
            if vtt:
                ep["subtitle_file"] = str(vtt.relative_to(BASE_DIR))
                logger.info("  ↳ subtitle sidecar: %s", vtt.name)
            ep["status"]["audio_downloaded"] = True
        else:
            _add_err(data, vid, "Audio download failed after retries")
            logger.error("  ↳ FAILED")
        _meta_save(data)

    data = _meta_load()
    n = sum(1 for ep in data["episodes"] if ep["status"]["audio_downloaded"])
    logger.info("Step 1 done — %d/%d have audio.\n", n, len(data["episodes"]))


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — GET TRANSCRIPTS
# ══════════════════════════════════════════════════════════════════════════════

def _parse_vtt(text: str) -> str:
    lines, out = text.replace("\r\n", "\n").split("\n"), []
    for line in lines:
        s = line.strip()
        if not s or s.startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        if re.match(r"^\d+$", s) or re.match(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->", s):
            continue
        clean = re.sub(r"<[^>]+>|\{[^}]*\}", "", s).strip()
        if clean and (not out or clean != out[-1]):
            out.append(clean)
    return " ".join(out)

def _transcript_youtube(video_id: str) -> str | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
    except ImportError:
        return None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            api   = YouTubeTranscriptApi()
            tlist = api.list(video_id)
            t = None
            for getter in (
                lambda: tlist.find_manually_created_transcript(["en"]),
                lambda: tlist.find_generated_transcript(["en"]),
            ):
                try: t = getter(); break
                except Exception: pass
            if t is None:
                for cand in tlist:
                    t = cand.translate("en") if cand.language_code != "en" else cand
                    break
            if t is None:
                return None
            segs = t.fetch()
            return " ".join(
                re.sub(r"\s+", " ", snip.text).strip()
                for snip in segs
                if not re.match(r"^\[.*\]$", snip.text.strip())
            )
        except (TranscriptsDisabled, NoTranscriptFound):
            return None
        except Exception as exc:
            logger.warning("YT transcript attempt %d/%d: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return None

def _transcript_vtt(subtitle_file: str | None) -> str | None:
    if not subtitle_file:
        return None
    p = BASE_DIR / subtitle_file
    return _parse_vtt(p.read_text(encoding="utf-8")) if p.exists() else None

def _transcript_whisper(audio_file: str) -> str | None:
    if not USE_OPENAI_WHISPER_FALLBACK or not OPENAI_API_KEY:
        return None
    p = BASE_DIR / audio_file
    if not p.exists() or p.stat().st_size / (1024 * 1024) > 24:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    client = OpenAI(api_key=OPENAI_API_KEY)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with p.open("rb") as fp:
                r = client.audio.transcriptions.create(model="whisper-1", file=fp, response_format="text")
            return r if isinstance(r, str) else r.text
        except Exception as exc:
            logger.warning("Whisper attempt %d/%d: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return None

def _clean_transcript(raw: str) -> str:
    text = re.sub(r"\[(?:Music|Applause|Laughter|Inaudible|music|applause)\]", "", raw, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip()

def step_get_transcripts() -> None:
    logger.info("━━━  STEP 2: GET TRANSCRIPTS  ━━━")
    data = _meta_load()
    todo = [ep for ep in data["episodes"]
            if ep["status"]["audio_downloaded"] and not ep["status"]["transcript_obtained"]]
    logger.info("%d to transcribe, %d already done",
                len(todo), sum(1 for ep in data["episodes"] if ep["status"]["transcript_obtained"]))

    for ep in todo:
        vid = ep["video_id"]
        logger.info("[%03d] %s", ep["episode_number"], ep["title"])

        transcript = source = None
        for fn, label in (
            (lambda: _transcript_youtube(vid),               "youtube_captions"),
            (lambda: _transcript_vtt(ep.get("subtitle_file")), "vtt_sidecar"),
            (lambda: _transcript_whisper(ep["audio_file"]),  "whisper_api"),
        ):
            transcript = fn()
            if transcript:
                source = label
                logger.info("  ↳ source: %s", label)
                break

        data = _meta_load()
        ep   = _get_ep(data, vid)
        if transcript:
            transcript = _clean_transcript(transcript)
            (BASE_DIR / ep["transcript_file"]).write_text(transcript, encoding="utf-8")
            ep["transcript_source"]             = source
            ep["status"]["transcript_obtained"] = True
            logger.info("  ↳ %d words", len(transcript.split()))
        else:
            _add_err(data, vid, "No transcript source available")
            logger.warning("  ↳ no transcript found")
        _meta_save(data)

    data = _meta_load()
    n = sum(1 for ep in data["episodes"] if ep["status"]["transcript_obtained"])
    logger.info("Step 2 done — %d/%d have transcripts.\n", n, len(data["episodes"]))


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — GENERATE DESCRIPTIONS  (GPT-4o-mini)
# ══════════════════════════════════════════════════════════════════════════════

# ── Prompt constants (exported so the Streamlit UI can display and edit them) ──
# Use <<<TITLE>>> and <<<EXCERPT>>> as substitution markers — no f-string escaping needed.

SYSTEM_PROMPT = (
    "You write clear, content-first summaries, descriptions, and titles for conversations, "
    "meetings, podcasts, workshops, playlists, and group discussions. You prioritize specificity, "
    "accuracy, and the actual substance of the discussion over promotional, dramatic, or overly "
    "polished language."
)

PROMPT_TEMPLATE = """\
Write a suggested title, a meeting/session description, and key quotes for the transcript below.

TITLE INSTRUCTIONS

* Always start with the episode or meeting number if one is present in the source title
* Preserve any exact series, program, or playlist name from the source title when relevant
* If the session belongs to a named series with a part number, use:
    {number}. {Series Name} Part {N}. {Descriptive Subtitle}
* If there is no clear series or part number, use:
    {number}. {Descriptive Subtitle}
    or simply:
    {Descriptive Subtitle}
* The descriptive subtitle should clearly name the actual topic, tension, question, or theme being explored
* Avoid dramatic, poetic, or overly abstract phrasing
* Prefer direct, searchable language over cleverness
* Keep titles concise but specific
* Examples:
    "42. Navigating Conflict in Leadership Teams"
    "18. Burnout, Ambition, and the Fear of Slowing Down"
    "Team Meeting Part 3. Feedback, Trust, and Difficult Conversations"

TERM CORRECTIONS

* Lightly clean obvious transcription mistakes, names, repeated words, and malformed phrases throughout the title, description, and quotes
* Preserve the natural language and terminology of the speakers
* Do not over-correct into overly formal language
* Keep common spellings and searchable wording unless a specialized term clearly requires correction
* Also apply these specific corrections:
    Jagadan Pandit / Jagadananda Pandit → Jagadananda Pandita
    Udava Gita → Uddhava Gita
    Mahamantra / Maha-mantra → Hare Krishna mantra
    namaparadha / namarada / nama aparadha → nama-aparadha
    nama abhasa / namabhasa → nama-abhasa
    sudhanam / sudhanama / suddha nama → suddha-nama
    pema → prema
    shreddha / shraddha / shradha → sraddha
    acharas / acharyas → acaryas
    Bhaktivinoda Thakur → Bhaktivinoda Thakura
    Haridas Takur / Haridas Thakur → Haridasa Thakura
    Sacinand Maharaj / Sachinand Maharaj → Sacinandana Swami

DESCRIPTION INSTRUCTIONS

* 4–8 sentences total
* There may be multiple speakers. Refer to people naturally by name if identifiable, or use phrases like:
    "the group explores," "the conversation turns to," "several participants reflect on," "the discussion examines," etc.
* Do NOT refer to "the speaker," "the presenter," or "the episode"
* Do NOT open with:
    "In this episode," "This episode," or "The episode"
* Strong openings name the actual topic, tension, or question directly:
    "The difficulty of giving honest feedback…",
    "A conversation about burnout and ambition…",
    "The group explores what happens when…"
* Descriptions should feel specific to this conversation, not interchangeable with any other meeting
* Capture the real texture of the discussion:
    disagreements, uncertainty, vulnerability, humor, conflict, practical challenges, changing perspectives, etc.
* Include concrete themes, distinctions, frameworks, stories, or questions that came up
* Structure:
    open with the main topic or tension →
    describe 2–4 specific movements or ideas from the conversation →
    end with a grounded observation or unresolved question
* Neutral but human. Clear but not corporate.
* Avoid generic AI-summary phrasing such as:
    "ultimately," "highlights," "emphasizes," "powerful," "transformative," "insightful," "deep dive," "thought-provoking"
* Avoid vague abstractions unless they are explicitly central to the discussion
* Do not end with a call to action

QUOTES INSTRUCTIONS

* Select the 5–10 strongest quotes from the conversation
* Prioritize quotes that are:
    memorable,
    emotionally honest,
    intellectually sharp,
    funny,
    tension-filled,
    practical,
    revealing,
    or uniquely phrased
* Quotes should usually be short and self-contained
* Lightly clean spoken artifacts:
    remove filler words, false starts, repeated phrases, and transcription noise
* Preserve the speaker's voice and natural phrasing
* If multiple speakers are identifiable, attribute quotes when helpful:
    - "Name: [quote]"
* Do NOT include long rambling excerpts unless the language is especially strong
* Avoid quotes that depend heavily on missing context
* Goal: capture the strongest original observations and moments from the conversation

OUTPUT FORMAT (use exactly this structure):

TITLE
[suggested title here]

DESCRIPTION
[your 4–8 sentence description here]

QUOTES

- "[quote 1]"
- "[quote 2]"
- "[quote 3]"
(continue for all quotes)

Source title: <<<TITLE>>>

Transcript:
---
<<<EXCERPT>>>
---"""

# Internal aliases kept for backward compatibility
_SYS = SYSTEM_PROMPT

def _desc_prompt(title: str, excerpt: str, template: str = PROMPT_TEMPLATE) -> str:
    return template.replace("<<<TITLE>>>", title).replace("<<<EXCERPT>>>", excerpt)

def _truncate(text: str) -> str:
    words = text.split()
    return text if len(words) <= TRANSCRIPT_MAX_WORDS else " ".join(words[:TRANSCRIPT_MAX_WORDS]) + " [...]"

def _generate_description(
    title: str,
    transcript: str,
    system_prompt: str = SYSTEM_PROMPT,
    prompt_template: str = PROMPT_TEMPLATE,
) -> str | None:
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package missing — run: pip install openai")
        sys.exit(1)

    client = OpenAI(api_key=OPENAI_API_KEY)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=OPENAI_DESCRIPTION_MODEL,
                max_tokens=DESCRIPTION_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": _desc_prompt(title, _truncate(transcript), prompt_template)},
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning("OpenAI attempt %d/%d: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return None

def step_generate_descriptions() -> None:
    logger.info("━━━  STEP 3: GENERATE DESCRIPTIONS  ━━━")
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set — add it to .env")
        sys.exit(1)

    data = _meta_load()
    todo = [ep for ep in data["episodes"]
            if ep["status"]["transcript_obtained"] and not ep["status"]["description_generated"]]
    logger.info("%d to describe, %d already done",
                len(todo), sum(1 for ep in data["episodes"] if ep["status"]["description_generated"]))

    for ep in todo:
        vid = ep["video_id"]
        logger.info("[%03d] %s", ep["episode_number"], ep["title"])

        t_path = BASE_DIR / ep["transcript_file"]
        if not t_path.exists():
            logger.warning("  ↳ transcript file missing — skipping")
            continue

        desc = _generate_description(ep["title"], t_path.read_text(encoding="utf-8"))

        data = _meta_load()
        ep   = _get_ep(data, vid)
        if desc:
            (BASE_DIR / ep["description_file"]).write_text(desc, encoding="utf-8")
            ep["description"]                     = desc
            ep["status"]["description_generated"] = True
            logger.info("  ↳ %d chars", len(desc))
        else:
            _add_err(data, vid, "Description generation failed")
            logger.error("  ↳ FAILED")
        _meta_save(data)

    data = _meta_load()
    n = sum(1 for ep in data["episodes"] if ep["status"]["description_generated"])
    logger.info("Step 3 done — %d/%d have descriptions.\n", n, len(data["episodes"]))


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — WRITE GOOGLE DOC
# ══════════════════════════════════════════════════════════════════════════════

def _google_service():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        logger.error("Google packages missing — run setup again")
        sys.exit(1)

    if not GOOGLE_CREDENTIALS_FILE.exists():
        logger.error(
            "credentials/credentials.json not found.\n"
            "See README.md → 'Set up Google Docs API credentials'."
        )
        sys.exit(1)

    creds = None
    if GOOGLE_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_FILE), GOOGLE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CREDENTIALS_FILE), GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)
        GOOGLE_TOKEN_FILE.write_text(creds.to_json())
    return build("docs", "v1", credentials=creds)

def _doc_end(service, doc_id: str) -> int:
    doc = service.documents().get(documentId=doc_id).execute()
    content = doc.get("body", {}).get("content", [])
    return content[-1]["startIndex"] if len(content) >= 2 else 1

def _parse_suggested_title(content: str) -> str:
    """Extract the line after the TITLE label (handles plain or **bold** markdown)."""
    m = re.search(r'^\*{0,2}TITLE\*{0,2}[ \t]*\n(.+)', content, re.MULTILINE)
    return m.group(1).strip() if m else ""

def _strip_title_block(content: str) -> str:
    """Remove the TITLE block and normalize any **bold** markdown on section labels."""
    out = re.sub(r'^\*{0,2}TITLE\*{0,2}[ \t]*\n.+\n?', '', content, flags=re.MULTILINE)
    out = re.sub(r'^\*{0,2}(DESCRIPTION|QUOTES)\*{0,2}', r'\1', out, flags=re.MULTILINE)
    return out.strip()

_CALIBRI_BOLD   = {"weightedFontFamily": {"fontFamily": "Calibri", "weight": 400},
                   "fontSize": {"magnitude": 11, "unit": "PT"}, "bold": True}
_CALIBRI_NORMAL = {"weightedFontFamily": {"fontFamily": "Calibri", "weight": 400},
                   "fontSize": {"magnitude": 11, "unit": "PT"}, "bold": False}
_FONT_FIELDS    = "bold,weightedFontFamily,fontSize"

def _ep_requests(ep: dict, at: int) -> list[dict]:
    raw        = ep["description"]
    title_text = _parse_suggested_title(raw) or ep["title"]
    body_text  = _strip_title_block(raw)

    heading  = f"{title_text}\n"
    body     = f"{body_text}\n\n"
    h_end    = at + len(heading)
    b_end    = h_end + len(body)

    return [
        {"insertText": {"location": {"index": at}, "text": heading + body}},
        # Heading 1 paragraph style for document outline
        {"updateParagraphStyle": {
            "range": {"startIndex": at, "endIndex": h_end},
            "paragraphStyle": {"namedStyleType": "HEADING_1"},
            "fields": "namedStyleType",
        }},
        # Body: normal paragraph style
        {"updateParagraphStyle": {
            "range": {"startIndex": h_end, "endIndex": b_end},
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "fields": "namedStyleType",
        }},
        # Title text: Calibri 11pt bold
        {"updateTextStyle": {
            "range": {"startIndex": at, "endIndex": h_end - 1},
            "textStyle": _CALIBRI_BOLD,
            "fields": _FONT_FIELDS,
        }},
        # Body text: Calibri 11pt not bold
        {"updateTextStyle": {
            "range": {"startIndex": h_end, "endIndex": b_end - 1},
            "textStyle": _CALIBRI_NORMAL,
            "fields": _FONT_FIELDS,
        }},
    ]

def _batch_update(service, doc_id: str, reqs: list[dict]) -> bool:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            service.documents().batchUpdate(documentId=doc_id, body={"requests": reqs}).execute()
            return True
        except Exception as exc:
            logger.warning("Docs API attempt %d/%d: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return False

def step_write_google_doc() -> None:
    logger.info("━━━  STEP 4: WRITE GOOGLE DOC  ━━━")
    data = _meta_load()
    if not data.get("playlist_title"):
        logger.error("No playlist data — run step 1 first.")
        sys.exit(1)

    svc    = _google_service()
    doc_id = data.get("google_doc_id")
    if doc_id:
        logger.info("Reusing Google Doc %s", doc_id)
    else:
        doc    = svc.documents().create(body={"title": data["playlist_title"]}).execute()
        doc_id = doc["documentId"]
        data["google_doc_id"] = doc_id
        _meta_save(data)
        logger.info("Created Google Doc '%s' (%s)", data["playlist_title"], doc_id)

    todo = [ep for ep in data["episodes"]
            if ep["status"]["description_generated"] and not ep["status"]["google_doc_updated"]]
    logger.info("%d to write, %d already done",
                len(todo), sum(1 for ep in data["episodes"] if ep["status"]["google_doc_updated"]))

    for ep in todo:
        vid  = ep["video_id"]
        desc = ep.get("description")
        if not desc:
            p = BASE_DIR / ep["description_file"]
            desc = p.read_text(encoding="utf-8").strip() if p.exists() else None
        if not desc:
            logger.warning("[%03d] no description — skipping", ep["episode_number"])
            continue
        ep["description"] = desc
        logger.info("[%03d] %s", ep["episode_number"], ep["title"])

        reqs = _ep_requests(ep, _doc_end(svc, doc_id))
        ok   = _batch_update(svc, doc_id, reqs)

        data = _meta_load()
        ep   = _get_ep(data, vid)
        if ok:
            ep["status"]["google_doc_updated"] = True
        else:
            _add_err(data, vid, "Google Doc write failed")
            logger.error("  ↳ FAILED")
        _meta_save(data)
        time.sleep(GDOCS_INTER_EPISODE_DELAY)

    data  = _meta_load()
    done  = sum(1 for ep in data["episodes"] if ep["status"]["google_doc_updated"])
    ready = sum(1 for ep in data["episodes"] if ep["status"]["description_generated"])
    logger.info("Step 4 done — %d/%d written to doc.", done, ready)
    logger.info("View: https://docs.google.com/document/d/%s/edit\n", doc_id)


# ══════════════════════════════════════════════════════════════════════════════
# PROGRESS TABLE
# ══════════════════════════════════════════════════════════════════════════════

def show_progress() -> None:
    data = _meta_load()
    if not data["episodes"]:
        print("No episodes yet. Run step 1 to fetch the playlist.")
        return
    cols = ("audio_downloaded", "transcript_obtained", "description_generated", "google_doc_updated")
    hdr  = f"{'#':>4}  {'Title':<52}  DL  TR  DS  GD  Errors"
    print(hdr)
    print("─" * len(hdr))
    for ep in data["episodes"]:
        s      = ep["status"]
        flags  = "   ".join("✓" if s[c] else "·" for c in cols)
        errs   = f"  ⚠ {len(ep['errors'])}" if ep["errors"] else ""
        title  = ep["title"][:52]
        print(f"{ep['episode_number']:>4}  {title:<52}  {flags}{errs}")
    totals = {c: sum(1 for ep in data["episodes"] if ep["status"][c]) for c in cols}
    n = len(data["episodes"])
    print("─" * len(hdr))
    print(f"     {'TOTAL':<52}  " + "   ".join(f"{totals[c]}/{n}" for c in cols))


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

STEPS = {
    1: ("Download audio",        step_download_audio),
    2: ("Get transcripts",       step_get_transcripts),
    3: ("Generate descriptions", step_generate_descriptions),
    4: ("Write Google Doc",      step_write_google_doc),
}

def _parse_steps(value: str) -> list[int]:
    result = []
    for part in value.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            result.extend(range(int(lo), int(hi) + 1))
        else:
            result.append(int(part))
    return sorted(set(result))

def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube playlist → Google Doc pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python pipeline.py              # run all steps\n"
            "  python pipeline.py --step 2     # run only step 2\n"
            "  python pipeline.py --steps 1,3  # steps 1 and 3\n"
            "  python pipeline.py --steps 2-4  # steps 2 through 4\n"
            "  python pipeline.py --list       # show progress table\n"
            "  python pipeline.py --url https://www.youtube.com/watch?v=XYZ  # single video\n"
        ),
    )
    parser.add_argument("--url", type=str, metavar="URL",
                        help="YouTube playlist or video URL (overrides PLAYLIST_URL in .env)")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--step",  type=int, metavar="N",    help="Run a single step (1-4)")
    g.add_argument("--steps", type=str, metavar="LIST", help="Run steps e.g. '1,3' or '2-4'")
    g.add_argument("--list",  action="store_true",      help="Show per-episode progress")
    args = parser.parse_args()

    if args.url:
        global PLAYLIST_URL
        PLAYLIST_URL = args.url

    if args.list:
        show_progress()
        return

    step_nums = (
        [args.step]            if args.step  else
        _parse_steps(args.steps) if args.steps else
        list(STEPS.keys())
    )

    bad = [n for n in step_nums if n not in STEPS]
    if bad:
        logger.error("Unknown step(s): %s  (valid: 1-4)", bad)
        sys.exit(1)

    failed: list[str] = []
    t0 = time.time()

    for n in step_nums:
        label, fn = STEPS[n]
        t1 = time.time()
        try:
            fn()
            logger.info("Step %d finished in %.1fs", n, time.time() - t1)
        except SystemExit:
            raise
        except Exception as exc:
            logger.exception("Step %d (%s) crashed: %s", n, label, exc)
            failed.append(f"Step {n}: {label}")
            logger.warning("Continuing with next step (pipeline is resumable).")

    logger.info("━━━  Finished in %.1fs  ━━━", time.time() - t0)
    if failed:
        for f in failed:
            logger.warning("  FAILED — %s", f)
        logger.info("Fix errors and re-run — completed work is skipped automatically.")
        sys.exit(1)

if __name__ == "__main__":
    main()
