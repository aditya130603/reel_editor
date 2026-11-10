# Reel Editor — Local Preset Video Editing

Self-hosted talking-head reel editor for **OpenClaw / Motion Graphics**. Pick a preset, upload a short reel, and the app transcribes locally with faster-whisper, highlights meaningful words, matches your own B-roll footage by filename tags, grades the footage, and exports MP4 using FFmpeg + libass.

**No Codex, subscription, paid inference, external LLM API or third-party queue is used for each edit.** The first version uses deterministic rules for emphasis and B-roll matching; it does not claim semantic understanding or professional manual-edit parity.

## What works in v0.1

- Browser upload and five editable presets: Medical Clean, Viral Punch, Luxury Minimal, Podcast Focus, Paper Soft.
- Automatic word-timestamp transcription on the VPS with faster-whisper.
- Subtitles with per-phrase color-highlighted emphasis words in ASS.
- Caption typography, position, stroke, size, font, grading, and pacing controlled by `presets.json`.
- Keyword-matched local B-roll with alpha-fade entrance/exit.
- Original dialogue audio retained; MP4 export; downloadable caption file and JSON edit plan.
- Single render slot and upload size/clip duration/FFmpeg runtime limits.

**Not implemented yet:** manual timeline GUI, multilingual caption fonts/accuracy QA, face-aware reframing, image-search B-roll, automatic sound effects, AI-based understanding of scenes, project persistence across restarts, multi-user authentication, and Remotion component effects. Kokoro is available for later voiceover functionality but is not needed for this pipeline.

## Install on your Ubuntu VPS

```bash
git clone https://github.com/aditya130603/reel_editor.git
cd reel_editor
sudo apt-get update
sudo apt-get install -y ffmpeg fonts-dejavu-core python3-venv python3-pip
# verify subtitles/libass support:
ffmpeg -hide_banner -filters | grep subtitles
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p assets/broll assets/fonts data
cp .env.example .env
# NOTE: the first whisper model download requires internet; after caching it runs locally.
set -a; source .env; set +a
uvicorn app:app --host 127.0.0.1 --port 8765
```

Open `http://localhost:8765` through an **SSH tunnel**:

```bash
ssh -L 8765:127.0.0.1:8765 root@YOUR_VPS_IP
```

Do **not** publicly expose port 8765 without authentication and HTTPS. A reverse proxy behind your existing Nginx setup is possible later. Do not interrupt your production OpenClaw gateway, CRM, HMS, AdsManagerOS, Dr.irizz, or Ollama services.

### Local B-roll assets

Put your licensed video clips or images in `assets/broll/`. Use meaningful underscore-separated keywords:

- `kidney_stone_scan.mp4` matches **kidney**, **stone** or **scan**.
- `pregnancy_ultrasound.mp4` matches **pregnancy** or **ultrasound**.
- `website_design.webp` matches **website** or **design**.

B-roll is only inserted when a spoken token exactly matches an asset filename tag; clips have preset-controlled minimum gaps, durations and fade transitions. No online asset lookups. If nothing matches, you still get a complete captioned edit.

### Motion Graphics / OpenClaw workflow

The Motion Graphics agent can send a multipart POST directly to the loopback API:

```bash
curl -s -F "video=@reel.mp4" -F "preset=medical_clean" http://127.0.0.1:8765/api/jobs
curl -s http://127.0.0.1:8765/api/jobs/JOB_ID
curl -L http://127.0.0.1:8765/api/jobs/JOB_ID/download -o edited.mp4
```

The job endpoint returns quickly, and the status endpoint gives queued, analyzing, transcribing, rendering, completed or failed. The browser polls automatically.

### Resource controls

Defaults: 720×1280 render, 180-second max clip, 500 MB max upload, CPU int8 Whisper small, single active render, 900-second FFmpeg timeout. Tune with `.env`. This app does **not** modify existing systemd services or OpenClaw settings. It runs only when started.

The input video is removed after successful rendering. Outputs stay in `data/` until you remove them manually. Set a retention policy before using long term. On failure, input is retained for debugging; clean `data/` periodically.

### Security & limitations

- This starter has **no authentication**. Loopback-only by default is intentional.
- Filenames never become shell commands, but avoid ingesting untrusted media without adequate OS isolation.
- Model weights must be available locally or downloaded at first run (via faster-whisper).
- To run with no network even on first use, pre-populate the model cache.
- Unlike a transcript-aware LLM editor, emphasis is based on content-word length, and B-roll matching is lexical, not semantic.
- FFmpeg must have the `subtitles` filter (libass); video filters differ among FFmpeg builds.
- A VPS deploy and actual rendered reel have **not** yet been verified through this repository.

## Next milestones

1. Render a sample clip on your VPS and fix any build-specific FFmpeg/libass issues.
2. Expand to per-word karaoke animation, custom typefaces, and original Remotion presets.
3. Add local embeddings for semantic B-roll matching, optional scene change/pause detection, non-AI smart reframing, licensed SFX.
4. Add timeline review/edit and reusable per-client brand kits.

Licensed media only: do not copy proprietary Captions AI templates or their copyrighted assets.
