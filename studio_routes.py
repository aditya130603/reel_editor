"""Browser studio V2. Multiple video uploads and local music, zero cloud LLM calls."""
from __future__ import annotations

import gc
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from studio_pipeline import (
    CLIP_TRANSITIONS, TITLE_EFFECTS, normalize_clips, join_clips,
    mix_music, drawtext_filters,
)

router = APIRouter()
ALLOWED_MUSIC = {".mp3", ".m4a", ".wav", ".flac", ".ogg"}


def process_studio(job_id: str, video_paths: list[Path], soundtrack: Path | None,
                   preset: str, captions: str | None, clip_transition: str,
                   title_effect: str, music_volume: float,
                   subject_depth: bool = False) -> None:
    # Late import avoids circular dependency with FastAPI app.
    import app as core

    folder = core.DATA / job_id
    try:
        core.status(job_id, state="queued", message="Waiting for the local render slot")
        with core.render_lock:
            core.status(job_id, state="assembling", message="Normalizing and joining your clips")
            if len(video_paths) > 1:
                normalized, lengths = normalize_clips(
                    video_paths, folder, core.RENDER_WIDTH, core.RENDER_HEIGHT,
                    core.FFMPEG_TIMEOUT, lambda p: core.probe(p)["has_audio"])
                if sum(lengths) > core.MAX_DURATION_SECONDS + (len(lengths)-1)*.6:
                    raise RuntimeError("Combined video exceeds the configured maximum duration")
                merged = folder / "merged.mp4"
                duration = join_clips(normalized, lengths, merged,
                                      clip_transition, timeout=core.FFMPEG_TIMEOUT)
            else:
                merged = video_paths[0]
                duration = core.probe(merged)["duration"]
            if duration > core.MAX_DURATION_SECONDS:
                raise RuntimeError(f"Maximum final duration is {core.MAX_DURATION_SECONDS}s")
            if duration < .6:
                raise RuntimeError("Video is too short")
            core.status(job_id, state="transcribing", message="Transcribing the combined reel locally")
            words = []
            if core.probe(merged)["has_audio"]:
                try:
                    words = core.whisper_words(merged)
                except RuntimeError as e:
                    if "No speech detected" not in str(e):
                        raise
            if os.getenv("WHISPER_KEEP_WARM", "0") != "1":
                core._whisper = None
                gc.collect()
            settings = dict(core.presets()[preset])
            if captions in core.STYLES:
                settings["caption_style"] = captions
            # Enforce safe font size and short captions on narrow portrait videos.
            settings["words_per_card"] = min(4, max(1, int(settings.get("words_per_card", 4))))
            settings["size"] = min(66, max(38, int(settings.get("size", 58))))
            ass = folder / "captions.ass"
            timeline = core.make_ass(words, settings, ass)
            broll = core.select_broll(words, settings, duration) if words else []
            titles, title_events = drawtext_filters(
                words, title_effect, folder, core.RENDER_WIDTH, core.RENDER_HEIGHT)
            matte = None
            if subject_depth and title_effect != "none" and title_events:
                core.status(job_id, state="masking", message="Segmenting speaker locally (experimental)")
                from subject_depth import create_person_mask
                matte = create_person_mask(merged, folder, duration,
                                           core.RENDER_WIDTH, core.RENDER_HEIGHT)
            core.status(job_id, state="rendering", message="Rendering titles, captions and B-roll",
                        titles_count=len(title_events), broll_count=len(broll))
            intermediate = folder / ("video_no_music.mp4" if soundtrack else "output.mp4")
            core.render(merged, ass, intermediate, settings, broll,
                        duration, core.probe(merged)["has_audio"], titles, matte)
            if soundtrack:
                core.status(job_id, state="mixing", message="Ducking music beneath speech")
                mix_music(intermediate, soundtrack, folder / "output.mp4",
                          music_volume, timeout=core.FFMPEG_TIMEOUT)
            plan = {
                "clips": [p.name for p in video_paths], "preset": preset,
                "clip_transition": clip_transition, "title_style": title_effect,
                "titles": title_events, "captions": timeline,
                "soundtrack": soundtrack.name if soundtrack else None,
                "broll": [{k: v for k, v in item.items() if k != "asset"} for item in broll],
            }
            (folder / "edit_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
            core.status(job_id, state="completed", message="Reel rendered",
                        url=f"/api/jobs/{job_id}/download",
                        plan_url=f"/api/jobs/{job_id}/plan",
                        titles_count=len(title_events), broll_count=len(broll))
    except Exception as error:
        core.status(job_id, state="failed", message=str(error)[-900:])
    finally:
        # Keep only output, captions and edit plan. Do not leave raw media on the VPS.
        for p in folder.glob("normalized_*.mp4"):
            p.unlink(missing_ok=True)
        for p in folder.glob("clip_*.mp4"):
            p.unlink(missing_ok=True)
        for name in ("merged.mp4", "video_no_music.mp4"):
            (folder / name).unlink(missing_ok=True)
        for p in video_paths:
            p.unlink(missing_ok=True)
        if soundtrack:
            soundtrack.unlink(missing_ok=True)


@router.get("/api/studio/options")
def options() -> dict:
    from caption_motion import STYLES
    return {"clip_transitions": CLIP_TRANSITIONS, "title_effects": TITLE_EFFECTS,
            "captions": STYLES}


@router.post("/api/studio/jobs")
async def create_studio_job(
    videos: list[UploadFile] = File(...),
    music: UploadFile | None = File(None),
    preset: str = Form("medical_clean"),
    caption_style: str | None = Form(None),
    clip_transition: str = Form("fade"),
    title_effect: str = Form("editorial"),
    music_volume: float = Form(.12),
    subject_depth: bool = Form(False)
) -> dict:
    import app as core
    if not 1 <= len(videos) <= 8:
        raise HTTPException(400, "Select 1–8 video clips")
    if any(Path(v.filename or "").suffix.lower() not in core.SUPPORTED_VIDEO for v in videos):
        raise HTTPException(400, "Only MP4, MOV, MKV or WebM video clips")
    if music and Path(music.filename or "").suffix.lower() not in ALLOWED_MUSIC:
        raise HTTPException(400, "Music must be MP3, WAV, OGG, M4A or FLAC")
    if preset not in core.presets():
        raise HTTPException(400, "Unknown preset")
    if caption_style and caption_style not in core.STYLES:
        raise HTTPException(400, "Unknown caption animation")
    if clip_transition not in CLIP_TRANSITIONS or title_effect not in TITLE_EFFECTS:
        raise HTTPException(400, "Unsupported transition or title effect")
    if subject_depth and title_effect == "none":
        raise HTTPException(400, "Subject depth requires a title effect")
    if not 0 <= music_volume <= .35:
        raise HTTPException(400, "Music volume must be 0–0.35")
    health = core.verify_tools()
    if not health["ready"]:
        raise HTTPException(503, health["reason"])
    job = uuid.uuid4().hex
    with core.lock:
        if any(j["state"] not in {"completed", "failed"} for j in core.jobs.values()):
            raise HTTPException(429, "Another reel is currently processing")
        core.jobs[job] = {
            "id": job, "state": "uploading", "preset": preset,
            "message": "Receiving media",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    folder = core.DATA / job
    folder.mkdir(parents=True, exist_ok=True)
    targets = []
    soundtrack = None
    total = 0
    try:
        queue = []
        for i, upload in enumerate(videos):
            p = folder / f"clip_{i:02d}.mp4"
            targets.append(p)
            queue.append((upload, p))
        if music:
            soundtrack = folder / ("soundtrack" + Path(music.filename or "").suffix.lower())
            queue.append((music, soundtrack))
        for upload, file in queue:
            with file.open("wb") as out:
                while chunk := await upload.read(1024 * 1024):
                    total += len(chunk)
                    if total > core.MAX_UPLOAD_MB * 1024 * 1024:
                        raise HTTPException(413, "Combined media exceeds the upload size limit")
                    out.write(chunk)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        with core.lock:
            core.jobs.pop(job, None)
        raise
    worker = threading.Thread(
        target=process_studio,
        args=(job, targets, soundtrack, preset, caption_style,
              clip_transition, title_effect, music_volume, subject_depth),
        daemon=True,
    )
    worker.start()
    return {"id": job, "state": "queued"}


@router.post("/api/studio/assets")
async def add_broll_assets(
    files: list[UploadFile] = File(...),
    tags: str = Form(""),
) -> dict:
    """Upload licensed local cutaways; no external image search or generation."""
    import app as core
    if not 1 <= len(files) <= 10:
        raise HTTPException(400, "Select 1–10 B-roll assets")
    if len(tags) > 250:
        raise HTTPException(400, "Tags field is too long")
    extra_tags = [t.strip() for t in re.split(r"[,;]", tags) if t.strip()]
    saved = []
    for upload in files:
        ext = Path(upload.filename or "").suffix.lower()
        if ext not in core.SUPPORTED_BROLL:
            raise HTTPException(400, "B-roll must be MP4, MOV, WebM, PNG, JPEG or WebP")
        stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(upload.filename or "").stem).strip("_")[:100]
        if not stem:
            raise HTTPException(400, "Invalid asset filename")
        target = core.ASSETS / (stem + ext)
        if target.exists():
            raise HTTPException(409, f"Asset {target.name} already exists")
        written = 0
        try:
            with target.open("xb") as out:
                while chunk := await upload.read(1024 * 1024):
                    written += len(chunk)
                    if written > 200 * 1024 * 1024:
                        raise HTTPException(413, "B-roll asset exceeds 200 MB")
                    out.write(chunk)
            # ffprobe handles both motion and still-image media; reject broken files.
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(target)],
                text=True, capture_output=True, timeout=20
            )
            if probe.returncode or "video" not in probe.stdout:
                raise HTTPException(400, f"Cannot decode B-roll file: {target.name}")
            if extra_tags:
                sidecar = target.with_name(target.name + ".json")
                sidecar.write_text(json.dumps({
                    "tags": extra_tags,
                    "description": "User-provided licensed B-roll"
                }), encoding="utf-8")
            saved.append(target.name)
        except Exception:
            target.unlink(missing_ok=True)
            raise
    return {"saved": saved, "asset_count": len(core.load_assets())}
