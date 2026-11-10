"""Local-first preset reel editor. No Codex, cloud inference, or external API calls."""
from __future__ import annotations

import json
import gc
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from caption_motion import STYLES, render_ass
TRANSITIONS = {"soft_fade": "Subtle crossfade", "slide_left": "Glide in from right", "slide_right": "Glide in from left", "slide_up": "Glide in from bottom", "slide_down": "Glide in from top", "hard_cut": "Clean cut with no fade"}
from broll_matcher import catalog as broll_catalog, choose as choose_broll

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ASSETS = ROOT / "assets" / "broll"
SFX_DIR = ROOT / "assets" / "sfx"
PRESETS = ROOT / "presets.json"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
RENDER_HEIGHT = int(os.getenv("RENDER_HEIGHT", "1280"))
RENDER_WIDTH = int(os.getenv("RENDER_WIDTH", "720"))
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "int8")
MAX_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SECONDS", "180"))
FFMPEG_TIMEOUT = int(os.getenv("FFMPEG_TIMEOUT", "900"))
REEL_FONTDIR = os.getenv("REEL_FONTDIR", str(ROOT / "assets" / "fonts"))
SUPPORTED_VIDEO = {".mp4", ".mov", ".mkv", ".webm"}
SUPPORTED_BROLL = SUPPORTED_VIDEO | {".png", ".jpg", ".jpeg", ".webp"}
STOPWORDS = set("a an the and or if but to from for with at by of in on is are was were be been being it this that those these i you we they he she as do does did have has had my your our their so can will would should could not no yes just like very more some there then than what when where why how who which all about into out up down".split())
jobs: dict[str, dict[str, Any]] = {}
lock = threading.Lock()
render_lock = threading.Lock()
transcription_lock = threading.Lock()
_whisper = None

for directory in (DATA, ASSETS, SFX_DIR, Path(REEL_FONTDIR)):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Reel Editor", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def presets() -> dict:
    return json.loads(PRESETS.read_text(encoding="utf-8"))


def status(job_id: str, **update: Any) -> None:
    with lock:
        jobs[job_id].update(update)
        snapshot = dict(jobs[job_id])
    # Persist job state so an idle auto-sync restart does not lose downloads.
    folder = DATA / job_id
    if folder.exists():
        tmp = folder / "job.json.tmp"
        tmp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        tmp.replace(folder / "job.json")


def cmd(args: list[str], timeout: int = 60) -> str:
    process = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    if process.returncode:
        raise RuntimeError((process.stderr or process.stdout)[-3500:])
    return process.stdout


def probe(path: Path) -> dict:
    raw = cmd(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
               "-of", "json", str(path)])
    data = json.loads(raw)
    return {"duration": float(data.get("format", {}).get("duration") or 0),
            "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
            "has_video": any(s.get("codec_type") == "video" for s in data.get("streams", []))}


def verify_tools() -> dict:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return {"ready": False, "reason": "ffmpeg and ffprobe must be installed"}
    filters = cmd([ffmpeg, "-hide_banner", "-filters"], 20)
    has_ass = "subtitles" in filters and "overlay" in filters
    return {"ready": has_ass, "ffmpeg": ffmpeg, "libass": has_ass,
            "whisper_model": WHISPER_MODEL, "device": WHISPER_DEVICE,
            "reason": "" if has_ass else "FFmpeg requires libass subtitle support"}


def whisper_words(video: Path) -> list[dict]:
    global _whisper
    with transcription_lock:
        if _whisper is None:
            from faster_whisper import WhisperModel
            _whisper = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE,
                                    compute_type=WHISPER_COMPUTE)
        segments, _ = _whisper.transcribe(str(video), beam_size=3, word_timestamps=True,
                                          vad_filter=True, condition_on_previous_text=False)
        words = []
        for seg in segments:
            for w in seg.words or []:
                token = w.word.strip()
                if token:
                    words.append({"start": max(0, round(w.start, 3)),
                                  "end": max(0, round(w.end, 3)), "text": token})
        if not words:
            raise RuntimeError("No speech detected; try a reel with clear audio.")
        return words


