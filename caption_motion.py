"""Original ASS caption motion system; deterministic and fully offline.

Styles are composed from libass tags, not copied from proprietary preset packs.
All timing is taken from faster-whisper word timestamps.
"""
from __future__ import annotations

import re
from pathlib import Path

STOP = set("a an the and or if but to from for with at by of in on is are was were be been being it this that those these i you we they he she as do does did have has had my your our their so can will would should could not no yes just like very more some there then than what when where why how who which all about into out up down".split())

INTENSIFIERS = set("never always only must crucial urgent important warning dangerous serious severe life risk stop avoid remember suddenly immediately best worst first last biggest tiny huge major critical essential vital exactly".split())
MEDICAL = set("cancer tumour tumor bleeding surgery operation pregnancy cyst pain infection kidney heart brain fever blood emergency symptoms treatment diagnose diagnosis prevent diabetes".split())
NEGATIONS = set("not no never don't cannot won't shouldn't isn't aren't".split())
STYLES = {
    "highlight": "Color-emphasized phrase cards with a restrained entrance",
    "karaoke": "Word-by-word synchronized highlight with pop motion",
    "clean": "Subtle opacity fade with minimal typography",
    "editorial": "Elegant slide-up phrase introduction",
    "punch": "Overscale entrance with controlled punch-in",
    "typewriter": "Progressive words, revealed at speech timing",
    "outline": "Contemporary outlined caption treatment",
    "word_focus": "One word on screen at a time; large and precise",
    "soft_bounce": "Overshoot-and-settle phrase animation",
    "lower_third": "Reserved lower-third captions",
    "glow": "Soft bright text with a small shadow",
    "cinematic": "Wide-spaced slow fade, restrained motion",
}


def color(value: str) -> str:
    value = str(value).lstrip("#").upper()
    if not re.fullmatch(r"[A-F0-9]{6}", value):
        value = "FFFFFF"
    return "&H00" + value[4:6] + value[2:4] + value[:2]


def stamp(seconds: float) -> str:
    cs = max(0, round(seconds * 100))
    return f"{cs // 360000}:{(cs // 6000) % 60:02}:{(cs // 100) % 60:02}.{cs % 100:02}"


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def escape(value: str) -> str:
    return str(value).replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", " ")


def tokenize(value: str) -> str:
    return re.sub(r"[^\w']", "", value.casefold()).strip("'").lower()


def groups(words: list[dict], max_words: int, max_duration: float = 2.7) -> list[list[dict]]:
    output, segment = [], []
    for word in words:
        if segment and (
            float(word["start"]) - float(segment[-1]["end"]) > 0.54
            or len(segment) >= max_words
            or float(word["end"]) - float(segment[0]["start"]) > max_duration
        ):
            output.append(segment)
            segment = []
        segment.append(word)
        if re.search(r"[.!?]$", word["text"]) and len(segment) >= 2:
            output.append(segment)
            segment = []
    if segment:
        output.append(segment)
    return output


def importance(word: str) -> float:
    """Heuristic, not semantic AI. Strong words and numbers outrank filler."""
    token = tokenize(word)
    if not token or token in STOP:
        return -10
    score = min(len(token), 11) * 0.22
    if token in INTENSIFIERS:
        score += 5
    if token in MEDICAL:
        score += 2.4
    if token in NEGATIONS:
        score += 3.5
    if token.isdigit():
        score += 4.5
    if re.search(r"[!?]$", word):
        score += 0.5
    return score


def hero_index(group: list[dict]) -> int | None:
    if not group:
        return None
    scored = [(importance(w["text"]), i) for i, w in enumerate(group)]
    score, index = max(scored)
    return index if score > 0 else None


