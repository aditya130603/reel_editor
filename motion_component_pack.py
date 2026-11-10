"""Original local kinetic motion components for Reel Studio.

Inspired by broad editorial/HUD design conventions, not copied from third-party
templates. Pillow renders tiny RGBA frame sequences. FFmpeg encodes each as
qtrle (lossless alpha) then the normal FFmpeg renderer composites it.
No browser, Node process, paid model or third-party render service.
"""
from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path

PACKS = {
    "off": "Captions only / no kinetic graphics",
    "editorial_clean": "Minimal editorial — precise fades, bold emphasis and statistics",
    "neon_business": "Premium neon — animated cards, bright accents, HUD gauges",
    "documentary": "Documentary — sober metrics, minimal badges and underlines",
}
COMPONENTS = {
    "kinetic_headline": "Short animated headline",
    "metric_card": "Number and label, magazine style",
    "progress_ring": "Arc-shaped progress indicator",
    "rating_strip": "Five stars and evaluation card",
    "comparison": "Two floating comparison cards",
    "lower_label": "Minimal lower-third annotation",
    "neon_badge": "Luminous floating tag",
    "bar_meter": "Animated segmented percentage bar",
}
MAX_EVENTS = 4
CLIP_LENGTH = 2.0
FPS = 12


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def clean_term(word: str) -> str:
    return re.sub(r"[^\w%₹$.,+-]", "", word).strip(".,")[:20]


def plan_components(words: list[dict], pack: str, video_duration: float,
                    maximum: int = MAX_EVENTS) -> list[dict]:
    """Deterministic content triggers; no fabricated numerical claims."""
    if pack not in PACKS or pack == "off" or video_duration < 3:
        return []
    from caption_motion import importance
    ranked = []
    for i, word in enumerate(words):
        term = clean_term(str(word.get("text", "")))
        if not term or len(term) < 2:
            continue
        at = float(word.get("start", 0))
        if at < .5 or at + CLIP_LENGTH >= video_duration - .1:
            continue
        tokens = [clean_term(str(w["text"])) for w in words[max(0, i - 2):min(len(words), i + 4)]]
        phrase = " ".join(t for t in tokens if t)[:54]
        score = importance(term)
        if re.search(r"[%₹$]", term):
            kind, score = ("progress_ring" if "%" in term else "metric_card"), 10
        elif re.fullmatch(r"\d+(?:[.,]\d+)?", term):
            kind, score = "metric_card", 8
        elif "star" in phrase.lower() or "rating" in phrase.lower():
            kind, score = "rating_strip", 6
        elif any(t in phrase.lower() for t in ("versus", "vs ", "compare", "difference")):
            kind, score = "comparison", 5
        elif score >= 2.5:
            kind = "neon_badge" if pack == "neon_business" else "kinetic_headline"
        else:
            continue
        ranked.append({"at": round(at, 3), "end": round(at + CLIP_LENGTH, 3),
                       "kind": kind, "word": term.upper(), "phrase": phrase,
                       "score": score, "pack": pack})
    # Reserve long, quiet spacing. The spoken number/phrase drives the component.
    ranked.sort(key=lambda e: (-e["score"], e["at"]))
    output = []
    for cue in ranked:
        if any(abs(cue["at"] - old["at"]) < 4.2 for old in output):
            continue
        output.append(cue)
        if len(output) >= min(maximum, MAX_EVENTS):
            break
    return sorted(output, key=lambda e: e["at"])


def font_path(bold: bool = True) -> str:
    options = (
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"]
        if bold else
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"]
    )
    for item in options:
        if Path(item).is_file():
            return item
    raise RuntimeError("A DejaVu or Liberation font is required")


def fit_font(ImageFont, text: str, bold: bool, max_px: int, max_width: int):
    size = max_px
    while size >= 12:
        font = ImageFont.truetype(font_path(bold), size)
        if font.getlength(text) <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(font_path(bold), 12)


