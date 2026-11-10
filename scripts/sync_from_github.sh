#!/usr/bin/env bash
# Atomic-ish fast-forward deploy, ONLY for /opt/reel_editor.
# Timer starts this script, not a resident worker. Never touches OpenClaw.
set -euo pipefail
ROOT=/opt/reel_editor
UNIT=reel-editor.service
cd "$ROOT"
[[ "$EUID" -eq 0 ]] || { echo "Sync must be run by root via systemd"; exit 1; }
[[ -d .git && -x .venv/bin/python ]] || { echo "Not initialized"; exit 1; }
export GIT_TERMINAL_PROMPT=0
git_safe() { git -c safe.directory="$ROOT" -C "$ROOT" "$@"; }
# Fail closed when local tracked files were edited manually.
[[ -z "$(git_safe status --porcelain --untracked-files=no)" ]] || {
  echo "Local changes detected. Refusing to overwrite VPS edits."; exit 0;
}
BEFORE="$(git_safe rev-parse HEAD)"
if ! git_safe fetch --no-tags origin main; then
  echo "GitHub fetch failed. Check credentials/deploy key for private repository."
  exit 1
fi
AFTER="$(git_safe rev-parse refs/remotes/origin/main)"
[[ "$BEFORE" != "$AFTER" ]] || { echo "Already up to date."; exit 0; }
git_safe merge-base --is-ancestor "$BEFORE" "$AFTER" || {
  echo "Remote history diverged; refusing non-fast-forward update."; exit 1;
}
# Avoid interrupting a render; exit and allow the next timer tick to retry.
BUSY="$(curl --max-time 4 -fsS http://127.0.0.1:8765/api/admin/busy || echo unknown)"
[[ "$BUSY" == '{"busy":false}' ]] || {
  echo "Editor busy or health endpoint unavailable. Deferring update."; exit 0;
}
git_safe merge --ff-only "$AFTER"
rollback() {
  echo "Update failed; rolling back code to $BEFORE"
  git_safe reset --hard "$BEFORE"
  systemctl restart "$UNIT" || true
}
trap rollback ERR
runuser -u reel-editor -- "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
(cd "$ROOT" && runuser -u reel-editor -- "$ROOT/.venv/bin/python" -m compileall -q app.py caption_motion.py broll_matcher.py studio_pipeline.py studio_routes.py)
(cd "$ROOT" && runuser -u reel-editor -- "$ROOT/.venv/bin/python" -m unittest discover -s tests -q)
systemctl restart "$UNIT"
sleep 2
curl --max-time 10 -fsS http://127.0.0.1:8765/api/health | grep -q '"ready":true'
trap - ERR
echo "Reel Editor synced and restarted: $AFTER"
