"""Coherent, one-choice agency editing profiles.

These are complete edit decisions—not pick-your-own-effect menus.
Graphics occupy upper safe regions; captions occupy a separate lower strip.
Only licensed local cutaway media is eligible for B-roll.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PROFILES = {
  "clinical_pro": {
    "name": "Clinical Pro",
    "description": "Medical-grade editorial cuts, teal/white captions, careful annotation",
    "caption": "clinical_box",
    "palette": ["#68E7D8", "#F9FFFF", "#162C31"],
    "font": "DejaVu Sans", "size": 52, "position": .855,
    "graphics": ["scribble", "click", "diagram_lines", "paper_corner"],
    "transitions": ["shutter", "light_leak", "paper_fold"],
    "intensity": "restrained", "event_gap": 6.5,
    "broll_gap": 7.0, "broll_limit": 4, "music_volume": .065,
    "base_preset": "medical_clean"
  },
  "paper_story": {
    "name": "Paper Story",
    "description": "Torn-paper reveals, doodles, analog textures and ink-like annotations",
    "caption": "paper_tape",
    "palette": ["#FFDA77", "#FFF9ED", "#241C16"],
    "font": "DejaVu Sans", "size": 50, "position": .855,
    "graphics": ["scribble", "paper_corner", "sticker"],
    "transitions": ["paper_fold", "film_burn", "shutter"],
    "intensity": "creative", "event_gap": 5.0,
    "broll_gap": 6.0, "broll_limit": 5, "music_volume": .11,
    "base_preset": "paper_soft"
  },
  "film_retro": {
    "name": "Film Editorial",
    "description": "Film burns, light leaks, dust, shutters and expressive captions",
    "caption": "film_subtitle",
    "palette": ["#F4CD86", "#FFF7E5", "#211B19"],
    "font": "DejaVu Serif", "size": 48, "position": .855,
    "graphics": ["film_grain", "scribble", "light_rays"],
    "transitions": ["film_burn", "light_leak", "shutter", "countdown"],
    "intensity": "cinematic", "event_gap": 5.5,
    "broll_gap": 7.0, "broll_limit": 5, "music_volume": .09,
    "base_preset": "cinematic_story"
  },
  "neon_agency": {
    "name": "Neon Agency",
    "description": "Kinetic headlines, neon outlines, pop markers and glossy wipes",
    "caption": "neon_karaoke",
    "palette": ["#B4FF45", "#F8FFFF", "#101B23"],
    "font": "DejaVu Sans", "size": 55, "position": .855,
    "graphics": ["click", "scribble", "diagram_lines", "light_rays"],
    "transitions": ["flash", "shutter", "light_leak"],
    "intensity": "punchy", "event_gap": 4.6,
    "broll_gap": 5.5, "broll_limit": 5, "music_volume": .13,
    "base_preset": "viral_punch"
  },
}
EFFECT_DURATIONS = {
    "scribble": 1.05, "click": .65, "diagram_lines": 1.15,
    "paper_corner": .95, "sticker": 1.0,
    "film_grain": 1.5, "light_rays": 1.4,
    "film_burn": .72, "light_leak": .9, "shutter": .48,
    "paper_fold": .85, "flash": .28, "countdown": 1.5,
}
EMPHASIS = set("never important warning critical serious always only urgent risk surgery cancer avoid stop risk treatment first last must pain".split())


def compact(word: str) -> str:
    return re.sub(r"[^\w₹$%+-]", "", str(word)).lower()


def plan(words: list[dict], duration: float, profile_key: str) -> list[dict]:
    """Deterministic editorial pacing: graphics, transitions and no overlap.

    - Graphic events in upper safe area, never the caption zone.
    - Transition effects occur no more often than each preset's configured gap.
    - No overlays at the first/last 0.6 seconds.
    - Strong spoken words affect which moments are highlighted.
    """
    if profile_key not in PROFILES:
        raise ValueError("Unknown agency preset")
    cfg = PROFILES[profile_key]
    if duration < 2:
        return []
    gap = cfg["event_gap"]
    # One curated effect every 5-7 s, with a little timing snap to spoken word boundaries.
    target = 2.2
    index = 0
    events = []
    while target + 1.5 < duration and len(events) < 16:
        nearby = [w for w in words if abs(float(w.get("start", 0)) - target) <= 1.2
                  and .5 < float(w.get("start", 0)) < duration - 1.7]
        def score(w):
            t = compact(w.get("text", ""))
            return (5 if t in EMPHASIS else 0) + min(len(t), 12) * .12
        chosen = max(nearby, key=score) if nearby else None
        at = float(chosen["start"]) if chosen is not None else target
        if events and at < events[-1]["at"] + 2.0:
            at = events[-1]["at"] + 2.2
        at = min(at, duration - 1.7)
        # A proper edit rhythm, not effects every other frame.
        kind_group = "transition" if index % 3 == 2 else "graphic"
        pool = cfg["transitions"] if kind_group == "transition" else cfg["graphics"]
        kind = pool[(index // (3 if kind_group == "transition" else 2)) % len(pool)]
        if kind == "countdown" and (index < 4 or duration < 28):
            kind = "light_leak"
        text = compact(chosen["text"]).upper() if chosen else ""
        events.append({
            "at": round(at, 3), "kind": kind, "duration": EFFECT_DURATIONS[kind],
            "role": kind_group,
            "word": text[:15],
            "zone": "upper-left" if index % 2 == 0 else "upper-right",
            "profile": profile_key,
        })
        target += gap
        index += 1
    return events


def caption_config(profile_key: str) -> dict:
    profile = PROFILES[profile_key]
    return {"caption_style": profile["caption"], "size": profile["size"],
            "font": profile["font"], "caption_position": profile["position"],
            "words_per_card": 3, "primary": profile["palette"][1].lstrip("#"),
            "accent": profile["palette"][0].lstrip("#"),
            "outline": 2, "safe_horizontal": .82,
            "safe_lower": .91}


def broll_config(profile_key: str) -> dict:
    cfg = PROFILES[profile_key]
    return {"broll": True, "max_broll": cfg["broll_limit"],
            "broll_duration": 1.9 if cfg["intensity"]=="punchy" else 2.5,
            "min_broll_gap": cfg["broll_gap"], "broll_match": "lexical"}
