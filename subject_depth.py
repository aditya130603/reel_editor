"""Optional LOCAL selfie-depth masks for genuine text-behind-person compositing.

Not installed by default. Run requirements-depth.txt to enable MediaPipe.
Avoids persistent GPU/model workers; processes a single clip under a bounded timeout.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


def create_person_mask(video: Path, workdir: Path, seconds: float,
                       output_width: int, output_height: int,
                       max_seconds: float = 45) -> Path:
    if seconds > max_seconds:
        raise RuntimeError(f"Subject masking currently supports at most {max_seconds}s")
    try:
        import cv2
        import mediapipe as mp
        import numpy as np
    except ImportError as error:
        raise RuntimeError(
            "Depth text requires optional local segmentation dependencies. "
            "Install with .venv/bin/pip install -r requirements-depth.txt"
        ) from error
    if not hasattr(mp, "solutions") or not hasattr(mp.solutions, "selfie_segmentation"):
        raise RuntimeError("MediaPipe selfie segmentation API is unavailable in this version")
    width, height, fps = 320, 568, 12
    maskdir = workdir / "subject_masks"
    maskdir.mkdir(exist_ok=True)
    process = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
         "-i", str(video), "-vf", f"fps={fps},scale={width}:{height}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    pixels = width * height * 3
    expected = max(1, round(seconds * fps))
    count = 0
    start = time.monotonic()
    try:
        with mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1) as engine:
            while count < expected + 3:
                if time.monotonic() - start > 240:
                    raise RuntimeError("Subject segmentation exceeded 4-minute limit")
                frame = process.stdout.read(pixels) if process.stdout else b""
                if len(frame) != pixels:
                    break
                image = np.frombuffer(frame, dtype=np.uint8).reshape((height, width, 3))
                result = engine.process(image)
                if result.segmentation_mask is None:
                    raise RuntimeError("Could not segment the speaker")
                alpha = np.clip(result.segmentation_mask, 0, 1)
                # Gentle feather: hair looks less cut out than binary alpha.
                alpha = cv2.GaussianBlur(alpha, (5, 5), 0.9)
                alpha = np.uint8(alpha * 255)
                cv2.imwrite(str(maskdir / f"frame_{count:05d}.png"), alpha)
                count += 1
        if count < 2:
            raise RuntimeError("Not enough foreground mask frames generated")
        target = workdir / "subject_alpha.mkv"
        output = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
             "-framerate", str(fps), "-i", str(maskdir / "frame_%05d.png"),
             "-vf", f"fps=30,scale={output_width}:{output_height}",
             "-c:v", "ffv1", "-pix_fmt", "gray", str(target)],
            capture_output=True, text=True, timeout=120, check=False
        )
        if output.returncode:
            raise RuntimeError("Mask encoding failed: " + output.stderr[-600:])
        return target
    finally:
        if process.poll() is None:
            process.kill()
        if process.stdout:
            process.stdout.close()
        process.wait(timeout=10)
        shutil.rmtree(maskdir, ignore_errors=True)
