#!/usr/bin/env bash
# One-time release upgrade on SAME existing OpenClaw VPS.
# Only updates /opt/reel_editor and restarts reel-editor.service after tests.
set -euo pipefail
[[ "$EUID" -eq 0 ]] || { echo "Run as root/sudo" >&2; exit 1; }
ROOT=/opt/reel_editor
cd "$ROOT"
git_safe(){ git -c safe.directory="$ROOT" -C "$ROOT" "$@"; }
[[ -z "$(git_safe status --porcelain --untracked-files=no)" ]] || {
    echo "Tracked VPS changes exist. Refusing to overwrite them." >&2; exit 1;
}
if ! curl -fsS --max-time 5 http://127.0.0.1:8765/api/admin/busy | grep -Fq '"busy":false'; then
    echo "Editor is busy or unavailable. Do not restart during render." >&2
    exit 1
fi
BEFORE="$(git_safe rev-parse HEAD)"
git_safe fetch --no-tags origin main
AFTER="$(git_safe rev-parse refs/remotes/origin/main)"
if [[ "$BEFORE" == "$AFTER" ]]; then
    echo "Already latest. Checking tests and service configuration."
else
    git_safe merge-base --is-ancestor "$BEFORE" "$AFTER" || {
       echo "Cannot fast-forward. Review Git history manually." >&2; exit 1;
    }
    git_safe merge --ff-only "$AFTER"
fi
rollback(){
    echo "Upgrade failed; restoring previous commit" >&2
    git_safe reset --hard "$BEFORE" || true
}
trap rollback ERR
runuser -u reel-editor -- "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
(cd "$ROOT" && runuser -u reel-editor -- "$ROOT/.venv/bin/python" -m compileall -q \
 app.py studio_routes.py studio_pipeline.py agency_director.py agency_captions.py \
 agency_fx.py agency_sfx.py agency_music.py)
(cd "$ROOT" && runuser -u reel-editor -- "$ROOT/.venv/bin/python" -m unittest discover -s tests -q)
trap - ERR
systemctl restart reel-editor.service
curl --retry 5 --retry-delay 1 --max-time 6 -fsS http://127.0.0.1:8765/api/health
echo
echo "Agency V4 deployed on the SAME VPS, localhost:8765, gateway untouched."
echo "Visual review still required before treating presets as production quality."
