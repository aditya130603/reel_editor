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
from motion_component_pack import PACKS, plan_components, render_components
from agency_director import PROFILES, plan as agency_plan, caption_config, broll_config
from agency_captions import make_subs
from agency_fx import render_fx
from agency_sfx import write_cues, add_effect_sound
from studio_pipeline import (
    CLIP_TRANSITIONS, TITLE_EFFECTS, normalize_clips, join_clips,
    mix_music, drawtext_filters,
)

router = APIRouter()
ALLOWED_MUSIC = {".mp3", ".m4a", ".wav", ".flac", ".ogg"}
MUSIC_DIR = Path(__file__).resolve().parent / "assets" / "music"


def process_studio(job_id: str, video_paths: list[Path], soundtrack: Path | None,
                   preset: str, captions: str | None, clip_transition: str,
                   title_effect: str, music_volume: float,
                   subject_depth: bool = False, motion_pack: str = "editorial_clean",
                   agency_preset: str | None = None) -> None:
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
            ass = folder / "captions.ass"
            agency_events = []
            if agency_preset in PROFILES:
                profile = PROFILES[agency_preset]
                settings = dict(core.presets()[profile["base_preset"]])
                settings.update(broll_config(agency_preset))
                settings["sfx"] = False
                timeline = make_subs(words, caption_config(agency_preset), ass,
                                     core.RENDER_WIDTH, core.RENDER_HEIGHT)
                # Whole edit determined by ONE profile. Never stack arbitrary
                # template graphics over captions, or over the speaker's face.
                titles, title_events = [], []
                agency_events = agency_plan(words, duration, agency_preset)
                motion_media = render_fx(agency_events, folder)
            else:
                settings = dict(core.presets()[preset])
                if captions in core.STYLES:
                    settings["caption_style"] = captions
                settings["words_per_card"] = min(4, max(1, int(settings.get("words_per_card", 4))))
                settings["size"] = min(66, max(38, int(settings.get("size", 58))))
                timeline = core.make_ass(words, settings, ass)
                titles, title_events = drawtext_filters(
                    words, title_effect, folder, core.RENDER_WIDTH, core.RENDER_HEIGHT)
                if motion_pack != "off":
                    titles, title_events = [], []
                motion_cues = plan_components(words, motion_pack, duration)
                motion_media = render_components(motion_cues, folder,
                                                 core.RENDER_WIDTH, core.RENDER_HEIGHT)
            broll = core.select_broll(words, settings, duration) if words else []
            matte = None
            if subject_depth and (title_events or motion_media):
                core.status(job_id, state="masking", message="Segmenting speaker locally (experimental)")
                from subject_depth import create_person_mask
                matte = create_person_mask(merged, folder, duration,
                                           core.RENDER_WIDTH, core.RENDER_HEIGHT)
            core.status(job_id, state="rendering", message="Rendering titles, captions and B-roll",
                        titles_count=len(title_events)+len(motion_media),
                        broll_count=len(broll))
            has_fx_audio = bool(agency_events and core.probe(merged)["has_audio"])
            intermediate = folder / ("video_before_fx.mp4" if has_fx_audio else
                                     "video_no_music.mp4" if soundtrack else "output.mp4")
            core.render(merged, ass, intermediate, settings, broll,
                        duration, core.probe(merged)["has_audio"], titles, matte, motion_media)
            mixed = intermediate
            if has_fx_audio:
                sound = folder / "visual_cues.wav"
                if write_cues(agency_events, duration, sound):
                    mixed = folder / ("video_no_music.mp4" if soundtrack else "output.mp4")
                    core.status(job_id, state="mixing", message="Adding synchronized shutter and paper sound cues")
                    add_effect_sound(intermediate, sound, mixed, timeout=core.FFMPEG_TIMEOUT)
                else:
                    mixed = intermediate
            if soundtrack:
                core.status(job_id, state="mixing", message="Ducking music beneath speech")
                mix_music(mixed, soundtrack, folder / "output.mp4",
                          volume=PROFILES[agency_preset]["music_volume"] if agency_preset in PROFILES else music_volume,
                          timeout=core.FFMPEG_TIMEOUT)
            elif mixed != folder / "output.mp4":
                mixed.replace(folder / "output.mp4")
            plan = {
                "clips": [p.name for p in video_paths], "preset": preset,
                "clip_transition": clip_transition, "title_style": title_effect,
                "titles": title_events, "motion_pack": motion_pack,
                "agency_preset": agency_preset,
                "agency_fx": agency_events,
                "motion_components": [{k:v for k,v in item.items() if k != "path"}
                                       for item in motion_media],
                "captions": timeline,
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
        for p in folder.glob("fx_asset_*.mov"):
            p.unlink(missing_ok=True)
        for p in folder.glob("motion_component_*.mov"):
            p.unlink(missing_ok=True)
        for p in folder.glob("normalized_*.mp4"):
            p.unlink(missing_ok=True)
        for p in folder.glob("clip_*.mp4"):
            p.unlink(missing_ok=True)
        for name in ("merged.mp4", "video_no_music.mp4"):
            (folder / name).unlink(missing_ok=True)
        for p in video_paths:
            p.unlink(missing_ok=True)
        if soundtrack and soundtrack.parent == folder:
            soundtrack.unlink(missing_ok=True)


@router.get("/api/studio/music")
def music_library() -> dict:
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    return {"tracks": [p.name for p in sorted(MUSIC_DIR.iterdir())
                       if p.is_file() and p.suffix.lower() in ALLOWED_MUSIC]}


@router.get("/api/studio/agency-presets")
def agency_presets() -> dict:
    return {key:{"name":value["name"],"description":value["description"]}
            for key,value in PROFILES.items()}


@router.get("/api/studio/options")
def options() -> dict:
    from caption_motion import STYLES
    return {"clip_transitions": CLIP_TRANSITIONS, "title_effects": TITLE_EFFECTS,
            "motion_packs": PACKS,
            "captions": STYLES}


@router.post("/api/studio/jobs")
async def create_studio_job(
    videos: list[UploadFile] = File(...),
    music: UploadFile | None = File(None),
    music_track: str | None = Form(None),
    preset: str = Form("medical_clean"),
    caption_style: str | None = Form(None),
    clip_transition: str = Form("fade"),
    title_effect: str = Form("editorial"),
    music_volume: float = Form(.12),
    subject_depth: bool = Form(False),
    motion_pack: str = Form("editorial_clean"),
    agency_preset: str | None = Form(None)
) -> dict:
    import app as core
    if not 1 <= len(videos) <= 8:
        raise HTTPException(400, "Select 1–8 video clips")
    if any(Path(v.filename or "").suffix.lower() not in core.SUPPORTED_VIDEO for v in videos):
        raise HTTPException(400, "Only MP4, MOV, MKV or WebM video clips")
    if music and music_track:
        raise HTTPException(400, "Choose either uploaded music or a library track")
    if music_track and (Path(music_track).name != music_track
                        or not (MUSIC_DIR / music_track).is_file()
                        or Path(music_track).suffix.lower() not in ALLOWED_MUSIC):
        raise HTTPException(400, "Unknown or unsafe music-library track")
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
    if motion_pack not in PACKS:
        raise HTTPException(400, "Unknown motion pack")
    if agency_preset and agency_preset not in PROFILES:
        raise HTTPException(400,"Unknown agency preset")
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
        elif music_track:
            soundtrack = MUSIC_DIR / music_track
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
              clip_transition, title_effect, music_volume, subject_depth, motion_pack, agency_preset),
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