def paint_frame(cue: dict, width: int, height: int, progress: float):
    from PIL import Image, ImageDraw, ImageFont
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    neon = cue["pack"] == "neon_business"
    accent = (129, 255, 55, 246) if neon else (118, 226, 218, 238)
    white = (250, 251, 251, 253)
    soft = (220, 230, 232, 210)
    dark = (9, 18, 26, 222)
    x1, x2 = int(width * .10), int(width * .90)
    target_y = int(height * (.64 if neon else .70))
    enter = ease(min(1, progress / .22))
    leave = ease(min(1, (1 - progress) / .18))
    visibility = min(enter, leave)
    dy = int((1 - enter) * 28)
    y = target_y + dy
    kind = cue["kind"]
    word = cue["word"][:20]

    if kind in {"kinetic_headline", "neon_badge", "lower_label"}:
        if neon or kind == "neon_badge":
            draw.rounded_rectangle((x1, y-26, x2, y+74), radius=17,
                                   fill=(7, 20, 31, 226), outline=accent, width=2)
            draw.rounded_rectangle((x1+9, y+58, x1 + 10 + int((x2-x1-28)*enter), y+63),
                                   radius=2, fill=accent)
        f = fit_font(ImageFont, word, True, 43 if neon else 35, x2-x1-28)
        draw.text((width/2, y+15), word, font=f, fill=white, anchor="mm",
                  stroke_width=1, stroke_fill=(5, 9, 12))
    elif kind == "metric_card":
        f = fit_font(ImageFont, word, True, 65, x2-x1-40)
        draw.rounded_rectangle((x1, y-45, x2, y+87), radius=19,
                               fill=dark, outline=accent, width=2)
        draw.text((width/2, y+7), word, font=f, fill=accent, anchor="mm")
        small = ImageFont.truetype(font_path(False), 16)
        draw.text((width/2, y+65), "KEY FIGURE", font=small, fill=soft, anchor="mm")
    elif kind == "progress_ring":
        center = (width//2, y+15)
        radius = 65
        bbox = (center[0]-radius, center[1]-radius,
                center[0]+radius, center[1]+radius)
        draw.arc(bbox, 130, 410, fill=(255,255,255,70), width=9)
        matches = re.findall(r"\d+", word)
        pct = min(100, int(matches[0])) if matches else 50
        draw.arc(bbox, 130, 130+int(280*pct/100*enter), fill=accent, width=10)
        f = fit_font(ImageFont, word, True, 36, 105)
        draw.text(center, word, font=f, fill=white, anchor="mm")
    elif kind == "rating_strip":
        draw.rounded_rectangle((x1, y-25, x2, y+61), radius=24, fill=dark,
                               outline=accent, width=2)
        stars = "★★★★★"
        f = fit_font(ImageFont, stars, True, 34, x2-x1-30)
        draw.text((width/2, y+17), stars, font=f, fill=(255,202,68,255), anchor="mm")
    elif kind == "comparison":
        middle = width//2
        for side, label in ((0, "OPTION A"), (1, "OPTION B")):
            left = x1+side*(middle-x1+7)
            right = middle-7 if side == 0 else x2
            top = y - 18 + int((1-enter)*18)
            draw.rounded_rectangle((left, top, right, y+74), radius=14,
                                   fill=dark, outline=accent if side else soft, width=2)
            f = fit_font(ImageFont, label, True, 18, right-left-12)
            draw.text(((left+right)/2,y+26),label,font=f,fill=white,anchor="mm")
    elif kind == "bar_meter":
        draw.rounded_rectangle((x1,y-28,x2,y+57),radius=14,fill=dark,outline=accent,width=2)
        for i in range(10):
            ax=x1+14+i*((x2-x1-28)//10)
            ay=y+11
            draw.rounded_rectangle((ax,ay,ax+14,ay+22),radius=3,
                                   fill=accent if i < int(enter*8) else (255,255,255,60))
        f=fit_font(ImageFont,word,True,18,x2-x1-24)
        draw.text((width/2,y-10),word,font=f,fill=white,anchor="mm")
    else:
        return canvas
    if visibility < 1:
        alpha = layer.getchannel("A").point(lambda v: int(v * visibility))
        layer.putalpha(alpha)
    return Image.alpha_composite(canvas, layer)


def render_components(cues: list[dict], folder: Path, width: int, height: int,
                      ffmpeg_timeout: int = 90) -> list[dict]:
    """Return overlay movie paths and absolute start times.

    Limit to four × 2-second overlays, 12 fps, half-size rendering.
    Remove PNG frames immediately after encoding (including on failure).
    """
    if not cues:
        return []
    from PIL import Image
    render_w, render_h = min(360, width), min(640, height)
    results = []
    for idx, cue in enumerate(cues[:MAX_EVENTS]):
        frames = folder / f"motion_frames_{idx:02d}"
        frames.mkdir(parents=True, exist_ok=True)
        target = folder / f"motion_component_{idx:02d}.mov"
        try:
            count = round(CLIP_LENGTH * FPS)
            for frame in range(count):
                progress = frame / max(count-1, 1)
                image = paint_frame(cue, render_w, render_h, progress)
                image.save(frames / f"frame_{frame:04d}.png", optimize=False)
            args = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                    "-y", "-framerate", str(FPS), "-i", str(frames/"frame_%04d.png"),
                    "-c:v", "qtrle", "-pix_fmt", "argb", str(target)]
            proc = subprocess.run(args, capture_output=True, text=True,
                                  check=False, timeout=ffmpeg_timeout)
            if proc.returncode or not target.is_file():
                raise RuntimeError("Motion component encode failed: " + proc.stderr[-600:])
            results.append({"path": target, "at": cue["at"], "kind": cue["kind"],
                            "word": cue["word"]})
        finally:
            shutil.rmtree(frames, ignore_errors=True)
    return results
