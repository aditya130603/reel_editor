#!/usr/bin/env bash
# Installs Reel Editor alongside OpenClaw on the SAME Linux VPS.
# Run explicitly as root from an existing checkout (which may be private).
# Does not alter OpenClaw or any other systemd service.
set -euo pipefail
[[ "${EUID}" -eq 0 ]] || { echo "Run as root: sudo bash scripts/install_same_vps.sh" >&2; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
APP_USER="reel-editor"
PORT="${REEL_EDITOR_PORT:-8765}"
[[ "${PORT}" =~ ^[0-9]+$ ]] && ((PORT > 1023 && PORT < 65536)) || { echo "Invalid port" >&2; exit 1; }
if ss -ltn "( sport = :${PORT} )" | grep -q ":${PORT}"; then
  echo "Port ${PORT} already in use; choose another REEL_EDITOR_PORT." >&2
  exit 1
fi
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || {
  echo "Install ffmpeg with libass first. Existing services were not changed." >&2; exit 1;
}
# Capture the output first: grep -q piped under pipefail can produce a
# false failure when FFmpeg gets SIGPIPE after grep exits early.
FILTER_OUTPUT="$(ffmpeg -hide_banner -filters 2>&1)" || {
  echo "Unable to inspect FFmpeg filters." >&2; exit 1;
}
if ! grep -Eq '^[[:space:].A-Z]+[[:space:]]+subtitles[[:space:]]' <<< "$FILTER_OUTPUT"; then
  echo "FFmpeg has no libass subtitles/ass filter. Check: ffmpeg -hide_banner -filters | grep -E 'subtitles|ass'" >&2
  echo "Existing production services were not changed." >&2
  exit 1
fi
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd is required" >&2; exit 1; }
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/reel-editor --create-home --shell /usr/sbin/nologin "$APP_USER"
fi
mkdir -p "$ROOT/data" "$ROOT/assets/broll" "$ROOT/assets/fonts" "$ROOT/assets/sfx" /var/lib/reel-editor/.cache
# Don't change ownership of system directories such as /home/openclaw itself.
chown -R "$APP_USER:$APP_USER" "$ROOT" /var/lib/reel-editor
if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
fi
chown "$APP_USER:$APP_USER" "$ROOT/.env"
chmod 600 "$ROOT/.env"
runuser -u "$APP_USER" -- python3 -m venv "$ROOT/.venv"
runuser -u "$APP_USER" -- "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
runuser -u "$APP_USER" -- "$ROOT/.venv/bin/python" -m compileall -q "$ROOT/app.py" "$ROOT/caption_motion.py" "$ROOT/broll_matcher.py"
(cd "$ROOT" && runuser -u "$APP_USER" -- "$ROOT/.venv/bin/python" -m unittest discover -s tests -v)
UNIT=/etc/systemd/system/reel-editor.service
if [[ -f "$UNIT" ]]; then
  echo "Existing $UNIT found; not overwriting. Check it manually." >&2
  exit 1
fi
cat > "$UNIT" <<EOF
[Unit]
Description=Reel Editor (local API for OpenClaw Motion Graphics)
After=network.target
[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$ROOT
EnvironmentFile=$ROOT/.env
Environment=HF_HOME=/var/lib/reel-editor/.cache/huggingface
Environment=XDG_CACHE_HOME=/var/lib/reel-editor/.cache
ExecStart=$ROOT/.venv/bin/uvicorn app:app --host 127.0.0.1 --port $PORT --workers 1
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
KillMode=control-group
CPUQuota=150%
MemoryMax=4G
TasksMax=70
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=false
ReadWritePaths=$ROOT/data $ROOT/assets $ROOT/.env /var/lib/reel-editor
UMask=0077
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now reel-editor.service
echo "Reel Editor is installed on the SAME VPS, localhost:$PORT only."
echo "Gateway 18789 and all existing OpenClaw services remain untouched."
echo "Check: systemctl status reel-editor --no-pager; curl http://127.0.0.1:$PORT/api/health"
echo "For browser access use SSH tunneling or an existing authenticated reverse proxy."
