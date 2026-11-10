# Agency V4 — one-preset video editing

## Why V4 replaced the previous dashboard

The 63.1-second user-provided result had unbroken talking-head video and basic blue/white captions on the doctor's torso. The controls allowed unrelated graphics to overlap. V4 replaces that approach with four coherent complete profiles: **Clinical Pro**, **Paper Story**, **Film Editorial**, and **Neon Agency**.

Each preset automatically chooses caption styling, portrait-safe zones, cadence, real effects, synchronized audio cues, locally generated music, and cutaway matching. The browser exposes one main creative choice: the preset.

### Actual procedural overlays now generated into the video

- Camera shutter with moving mechanical blades
- Flash transition
- Warm film burn
- Amber light leak
- Sun-rays optical streaks
- Film grain, dust and scratches
- Paper fold/torn-paper wipe
- Folded paper annotation
- Scribble marker and drawn circles
- Click rings and pop indicators
- Sticker/icon marker and technical label lines
- Countdown/film leader (sparingly, in film preset)

The layers are actual transparent QTRLE videos produced locally by Pillow and FFmpeg; no proprietary asset packs or paid model calls. Each temporary image frame is deleted immediately after animation encoding.

### Stylized captions

Clinical caption plates, paper-tape subtitles, warm film serif subtitles, lime word-synced karaoke and two more reusable typography treatments. Short word groups, per-word timestamps, two-line wrapping and a protected lower-third position are generated automatically. Persistent callout graphics are restricted to outer side gutters, not the face or caption region.

### Sound

Paper swipes, clicks, film hits and shutters have local procedurally rendered WAV cues timed to their visual overlays. If the user does not provide licensed background music, the preset creates a short original 12-second ambient bed and loops/ducks it beneath speech. The source voice remains audible. CC0 imports from ANVEAI remain available but are not required.

### Honest limitations

- No human-grade semantic interpretation of all speech; effect times are deterministic around word timestamps, and meaningful stock B-roll requires locally supplied/licensed clips.
- The generated music is light procedural underscoring, not a substitute for licensed professional music.
- Results are tested with synthetic clips; real footage still requires a visual quality review for face overlap, translation accuracy and effect suitability.
- Strong Captions AI-level quality remains a creative benchmark, not a verified claim of equivalence.

## Deploy on your SAME VPS

With your existing Reel Editor service on 127.0.0.1:8765, as root:

```bash
cd /opt/reel_editor
git -c safe.directory=/opt/reel_editor pull --ff-only origin main
bash scripts/upgrade_agency_v4.sh
```

The script refuses to interrupt active renders, runs the suite, restarts only Reel Editor, and does not modify the OpenClaw gateway or other VPS services. If GitHub auto-sync was already enabled, it can apply a clean update on its next idle check, but **the timer is not assumed to be enabled**.

Then access the existing localhost/SSH tunnel browser at `http://localhost:8765`.

To check via curl:

```bash
curl -s http://127.0.0.1:8765/api/health
curl -s http://127.0.0.1:8765/api/studio/agency-presets
```

### One-preset automation request

```bash
curl -s -F 'videos=@/path/raw_reel.mp4' -F 'agency_preset=clinical_pro' \
  http://127.0.0.1:8765/api/studio/jobs
```

Use the RAW source file, not a reel that already has subtitles burned into the pixels, or both caption layers will show. Poll `/api/jobs/<ID>`, then use the output download URL.

To combine footage, supply multiple `videos=@...` fields. Existing licensed local B-roll is automatically matched by filenames/tags. For a one-click agent command, set only `agency_preset` and submit footage; the preset makes the rest of the decisions.

### Testing and acceptance

Before treating any edit as production-ready, compare the result with the user's reference videos: overlays must be visible, typography must not leave the frame, graphics should avoid the face, cuts must have purpose, voice should be clear, and no invented facts or ratings may appear. The first real render on the VPS is not yet visually verified.