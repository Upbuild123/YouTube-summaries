#!/usr/bin/env python3
"""
Step 4 — Create (or update) a Google Doc with all episode titles and descriptions.

Document format
---------------
  [Document title = playlist title]

  HEADING_2  Episode 1: <title>
  NORMAL     <description>
  (blank line)
  HEADING_2  Episode 2: <title>
  ...

Resumable: the Google Doc ID is stored in metadata.json so the same document
is reused across runs.  Episodes already marked google_doc_updated=true are
appended only once.

Authentication
--------------
The first run opens a browser for OAuth consent.  The resulting token is saved
to credentials/token.json and reused on subsequent runs.

Required files in credentials/
  credentials.json  — OAuth 2.0 client secret downloaded from Google Cloud Console
"""

import logging
import sys
import time
from pathlib import Path

from tqdm import tqdm

import metadata_manager as mm
from config import (
    GDOCS_INTER_EPISODE_DELAY, GOOGLE_CREDENTIALS_FILE,
    GOOGLE_SCOPES, GOOGLE_TOKEN_FILE, LOG_FILE,
    MAX_RETRIES, RETRY_DELAY,
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


# ── Google auth ───────────────────────────────────────────────────────────────

def get_google_service():
    """Return an authenticated Google Docs API service object."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        logger.error(
            "Google API packages missing. Run: pip install "
            "google-api-python-client google-auth-oauthlib google-auth-httplib2"
        )
        sys.exit(1)

    if not GOOGLE_CREDENTIALS_FILE.exists():
        logger.error(
            "Google credentials file not found at %s\n"
            "Follow the README instructions to create it.", GOOGLE_CREDENTIALS_FILE
        )
        sys.exit(1)

    creds = None
    if GOOGLE_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_FILE), GOOGLE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(GOOGLE_CREDENTIALS_FILE), GOOGLE_SCOPES
            )
            creds = flow.run_local_server(port=0)
        GOOGLE_TOKEN_FILE.write_text(creds.to_json())

    service = build("docs", "v1", credentials=creds)
    return service


# ── Document creation ─────────────────────────────────────────────────────────

def create_document(service, title: str) -> str:
    """Create a new Google Doc and return its document ID."""
    doc = service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    logger.info("Created Google Doc '%s' (id=%s)", title, doc_id)
    return doc_id


# ── Document content helpers ──────────────────────────────────────────────────

def get_doc_end_index(service, doc_id: str) -> int:
    """Return the index one position before the final paragraph marker."""
    doc     = service.documents().get(documentId=doc_id).execute()
    content = doc.get("body", {}).get("content", [])
    # The last element is always an end-of-segment structural element.
    # We insert just before it.
    if len(content) >= 2:
        return content[-1]["startIndex"]
    return 1  # Empty document — insert at the very beginning


def build_episode_requests(ep: dict, insert_at: int) -> tuple[list[dict], int]:
    """
    Build a batchUpdate request list that inserts one episode (heading +
    description) at *insert_at* and styles the heading HEADING_2.

    Returns (requests, new_insert_at) so the caller can chain episodes.
    """
    heading_text = f"Episode {ep['episode_number']}: {ep['title']}\n"
    body_text    = f"{ep['description']}\n\n"
    full_text    = heading_text + body_text

    heading_start = insert_at
    heading_end   = insert_at + len(heading_text)
    new_end       = insert_at + len(full_text)

    requests = [
        {
            "insertText": {
                "location": {"index": insert_at},
                "text":     full_text,
            }
        },
        {
            "updateParagraphStyle": {
                "range": {
                    "startIndex": heading_start,
                    "endIndex":   heading_end,
                },
                "paragraphStyle": {"namedStyleType": "HEADING_2"},
                "fields": "namedStyleType",
            }
        },
    ]
    return requests, new_end


def apply_requests_with_retry(service, doc_id: str, requests: list[dict]) -> bool:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()
            return True
        except Exception as exc:
            logger.warning(
                "batchUpdate attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    data = mm.load()

    if not data.get("playlist_title"):
        logger.error("No playlist data found. Run 01_download_audio.py first.")
        sys.exit(1)

    service = get_google_service()

    # ── Get or create the Google Doc ─────────────────────────────────────────
    doc_id = data.get("google_doc_id")
    if doc_id:
        logger.info("Reusing existing Google Doc (id=%s)", doc_id)
    else:
        doc_id = create_document(service, data["playlist_title"])
        data["google_doc_id"] = doc_id
        mm.save(data)

    # ── Collect episodes ready to add ────────────────────────────────────────
    to_add = [
        ep for ep in data["episodes"]
        if ep["status"]["description_generated"] and not ep["status"]["google_doc_updated"]
    ]
    skipped = sum(1 for ep in data["episodes"] if ep["status"]["google_doc_updated"])
    logger.info(
        "%d episode(s) to write to Google Doc (skipping %d already written)",
        len(to_add), skipped,
    )

    if not to_add:
        logger.info("Nothing to do — all episodes are already in the doc.")
        return

    for ep in tqdm(to_add, desc="Google Doc", unit="ep"):
        video_id = ep["video_id"]
        logger.info("[%03d] Writing to doc: %s", ep["episode_number"], ep["title"])

        # Resolve description (from file if not cached in metadata)
        description = ep.get("description")
        if not description:
            desc_path = BASE_DIR / ep["description_file"]
            if desc_path.exists():
                description = desc_path.read_text(encoding="utf-8").strip()
            else:
                logger.warning("  ↳ Description file missing — skipping")
                continue

        ep["description"] = description  # ensure it's populated for request builder

        # Insert at the current end of the document
        insert_at = get_doc_end_index(service, doc_id)
        requests, _ = build_episode_requests(ep, insert_at)

        success = apply_requests_with_retry(service, doc_id, requests)

        data = mm.load()
        ep   = mm.get_episode(data, video_id)

        if success:
            ep["status"]["google_doc_updated"] = True
        else:
            mm.add_error(data, video_id, "Google Doc write failed after retries")
            logger.error("[%03d] FAILED to write to doc", ep["episode_number"])

        mm.save(data)

        # Brief pause to avoid hitting Docs API rate limits
        time.sleep(GDOCS_INTER_EPISODE_DELAY)

    done = sum(1 for ep in data["episodes"] if ep["status"]["google_doc_updated"])
    total_ready = sum(1 for ep in data["episodes"] if ep["status"]["description_generated"])
    logger.info("Done. %d/%d episodes written to Google Doc.", done, total_ready)
    logger.info(
        "View doc: https://docs.google.com/document/d/%s/edit", doc_id
    )


if __name__ == "__main__":
    main()