def enter(style: str, length_ms: int) -> str:
    m = max(80, min(240, length_ms // 3))
    if style in {"clean", "lower_third", "cinematic", "glow"}:
        return f"\\fad({m},130)"
    if style == "editorial":
        return f"\\fad(100,100)\\fscx96\\fscy96\\t(0,{m},\\fscx100\\fscy100)"
    if style in {"punch", "karaoke", "word_focus"}:
        return f"\\fad(50,75)\\fscx116\\fscy116\\t(0,{m},\\fscx100\\fscy100)"
    if style == "soft_bounce":
        return (f"\\fad(50,90)\\fscx85\\fscy85"
                f"\\t(0,{m},\\fscx107\\fscy107)"
                f"\\t({m},{m+110},\\fscx100\\fscy100)")
    return f"\\fad(65,100)\\fscx103\\fscy103\\t(0,{m},\\fscx100\\fscy100)"


def hero_text(group: list[dict], accent: str, hero: int | None, style: str) -> str:
    output = []
    for i, word in enumerate(group):
        part = escape(word["text"])
        if i == hero and style != "lower_third":
            part = "{\\c" + accent + "\\b1}" + part + "{\\r}"
        output.append(part)
    return " ".join(output)


def events(words: list[dict], preset: dict) -> tuple[list[str], list[dict]]:
    style = preset.get("caption_style", "highlight")
    if style not in STYLES:
        style = "highlight"
    count = max(1, int(preset.get("words_per_card", 4)))
    if style == "word_focus":
        count = 1
    grouped = groups(words, count)
    accent = color(preset.get("accent", "79DFCC"))
    rows, timeline = [], []
    for group in grouped:
        start = max(0, float(group[0]["start"]))
        end = max(start + .12, float(group[-1]["end"]) + .11)
        if style == "word_focus":
            end = max(end, start + .22)
        hero = hero_index(group)
        full = clean(" ".join(item["text"] for item in group))
        timeline.append({"start": round(start, 3), "end": round(end, 3),
                         "text": full, "emphasis": group[hero]["text"] if hero is not None else None,
                         "caption_style": style})
        length_ms = int((end - start) * 1000)
        entrance = enter(style, length_ms)
        if style == "typewriter":
            for i, word in enumerate(group):
                item_start = max(start, float(word["start"]))
                text = hero_text(group[:i+1], accent, i if hero == i else None, style)
                item_end = max(item_start + .06, float(group[i+1]["start"])) if i+1 < len(group) else end
                rows.append(f"Dialogue: 0,{stamp(item_start)},{stamp(item_end)},Main,,0,0,0,,{{{enter('clean', 200)}}}{text}")
            continue
        if style == "karaoke":
            # One dialogue event per word: earlier words stay muted, active word
            # gets a larger accent, following words remain white.
            for i, word in enumerate(group):
                a = max(start, float(word["start"]))
                b = min(end, max(a + .09, float(group[i+1]["start"]) if i+1 < len(group) else end))
                parts = []
                for j, other in enumerate(group):
                    value = escape(other["text"])
                    if j == i:
                        parts.append("{\\c" + accent + "\\fscx111\\fscy111}" + value + "{\\r}")
                    elif j < i:
                        parts.append("{\\alpha&H50&}" + value + "{\\r}")
                    else:
                        parts.append(value)
                rows.append(f"Dialogue: 0,{stamp(a)},{stamp(b)},Main,,0,0,0,,{' '.join(parts)}")
            continue
        text = hero_text(group, accent, hero, style)
        rows.append(f"Dialogue: 0,{stamp(start)},{stamp(end)},Main,,0,0,0,,{{{entrance}}}{text}")
    return rows, timeline


def render_ass(words: list[dict], preset: dict, path: Path, width: int = 720,
               height: int = 1280) -> list[dict]:
    style = preset.get("caption_style", "highlight")
    size = round(float(preset.get("size", 64)) * height / 1280)
    if style == "word_focus":
        size = round(size * 1.16)
    position = max(.15, min(.93, float(preset.get("caption_position", .8))))
    margin = round(height * (1 - position))
    font = str(preset.get("font", "DejaVu Sans")).replace(",", " ")
    outline = int(preset.get("outline", 3))
    if style in {"clean", "lower_third", "cinematic"}:
        outline = min(outline, 2)
    if style == "outline":
        outline = max(4, outline)
    shadow = 0 if style in {"clean", "cinematic"} else 1
    spacing = 2 if style == "cinematic" else 0
    back = "&H80000000"
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{size},{color(preset.get('primary','FFFFFF'))},{color(preset.get('accent','79DFCC'))},&H00202020,{back},1,0,0,0,100,100,{spacing},0,1,{outline},{shadow},2,32,32,{margin},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines, timeline = events(words, preset)
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return timeline
