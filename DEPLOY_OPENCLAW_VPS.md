# Install alongside OpenClaw on the same VPS

**Architecture:** `OpenClaw (127.0.0.1:18789)` and `Reel Editor (127.0.0.1:8765)` are separate processes on the **same Hostinger VPS**. Motion Graphics calls Reel Editor via localhost; there is no second VPS, no Docker, no paid model and no new external API.

This design deliberately does not merge the Reel Editor runtime into the OpenClaw gateway process. A heavy FFmpeg render cannot crash the gateway just because it is running in a different service; CPU and memory are bounded by a dedicated systemd cgroup.

## Installation

On the VPS, using GitHub credentials that permit access to the private repository:

```bash
cd /opt
sudo git clone https://github.com/aditya130603/reel_editor.git
cd reel_editor
sudo bash scripts/install_same_vps.sh
```

If the repository is already cloned, run from its root:

```bash
sudo bash scripts/install_same_vps.sh
```

The script creates an unprivileged `reel-editor` account, installs dependencies into this project's venv, runs the smoke tests, and creates the `reel-editor.service` systemd service. It does not alter the gateway, its providers/keys, nginx or any production application. Existing service names are not reused. It refuses to replace an existing Reel Editor unit.

**Operational note:** run only after reviewing the script; it changes ownership of the checkout directory to the dedicated service account. Keep the repo under `/opt/reel_editor`, not inside `/home/openclaw`, so your OpenClaw files and secrets are never touched. The service writes only to Reel Editor paths and its own cache. The first Whisper model download may require internet; transcription and rendering thereafter run locally.

## API from Motion Graphics agent

```bash
curl -s http://127.0.0.1:8765/api/health
curl -s http://127.0.0.1:8765/api/presets
curl -s -F "video=@/path/to/reel.mp4" -F "preset=medical_clean" -F "caption_style=karaoke" http://127.0.0.1:8765/api/jobs
curl -s http://127.0.0.1:8765/api/jobs/<JOB_ID>
curl -L http://127.0.0.1:8765/api/jobs/<JOB_ID>/download -o output.mp4
```

To connect this with OpenClaw, give Motion Graphics permission to call the loopback endpoint and access its authorized media files. Don't expose the API publicly: it has no user authentication. Keep it behind localhost, SSH, or a separate authenticated reverse proxy.

## Resources and lifecycle

The systemd service uses one Uvicorn worker, `CPUQuota=150%`, `MemoryMax=4G`, `TasksMax=70`. FFmpeg threads are limited and only one job is accepted at a time. The server remains available for job submissions; render subprocesses exit upon completion. Whisper is released unless configured to stay warm. Change these cgroup caps if your total VPS memory or CPU allocation differs. A 4G cap may be insufficient for larger Whisper models.

```bash
systemctl status reel-editor --no-pager
journalctl -u reel-editor -n 100 --no-pager
systemctl restart reel-editor
systemctl stop reel-editor
```

**Not done from this chat:** the server is not actually installed, and OpenClaw agent configurations have not been edited. The GitHub repo includes the installer and API instructions for doing that safely.
