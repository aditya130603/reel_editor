#!/usr/bin/env bash
# Explicit opt-in. This only enables a 10-minute oneshot timer.
set -euo pipefail
[[ "$EUID" -eq 0 ]] || { echo "Run with sudo" >&2; exit 1; }
cd /opt/reel_editor
install -m 0644 deploy/reel-editor-sync.service /etc/systemd/system/reel-editor-sync.service
install -m 0644 deploy/reel-editor-sync.timer /etc/systemd/system/reel-editor-sync.timer
systemctl daemon-reload
systemctl enable --now reel-editor-sync.timer
echo "Automatic sync timer enabled. It will only update clean, idle editors and fast-forward GitHub main."
echo "Check: systemctl list-timers reel-editor-sync.timer"
echo "Disable: systemctl disable --now reel-editor-sync.timer"
