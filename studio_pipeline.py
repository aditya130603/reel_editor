"""Offline multi-clip, soundtrack and editorial motion graphics pipeline.

Never invokes external providers, paid models, or a subprocess shell.
Each temporary encode is bounded by a timeout and a single-app render lock.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

CLIP_TRANSITIONS = {
    "fade": "Soft crossfade", "fadeblack": "Fade through black",
    "smoothleft": "Soft horizontal glide", "smoothright": "Soft reverse glide",
    "slideleft": "Slide left", "slideright": "Slide right",
    "wipeleft": "Quick editorial wipe", "circleopen": "Soft circular reveal",
    "cut": "Straight cut",
}
TITLE_EFFECTS = {
    "none": "No extra titles",
    "editorial": "Large editorial words above the speaker",
    "side_stack": "Keywords on the left of the frame",
    "poster": "Large translucent typography",
}


def run(arguments: list[str], timeout: int = 900) -> None:
    proc = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=timeout, check=False)
    if proc.returncode:
        raise RuntimeError((proc.stderr or proc.stdout)[-1800:])


def duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=15, check=True)
    return float(proc.stdout.strip())


def normalize_clips(paths: list[Path], work: Path, width: int, height: int,
                    timeout: int, has_audio) -> tuple[list[Path], list[float]]:
    if not 1 <= len(paths) <= 8:
        raise ValueError("Upload between one and eight clips")
    out_files, lengths = [], []
    for i, src in enumerate(paths):
        length = duration(src)
        if not .6 <= length <= 180:
            raise ValueError(f"Clip {i + 1} must be between 0.6 and 180 seconds")
        dest = work / f"normalized_{i:02d}.mp4"
        video_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps=30,"
            "format=yuv420p"
        )
        args = ["ffmpeg", "-nostdin", "-hide_banner", "-y", "-i", str(src)]
        if not has_audio(src):
            args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            audio_index = "1:a:0"
        else:
            audio_index = "0:a:0"
        args += [
            "-map", "0:v:0", "-map", audio_index, "-vf", video_filter,
            "-af", "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo",
            "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "22", "-threads", "2", "-c:a", "aac", "-b:a", "128k",
            "-ar", "48000", "-ac", "2",
            "-t", f"{length:.3f}", str(dest)
        ]
        run(args, timeout)
        out_files.append(dest)
        lengths.append(duration(dest))
    return out_files, lengths


def join_clips(clips: list[Path], lengths: list[float], output: Path,
               style: str, seconds: float = .28, timeout: int = 900) -> float:
    if len(clips) == 1:
        # Copy intermediate; preserve normalized audio/video properties.
        run(["ffmpeg", "-nostdin", "-hide_banner", "-y", "-i", str(clips[0]),
             "-c", "copy", str(output)], timeout)
        return duration(output)

    if style not in CLIP_TRANSITIONS:
        raise ValueError("Unsupported clip transition")
    cross = 0 if style == "cut" else min(max(.12, seconds), .6, min(lengths) / 3)
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-y"]
    for p in clips:
        args += ["-i", str(p)]
    graphs = []
    for i in range(len(clips)):
        graphs += [f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[v{i}]",
                   f"[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[a{i}]"]
    previous_v, previous_a = "v0", "a0"
    running = lengths[0]
    for i in range(1, len(clips)):
        vout, aout = f"vx{i}", f"ax{i}"
        if style == "cut":
            graphs.append(
                f"[{previous_v}][{previous_a}][v{i}][a{i}]concat=n=2:v=1:a=1"
                f"[{vout}][{aout}]"
            )
        else:
            offset = max(0, running - cross)
            graphs.append(
                f"[{previous_v}][v{i}]xfade=transition={style}:"
                f"duration={cross:.3f}:offset={offset:.3f}[{vout}]"
            )
            graphs.append(
                f"[{previous_a}][a{i}]acrossfade=d={cross:.3f}:c1=tri:c2=tri[{aout}]"
            )
        previous_v, previous_a = vout, aout
        running += lengths[i] - cross
    args += [
        "-filter_complex", ";".join(graphs), "-map", f"[{previous_v}]",
        "-map", f"[{previous_a}]", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "22", "-threads", "2", "-filter_complex_threads", "2",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(output)
    ]
    run(args, timeout)
    return duration(output)


def mix_music(video: Path, music: Path, output: Path,
              volume: float = .12, timeout: int = 900) -> None:
    """Retain speech at full level, duck bed under speech, never use music from web."""
    volume = max(0, min(.35, float(volume)))
    args = [
        "ffmpeg", "-nostdin", "-hide_banner", "-y",
        "-i", str(video), "-stream_loop", "-1", "-i", str(music),
        "-filter_complex",
        f"[1:a]aresample=48000,volume={volume:.3f}[bed];"
        # FFmpeg output pads are single-consumer: split the speech stream
        # before using it for both the sidechain detector and the final mix.
        "[0:a]aresample=48000,asplit=2[voice_main][voice_detector];"
        "[bed][voice_detector]sidechaincompress=threshold=0.035:ratio=6:attack=25:release=280[duck];"
        "[voice_main][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix]",
        "-map", "0:v:0", "-map", "[mix]", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "160k", "-shortest", str(output)
    ]
    run(args, timeout)


def salient_words(words: list[dict], max_events: int = 6,
                   min_gap: float = 4.0) -> list[dict]:
    """Heuristic typography placement, intentionally without cloud semantic inference."""
    from caption_motion import importance
    ranked = []
    for w in words:
        term = str(w["text"]).strip(" .,!?;:")
        if not (3 <= len(term) <= 16) or not re.fullmatch(r"[\w'-]+", term):
            continue
        score = importance(term)
        if score > 0.9:
            ranked.append((score, float(w["start"]), term))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    selected = []
    for score, at, term in ranked:
        if any(abs(at - event["at"]) < min_gap for event in selected):
            continue
        selected.append({"at": max(.1, at), "end": at + 1.65, "word": term.upper(),
                         "score": round(score, 2)})
        if len(selected) >= max_events:
            break
    return sorted(selected, key=lambda e: e["at"])


def drawtext_filters(words: list[dict], style: str, folder: Path,
                     width: int, height: int) -> tuple[list[str], list[dict]]:
    """Text effects are placed around/above the person, NOT behind by default.

    True behind-person compositing requires an aligned alpha foreground/matte.
    The editor never falsely claims that ordinary drawtext is subject-masked.
    """
    if style not in TITLE_EFFECTS or style == "none":
        return [], []
    entries = salient_words(words)
    expressions = []
    for i, entry in enumerate(entries):
        file = folder / f"hero_{i:02d}.txt"
        file.write_text(entry["word"], encoding="utf-8")
        # POSIX path escaped for FFmpeg filter syntax.
        path = str(file).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        at, end = entry["at"], entry["end"]
        if style == "side_stack":
            desired_size, x, y, color = round(width * .085), "w*0.05", "h*0.18", "white@0.90"
        elif style == "poster":
            desired_size, x, y, color = round(width * .155), "(w-text_w)/2", "h*0.20", "white@0.36"
        else:
            desired_size, x, y, color = round(width * .11), "(w-text_w)/2", "h*0.16", "white@0.88"
        # Keep long words within the same horizontal safe area as captions.
        size = min(desired_size, max(18, int(width * .78 / (len(entry["word"]) * .59))))
        # Explicit static enable windows: no user-submitted FFmpeg expressions.
        expressions.append(
            f"drawtext=textfile='{path}':fontsize={size}:fontcolor={color}:"
            f"borderw=2:bordercolor=black@0.2:x={x}:y={y}:"
            f"enable='between(t,{at:.3f},{end:.3f})'"
        )
    return expressions, entries
