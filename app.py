#!/usr/bin/env python3
"""
app.py — Streamlit frontend for the podcast pipeline.

Run with:
    source venv/bin/activate
    streamlit run app.py
"""
from __future__ import annotations

import re
import sys
import time
from datetime import date
from pathlib import Path

import streamlit as st

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="YouTube Notes and Quotes",
    page_icon="🎙️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* Base */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
/* Hide Streamlit's default header bar */
[data-testid="stHeader"] { display: none !important; }
header { display: none !important; }

.block-container {
    padding-top: 2rem;
    padding-bottom: 4rem;
    max-width: 760px;
}

/* App background — deep dark */
.stApp {
    background-color: #0a0a0f;
}

/* Title */
h1 {
    font-size: 1.9rem !important;
    font-weight: 700 !important;
    background: linear-gradient(90deg, #a855f7, #d946ef);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.02em;
}

/* Subheadings */
h2, h3 {
    color: #e2d9f3 !important;
    font-weight: 600 !important;
}

/* Step labels */
.step-label {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #a855f7;
    background: rgba(168, 85, 247, 0.1);
    border: 1px solid rgba(168, 85, 247, 0.25);
    border-radius: 4px;
    padding: 0.15rem 0.55rem;
    margin-bottom: 0.5rem;
}

/* Divider */
hr {
    border-color: rgba(168, 85, 247, 0.15) !important;
    margin: 1.6rem 0 !important;
}

/* Primary buttons — purple */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7c3aed, #a855f7) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    padding: 0.55rem 1.2rem !important;
    transition: opacity 0.15s ease;
}
.stButton > button[kind="primary"]:hover { opacity: 0.88; }
.stButton > button[kind="primary"]:disabled { opacity: 0.35; }

/* Secondary buttons */
.stButton > button:not([kind="primary"]) {
    background: rgba(168, 85, 247, 0.08) !important;
    border: 1px solid rgba(168, 85, 247, 0.3) !important;
    color: #c4b5fd !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
}
.stButton > button:not([kind="primary"]):hover {
    background: rgba(168, 85, 247, 0.18) !important;
}

/* Text inputs */
.stTextInput > div > div > input {
    background: #12101a !important;
    border: 1px solid rgba(168, 85, 247, 0.3) !important;
    border-radius: 8px !important;
    color: #e2d9f3 !important;
    padding: 0.6rem 0.9rem !important;
}
.stTextInput > div > div > input:focus {
    border-color: #a855f7 !important;
    box-shadow: 0 0 0 2px rgba(168, 85, 247, 0.2) !important;
}

/* Text areas */
.stTextArea > div > div > textarea {
    background: #12101a !important;
    border: 1px solid rgba(168, 85, 247, 0.3) !important;
    border-radius: 8px !important;
    color: #e2d9f3 !important;
    font-family: 'Inter', monospace !important;
    font-size: 0.85rem !important;
}

/* Expanders */
.streamlit-expanderHeader {
    background: rgba(168, 85, 247, 0.06) !important;
    border: 1px solid rgba(168, 85, 247, 0.2) !important;
    border-radius: 8px !important;
    color: #c4b5fd !important;
    font-weight: 500 !important;
}

/* Metrics */
[data-testid="stMetricValue"] {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: #a855f7 !important;
}
[data-testid="stMetricLabel"] {
    color: #9ca3af !important;
    font-size: 0.8rem !important;
}

/* Episode rows */
.ep-row {
    display: flex;
    align-items: baseline;
    gap: 0.7rem;
    padding: 0.4rem 0;
    border-bottom: 1px solid rgba(168, 85, 247, 0.1);
    font-size: 0.88rem;
    color: #d1d5db;
}
.ep-num {
    font-weight: 700;
    min-width: 2.8rem;
    color: #a855f7;
}
.ep-date {
    color: #6b7280;
    font-size: 0.78rem;
    white-space: nowrap;
}

