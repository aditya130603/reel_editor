#!/usr/bin/env bash
# Offline-first reel editor setup. Does not start or modify any systemd service.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  echo "ERROR: FFmpeg/ffprobe not installed. Install distro ffmpeg with libass first." >&2
  exit 1
fi
# Don't combine grep -q with pipefail: FFmpeg may see SIGPIPE and trigger
# a false failure when the filter is actually present.
FILTER_OUTPUT="$(ffmpeg -hide_banner -filters 2>&1)" || {
  echo "ERROR: Could not inspect FFmpeg filters." >&2
  exit 1
}
if ! grep -Eq '^[[:space:].A-Z]+[[:space:]]+(subtitles|ass)[[:space:]]' <<< "$FILTER_OUTPUT"; then
  echo "ERROR: FFmpeg lacks the libass subtitles/ass filter." >&2
  exit 1
fi
if ! command -v python3 >/dev/null; then
  echo "ERROR: python3 is required." >&2
  exit 1
fi
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
mkdir -p data assets/broll assets/sfx assets/fonts
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
set -a
. ./.env
set +a
python -m compileall -q app.py caption_motion.py broll_matcher.py
python -m unittest discover -s tests -v
echo
echo "Setup and smoke tests complete. Start locally with:"
echo "  cd $(pwd) && . .venv/bin/activate && set -a && . ./.env && set +a"
echo "  uvicorn app:app --host 127.0.0.1 --port 8765"
echo "Use an SSH tunnel or authenticated HTTPS proxy to access the UI."
echo "No existing production services or OpenClaw configuration were changed."
