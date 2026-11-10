# Reel Studio V2 — update on existing OpenClaw VPS

Reel Editor remains on 127.0.0.1:8765; OpenClaw stays on 127.0.0.1:18789. No second server is required.

## New editing features

- Upload and reorder 1–8 video clips.
- Real between-clip xfade transitions: fade, smooth glide, slide, wipe, circle and hard cut.
- Upload a local soundtrack; loop it and duck under original voice audio.
- Screen-safe two-line captions and font sizing for long words.
- Contextual editorial titles and motion words above or around the subject.
- Optional real behind-person text using a locally generated portrait mask (MediaPipe, experimental).
- Upload licensed B-roll clips/images in the browser, add keyword tags, reuse the local asset library.
- No cloud model calls or Codex are required for rendering.

## Upgrade your existing installation

Run on your VPS as root, without re-running the original installer:

```bash
cd /opt/reel_editor
git -c safe.directory=/opt/reel_editor pull --ff-only origin main
.venv/bin/python -m pip install -r requirements.txt
systemctl restart reel-editor
curl -s http://127.0.0.1:8765/api/health
curl -s http://127.0.0.1:8765/api/studio/options
```

Access it through your existing SSH tunnel: http://localhost:8765

## Enable optional local depth masking

To enable the experimental 'Text behind speaker' checkbox:

```bash
cd /opt/reel_editor
.venv/bin/python -m pip install -r requirements-depth.txt
systemctl restart reel-editor
```

This requires extra CPU/RAM, supports reels up to 45 seconds, and may produce imperfect hair/hand edges. It is disabled by default and does not call paid services. If the optional dependency cannot install on your Ubuntu/Python combination, leave the checkbox off; all other editor features still work.

## One-time opt-in GitHub → VPS automatic code sync

```bash
cd /opt/reel_editor
bash scripts/enable_auto_sync.sh
systemctl list-timers reel-editor-sync.timer
```

The timer is a short-lived oneshot every ~10 minutes, NOT a permanently running polling service. It:

1. Checks for dirty tracked files (refuses to overwrite VPS edits).
2. Fetches private GitHub main; safely fails if unattended GitHub credentials are missing.
3. Allows fast-forward updates only.
4. Refuses to restart while the editor reports an active render.
5. Runs tests as the unprivileged reel-editor account and restarts ONLY reel-editor.service.
6. Attempts rollback to the previous commit if tests or health checks fail.

The timer does not modify OpenClaw, nginx, WhatsApp, HMS, AdsManagerOS, Dr.irizz, Ollama or databases. It does not sync video files, local assets or secrets TO GitHub; only code updates FROM GitHub to the VPS.

Important: The timer needs noninteractive, read-only access to your private GitHub repo. If git fetch fails, configure a repo-specific read-only deploy key or another secure credential mechanism. Never commit or paste credentials into this repository.

```bash
journalctl -u reel-editor-sync.service -n 60 --no-pager
systemctl disable --now reel-editor-sync.timer  # disable anytime
```

## Test in the browser

Upload two short video clips, reorder them, select Medical Clean and Fade, add your own licensed soundtrack, choose Editorial titles and render. The output should show a real clip transition, text animation and music beneath the original voice.

For automatic B-roll, add locally licensed videos or images through the B-roll upload area, with meaningful tags. If the library is empty, the editor will not invent B-roll assets.

## Limits

Up to 8 clips, maximum 180 seconds and 500 MB total uploaded media; one active job at a time. The browser has no public authentication, so keep the service bound to localhost. Genuine behind-person segmentation remains an optional experimental feature. The alpha-compositing operation is synthetic-test verified, not visually verified on your particular real footage. No frame-accurate manual timeline or beat-aware automatic cutting yet.