def phrase_groups(words: list[dict], max_words: int) -> list[list[dict]]:
    groups = []
    part = []
    for w in words:
        if part and (w["start"] - part[-1]["end"] > 0.62 or len(part) >= max_words):
            groups.append(part)
            part = []
        part.append(w)
        if re.search(r"[.!?]$", w["text"]) and len(part) >= 2:
            groups.append(part)
            part = []
    if part:
        groups.append(part)
    return groups


def emphasis_index(group: list[dict], every: int) -> int | None:
    if not group:
        return None
    candidates = [(i, len(re.sub(r"[^a-zA-Z]", "", w["text"])))
                  for i, w in enumerate(group)
                  if w["text"].strip(".,!?;:'\"").lower() not in STOPWORDS]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[1])[0]


def ass_color(rgb: str) -> str:
    rgb = rgb.lstrip("#").upper()
    if not re.fullmatch(r"[A-F0-9]{6}", rgb):
        rgb = "FFFFFF"
    return "&H00" + rgb[4:6] + rgb[2:4] + rgb[0:2]


def ass_time(seconds: float) -> str:
    centis = max(0, round(seconds * 100))
    return f"{centis // 360000}:{(centis // 6000) % 60:02}:{(centis // 100) % 60:02}.{centis % 100:02}"


def escape_ass(text: str) -> str:
    return text.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", " ")


def make_ass(words: list[dict], preset: dict, path: Path) -> list[dict]:
    """Compatibility layer: v2 caption motion engine."""
    return render_ass(words, preset, path, RENDER_WIDTH, RENDER_HEIGHT)


def load_assets() -> list[dict]:
    return broll_catalog(ASSETS)


def select_broll(words: list[dict], preset: dict, video_duration: float) -> list[dict]:
    return choose_broll(words, preset, video_duration, ASSETS)


def filter_path(path: Path) -> str:
    # Escape for FFmpeg filter arguments (not for shell: subprocess uses an argv list).
    s = str(path.absolute()).replace("\\", "/")
    return s.replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")


