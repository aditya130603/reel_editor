"""Procedural, original sound cues synchronized to the visual FX timeline.

Produces one bounded WAV with light click, shutter, paper, swipe and film noise.
Preserves dialogue; the mixed sound peaks are kept quiet (-25 dBFS-ish).
"""
from __future__ import annotations

import array
import hashlib
import math
import random
import subprocess
import wave
from pathlib import Path

RATE=22050
GAIN=.14

def write_cues(events:list[dict],length:float,path:Path)->bool:
    if not events:
        return False
    total=round(length*RATE)
    if total<=0 or total>180*RATE:
        raise ValueError("Sound cue timeline outside bounded length")
    mix=array.array('f',[0.0])*total
    used=0
    for event in events[:16]:
        kind=event["kind"]
        if kind in ("film_grain","diagram_lines","light_rays","sticker"):
            continue
        at=float(event.get("at",0))
        if at<0 or at>=length:
            continue
        style="click" if kind in ("click","scribble") else (
            "shutter" if kind in ("shutter","countdown") else (
            "paper" if kind in ("paper_fold","paper_corner") else "sweep"))
        clip_dur={"click":.16,"shutter":.25,"paper":.42,"sweep":.39}[style]
        n=round(clip_dur*RATE)
        start=round(at*RATE)
        seed=int.from_bytes(hashlib.sha256(f"{kind}:{at}".encode()).digest()[:4],"big")
        rng=random.Random(seed)
        prev=0.0
        for i in range(min(n,total-start)):
            t=i/RATE
            p=i/max(n,1)
            env=(1-p)**(4 if style=="click" else 2)
            noise=rng.uniform(-1,1)
            if style=="click":
                sample=noise*.50+math.sin(t*math.tau*155)*.18
            elif style=="shutter":
                sample=noise*.24+math.sin(t*math.tau*75)*.26
                if .45<p<.56:
                    sample+=rng.uniform(-.4,.4)
            elif style=="paper":
                prev=.85*prev+.15*noise
                sample=(noise-prev)*.25
            else:
                prev=.8*prev+.2*noise
                sample=(noise*.3+prev*.5)*math.sin(p*math.pi)
            mix[start+i]+=sample*env*GAIN
        used+=1
    if not used:return False
    ints=array.array('h',(int(max(-.88,min(.88,x))*32767) for x in mix))
    with wave.open(str(path),"wb") as file:
        file.setnchannels(1);file.setsampwidth(2);file.setframerate(RATE)
        file.writeframes(ints.tobytes())
    return True

def add_effect_sound(video:Path, fx_wav:Path, output:Path,timeout:int=900):
    cmd=["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
         "-i",str(video),"-i",str(fx_wav),
         "-filter_complex","[0:a:0]aresample=48000[dialogue];"
         "[1:a:0]aresample=48000,volume=0.70[fx];"
         "[dialogue][fx]amix=inputs=2:duration=first:"
         "dropout_transition=0:normalize=0[mixed]",
         "-map","0:v:0","-map","[mixed]","-c:v","copy",
         "-c:a","aac","-b:a","160k","-shortest",str(output)]
    process=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
    if process.returncode:
        raise RuntimeError("Effect sound mix failed: "+process.stderr[-800:])
