"""Small original procedural ambient beds for one-click edits.

12-second seamless-ish quiet musical beds, no copyrighted sample packs and no
runtime providers. A properly licensed local track still takes precedence.
Designed for restrained underscoring of speech, not replacing a music producer.
"""
from __future__ import annotations

import array
import math
import wave
from pathlib import Path

RATE=16000
LENGTH=12
SCALE={
    "clinical_pro": {"notes":[(220,277.18,329.63),(196,246.94,293.66),(174.61,220,261.63),(196,246.94,293.66)],"bass":.10,"drums":.0},
    "paper_story": {"notes":[(220,261.63,329.63),(174.61,220,261.63),(196,246.94,293.66),(164.81,220,261.63)],"bass":.11,"drums":.018},
    "film_retro": {"notes":[(174.61,220,261.63),(146.83,174.61,220),(130.81,164.81,196),(146.83,196,246.94)],"bass":.13,"drums":.0},
    "neon_agency": {"notes":[(220,261.63,329.63),(196,246.94,329.63),(174.61,220,293.66),(196,246.94,293.66)],"bass":.17,"drums":.045},
}
def music_bed(style:str,destination:Path) -> None:
    if style not in SCALE:
        raise ValueError("Unknown soundtrack profile")
    cfg=SCALE[style]
    count=RATE*LENGTH
    data=array.array("h")
    last=0.0
    for i in range(count):
        t=i/RATE
        chord_idx=min(3,int(t//3))
        chord=cfg["notes"][chord_idx]
        local=t%3
        # A tiny cross-chord envelope; suppress audible clicks at each 3s change.
        gain=.78+.22*min(1,local/.12, (3-local)/.12)
        harmonics=0
        for frequency in chord:
            harmonics+=(math.sin(t*frequency*2*math.pi)*.70+
                        math.sin(t*frequency*2*math.pi*2.002)*.12)
        harmonics/=len(chord)
        bass=math.sin(t*math.pi*2*(chord[0]/2))*cfg["bass"]
        beat=0.0
        if cfg["drums"]:
            phase=(t*2)%1
            if phase<.18:
                beat=math.sin(2*math.pi*(92*(t%0.5)))*math.exp(-phase*30)*cfg["drums"]
        sample=(harmonics*.22+bass+beat)*gain
        last=.85*last+.15*sample
        # Soft, non-intrusive output; further ducked beneath dialogue.
        value=(last*.82+sample*.18)*.62
        # Smooth 100ms on loop endpoints.
        envelope=min(1,t/.1,(LENGTH-t)/.1)
        data.append(int(max(-.90,min(.90,value*envelope))*32767))
    with wave.open(str(destination),"wb") as file:
        file.setnchannels(1);file.setsampwidth(2);file.setframerate(RATE)
        file.writeframes(data.tobytes())
