"""Local B-roll editor: phrase-level scoring, synonyms, optional Ollama embeddings.

Embeddings are only requested from localhost; no external network endpoints.
"""
from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

MEDIA_EXT = {".mp4", ".mkv", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".webp"}
STOP = set("the a an and but for of to is are with from into at by that this what when while then you your i my we be it as on in or was were".split())
ALIASES = {
    "heart": {"cardiac", "cardiology", "heartbeat"},
    "kidney": {"renal", "urology", "urinary"},
    "stone": {"calculus", "stones"},
    "pregnancy": {"pregnant", "maternity", "prenatal", "baby"},
    "child": {"children", "kid", "kids", "pediatric"},
    "cancer": {"oncology", "tumor", "tumour"},
    "surgery": {"operation", "surgical", "surgeon"},
    "medicine": {"medical", "healthcare", "hospital", "doctor", "clinic"},
    "website": {"web", "browser", "landingpage"},
    "marketing": {"advertising", "ads", "campaign"},
    "money": {"finance", "cash", "rupee"},
    "exercise": {"fitness", "workout", "gym"},
    "food": {"nutrition", "diet", "meal"},
    "video": {"reel", "filming", "camera"},
}
REVERSE = {alias: key for key, values in ALIASES.items() for alias in values}


def tokens(value: str) -> list[str]:
    return [t for t in re.findall(r"[\w]+", value.lower()) if len(t) > 2 and t not in STOP]


def normalize(value: str) -> str:
    value = value.lower()
    if value in REVERSE:
        return REVERSE[value]
    if value.endswith("ies") and len(value) > 5:
        return value[:-3] + "y"
    if value.endswith("ing") and len(value) > 6:
        return value[:-3]
    if value.endswith("s") and len(value) > 4:
        return value[:-1]
    return value


def catalog(directory: Path) -> list[dict]:
    items = []
    if not directory.exists():
        return []
    for p in sorted(directory.iterdir()):
        if not p.is_file() or p.suffix.lower() not in MEDIA_EXT:
            continue
        tags = tokens(p.stem.replace("-", " ").replace("_", " "))
        # Optional sidecar: file.mp4.json containing tags and short description.
        meta = p.with_name(p.name + ".json")
        description = ""
        if meta.is_file():
            try:
                obj = json.loads(meta.read_text(encoding="utf-8"))
                tags.extend(tokens(" ".join(obj.get("tags", []))))
                description = str(obj.get("description", ""))[:300]
            except (ValueError, TypeError, OSError):
                pass
        items.append({"path": p, "name": p.name,
                      "tags": list(dict.fromkeys(tags)), "description": description})
    return items


def lexical_score(sentence: str, asset: dict) -> float:
    terms = {normalize(t) for t in tokens(sentence)}
    tags = {normalize(t) for t in asset["tags"]}
    details = {normalize(t) for t in tokens(asset.get("description", ""))}
    if not terms or not tags:
        return 0
    matching = terms & (tags | details)
    if not matching:
        return 0
    strong = terms & tags
    return (2.6 * len(strong) + .7 * len(matching - strong)) / (1 + math.log1p(len(tags)))


def local_embedding(text: str, model: str, timeout: float = 2.5) -> list[float] | None:
    """Strict loopback only. Ollama API is optional, with graceful lexical fallback."""
    body = json.dumps({"model": model, "input": text}).encode()
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/embed", body,
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            parsed = json.load(response)
        vector = parsed.get("embeddings", [[]])[0]
        return vector if vector and all(isinstance(v, (int, float)) for v in vector) else None
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def similarity(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        return 0
    dot = sum(x*y for x,y in zip(a,b))
    lengths = math.sqrt(sum(x*x for x in a)*sum(y*y for y in b))
    return dot / lengths if lengths else 0


def candidates(words: list[dict], seconds: float, max_words: int = 15) -> list[dict]:
    result, phrase = [], []
    for word in words:
        if phrase and (
            len(phrase) >= max_words or
            float(word["start"]) - float(phrase[-1]["end"]) > .55 or
            (str(phrase[-1]["text"]).endswith((".", "?", "!")) and len(phrase) >= 3)
        ):
            result.append(phrase)
            phrase = []
        phrase.append(word)
    if phrase:
        result.append(phrase)
    return [{"start": float(p[0]["start"]), "end": float(p[-1]["end"]),
             "text": " ".join(w["text"] for w in p)} for p in result if p]


def choose(words: list[dict], preset: dict, seconds: float,
           asset_dir: Path) -> list[dict]:
    if not preset.get("broll", False):
        return []
    assets = catalog(asset_dir)
    if not assets:
        return []
    limit = max(0, int(preset.get("max_broll", 3)))
    if not limit:
        return []
    span = max(1.0, min(float(preset.get("broll_duration", 2.5)), 6.0))
    gap = max(.5, float(preset.get("min_broll_gap", 6.0)))
    scenes = candidates(words, seconds)
    ranked = []
    mode = preset.get("broll_match", "lexical")
    model = os.getenv("OLLAMA_EMBED_MODEL", "")
    use_embeds = mode == "ollama" and bool(model)
    cache = {}
    if use_embeds:
        for asset in assets:
            sample = " ".join(asset["tags"]) + " " + asset["description"]
            cache[asset["name"]] = local_embedding(sample, model)
        if not any(cache.values()):
            use_embeds = False
    for scene in scenes:
        # Cutaway only when viewer has heard enough context.
        at = max(.4, float(scene["start"]) + .14)
        at = min(at, max(0, seconds-span-.1))
        if at < .2 or seconds-at < span+.1:
            continue
        text = scene["text"]
        embedding = local_embedding(text, model) if use_embeds else None
        for asset in assets:
            lexical = lexical_score(text, asset)
            semantic = similarity(embedding, cache[asset["name"]]) if embedding and cache.get(asset["name"]) else 0
            if lexical <= 0 and semantic < .40:
                continue
            score = lexical + max(0, semantic - .35)*4
            ranked.append({"start": round(at, 3), "duration": span,
                           "asset": asset["path"], "filename": asset["name"],
                           "keyword": text[:120], "score": round(score, 3),
                           "method": "ollama" if semantic > 0 else "lexical"})
    # Highest-quality matches first; only one b-roll event per sufficiently spaced window.
    ranked.sort(key=lambda item: (-item["score"], item["start"], item["filename"]))
    selected, used = [], set()
    for item in ranked:
        if item["filename"] in used:
            continue
        if any(abs(item["start"] - previous["start"]) < gap for previous in selected):
            continue
        selected.append(item)
        used.add(item["filename"])
        if len(selected) >= limit:
            break
    return sorted(selected, key=lambda item: item["start"])
