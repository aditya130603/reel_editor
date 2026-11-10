"""Local-first preset reel editor. No Codex, cloud inference, or external API calls."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ASSETS = ROOT / "assets" / "broll"
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

for directory in (DATA, ASSETS, Path(REEL_FONTDIR)):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Reel Editor", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def presets() -> dict:
    return json.loads(PRESETS.read_text(encoding="utf-8"))


def status(job_id: str, **update: Any) -> None:
    with lock:
        jobs[job_id].update(update)


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
    font_size = int(preset["size"]) * RENDER_HEIGHT / 1280
    margin_v = int(RENDER_HEIGHT * (1 - float(preset["caption_position"])))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {RENDER_WIDTH}
PlayResY: {RENDER_HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{preset["font"]},{font_size:.0f},{ass_color(preset["primary"])},{ass_color(preset["accent"])},&H00151515,&H96000000,1,0,0,0,100,100,0,0,1,{int(preset["outline"])},1,2,35,35,{margin_v},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    groups = phrase_groups(words, int(preset["words_per_card"]))
    lines = []
    for group in groups:
        winner = emphasis_index(group, int(preset["emphasis_every"]))
        parts = []
        for i, word in enumerate(group):
            t = escape_ass(word["text"])
            if i == winner:
                t = "{\\c" + ass_color(preset["accent"]) + "\\fscx108\\fscy108}" + t + "{\\r}"
            parts.append(t)
        start = group[0]["start"]
        end = max(start + 0.25, group[-1]["end"] + 0.08)
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Main,,0,0,0,,{' '.join(parts)}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return [{"start": g[0]["start"], "end": g[-1]["end"],
             "text": " ".join(w["text"] for w in g),
             "emphasis": g[emphasis_index(g, 3)]["text"] if emphasis_index(g, 3) is not None else None}
            for g in groups]


def load_assets() -> list[dict]:
    items = []
    for p in sorted(ASSETS.iterdir()):
        if p.is_file() and p.suffix.lower() in SUPPORTED_BROLL:
            # Example filename: kidney_stone_scan.mp4 -> kidney, stone, scan
            tags = [t for t in re.split(r"[_\-\s]+", p.stem.lower()) if t]
            items.append({"path": p, "name": p.name, "tags": tags})
    return items


def select_broll(words: list[dict], preset: dict, video_duration: float) -> list[dict]:
    if not preset.get("broll"):
        return []
    assets = load_assets()
    if not assets:
        return []
    choices = []
    duration = float(preset["broll_duration"])
    gap = float(preset["min_broll_gap"])
    last = -999
    seen = set()
    for w in words:
        token = re.sub(r"[^a-z0-9]", "", w["text"].lower())
        if len(token) < 4 or token in STOPWORDS:
            continue
        at = max(0, float(w["start"]) - 0.2)
        if at - last < gap or at + duration > video_duration - 0.2:
            continue
        matching = [a for a in assets if token in a["tags"] and a["name"] not in seen]
        if not matching:
            continue
        item = matching[0]
        choices.append({"start": at, "duration": duration, "asset": item["path"],
                        "filename": item["name"], "keyword": token})
        last = at
        seen.add(item["name"])
        if len(choices) >= int(preset["max_broll"]):
            break
    return choices


def filter_path(path: Path) -> str:
    # Escape for FFmpeg filter arguments (not for shell: subprocess uses an argv list).
    s = str(path.absolute()).replace("\\", "/")
    return s.replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")


def render(video: Path, ass: Path, output: Path, preset: dict,
           broll: list[dict], duration: float, has_audio: bool) -> None:
    args = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", str(video)]
    for item in broll:
        if item["asset"].suffix.lower() in SUPPORTED_VIDEO:
            args += ["-stream_loop", "-1", "-i", str(item["asset"])]
        else:
            args += ["-loop", "1", "-framerate", "30", "-i", str(item["asset"])]
    # The base keeps original speech audio, while short keyword-matched cutaways
    # appear using alpha fades. Captions are overlaid LAST so they remain visible.
    scale = (f"scale={RENDER_WIDTH}:{RENDER_HEIGHT}:force_original_aspect_ratio=increase,"
             f"crop={RENDER_WIDTH}:{RENDER_HEIGHT},setsar=1,fps=30")
    filters = [f"[0:v]{scale},{preset['grading']},format=yuv420p[base0]"]
    previous = "base0"
    for i, item in enumerate(broll, start=1):
        at, dur = item["start"], item["duration"]
        transition = min(float(preset["transition"]), dur / 3)
        # Trim before timeline offset; transparent in/out avoids hard changes.
        filters.append(
            f"[{i}:v]{scale},trim=duration={dur:.3f},setpts=PTS-STARTPTS,"
            f"format=yuva420p,fade=t=in:st=0:d={transition:.3f}:alpha=1,"
            f"fade=t=out:st={dur-transition:.3f}:d={transition:.3f}:alpha=1,"
            f"setpts=PTS+{at:.3f}/TB[cut{i}]"
        )
        filters.append(f"[{previous}][cut{i}]overlay=eof_action=pass:shortest=0:"
                       f"format=auto[base{i}]")
        previous = f"base{i}"
    filters.append(f"[{previous}]format=yuv420p,subtitles='{filter_path(ass)}':"
                   f"fontsdir='{filter_path(Path(REEL_FONTDIR))}'[finished]")
    args += ["-filter_complex", ";".join(filters), "-map", "[finished]"]
    if has_audio:
        args += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k"]
    else:
        args += ["-an"]
    args += ["-c:v", "libx264", "-preset", os.getenv("ENCODE_PRESET", "veryfast"),
             "-crf", os.getenv("ENCODE_CRF", "21"), "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", "-t", f"{duration:.3f}", str(output)]
    cmd(args, timeout=FFMPEG_TIMEOUT)


def execute(job_id: str, filename: str, key: str) -> None:
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
            settings = presets()[key]
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
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health() -> dict:
    return verify_tools()


@app.get("/api/presets")
def get_presets() -> dict:
    return presets()


@app.get("/api/assets")
def get_assets() -> list[dict]:
    return [{"name": a["name"], "tags": a["tags"]} for a in load_assets()]


@app.post("/api/jobs")
async def create_job(video: UploadFile = File(...), preset: str = Form("medical_clean")) -> dict:
    if preset not in presets():
        raise HTTPException(400, "Unknown preset")
    if Path(video.filename or "").suffix.lower() not in SUPPORTED_VIDEO:
        raise HTTPException(400, "Only MP4, MOV, MKV or WebM videos are supported")
    check = verify_tools()
    if not check["ready"]:
        raise HTTPException(503, check["reason"])
    # Refuse new work while another job is being analyzed or rendered.
    with lock:
        if any(j["state"] not in {"completed", "failed"} for j in jobs.values()):
            raise HTTPException(429, "Editor busy: finish the current job first")
    job_id = uuid.uuid4().hex
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
        raise
    with lock:
        jobs[job_id] = {"id": job_id, "state": "queued", "message": "Accepted", "preset": preset,
                        "created_at": datetime.now(timezone.utc).isoformat()}
    thread = threading.Thread(target=execute, args=(job_id, video.filename or "reel", preset),
                              daemon=True)
    thread.start()
    return {"id": job_id, "state": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with lock:
        found = jobs.get(job_id)
        if found is None:
            raise HTTPException(404, "Unknown job")
        return dict(found)


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str) -> FileResponse:
    output = DATA / job_id / "output.mp4"
    if job_id not in jobs or jobs[job_id]["state"] != "completed" or not output.exists():
        raise HTTPException(404, "Output not ready")
    return FileResponse(output, filename=f"edited_{job_id[:8]}.mp4", media_type="video/mp4")


@app.get("/api/jobs/{job_id}/plan")
def download_plan(job_id: str) -> FileResponse:
    output = DATA / job_id / "edit_plan.json"
    if job_id not in jobs or not output.exists():
        raise HTTPException(404, "Plan not ready")
    return FileResponse(output, filename=f"edit_plan_{job_id[:8]}.json")


@app.get("/api/jobs/{job_id}/captions")
def download_captions(job_id: str) -> FileResponse:
    output = DATA / job_id / "captions.ass"
    if job_id not in jobs or not output.exists():
        raise HTTPException(404, "Captions not ready")
    return FileResponse(output, filename=f"captions_{job_id[:8]}.ass")
