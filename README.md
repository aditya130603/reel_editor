# Reel Editor — Local Preset Video Editing

Self-hosted talking-head reel editor for **OpenClaw / Motion Graphics**. Pick a preset, upload a short reel, and the app transcribes locally with faster-whisper, highlights meaningful words, matches B-roll to spoken phrases and emphasis-word timestamps, grades the footage, and exports MP4 using FFmpeg + libass.

**No Codex, subscription, paid inference, external LLM API or third-party queue is used for each edit.** The first version uses deterministic rules for emphasis and B-roll matching; it does not claim semantic understanding or professional manual-edit parity.

## What works in v0.2

- Browser upload and **13 editable presets** for medical, podcast, editorial, documentary, minimal, cinematic, bold and storytelling reels.
- Automatic word-timestamp transcription on the VPS with faster-whisper.
- **12 caption animation modes** (highlight, karaoke, clean, editorial, punch, typewriter, outline, word-focus, soft-bounce, lower-third, glow, cinematic) generated with timed ASS animation tags.
- Caption typography, position, stroke, size, font, grading, and pacing controlled by `presets.json`.
- Phrase-scored, synonym-aware local B-roll using filenames and optional sidecar JSON descriptions, with optional Ollama embeddings served strictly on localhost. No cloud inference.
- **Six original cutaway transitions:** soft fade, left/right/up/down slide, and clean cut. All use the FFmpeg filtergraph, with captions kept above cutaways.
- **Four subtle Ken Burns treatments** for still-image B-roll: slow push, slow pull, pan left, pan right.
- **Optional local transition SFX**, quietly mixed under dialogue when an appropriate user-provided, licensed sound file is present. No downloads or third-party SFX APIs.
- Original dialogue audio retained; MP4 export; downloadable caption file and JSON edit plan.
- Single render slot, configurable FFmpeg threads and upload size/clip duration/runtime limits. Whisper weights are released after a job unless configured otherwise.
- Browser controls to override caption animation and transition per job without changing your preset file.

**Not implemented yet:** manual timeline GUI, human transcript correction, face-aware reframing, full visual image-search B-roll, advanced automatic sound design, semantic scene understanding beyond basic optional text embeddings, project persistence across restarts, multi-user authentication, and Remotion effects. Actual reel and VPS deployment checks are still required; the code is not a production-certified clone of Captions. Kokoro is available for later voiceover functionality but is not needed for this pipeline.

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
mkdir -p assets/broll assets/sfx assets/fonts data
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

B-roll candidates are scored against spoken phrases and asset tags, using token normalization and domain synonym mappings. Use sidecar files like `kidney_scan.mp4.json` with `{"tags":["renal","kidney"],"description":"A doctor discussing scans"}` to improve accuracy. Clips are placed at the timestamp of a matching spoken word when one is present; otherwise optional local embedding matches anchor to the phrase emphasis. Clips respect preset-controlled gaps, durations, and transitions. No online asset lookups. If nothing matches, you still get captioned output.

### Optional local transitions SFX and still-image motion

Add your own properly licensed `assets/sfx/soft_whoosh.wav` (or a matching MP3/OGG file; set `sfx_file` accordingly). Presets with `"sfx": true` will automatically include a quiet cutaway whoosh when B-roll exists. If the file is missing, sound effects are silently skipped; speech audio remains intact.

Still-image B-roll can apply `broll_motion` values `slow_push`, `slow_pull`, `pan_left`, `pan_right`, or `none`. Video clips are not artificially zoomed. Use gentle motion to avoid an overedited effect.

### Motion Graphics / OpenClaw workflow

The Motion Graphics agent can send a multipart POST directly to the loopback API:

```bash
curl -s -F "video=@reel.mp4" -F "preset=medical_clean" -F "caption_style=karaoke" -F "transition_style=soft_fade" http://127.0.0.1:8765/api/jobs
curl -s http://127.0.0.1:8765/api/jobs/JOB_ID
curl -L http://127.0.0.1:8765/api/jobs/JOB_ID/download -o edited.mp4
```

The job endpoint returns quickly, and the status endpoint gives queued, analyzing, transcribing, rendering, completed or failed. The browser polls automatically.

### Optional semantic B-roll matching (local Ollama)

Default lexical matching is fast and works without an embedding model. To enable additional context matching, install an embedding model into your **existing** Ollama instance (do not create another Ollama server) and configure:

```bash
ollama pull nomic-embed-text
# .env
OLLAMA_EMBED_MODEL=nomic-embed-text
```

Set `"broll_match": "ollama"` for selected presets in `presets.json`. The matcher only contacts `http://127.0.0.1:11434/api/embed`; if the local model is missing, it falls back to lexical matching. This may consume CPU/RAM. Keep lexical matching for most reels on a shared VPS.

### Adjusting presets

Every named preset is editable in `presets.json`. Set `caption_style`, `transition_style`, `font`, `size`, `primary`, `accent`, `outline`, `caption_position`, `words_per_card`, `grading`, `max_broll`, `broll_duration`, and `min_broll_gap`. The browser offers convenient per-render animation and transition overrides. Start with **Medical Clean** for professional talking heads.

### Automated checks

The repository runs GitHub Actions on pushes and pull requests. The latest expanded suite has **15 passing tests**, covering subtitle generation, word-timed B-roll matching, each transition, still-image zoom/pan and local SFX mixing. These use synthetic media and do not download a Whisper model. Check the latest Actions run after modifying FFmpeg logic.

### Resource controls

Defaults: 720×1280 render, 180-second max clip, 500 MB max upload, CPU int8 Whisper small, single active render, 2 FFmpeg threads, 900-second FFmpeg timeout. Tune with `.env`. This app does **not** modify existing systemd services or OpenClaw settings. It runs only when started.

The input video is removed after successful rendering. Outputs stay in `data/` until you remove them manually. Set a retention policy before using long term. On failure, input is retained for debugging; clean `data/` periodically.

### Security & limitations

- This starter has **no authentication**. Loopback-only by default is intentional.
- Filenames never become shell commands, but avoid ingesting untrusted media without adequate OS isolation.
- Model weights must be available locally or downloaded at first run (via faster-whisper).
- To run with no network even on first use, pre-populate the model cache.
- Unlike a transcript-aware LLM editor, emphasis is based on content-word length, and B-roll matching is lexical, not semantic.
- FFmpeg must have the `subtitles` filter (libass); video filters differ among FFmpeg builds.
- CI has verified 15 tests, including synthetic FFmpeg render, transition, still-image motion, and SFX cases. A VPS deploy and actual user-provided reel have **not** yet been verified.

## Next milestones

1. Validate an actual 30–40 second reel on the VPS, including all transitions, fonts and timings.
2. Add a correction timeline and face-safe caption placement.
3. Add a licensed SFX/music library with audio ducking and local visual image/clip search.
4. Extend the original motion templates with Remotion for animated cards, callouts and premium hook sequences.
5. Add reusable brand kits, retention cleanup, authorization and resumable job records.

Licensed media only: do not copy proprietary Captions AI templates or their copyrighted assets.