def render(video: Path, ass: Path, output: Path, preset: dict,
           broll: list[dict], duration: float, has_audio: bool,
           title_filters: list[str] | None = None,
           subject_mask: Path | None = None) -> None:
    args = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", str(video)]
    for item in broll:
        if item['asset'].suffix.lower() in SUPPORTED_VIDEO:
            args += ["-stream_loop", "-1", "-i", str(item['asset'])]
        else:
            args += ["-loop", "1", "-framerate", "30", "-i", str(item['asset'])]
    # Optional licensed local sound effects on B-roll cuts; otherwise no SFX inputs.
    sound = SFX_DIR / Path(str(preset.get("sfx_file", "soft_whoosh.wav"))).name
    with_sfx = bool(has_audio and broll and preset.get("sfx", False)
                    and sound.suffix.lower() in {".wav", ".mp3", ".ogg"}
                    and sound.is_file())
    if with_sfx:
        for _ in broll:
            args += ["-i", str(sound)]
    if subject_mask:
        args += ["-i", str(subject_mask)]
    # The base keeps original speech audio, while short keyword-matched cutaways
    # appear using alpha fades. Captions are overlaid LAST so they remain visible.
    scale = (f"scale={RENDER_WIDTH}:{RENDER_HEIGHT}:force_original_aspect_ratio=increase,"
             f"crop={RENDER_WIDTH}:{RENDER_HEIGHT},setsar=1,fps=30")
    if subject_mask:
        filters = [f"[0:v]split=2[scene_src][person_src]",
                   f"[scene_src]{scale},{preset['grading']},format=yuv420p[base0]"]
    else:
        filters = [f"[0:v]{scale},{preset['grading']},format=yuv420p[base0]"]
    previous = "base0"
    for i, item in enumerate(broll, start=1):
        at, dur = item["start"], item["duration"]
        transition = min(float(preset["transition"]), dur / 3)
        if preset.get("transition_style") == "hard_cut":
            transition = .001
        # Trim before timeline offset; transparent in/out avoids hard changes.
        motion = str(preset.get("broll_motion", "slow_push"))
        lead = f"[{i}:v]{scale}"
        if item["asset"].suffix.lower() not in SUPPORTED_VIDEO and motion != "none":
            motions = {
                "slow_push": ("min(1.0+on*0.0008,1.07)",
                              "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
                "slow_pull": ("max(1.0,1.07-on*0.0008)",
                              "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
                "pan_left": ("1.06", "max(0,(iw-iw/zoom)*(1-on/120))",
                             "ih/2-(ih/zoom/2)"),
                "pan_right": ("1.06", "min(iw-iw/zoom,(iw-iw/zoom)*on/120)",
                              "ih/2-(ih/zoom/2)"),
            }
            z, x_motion, y_motion = motions.get(motion, motions["slow_push"])
            lead += (f",zoompan=z='{z}':x='{x_motion}':y='{y_motion}':"
                     f"d=1:s={RENDER_WIDTH}x{RENDER_HEIGHT}:fps=30")
        filters.append(
            lead + f",trim=duration={dur:.3f},setpts=PTS-STARTPTS,"
            f"format=yuva420p,fade=t=in:st=0:d={transition:.3f}:alpha=1,"
            f"fade=t=out:st={dur-transition:.3f}:d={transition:.3f}:alpha=1,"
            f"setpts=PTS+{at:.3f}/TB[cut{i}]"
        )
        transition_style = preset.get("transition_style", "soft_fade")
        # Slide is evaluated on global timeline t; source PTS is offset to at.
        if transition_style == "slide_left":
            x = f"max(0,W*(1-(t-{at:.3f})/{transition:.3f}))"
        elif transition_style == "slide_right":
            x = f"min(0,-W*(1-(t-{at:.3f})/{transition:.3f}))"
        else:
            x = "0"
        if transition_style == "slide_up":
            y = f"max(0,H*(1-(t-{at:.3f})/{transition:.3f}))"
        elif transition_style == "slide_down":
            y = f"min(0,-H*(1-(t-{at:.3f})/{transition:.3f}))"
        else:
            y = "0"
        filters.append(f"[{previous}][cut{i}]overlay=x='{x}':y='{y}':"
                       f"eof_action=pass:shortest=0:format=auto[base{i}]")
        previous = f"base{i}"
    if title_filters:
        filters.append(f"[{previous}]" + ",".join(title_filters) + "[graphics]")
        previous = "graphics"
    if subject_mask and title_filters:
        # Input order: main video, B-roll, optional SFX, then mask.
        mask_idx = 1 + len(broll) + (len(broll) if with_sfx else 0)
        filters.append(f"[person_src]{scale},format=rgba[person_rgba]")
        filters.append(f"[{mask_idx}:v]scale={RENDER_WIDTH}:{RENDER_HEIGHT},"
                       "format=gray[mask_gray]")
        filters.append("[person_rgba][mask_gray]alphamerge[person_front]")
        filters.append(f"[{previous}][person_front]overlay=x=0:y=0:"
                       "eof_action=pass:shortest=0:format=auto[composited]")
        previous = "composited"
    filters.append(f"[{previous}]format=yuv420p,subtitles='{filter_path(ass)}':"
                   f"fontsdir='{filter_path(Path(REEL_FONTDIR))}'[finished]")
    if with_sfx:
        filters.append("[0:a:0]aresample=48000,aformat=channel_layouts=stereo[dialogue]")
        parts = ["[dialogue]"]
        volume = max(0.0, min(0.22, float(preset.get("sfx_volume", .09))))
        for i, item in enumerate(broll):
            n = 1 + len(broll) + i
            delay_ms = max(0, int(1000 * item["start"]))
            filters.append(f"[{n}:a]atrim=duration=0.55,asetpts=PTS-STARTPTS,"
                           f"aresample=48000,aformat=channel_layouts=stereo,"
                           f"volume={volume:.3f},afade=t=out:st=0.36:d=0.19,"
                           f"adelay={delay_ms}:all=1[sound{i}]")
            parts.append(f"[sound{i}]")
        filters.append("".join(parts) + f"amix=inputs={len(parts)}:"
                       "duration=first:dropout_transition=0[mixed]")
    args += ["-filter_complex", ";".join(filters), "-map", "[finished]"]
    if has_audio:
        args += ["-map", "[mixed]" if with_sfx else "0:a:0",
                 "-c:a", "aac", "-b:a", "160k"]
    else:
        args += ["-an"]
    args += ["-threads", os.getenv("FFMPEG_THREADS", "2"), "-filter_complex_threads", "2", "-c:v", "libx264", "-preset", os.getenv("ENCODE_PRESET", "veryfast"),
             "-crf", os.getenv("ENCODE_CRF", "21"), "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", "-t", f"{duration:.3f}", str(output)]
    cmd(args, timeout=FFMPEG_TIMEOUT)


def execute(job_id: str, filename: str, key: str, caption_style: str | None = None, transition_style: str | None = None) -> None:
    folder = DATA / job_id
    input_file = folder / "input.mp4"
    try:
        # Single active job: no unbounded render workers or model contention.
        status(job_id, state="queued", message="Waiting for the local rendering slot")
        with render_lock:
            status(job_id, state="analyzing", message="Inspecting source video")
            info = probe(input_file)
            if not info["has_video"] or info["duration"] < 0.5:
                raise RuntimeError("Source file has no usable video stream")
            if info["duration"] > MAX_DURATION_SECONDS:
                raise RuntimeError(f"Video must be at most {MAX_DURATION_SECONDS} seconds")
            if not info["has_audio"]:
                raise RuntimeError("Speech track required for automatic captions")
            status(job_id, state="transcribing", message="Transcribing with local faster-whisper")
            words = whisper_words(input_file)
            # Free Whisper weights and thread resources after transcription.
            if os.getenv("WHISPER_KEEP_WARM", "0") != "1":
                global _whisper
                _whisper = None
                gc.collect()
            settings = dict(presets()[key])
            if caption_style in STYLES:
                settings["caption_style"] = caption_style
            if transition_style in TRANSITIONS:
                settings["transition_style"] = transition_style
            ass = folder / "captions.ass"
            timeline = make_ass(words, settings, ass)
            selected = select_broll(words, settings, info["duration"])
            (folder / "edit_plan.json").write_text(json.dumps({
                "preset": key, "source": filename, "timeline": timeline,
                "broll": [{**{k: v for k, v in item.items() if k != "asset"}} for item in selected]
            }, indent=2), encoding="utf-8")
            status(job_id, state="rendering", message="Applying captions, grading and B-roll",
                   broll_count=len(selected))
            render(input_file, ass, folder / "output.mp4", settings, selected,
                   info["duration"], info["has_audio"])
            status(job_id, state="completed", message="Rendered locally", url=f"/api/jobs/{job_id}/download",
                   plan_url=f"/api/jobs/{job_id}/plan")
    except Exception as exc:
        status(job_id, state="failed", message=str(exc)[-700:])
    finally:
        # Do not keep raw uploads after a successful edit. Keep outputs for download.
        if jobs[job_id]["state"] == "completed":
            input_file.unlink(missing_ok=True)


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "studio.html")


@app.get("/api/health")
def health() -> dict:
    return verify_tools()


@app.get("/api/admin/busy")
def editor_busy() -> dict:
    # Loopback-only status for the safe self-update timer.
    with lock:
        return {"busy": any(j["state"] not in {"completed", "failed"} for j in jobs.values())}


@app.get("/api/presets")
def get_presets() -> dict:
    return presets()


@app.get("/api/caption-styles")
def get_caption_styles() -> dict:
    return STYLES


@app.get("/api/transitions")
def get_transition_styles() -> dict:
    return TRANSITIONS


@app.get("/api/assets")
def get_assets() -> list[dict]:
    return [{"name": a["name"], "tags": a["tags"]} for a in load_assets()]


@app.post("/api/jobs")
async def create_job(video: UploadFile = File(...), preset: str = Form("medical_clean"),
                     caption_style: str | None = Form(None),
                     transition_style: str | None = Form(None)) -> dict:
    if preset not in presets():
        raise HTTPException(400, "Unknown preset")
    if caption_style and caption_style not in STYLES:
        raise HTTPException(400, "Unknown caption style")
    if transition_style and transition_style not in TRANSITIONS:
        raise HTTPException(400, "Unknown transition style")
    if Path(video.filename or "").suffix.lower() not in SUPPORTED_VIDEO:
        raise HTTPException(400, "Only MP4, MOV, MKV or WebM videos are supported")
    check = verify_tools()
    if not check["ready"]:
        raise HTTPException(503, check["reason"])
    # Reserve the only available slot BEFORE reading the upload.
    job_id = uuid.uuid4().hex
    with lock:
        if any(j["state"] not in {"completed", "failed"} for j in jobs.values()):
            raise HTTPException(429, "Editor busy: finish the current job first")
        jobs[job_id] = {"id": job_id, "state": "uploading", "message": "Receiving video",
                        "preset": preset,
                        "created_at": datetime.now(timezone.utc).isoformat()}
    folder = DATA / job_id
    folder.mkdir(parents=True)
    target = folder / "input.mp4"
    size = 0
    try:
        with target.open("wb") as out:
            while part := await video.read(1024 * 1024):
                size += len(part)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(413, "Upload exceeds MAX_UPLOAD_MB")
                out.write(part)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        with lock:
            jobs.pop(job_id, None)
        raise
    status(job_id, state="queued", message="Accepted")
    thread = threading.Thread(target=execute, args=(job_id, video.filename or "reel", preset, caption_style, transition_style),
                              daemon=True)
    thread.start()
    return {"id": job_id, "state": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(404, "Unknown job")
    with lock:
        found = jobs.get(job_id)
        if found is not None:
            return dict(found)
    record = DATA / job_id / "job.json"
    if record.is_file():
        try:
            return json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    raise HTTPException(404, "Unknown job")


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str) -> FileResponse:
    output = DATA / job_id / "output.mp4"
    if get_job(job_id).get("state") != "completed" or not output.exists():
        raise HTTPException(404, "Output not ready")
    return FileResponse(output, filename=f"edited_{job_id[:8]}.mp4", media_type="video/mp4")


@app.get("/api/jobs/{job_id}/plan")
def download_plan(job_id: str) -> FileResponse:
    output = DATA / job_id / "edit_plan.json"
    if get_job(job_id).get("state") != "completed" or not output.exists():
        raise HTTPException(404, "Plan not ready")
    return FileResponse(output, filename=f"edit_plan_{job_id[:8]}.json")


@app.get("/api/jobs/{job_id}/captions")
def download_captions(job_id: str) -> FileResponse:
    output = DATA / job_id / "captions.ass"
    if job_id not in jobs or not output.exists():
        raise HTTPException(404, "Captions not ready")
    return FileResponse(output, filename=f"captions_{job_id[:8]}.ass")


# Studio V2 routes are separate to retain the original single-file API.
from studio_routes import router as studio_router
# Register concrete routes directly. Works consistently with new FastAPI router versions.
for studio_route in studio_router.routes:
    app.add_api_route(studio_route.path, studio_route.endpoint,
                      methods=list(studio_route.methods or {"GET"}),
                      name=studio_route.name)
