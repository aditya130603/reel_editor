#!/usr/bin/env python3
"""Import vetted, CC0-generated ANVE motion-pack audio without installing its runtime.

Point at a manually downloaded/extracted motion-pack release or a local clone
whose generated WAV folders exist. We copy only sound and bed audio (not fonts,
trademarks, third-party imports or source code). Never uploads personal files.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def collect(source: Path, subfolder: str, limit: int) -> list[Path]:
    directory = source / subfolder
    if not directory.is_dir():
        return []
    return [p for p in sorted(directory.rglob("*.wav"))
            if p.is_file() and not p.is_symlink()][:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True,
                        help="Local ANVEAI/motion-pack root with generated WAV library folders")
    parser.add_argument("--sfx-count", type=int, default=12)
    parser.add_argument("--music-count", type=int, default=12)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    license_path = source / "LICENSE-MEDIA"
    if not license_path.is_file() or "CC0 1.0" not in license_path.read_text(encoding="utf-8"):
        parser.error("Source must have the verified ANVE motion-pack CC0 LICENSE-MEDIA")
    if not (0 <= args.sfx_count <= 50 and 0 <= args.music_count <= 30):
        parser.error("Keep imports bounded: sfx<=50, music<=30")
    items = [
        ("sfx", p) for p in collect(source, "sfx/library", args.sfx_count)
    ] + [
        ("music", p) for p in collect(source, "music/library/beds", args.music_count)
    ]
    if not items:
        parser.error("No WAV files found. Run upstream sfx/build_library.py and music/build_music.py first.")
    manifest = []
    for kind, src in items:
        dest_dir = ROOT / "assets" / kind
        name = "anve_cc0_" + "_".join(src.relative_to(source).parts[-3:])
        destination = dest_dir / name.replace(" ", "_")
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        manifest.append({"kind": kind, "source": str(src.relative_to(source)),
                         "installed": str(destination.relative_to(ROOT)),
                         "sha256": digest, "license": "CC0-1.0",
                         "provider": "ANVEAI/motion-pack"})
        if not args.dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copyfile(src, destination)
    print(json.dumps({"dry_run": args.dry_run, "count": len(manifest)}, indent=2))
    if not args.dry_run:
        out = ROOT / "assets" / "ANVE_AUDIO_ORIGINS.json"
        out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
