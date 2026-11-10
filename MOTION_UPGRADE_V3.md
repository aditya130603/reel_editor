# Reel Studio — reference-driven kinetic motion upgrade

## Benchmarks

Reviewed two user-provided portrait talking-head reference videos (16.3 seconds and 25.9 seconds). They demonstrate complementary directions:

- Editorial Clean: natural talking head, selective lower-left kinetic text, brief progress meter/icon callout; clean spaces without graphics.
- Neon Business: cyan/green-lit talking head, italic kinetic headlines, floating numeric cards, rating strip, logo callouts and HUD circle elements.

The components in this codebase are original designs using these general visual conventions. They are not extracted frames or cloned branded assets.

## Newly implemented

- Original transparency-preserving motion pack: `motion_component_pack.py`.
- 8 component renderers: kinetic headline, numeric card, progress ring, rating strip, comparison, lower label, neon badge, segmented meter.
- 3 visual directions plus off: `editorial_clean`, `neon_business`, `documentary`.
- Schedule up to four 2-second animations at relevant spoken-word timestamps. The algorithm is deterministic and never calls Codex.
- Generate 12 fps transparent overlays at up to 360x640, encode temporary qtrle alpha video and composite into the full-resolution output.
- Remove PNG frames immediately. The job cleanup removes encoded temporary motion clips.
- All numbers shown on metric, rating or comparison cards must come from spoken source words, never generated as fabricated statistics.
- Upload local licensed B-roll and select free CC0-imported background music from a dropdown.

## Install/update on your existing VPS

```bash
cd /opt/reel_editor
git -c safe.directory=/opt/reel_editor pull --ff-only origin main
/opt/reel_editor/.venv/bin/python -m pip install -r requirements.txt
systemctl restart reel-editor
curl -s http://127.0.0.1:8765/api/studio/options
curl -s http://127.0.0.1:8765/api/studio/music
```

Then refresh your existing browser tunnel at http://localhost:8765. Select **Neon Business** for the stronger second reference, or **Editorial Clean** for the understated first reference. Render once with no masking, then optionally test the local subject-mask checkbox if you already installed its dependencies.

## Optional CC0 sound/music import — upstream source

The upstream `ANVEAI/motion-pack` repository explicitly grants CC0 for its generated media (`LICENSE-MEDIA`), while its code is MIT and third-party assets retain their own terms. The importer is intentionally offline, copies a small curated subset and records SHA-256/provenance. This avoids installing hundreds of unnecessary components into production.

1. Acquire a copy of `https://github.com/ANVEAI/motion-pack` in a separate, temporary workspace (do not clone it inside OpenClaw). Pin a release tag and use matching release WAV archives, OR follow their documented Python 3.11 build instructions to generate the WAV libraries.
2. Confirm source tree has `LICENSE-MEDIA`, `sfx/library/**/*.wav` and `music/library/beds/*.wav`.
3. Preview the import:

```bash
cd /opt/reel_editor
.venv/bin/python scripts/import_anve_cc0_audio.py --source /path/to/motion-pack --dry-run
```

4. Import up to 12 SFX and 12 music beds:

```bash
.venv/bin/python scripts/import_anve_cc0_audio.py --source /path/to/motion-pack --sfx-count 12 --music-count 12
systemctl restart reel-editor
```

The library audio remains local in `assets/sfx` and `assets/music` and is ignored by Git. The import script records the exact upstream source paths, hashes and license in `assets/ANVE_AUDIO_ORIGINS.json`. No audio is copied to GitHub.

**Important:** The importer does not itself download or build the upstream pack. It requires generated/extracted WAV files already present. The source's Python and Node dependencies are not added to the production Reel Editor runtime.

## Resource bounds

- Same Hostinger VPS and existing localhost port 8765; production OpenClaw gateway at 18789 remains separate.
- One video job at a time. Up to four extra motion events per reel.
- Rendering uses the existing system FFmpeg/libass and a lightweight Pillow dependency.
- Optional depth segmentation remains experimental, more CPU-intensive, and still needs validation on your video.

## Gaps that still matter

These upgrades are real, tested renderer components, **not a complete high-end timeline editor**. Current limitations: automatic timing uses word heuristics rather than full semantic planning; graph cards need explicit content rules for every niche; no live drag-resize animation canvas; no branded logo management; no integrated automatic cut-to-beat system; actual subjective quality must be reviewed by a human using real footage.

## License notes

Read `MOTION_ASSET_RESEARCH.md` before importing external code/assets. Do not assume publicly visible GitHub repos are automatically MIT or safe for commercial reproduction.
