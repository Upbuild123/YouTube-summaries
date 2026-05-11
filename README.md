# YouTube Playlist Processor

Automated pipeline that downloads a YouTube playlist, fetches transcripts,
generates SEO-optimised podcast descriptions with Claude, and publishes
everything to a formatted Google Doc.

---

## What it does

| Step | Script | What happens |
|------|--------|--------------|
| 1 | `01_download_audio.py` | Downloads every episode as an MP3 (128 kbps). Also grabs auto-captions as `.vtt` sidecars when available. |
| 2 | `02_get_transcripts.py` | Fetches a plain-text transcript per episode. Tries YouTube captions first (free), then the VTT sidecar, then OpenAI Whisper API. |
| 3 | `03_generate_descriptions.py` | Sends each transcript to Claude and gets a 2–5 sentence SEO-optimised podcast description. |
| 4 | `04_write_google_doc.py` | Creates (or updates) a Google Doc with the playlist title as the document title, and each episode as a heading + description. |

All steps are **resumable**: completed episodes are skipped on re-runs.

---

## Prerequisites

- Python 3.11 or later
- `ffmpeg` installed (required by yt-dlp for audio conversion)
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`

---

## 1. Clone / download the project

```bash
cd your-projects-folder
# The files are already here — no git clone needed.
```

---

## 2. Create the virtual environment and install dependencies

```bash
chmod +x setup.sh
./setup.sh
```

This creates `venv/` and installs everything from `requirements.txt`.

Activate the environment before running any scripts:

```bash
source venv/bin/activate
```

---

## 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | From [console.anthropic.com](https://console.anthropic.com/) → API Keys |
| `PLAYLIST_URL` | Yes | The full YouTube playlist URL, e.g. `https://www.youtube.com/playlist?list=PLxxx` |
| `OPENAI_API_KEY` | No | Only needed if some episodes lack YouTube captions and you want Whisper transcription as a fallback. |

---

## 4. Set up Google Docs API credentials

You need an OAuth 2.0 client secret from Google Cloud Console.  This is a
one-time setup that takes about five minutes.

### 4a. Create a Google Cloud project (skip if you already have one)

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Click **Select a project → New Project**
3. Name it (e.g. `podcast-pipeline`) and click **Create**

### 4b. Enable the APIs

1. In the project, go to **APIs & Services → Library**
2. Search for **Google Docs API** → Enable
3. Search for **Google Drive API** → Enable

### 4c. Create OAuth 2.0 credentials

1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. If prompted, configure the OAuth consent screen first:
   - User type: **External**
   - App name: anything (e.g. `Podcast Pipeline`)
   - Add your Gmail address as a **Test user** on the "Test users" screen
4. Back on Create credentials:
   - Application type: **Desktop app**
   - Name: anything
5. Click **Create**, then **Download JSON**
6. Rename the downloaded file to `credentials.json` and place it at:

```
credentials/credentials.json
```

### 4d. First-run authorisation

The first time you run `04_write_google_doc.py` (or `run_all.py`), a browser
window opens asking you to sign in with Google and grant access.  After you
approve, a `credentials/token.json` file is saved and subsequent runs are
fully automatic.

---

## 5. Run the pipeline

### Full pipeline (all four steps)

```bash
source venv/bin/activate
python run_all.py
```

### Start from a specific step (useful after a crash)

```bash
python run_all.py --start 3   # skip steps 1–2, run 3–4
```

### Run only one step

```bash
python run_all.py --only 2
```

### Run steps individually

```bash
python 01_download_audio.py
python 02_get_transcripts.py
python 03_generate_descriptions.py
python 04_write_google_doc.py
```

---

## Folder layout

```
YouTube-automation/
├── .env                  ← your secrets (never commit)
├── credentials/
│   ├── credentials.json  ← Google OAuth client secret
│   └── token.json        ← auto-generated auth token
├── audio/                ← downloaded MP3s (+ .vtt sidecars)
├── transcripts/          ← plain-text transcripts
├── descriptions/         ← AI-generated descriptions
├── logs/
│   └── pipeline.log      ← full run log
├── metadata.json         ← central state / resumability record
├── config.py
├── metadata_manager.py
├── 01_download_audio.py
├── 02_get_transcripts.py
├── 03_generate_descriptions.py
├── 04_write_google_doc.py
├── run_all.py
└── requirements.txt
```

---

## metadata.json

Every episode is tracked with this structure:

```json
{
  "episode_number": 1,
  "video_id": "abc123",
  "youtube_url": "https://www.youtube.com/watch?v=abc123",
  "title": "Episode Title",
  "duration_seconds": 612,
  "audio_file": "audio/001_Episode_Title.mp3",
  "subtitle_file": "audio/001_Episode_Title.en.vtt",
  "transcript_file": "transcripts/001_Episode_Title.txt",
  "description_file": "descriptions/001_Episode_Title.txt",
  "description": "Generated text…",
  "transcript_source": "youtube_captions",
  "status": {
    "audio_downloaded": true,
    "transcript_obtained": true,
    "description_generated": true,
    "google_doc_updated": true
  },
  "errors": []
}
```

To force a re-run for one episode, set the relevant status flags to `false` in
`metadata.json` and delete the corresponding output files.

---

## Transcript sources

| Source | Speed | Cost | Notes |
|--------|-------|------|-------|
| YouTube captions | Fast | Free | Best quality for most videos |
| VTT sidecar | Fast | Free | Fallback using file from yt-dlp |
| OpenAI Whisper API | ~1 min/ep | ~$0.006/min | Fallback; requires `OPENAI_API_KEY` |

For a 172-episode playlist of 10-min episodes with Whisper: ≈ $10 total.

---

## Cost estimates (172 episodes × ~10 min)

| Service | Approximate cost |
|---------|-----------------|
| Anthropic Claude (descriptions) | ~$2–5 (depends on transcript length) |
| OpenAI Whisper (only if captions unavailable) | ~$0.006/min × minutes without captions |
| Google Docs API | Free within quota |
| YouTube download (yt-dlp) | Free |

---

## Troubleshooting

**`yt-dlp` says "Sign in to confirm you're not a bot"**
> Add cookies: `yt-dlp --cookies-from-browser chrome …` or export cookies
> manually. This is a YouTube rate-limit measure.

**Google Doc step fails with "insufficient authentication scopes"**
> Delete `credentials/token.json` and re-run step 4 to re-authorise.

**Whisper returns 413 (file too large)**
> The MP3 exceeds OpenAI's 25 MB limit. This shouldn't happen for 10-min
> episodes at 128 kbps (~9.6 MB), but lower `AUDIO_QUALITY` in `config.py`
> if needed.

**Episode has no transcript and no audio yet**
> Steps 2–3 require the audio to exist. Run step 1 first.

**Pipeline stopped mid-run**
> Just re-run the same command — all completed episodes are skipped.