/* Result box */
.result-box {
    border-radius: 14px;
    border: 1px solid rgba(168, 85, 247, 0.4);
    background: linear-gradient(135deg, #1a0d2e 0%, #0f0a1e 100%);
    padding: 2rem 2.2rem;
    text-align: center;
    margin-top: 1.2rem;
    box-shadow: 0 0 40px rgba(168, 85, 247, 0.12);
}
.result-box h2 {
    background: linear-gradient(90deg, #a855f7, #d946ef);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 0.4rem 0;
    font-size: 1.4rem;
}
.result-box p { color: #9ca3af; margin: 0.2rem 0 1rem 0; }
.result-box a { color: #c4b5fd; font-size: 0.9rem; word-break: break-all; }
.result-box a:hover { color: #a855f7; }

/* Info / warning / error banners */
.stAlert {
    border-radius: 8px !important;
    border-left-width: 3px !important;
}

/* Radio buttons */
.stRadio > div { gap: 0.8rem; }

/* General body text */
p, li, span, label, .stMarkdown p {
    color: #d1d5db !important;
}

/* Captions / helper text */
.stCaption, [data-testid="stCaptionContainer"], small,
div[data-testid="stText"], .stCaption p {
    color: #a78bfa !important;
    font-size: 0.82rem !important;
}

/* Input labels */
.stTextInput label, .stTextArea label, .stSelectbox label,
.stMultiSelect label, .stDateInput label, .stRadio label {
    color: #c4b5fd !important;
    font-weight: 500 !important;
}

/* Checkbox labels */
.stCheckbox label, .stCheckbox span {
    color: #d1d5db !important;
}

/* Tab labels */
.stTabs [data-baseweb="tab"] {
    color: #9ca3af !important;
    font-weight: 500 !important;
}
.stTabs [aria-selected="true"] {
    color: #a855f7 !important;
    border-bottom-color: #a855f7 !important;
}

/* Multiselect — container */
.stMultiSelect [data-baseweb="select"] > div {
    background: #12101a !important;
    border: 1px solid rgba(168, 85, 247, 0.3) !important;
    border-radius: 8px !important;
}

/* Multiselect — selected tags */
.stMultiSelect [data-baseweb="tag"] {
    background: rgba(168, 85, 247, 0.25) !important;
    color: #e2d9f3 !important;
}
.stMultiSelect [data-baseweb="tag"] span { color: #e2d9f3 !important; }

/* Multiselect — input text */
.stMultiSelect input { color: #e2d9f3 !important; background: transparent !important; }

/* Multiselect — dropdown list */
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="popover"] ul {
    background: #1a1525 !important;
    border: 1px solid rgba(168, 85, 247, 0.25) !important;
    border-radius: 8px !important;
}

/* Multiselect — dropdown options */
[data-baseweb="popover"] li,
[data-baseweb="menu-item"] {
    background: #1a1525 !important;
    color: #e2d9f3 !important;
}
[data-baseweb="popover"] li:hover,
[data-baseweb="menu-item"]:hover {
    background: rgba(168, 85, 247, 0.2) !important;
    color: #fff !important;
}

/* Info / warning box text */
[data-testid="stNotification"] p,
[data-testid="stNotification"] { color: #e2d9f3 !important; }

/* Status / spinner text */
[data-testid="stStatusWidget"] p,
[data-testid="stStatusWidget"] span { color: #d1d5db !important; }

/* Code blocks */
.stCode pre, .stCode code, [data-testid="stCode"] pre, [data-testid="stCode"] code {
    background: #ffffff !important;
    color: #111111 !important;
}
[data-testid="stCode"] { background: #ffffff !important; }
</style>
""", unsafe_allow_html=True)

# ── Write Google credentials from Streamlit secrets (Streamlit Cloud only) ────
def _write_google_secrets() -> None:
    creds_dir = Path(__file__).parent / "credentials"
    creds_dir.mkdir(exist_ok=True)
    try:
        if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
            (creds_dir / "credentials.json").write_text(
                st.secrets["GOOGLE_CREDENTIALS_JSON"], encoding="utf-8"
            )
        if "GOOGLE_TOKEN_JSON" in st.secrets:
            (creds_dir / "token.json").write_text(
                st.secrets["GOOGLE_TOKEN_JSON"], encoding="utf-8"
            )
    except Exception:
        pass  # running locally without secrets — credentials managed manually

_write_google_secrets()

# ── Import pipeline ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
try:
    from pipeline import (
        _fetch_playlist_info,
        _download_audio, _find_vtt,
        _transcript_youtube, _transcript_vtt, _transcript_whisper, _clean_transcript,
        _generate_description,
        _google_service, _doc_end, _ep_requests, _batch_update,
        _meta_load, _meta_save, _get_ep, _upsert_ep, _new_ep, _stem,
        BASE_DIR, AUDIO_DIR, AUDIO_FORMAT,
        OPENAI_API_KEY, GOOGLE_CREDENTIALS_FILE,
        SYSTEM_PROMPT as _DEFAULT_SYSTEM_PROMPT,
        PROMPT_TEMPLATE as _DEFAULT_PROMPT_TEMPLATE,
    )
    _PIPELINE_OK  = True
    _PIPELINE_ERR = ""
except Exception as _err:
    _PIPELINE_OK  = False
    _PIPELINE_ERR = str(_err)

# ── Date helpers ───────────────────────────────────────────────────────────────
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"]
)}
_DATE_RE = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s*(\d{1,2}),?\s*(\d{4})",
    re.IGNORECASE,
)


def _parse_date(title: str) -> date | None:
    m = _DATE_RE.search(title)
    if not m:
        return None
    try:
        mon = _MONTHS[m.group(1).lower()[:3]]
        return date(int(m.group(3)), mon, int(m.group(2)))
    except (KeyError, ValueError):
        return None


def _parse_ep_num(title: str) -> int | None:
    m = re.search(r"Morning Rounds\s*-\s*(\d+)", title)
    return int(m.group(1)) if m else None


def _extract_doc_id(url_or_id: str) -> str:
    """Extract a Google Doc ID from a full URL or return the string as-is."""
    m = re.search(r"/document/d/([a-zA-Z0-9_-]+)", url_or_id)
    return m.group(1) if m else url_or_id.strip()


def _is_playlist_url(url: str) -> bool:
    """
    Return True only for pure playlist URLs.
    A URL with watch?v= or youtu.be/ is always treated as a single video,
    even if it also carries a list= parameter.
    """
    if "watch?v=" in url or "youtu.be/" in url:
        return False
    return "playlist" in url or "list=" in url


def _fetch_single_video(url: str) -> dict:
    """
    Fetch metadata for a single YouTube video and return it in the same
    shape as _fetch_playlist_info so the rest of the app needs no changes.
    """
    import json as _json
    import subprocess as _sp
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--dump-single-json",
        "--no-playlist",
        "--quiet",
        "--js-runtimes", "node",
        url,
    ]
    r = _sp.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{r.stderr}")
    info = _json.loads(r.stdout)
    # Wrap in a playlist-shaped dict with a single entry
    return {
        "title": info.get("title", "Single Episode"),
        "entries": [{
            "id":       info.get("id", ""),
            "title":    info.get("title", ""),
            "duration": info.get("duration", 0),
        }],
    }


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE RUNNER  (defined before UI so it is in scope when the button fires)
# ══════════════════════════════════════════════════════════════════════════════
def _run_pipeline(
    sel_entries: list[dict],
    all_entries: list[dict],
    pl_title: str,
    pl_url: str,
    existing_doc_id: str = "",
    system_prompt: str = "",
    prompt_template: str = "",
) -> None:
    """Run all four pipeline steps for the selected episodes, updating Streamlit UI."""

    # ── Initialise metadata ───────────────────────────────────────────────────
    data = _meta_load()
    data["playlist_title"] = pl_title
    data["playlist_url"]   = pl_url

    for idx, entry in enumerate(all_entries, 1):
        vid   = entry["id"]
        title = entry.get("title", f"Episode {idx}")
        url   = f"https://www.youtube.com/watch?v={vid}"
        if _get_ep(data, vid) is None:
            _upsert_ep(data, _new_ep(idx, vid, title, url, entry.get("duration", 0)))
    _meta_save(data)

    n = len(sel_entries)

    with st.status("Running pipeline…", expanded=True) as status:

        # ── Step 1: Download audio ────────────────────────────────────────────
        st.write("#### ⬇️  Step 1 — Download Audio")
        prog1 = st.progress(0.0)
        log1  = st.empty()

        for i, entry in enumerate(sel_entries):
            vid   = entry["id"]
            title = entry.get("title", "")
            data  = _meta_load()
            ep    = _get_ep(data, vid)
            s     = _stem(ep["episode_number"], title)

            prog1.progress(i / n, text=f"{i}/{n}")
            log1.caption(f"⬇️  {title[:70]}")

            if not ep["status"]["audio_downloaded"]:
                tmpl = str(AUDIO_DIR / s) + ".%(ext)s"
                ok   = _download_audio(vid, tmpl)
                data = _meta_load()
                ep   = _get_ep(data, vid)
                if ok:
                    ep["audio_file"] = f"audio/{s}.{AUDIO_FORMAT}"
                    vtt = _find_vtt(s)
                    if vtt:
                        ep["subtitle_file"] = str(vtt.relative_to(BASE_DIR))
                    ep["status"]["audio_downloaded"] = True
                else:
                    ep.setdefault("errors", []).append("Audio download failed")
                _meta_save(data)

            prog1.progress((i + 1) / n, text=f"{i + 1}/{n}")

        log1.empty()
        prog1.progress(1.0, text="Done")
        st.write("✅  Audio download complete")

        # ── Step 2: Transcripts ───────────────────────────────────────────────
        # Try YouTube captions first (no audio needed) for all episodes,
        # then fall back to VTT/Whisper only for those that have audio.
        st.write("#### 📝  Step 2 — Transcripts")
        data     = _meta_load()
        to_trans = [e for e in sel_entries
                    if not _get_ep(data, e["id"])["status"]["transcript_obtained"]]
        prog2 = st.progress(0.0)
        log2  = st.empty()
        nt    = len(to_trans)

        for i, entry in enumerate(to_trans):
            vid   = entry["id"]
            title = entry.get("title", "")
            data  = _meta_load()
            ep    = _get_ep(data, vid)

            prog2.progress(i / max(nt, 1), text=f"{i}/{nt}")
            log2.caption(f"📝  {title[:70]}")

            transcript = source = None

            # Always try YouTube captions first — works without audio
            transcript = _transcript_youtube(vid)
            if transcript:
                source = "youtube_captions"

            # VTT sidecar — only if audio was downloaded
            if not transcript and ep.get("subtitle_file"):
                transcript = _transcript_vtt(ep.get("subtitle_file"))
                if transcript:
                    source = "vtt_sidecar"

            # Whisper — only if audio was downloaded
            if not transcript and ep["status"].get("audio_downloaded") and ep.get("audio_file"):
                transcript = _transcript_whisper(ep["audio_file"])
                if transcript:
                    source = "whisper_api"

            data = _meta_load()
            ep   = _get_ep(data, vid)
            if transcript:
                transcript = _clean_transcript(transcript)
                (BASE_DIR / ep["transcript_file"]).write_text(transcript, encoding="utf-8")
                ep["transcript_source"]             = source
                ep["status"]["transcript_obtained"] = True
            else:
                ep.setdefault("errors", []).append("No transcript source available")
            _meta_save(data)

            prog2.progress((i + 1) / max(nt, 1), text=f"{i + 1}/{nt}")

        log2.empty()
        prog2.progress(1.0, text="Done")
        st.write("✅  Transcripts complete")

        # ── Step 3: Descriptions ──────────────────────────────────────────────
        st.write("#### 🤖  Step 3 — AI Descriptions")
        data    = _meta_load()
        screen_mode = existing_doc_id == "__screen__"

        # In screen mode always regenerate so the user gets fresh output
        if screen_mode:
            to_desc = [e for e in sel_entries
                       if _get_ep(data, e["id"])["status"]["transcript_obtained"]]
        else:
            to_desc = [e for e in sel_entries
                       if _get_ep(data, e["id"])["status"]["transcript_obtained"]
                       and not _get_ep(data, e["id"])["status"]["description_generated"]]

        prog3 = st.progress(0.0)
        log3  = st.empty()
        nd    = len(to_desc)

        if nd == 0:
            no_transcript = [e for e in sel_entries
                             if not _get_ep(data, e["id"])["status"]["transcript_obtained"]]
            if no_transcript:
                msg = f"No transcripts found for {len(no_transcript)} episode(s) — cannot generate descriptions. Check that audio was downloaded and captions are available."
                st.warning(f"⚠️  {msg}")
                st.session_state.pipeline_errors = [msg]
            else:
                st.info("All descriptions already generated — nothing to do.")

        desc_errors = []
        for i, entry in enumerate(to_desc):
            vid   = entry["id"]
            title = entry.get("title", "")
            data  = _meta_load()
            ep    = _get_ep(data, vid)

            prog3.progress(i / max(nd, 1), text=f"{i}/{nd}")
            log3.caption(f"🤖  {title[:70]}")

            t_path = BASE_DIR / ep["transcript_file"]
            if not t_path.exists():
                desc_errors.append(f"Transcript file missing for: {title[:60]}")
                continue

            try:
                desc = _generate_description(
                    title, t_path.read_text(encoding="utf-8"),
                    **({"system_prompt": system_prompt} if system_prompt else {}),
                    **({"prompt_template": prompt_template} if prompt_template else {}),
                )
            except Exception as exc:
                desc_errors.append(f"API error for '{title[:50]}': {exc}")
                desc = None

            data = _meta_load()
            ep   = _get_ep(data, vid)
            if desc:
                (BASE_DIR / ep["description_file"]).write_text(desc, encoding="utf-8")
                ep["description"]                     = desc
                ep["status"]["description_generated"] = True
            else:
                err_msg = f"Description generation returned empty for: {title[:60]}"
                ep.setdefault("errors", []).append(err_msg)
                if err_msg not in desc_errors:
                    desc_errors.append(err_msg)
            _meta_save(data)

            prog3.progress((i + 1) / max(nd, 1), text=f"{i + 1}/{nd}")

        log3.empty()
        prog3.progress(1.0, text="Done")
        for err in desc_errors:
            st.error(f"❌  {err}")
        if not desc_errors:
            st.write("✅  Descriptions complete")
        st.session_state.pipeline_errors = desc_errors

        # ── Step 4: Output ────────────────────────────────────────────────────
        data = _meta_load()

        if screen_mode:
            # Screen mode — collect descriptions and display in app
            st.write("#### 📋  Step 4 — Collecting results")
            data    = _meta_load()
            results = []
            for entry in sel_entries:
                ep   = _get_ep(data, entry["id"])
                desc = ep.get("description") or (
                    (BASE_DIR / ep["description_file"]).read_text(encoding="utf-8").strip()
                    if ep.get("description_file") and (BASE_DIR / ep["description_file"]).exists() else None
                )
                if desc:
                    results.append({"title": entry.get("title", ""), "description": desc})
            if not results:
                st.error("❌  No output was generated. Check that transcripts exist and the OpenAI API key is set correctly.")
            st.session_state.screen_results = results
            st.session_state.doc_url        = ""
            st.session_state.pipeline_done  = True
            status.update(label="✅  Pipeline complete!", state="complete")
            st.rerun()

        else:
            # Google Doc mode
            st.write("#### 📄  Step 4 — Google Doc")
            log4 = st.empty()
            log4.caption("Authenticating with Google…")
            svc  = _google_service()

            if existing_doc_id:
                doc_id = existing_doc_id
                data["google_doc_id"] = doc_id
                sel_ids = {e["id"] for e in sel_entries}
                for ep in data["episodes"]:
                    if ep["video_id"] in sel_ids:
                        ep["status"]["google_doc_updated"] = False
                _meta_save(data)
                log4.caption(f"Appending to existing doc {doc_id}…")
            else:
                data["google_doc_id"] = None
                sel_ids = {e["id"] for e in sel_entries}
                for ep in data["episodes"]:
                    if ep["video_id"] in sel_ids:
                        ep["status"]["google_doc_updated"] = False
                _meta_save(data)
                doc    = svc.documents().create(body={"title": pl_title}).execute()
                doc_id = doc["documentId"]
                data   = _meta_load()
                data["google_doc_id"] = doc_id
                _meta_save(data)
                log4.caption(f"Created new doc {doc_id}…")

            to_write = [e for e in sel_entries
                        if _get_ep(data, e["id"])["status"]["description_generated"]
                        and not _get_ep(data, e["id"])["status"]["google_doc_updated"]]
            prog4 = st.progress(0.0)
            nw    = len(to_write)

            for i, entry in enumerate(to_write):
                vid  = entry["id"]
                data = _meta_load()
                ep   = _get_ep(data, vid)
                desc = ep.get("description") or (
                    (BASE_DIR / ep["description_file"]).read_text(encoding="utf-8").strip()
                    if (BASE_DIR / ep["description_file"]).exists() else None
                )
                if not desc:
                    continue
                ep["description"] = desc
                log4.caption(f"📄  Writing: {entry.get('title', '')[:70]}")
                prog4.progress(i / max(nw, 1), text=f"{i}/{nw}")
                reqs = _ep_requests(ep, _doc_end(svc, doc_id))
                ok   = _batch_update(svc, doc_id, reqs)
                data = _meta_load()
                ep   = _get_ep(data, vid)
                if ok:
                    ep["status"]["google_doc_updated"] = True
                _meta_save(data)
                time.sleep(0.4)
                prog4.progress((i + 1) / max(nw, 1), text=f"{i + 1}/{nw}")

            log4.empty()
            prog4.progress(1.0, text="Done")
            st.write("✅  Google Doc written")

            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            st.session_state.doc_url       = doc_url
            st.session_state.pipeline_done = True
            status.update(label="✅  Pipeline complete!", state="complete")


# ── Session state defaults ─────────────────────────────────────────────────────
_DEFAULTS: dict = {
    "fetched":        False,
    "entries":        [],
    "pl_title":       "",
    "pl_url":         "",
    "selected_ids":   set(),
    "pipeline_done":  False,
    "doc_url":        "",
    "doc_mode":         "screen",    # "screen" | "new" | "existing"
    "existing_doc_url": "",
    "system_prompt":    None,        # None = use default from pipeline.py
    "prompt_template":  None,        # None = use default from pipeline.py
    "prompt_preset":    "Description and Quotes",
    "screen_results":   [],          # list of {title, description} for screen mode
    "pipeline_errors":  [],          # errors to show after rerun
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.title("🎙️ YouTube Notes and Quotes")
st.caption(
    "Fetch a YouTube playlist or single video · filter episodes · download audio · "
    "transcribe · generate AI descriptions · publish to Google Docs"
)
st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — PLAYLIST URL
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="step-label">Step 1 — Source</div>', unsafe_allow_html=True)
st.subheader("Enter a YouTube URL")
st.caption("Paste a playlist URL or a single video URL — both are supported.")

url_input = st.text_input(
    "YouTube URL",
    value=st.session_state.pl_url,
    placeholder="Playlist: youtube.com/playlist?list=PL…  or  Video: youtube.com/watch?v=…",
    label_visibility="collapsed",
)

if st.button("🔍  Fetch", type="primary", use_container_width=True):
    if not url_input.strip():
        st.error("Please enter a YouTube URL.")
    elif not _PIPELINE_OK:
        st.error(f"Pipeline import failed — check your venv: {_PIPELINE_ERR}")
    else:
        is_playlist = _is_playlist_url(url_input.strip())
        spinner_msg = "Fetching playlist from YouTube…" if is_playlist else "Fetching video from YouTube…"
        with st.spinner(spinner_msg):
            try:
                if is_playlist:
                    info = _fetch_playlist_info(url_input.strip())
                else:
                    info = _fetch_single_video(url_input.strip())
                entries = info.get("entries", [])
                for e in entries:
                    e["_date"]   = _parse_date(e.get("title", ""))
                    e["_ep_num"] = _parse_ep_num(e.get("title", ""))
                st.session_state.entries        = entries
                st.session_state.pl_title       = info.get("title", "Podcast")
                st.session_state.pl_url         = url_input.strip()
                st.session_state.fetched        = True
                all_ids = [e["id"] for e in entries]
                st.session_state.selected_ids   = set(all_ids)
                st.session_state.episode_picker = all_ids
                st.session_state.pipeline_done  = False
                st.session_state.doc_url        = ""
            except Exception as ex:
                st.error(f"Failed to fetch: {ex}")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — FILTER EPISODES  (skipped for single-video URLs)
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.fetched:
    entries = st.session_state.entries
    is_single = len(entries) == 1

    st.divider()

    if is_single:
        # Single video — show title and go straight to run
        st.markdown('<div class="step-label">Step 2 — Episode</div>', unsafe_allow_html=True)
        e = entries[0]
        d = e["_date"].strftime("%b %-d, %Y") if e["_date"] else ""
        st.subheader(e.get("title", ""))
        if d:
            st.caption(d)
    else:
        # Playlist — show full filter UI
        st.markdown('<div class="step-label">Step 2 — Filter</div>', unsafe_allow_html=True)
        st.subheader(st.session_state.pl_title)
        st.caption(f"{len(entries)} episodes found in playlist")

        tab_date, tab_pick = st.tabs(["📅  Date Range", "☑️  Pick Episodes"])

        # ── Tab: Date Range ──────────────────────────────────────────────────
        with tab_date:
            dated   = [e for e in entries if e["_date"]]
            undated = [e for e in entries if not e["_date"]]

            if not dated:
                st.warning(
                    "No episode dates could be parsed from the titles. "
                    "Try the **Pick Episodes** tab instead."
                )
            else:
                all_dates = [e["_date"] for e in dated]
                c1, c2 = st.columns(2)
                with c1:
                    d_from = st.date_input(
                        "From", value=min(all_dates),
                        min_value=min(all_dates), max_value=max(all_dates),
                        key="d_from",
                    )
                with c2:
                    d_to = st.date_input(
                        "To", value=max(all_dates),
                        min_value=min(all_dates), max_value=max(all_dates),
                        key="d_to",
                    )

                in_range = [e for e in dated if d_from <= e["_date"] <= d_to]

                include_undated = False
                if undated:
                    include_undated = st.checkbox(
                        f"Also include {len(undated)} episode(s) with no parseable date"
                    )

                matched = in_range + (undated if include_undated else [])

                if d_from > d_to:
                    st.error("'From' date must be before 'To' date.")
                else:
                    st.info(f"**{len(matched)} episode(s)** match this range.")
                    if st.button("✅  Apply Date Filter", type="primary"):
                        st.session_state.selected_ids = {e["id"] for e in matched}
                        st.success(f"{len(matched)} episodes selected.")

        # ── Tab: Pick Episodes ───────────────────────────────────────────────
        with tab_pick:
            ca, cb = st.columns(2)
            with ca:
                if st.button("Select All", use_container_width=True):
                    all_ids = [e["id"] for e in entries]
                    st.session_state.episode_picker = all_ids
                    st.session_state.selected_ids   = set(all_ids)
                    st.rerun()
            with cb:
                if st.button("Clear All", use_container_width=True):
                    st.session_state.episode_picker = []
                    st.session_state.selected_ids   = set()
                    st.rerun()

            id_label = {
                e["id"]: f"Ep {e['_ep_num'] or '?':>3}  ·  {e.get('title', e['id'])}"
                for e in entries
            }

            chosen = st.multiselect(
                "Search and select episodes",
                options=[e["id"] for e in entries],
                default=st.session_state.get("episode_picker", [e["id"] for e in entries]),
                format_func=lambda vid: id_label.get(vid, vid),
                placeholder="Type to search by title or episode number…",
                label_visibility="collapsed",
                key="episode_picker",
            )
            st.session_state.selected_ids = set(chosen)

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 3 — SUMMARY + RUN
    # ══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown('<div class="step-label">Step 3 — Run</div>', unsafe_allow_html=True)
    st.subheader("Review and run")

    n_sel  = len(st.session_state.selected_ids)
    n_tot  = len(entries)

    if not is_single:
        m1, m2, m3 = st.columns(3)
        m1.metric("Selected", n_sel)
        m2.metric("Total",    n_tot)
        m3.metric("Skipping", n_tot - n_sel)

    # Episode preview (playlist only — single video title already shown above)
    if n_sel and not is_single:
        sel_set     = st.session_state.selected_ids
        sel_entries = [e for e in entries if e["id"] in sel_set]

        with st.expander(f"Preview — {n_sel} selected episode(s)", expanded=False):
            rows = []
            for e in sel_entries:
                ep = e.get("_ep_num", "?")
                d  = e["_date"].strftime("%b %-d, %Y") if e["_date"] else "—"
                rows.append(
                    f'<div class="ep-row">'
                    f'<span class="ep-num">#{ep}</span>'
                    f'<span style="flex:1">{e.get("title","")}</span>'
                    f'<span class="ep-date">{d}</span>'
                    f"</div>"
                )
            st.markdown("".join(rows), unsafe_allow_html=True)

    # Prerequisites
    prereqs_ok = True
    if not _PIPELINE_OK:
        st.error(f"❌ Pipeline could not be loaded: {_PIPELINE_ERR}")
        prereqs_ok = False
    if _PIPELINE_OK and not OPENAI_API_KEY:
        st.error("❌ `OPENAI_API_KEY` not set — needed for step 3 (descriptions).")
        prereqs_ok = False

    # ── Prompt selector ──────────────────────────────────────────────────────
    _PRESET_SIMPLE = """\
Write a description of the transcript below. Output exactly two things:

TITLE
Use the source title exactly as given — do not rewrite or shorten it.

DESCRIPTION
5–10 sentences. Summarize the main topics covered, the key ideas or arguments made, and any notable moments, tensions, or conclusions. Write in plain, clear prose. Do not use bullet points. Do not open with "In this episode" or "This episode." Do not end with a call to action.

OUTPUT FORMAT (use exactly this structure):
TITLE
[title here]

DESCRIPTION
[your description here]

Source title: <<<TITLE>>>

Transcript:
---
<<<EXCERPT>>>
---"""

    _PRESET_MORNING_ROUNDS = """\
Write a suggested title, a podcast description, and key quotes for the episode below.

TITLE INSTRUCTIONS
- Always start with the episode number extracted from the YouTube title
- Preserve the exact series name from the YouTube title — do not substitute one series for another (e.g. do not turn a "Prema Vivarta" episode into an "Uddhava Gita" episode or vice versa)
- If the episode belongs to a named series with a part number, use: {number}. {Series Name} Part {N}. {Descriptive Subtitle}
- If there is no series or part number, use: {number}. {Descriptive Subtitle}
- The descriptive subtitle should name the actual topic or theme directly — keep it clear and not overly long
- Avoid dramatic or poetic phrasing; prefer simple, direct naming of what the episode is about
- Use common English spellings in titles (no diacritics): "Uddhava Gita," "Srimad Bhagavatam," "Krishna," "prema," "sraddha"
- Examples:
  "167. Uddhava Gita Part 5. From Kama to Prema: Sincerity, Repentance, and Pure Chanting"
  "172. Prema Vivarta Part 5. Repentance, Lamentation, and the Path to Pure Chanting"
  "42. Why Chanting Fails Without Attention"

TERM CORRECTIONS
Apply these corrections everywhere — title, description, and quotes.
Use diacritics sparingly; prefer common search spellings for widely-searched terms:
  Jagadan Pandit / Jagadananda Pandit → Jagadananda Pandita
  Udava Gita → Uddhava Gita
  Shrimad Bhagavatam / Srimad Bhagavatam → Srimad Bhagavatam
  Chaitanya Charitamrita → Chaitanya Charitamrita
  Mahamantra / Maha-mantra → Hare Krishna mantra
  namaparadha / namarada / nama aparadha → nama-aparadha
  nama abhasa / namabhasa → nama-abhasa
  sudhanam / sudhanama / suddha nama → suddha-nama
  pema → prema
  shreddha / shraddha / shradha → sraddha
  maya → maya (acceptable as-is)
  jiva → jiva (acceptable as-is)
  acharas / acharyas → acaryas
  Bhaktivinoda Thakur → Bhaktivinoda Thakura
  Haridas Takur / Haridas Thakur → Haridasa Thakura
  Sacinand Maharaj / Sachinand Maharaj → Sacinandana Swami

DESCRIPTION INSTRUCTIONS
- 3–6 sentences total
- The sole speaker is Hari — use "Hari explores," "Hari examines," "Hari reflects on," "Hari draws a distinction," etc. rather than impersonal phrasing like "the speaker discusses"
- Also use "we explore," "we return to," or "we look at" where it fits naturally — vary between "Hari [verb]" and "we [verb]" so the structure feels alive, not formulaic
- Do NOT refer to "the speaker," "the presenter," or "the episode"
- Descriptions should feel emotionally alive and specific to this episode — not interchangeable with any other episode; capture what is unique about this particular discussion
- Neutral but not cold; grounded but not dry — let the actual texture of the teaching come through
- Do NOT open with "In this episode," "This episode," or "The episode"
- Good openings name the subject or tension directly: "Repentance and its role in…", "The distinction between lust and love…", "What makes chanting inattentive…", "Hari opens with…"
- Be specific: name the actual concepts, distinctions, or frameworks discussed; do not describe the episode in terms that could apply to any episode in the series
- Reflect tension, struggle, or nuance where present — don't only describe ideal outcomes
- Structure: open with what is covered → highlight 2–4 specific ideas or movements → end with a grounded observation (not a call to action)
- Naturally incorporate keywords people would actually search for (e.g. "Krishna consciousness," "Hare Krishna mantra," "Srimad Bhagavatam"); do not keyword-stuff
- Avoid these overused AI summary words: "ultimately," "highlights," "emphasizes," "crucial," "insightful," "powerful," "transformative," "enlightening," "profound"
- Do not end with a call to action or "encourages listeners to…"
- Avoid vague abstractions: "the Divine," "spiritual journey," "deeper connection," unless explicitly in the episode

QUOTES INSTRUCTIONS
- Select the 5–7 strongest quotes — prioritize fewer, better quotes over a longer list
- Quotes should be short, sharp, and self-contained — a single striking sentence or phrase is better than a long transcript excerpt
- Lightly clean spoken artifacts: remove filler words, false starts, and awkward repetition, but preserve Hari's voice, phrasing, and meaning
- Apply term corrections from the table above
- Include ONLY original statements from Hari — his own words and observations
- Do NOT include quotes where Hari is reading, reciting, or closely paraphrasing scripture or sacred texts
- Exclude lines with implied attribution: "Krishna says…", "the verse says…", "it is written…"
- If uncertain whether a line is original or sourced, exclude it
- Goal: capture Hari's voice, not the texts he is referencing

OUTPUT FORMAT (use exactly this structure):
TITLE
[suggested title here]

DESCRIPTION
[your 3–6 sentence description here]

QUOTES
- "[quote 1]"
- "[quote 2]"
- "[quote 3]"
(continue for all quotes)

YouTube title: <<<TITLE>>>

Transcript:
---
<<<EXCERPT>>>
---"""

    _PRESET_NEWSLETTER = """\
Write 2–3 standalone newsletter blurbs based on the transcript below.

Each blurb should work for a reader who has never heard the podcast — do not summarize the episode. Instead, take one specific idea, tension, or insight from the transcript and develop it into a short, standalone reflection.

STYLE & TONE
- Short paragraphs — often 1–3 sentences; white space is intentional and creates rhythm
- Voice: first person plural ("we") or second person ("you") — never "the speaker," "the presenter," or "the episode"
- Opens with a hook: a striking statement, a vivid contrast, a question, or an unexpected image
- Develops the idea through observation, analogy, or a concrete example drawn from the transcript
- May reference a teaching, Sanskrit term, or concept briefly — but always grounded in plain English
- Ends with a reflective question or quiet provocation — never a call to action, never promotional
- Warm but not soft. Philosophical but accessible. Specific, not vague.
- Avoid words like "transformative," "enlightening," "profound," "powerful," "ultimately"
- Do not mention the podcast, the episode, or the speaker by name

TITLE
Each blurb gets a short, punchy title — not a summary, more like a provocation or a direct question.
Examples:
  "Are you living for the tongue or the stomach?"
  "Never Let a Good Existential Crisis Go to Waste"
  "Own Your Needs or They Become Entitlements"
  "Same Block, Different Worlds. What Are You Awake To?"
  "What Has Been Done for Me?"

OUTPUT FORMAT
Separate each blurb with ---

---
[Title]

[Body — short paragraphs, a blank line between each]

---

Source title: <<<TITLE>>>

Transcript:
---
<<<EXCERPT>>>
---"""

    _PRESETS = {
        "Description and Quotes": None,  # None = use pipeline.py defaults
        "Description only": _PRESET_SIMPLE,
        "Morning Rounds specific output": _PRESET_MORNING_ROUNDS,
        "Newsletter Blurbs": _PRESET_NEWSLETTER,
        "Custom": "custom",
    }

    with st.expander("✏️  Output format", expanded=False):
        preset_choice = st.radio(
            "Choose a prompt",
            options=list(_PRESETS.keys()),
            index=list(_PRESETS.keys()).index(
                st.session_state.get("prompt_preset", "Description and Quotes")
            ),
            label_visibility="collapsed",
            key="prompt_preset_radio",
        )
        st.session_state["prompt_preset"] = preset_choice

        if preset_choice == "Description and Quotes":
            st.session_state.system_prompt   = None
            st.session_state.prompt_template = None
            st.caption("Generates a suggested title, a structured description, and 5–10 key quotes. Works across any type of recorded conversation.")

        elif preset_choice == "Description only":
            st.session_state.system_prompt   = None
            st.session_state.prompt_template = _PRESET_SIMPLE
            st.caption("Generates the YouTube video title plus a plain prose description. No quotes.")

        elif preset_choice == "Morning Rounds specific output":
            st.session_state.system_prompt   = None
            st.session_state.prompt_template = _PRESET_MORNING_ROUNDS
            st.caption("Hari is the sole speaker. Generates a title (with series name and episode number), a 3–6 sentence description, and 5–7 original quotes from Hari only — excluding scripture recitations.")

        elif preset_choice == "Newsletter Blurbs":
            st.session_state.system_prompt   = None
            st.session_state.prompt_template = _PRESET_NEWSLETTER
            st.caption("Generates 2–3 standalone newsletter blurbs. Each blurb takes one idea from the transcript and develops it into a short, punchy reflection — not a summary, not promotional.")

        # View prompt (shown for all presets except Custom, which already shows the text)
        if preset_choice != "Custom":
            active_tmpl = st.session_state.prompt_template or (_DEFAULT_PROMPT_TEMPLATE if _PIPELINE_OK else "")
            active_sys  = _DEFAULT_SYSTEM_PROMPT if _PIPELINE_OK else ""
            with st.expander("👁  View prompt", expanded=False):
                st.caption("System prompt")
                st.code(active_sys, language=None)
                st.caption("User prompt template")
                st.code(active_tmpl, language=None)

        else:
            st.caption(
                "Write your own prompt. Use `<<<TITLE>>>` and `<<<EXCERPT>>>` "
                "as placeholders — they are replaced with the episode title and transcript at runtime."
            )
            default_sys  = _DEFAULT_SYSTEM_PROMPT if _PIPELINE_OK else ""
            default_tmpl = _DEFAULT_PROMPT_TEMPLATE if _PIPELINE_OK else ""

            edited_sys = st.text_area(
                "System prompt",
                value=st.session_state.system_prompt or default_sys,
                height=80,
                key="prompt_sys_area",
            )
            edited_tmpl = st.text_area(
                "Prompt template",
                value=st.session_state.prompt_template or default_tmpl,
                height=400,
                key="prompt_tmpl_area",
            )
            if st.button("💾  Save custom prompt", use_container_width=True):
                st.session_state.system_prompt   = edited_sys
                st.session_state.prompt_template = edited_tmpl
                st.success("Custom prompt saved.")

    # ── Output destination ────────────────────────────────────────────────────
    st.markdown("**Output**")
    doc_mode = st.radio(
        "Output destination",
        options=["screen", "new", "existing"],
        format_func=lambda x: {
            "screen":   "Show on screen (copy & paste)",
            "new":      "Create a new Google Doc",
            "existing": "Append to an existing Google Doc",
        }[x],
        index=["screen", "new", "existing"].index(st.session_state.doc_mode)
              if st.session_state.doc_mode in ["screen", "new", "existing"] else 0,
        horizontal=True,
        label_visibility="collapsed",
    )
    st.session_state.doc_mode = doc_mode

    if doc_mode == "screen":
        st.caption("Descriptions will be displayed here after the pipeline runs — no Google account needed.")
        if _PIPELINE_OK and not GOOGLE_CREDENTIALS_FILE.exists():
            pass  # fine — Google Doc not needed for screen mode

    existing_doc_id = ""
    if doc_mode == "existing":
        existing_doc_url = st.text_input(
            "Paste the Google Doc link",
            value=st.session_state.existing_doc_url,
            placeholder="https://docs.google.com/document/d/…/edit",
            label_visibility="collapsed",
        )
        st.session_state.existing_doc_url = existing_doc_url
        if existing_doc_url.strip():
            existing_doc_id = _extract_doc_id(existing_doc_url.strip())
            st.caption(f"Doc ID: `{existing_doc_id}`")
        else:
            st.warning("Paste a Google Doc link to continue.")
            prereqs_ok = False

    if doc_mode in ("new", "existing") and _PIPELINE_OK and not GOOGLE_CREDENTIALS_FILE.exists():
        st.error(
            f"❌ Google credentials not found at `{GOOGLE_CREDENTIALS_FILE}` — "
            "needed for Google Doc output. Choose **Show on screen** to skip this."
        )
        prereqs_ok = False

    run_ok = n_sel > 0 and prereqs_ok and (doc_mode in ("screen", "new") or existing_doc_id)

    if st.button(
        f"▶  Run  ({n_sel} episode{'s' if n_sel != 1 else ''})",
        type="primary",
        use_container_width=True,
        disabled=not run_ok,
    ):
        sel_entries = [e for e in entries if e["id"] in st.session_state.selected_ids]
        try:
            _run_pipeline(
                sel_entries, entries,
                st.session_state.pl_title, st.session_state.pl_url,
                existing_doc_id=existing_doc_id if doc_mode != "screen" else "__screen__",
                system_prompt=st.session_state.system_prompt or "",
                prompt_template=st.session_state.prompt_template or "",
            )
        except Exception as _pipeline_exc:
            import traceback
            st.session_state.pipeline_errors = [traceback.format_exc()]
            st.session_state.pipeline_done   = True
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — RESULT
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.pipeline_done and st.session_state.doc_url:
    st.divider()
    url = st.session_state.doc_url
    st.markdown(
        f"""
        <div class="result-box">
            <h2>✅ Pipeline complete</h2>
            <p style="color:#8b9eb0; margin: 0.2rem 0 1rem 0;">Your Google Doc is ready</p>
            <a href="{url}" target="_blank">{url}</a>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("")
    st.code(url, language=None)

def _parse_output(raw: str) -> dict:
    """Split AI output into title, description, and quotes sections."""
    # Normalise bold markdown on section headers
    raw = re.sub(r'\*{1,2}(TITLE|DESCRIPTION|QUOTES)\*{1,2}', r'\1', raw)

    title = desc = quotes = ""

    m_title = re.search(r'^TITLE\s*\n(.+?)(?=\nDESCRIPTION|\nQUOTES|$)', raw, re.M | re.S)
    if m_title:
        title = m_title.group(1).strip()

    m_desc = re.search(r'^DESCRIPTION\s*\n(.+?)(?=\nQUOTES|$)', raw, re.M | re.S)
    if m_desc:
        desc = m_desc.group(1).strip()

    m_quotes = re.search(r'^QUOTES\s*\n(.+)', raw, re.M | re.S)
    if m_quotes:
        quotes = m_quotes.group(1).strip()

    # If no structure found, treat entire output as description
    if not title and not desc and not quotes:
        desc = raw.strip()

    return {"title": title, "description": desc, "quotes": quotes}


import streamlit.components.v1 as _cv1

def _copy_btn(text: str, key: str) -> None:
    """Render a copy-to-clipboard button using a data attribute to avoid JS escaping issues."""
    import json
    safe = json.dumps(text)  # properly escaped JSON string
    _cv1.html(f"""
    <script>
    (function() {{
        var btn = document.getElementById('cb_{key}');
        if (btn) return;
        btn = document.createElement('button');
        btn.id = 'cb_{key}';
        btn.textContent = 'Copy';
        btn.style.cssText = 'cursor:pointer;background:#fff;border:1px solid #d1d5db;border-radius:6px;padding:0.28rem 0.9rem;font-size:0.78rem;font-family:Inter,sans-serif;color:#555;font-weight:500;';
        btn.onclick = function() {{
            navigator.clipboard.writeText({safe}).then(function() {{
                btn.textContent = 'Copied!';
                setTimeout(function() {{ btn.textContent = 'Copy'; }}, 1500);
            }});
        }};
        document.body.appendChild(btn);
    }})();
    </script>
    """, height=38)


if st.session_state.pipeline_done and st.session_state.get("pipeline_errors"):
    st.divider()
    for err in st.session_state.pipeline_errors:
        st.error(f"❌  {err}")

if st.session_state.pipeline_done and st.session_state.screen_results:
    st.divider()
    for i, r in enumerate(st.session_state.screen_results):
        parsed = _parse_output(r["description"])
        yt_title = r["title"]

        # Title — prefer AI-generated, fall back to YouTube title
        display_title = parsed["title"] or yt_title
        st.markdown(f"### {display_title}")

        if parsed["description"]:
            st.markdown(parsed["description"])

        if parsed["quotes"]:
            st.markdown("**Quotes**")
            for line in parsed["quotes"].splitlines():
                line = line.strip()
                if line:
                    clean = re.sub(r'^[-•*]\s*', '', line)
                    st.markdown(f"- {clean}")

        # Copy button — passes the full clean text
        copy_text = display_title + "\n\n"
        if parsed["description"]:
            copy_text += parsed["description"] + "\n\n"
        if parsed["quotes"]:
            copy_text += "Quotes\n" + parsed["quotes"]
        _copy_btn(copy_text.strip(), key=str(i))

        st.divider()
