# Primary one-click agency workflow (V4)

The agent should receive **source footage and one preset name** only. Do not ask the user to pick caption style, transition, texture, animation or sound separately.

Choose one of: `clinical_pro`, `paper_story`, `film_retro`, `neon_agency`.

```bash
curl -s -F 'videos=@/path/to/source.mp4' \
  -F 'agency_preset=clinical_pro' \
  http://127.0.0.1:8765/api/studio/jobs
```

Use additional `videos=@...` fields if multiple clips were supplied, in the order given. The preset handles designed captions, real original effect assets, automatic music and sound cues. Poll `/api/jobs/<id>` and retrieve the MP4. Treat a built-in effect as a visual overlay, not a substitute for genuine topic B-roll. Never reuse already-captioned rendered clips when raw footage is available.

**Post-render QA:** inspect caption position and word synchronization, whether the effect is actually visible, whether graphics cover the face or captions, whether the soundtrack is under the voice, and whether a real B-roll match was found. Never claim Captions AI equivalence without a human-approved visual comparison.

# Motion Graphics Agent — Reel Editor Operating Instructions

This repository is the **local, preset-based reel editing engine** for OpenClaw Motion Graphics. Rendering must not invoke Codex or paid inference services.

## Agent workflow

1. Accept a video from the authorized user. Confirm that any content and B-roll is licensed and appropriate.
2. Use existing preset names from `GET http://127.0.0.1:8765/api/presets` or inspect `presets.json`.
3. Use `curl -s -F "video=@/path/reel.mp4" -F "preset=medical_clean" http://127.0.0.1:8765/api/jobs`.
4. Poll `GET /api/jobs/{id}` until `completed` or `failed`; never queue work in an unbounded loop.
5. Download finished video, ASS captions and edit plan; report missing B-roll and transcription uncertainties, do not claim creative quality not visually reviewed.
6. If needed, change preset keys or use `caption_style`/`transition_style` form fields. Never use AI calls for rendering; local faster-whisper and optional local Ollama embedding models are allowed.

## Reliability and resource rules

- One job at a time; the app reserves an upload slot and limits FFmpeg threads.
- Run in the project's venv, under an unprivileged Unix user. Bind only `127.0.0.1:8765`. SSH tunnel or existing authenticated HTTPS reverse proxy for the dashboard.
- Do not modify or restart production OpenClaw gateway, nginx, HMS, AdsManagerOS, WhatsApp Cloud Bridge, Dr.irizz, Ollama, databases, or related services to deploy this editor.
- No Docker required. No persistent worker farm. The dashboard server may run when necessary; FFmpeg render subprocesses exit after the job. Whisper is released unless `WHISPER_KEEP_WARM=1`.
- Timeouts are mandatory. Clean failed job temporary uploads and old completed media with an explicit retention policy.
- Keep GPU/CPU and disk limits predictable. Default is CPU int8 Whisper and 720x1280 H.264 output.
- Never send customer footage, hospital patient data, credentials, audio, or transcripts to third-party APIs without express user approval.
- No copyrighted music or commercial video effect pack assets without the necessary license. You may implement original effects inspired by broad aesthetic categories.

## QA gate

Before deploying to VPS, run:

```bash
python -m compileall -q app.py caption_motion.py broll_matcher.py
python -m unittest discover -s tests -v
```

Then manually test a real 30–40-second source with clear speech, licensed B-roll and two distinct presets. Verify: captions accurately match audio, transitions do not obscure the speaker, original sound remains clear, total duration is unchanged, and all spawned FFmpeg processes terminate.

Do not call a version perfect or production-ready without these checks.
