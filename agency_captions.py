"""Six editorial caption treatments with protected Instagram portrait safe zones.

All type is rendered with libass word timestamps. No random captions,
no head/face placement and no off-screen horizontal text.
"""
from __future__ import annotations

import re
from pathlib import Path

from caption_motion import color, stamp, escape, groups, importance

CAPTIONS = {
    "clinical_box": "Teal-emphasis clean clinical lower third",
    "paper_tape": "Off-white paper-strip subtitle with dark ink",
    "film_subtitle": "Warm cream classic film captions",
    "neon_karaoke": "Word-synced bright neon accent, no giant subtitles",
    "white_punch": "Bold white word pop, restrained",
    "yellow_focus": "Minimal white type with yellow emphasized keyword",
}
def visible_length(text):
    return len(re.sub(r"\{[^}]*\}","",text).replace(r"\N",""))

def split_lines(words:list[dict], max_chars:int):
    """Split phrase into at most 2 bounded lines, each within max_chars."""
    out=[]
    for group in groups(words,3,1.95):
        current=[]
        for w in group:
            word=str(w["text"]).strip()
            if not word:
                continue
            prospective=" ".join(str(x["text"]).strip() for x in current+[w])
            if current and len(prospective)>max_chars*2:
                out.append(current)
                current=[]
            current.append(w)
        if current:
            out.append(current)
    return out

def make_subs(words:list[dict],profile:dict,path:Path,width:int=720,
              height:int=1280) -> list[dict]:
    style=profile.get("caption","clinical_box")
    if style not in CAPTIONS:style="clinical_box"
    base_size=float(profile.get("size",52))
    font_size=int(max(34,min(57,base_size*height/1280)))
    # True screen-safe typography width: 82% of the video (0.8*720).
    maxchars=max(11,int(width*.78/(font_size*.62)))
    longest=max((len(str(w["text"])) for w in words),default=0)
    if longest>maxchars:
        font_size=max(30,int(width*.78/(longest*.64)))
        maxchars=max(11,int(width*.78/(font_size*.62)))
    segments=split_lines(words,maxchars)
    accent=color(profile.get("palette",["#62E4D4"])[0])
    is_paper=style=="paper_tape"
    is_film=style=="film_subtitle"
    main_col=color("211C1A" if is_paper else
                   "FFF6E3" if is_film else "F9FCFD")
    edge_col=color("EEDDB9" if is_paper else "111B1D")
    bg_col=color("F7EBD1" if is_paper else "111A1D")
    border=1
    outline=1 if is_paper else 3
    shadow=0 if is_paper else 1
    fontname="DejaVu Serif" if is_film else "DejaVu Sans"
    # Subtitles baseline .82 screen height, top cap ~.76, clear of app chrome.
    # .82 is chosen for Reels/TikTok UI protection. No motion subtitles above .69.
    margin_v=round(height*.18)
    margin_h=round(width*.09)
    head=f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{fontname},{font_size},{main_col},{accent},{edge_col},{bg_col},1,0,0,0,100,100,0,0,{border},{outline},{shadow},2,{margin_h},{margin_h},{margin_v},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    timeline=[]
    lines=[]
    for segment in segments:
        start=max(0,float(segment[0]["start"]))
        end=max(start+.12,float(segment[-1]["end"])+.1)
        plain=" ".join(str(w["text"]).strip() for w in segment)
        lengths=[len(str(w["text"]).strip()) for w in segment]
        score=sorted(((importance(w["text"]),i) for i,w in enumerate(segment)),reverse=True)
        hero=score[0][1] if score and score[0][0]>0 else None
        # Explicit two-line break aligned near midpoint; never overrun safe width.
        firstline=sum(lengths)+len(segment)-1
        cut=None
        if firstline>maxchars and len(segment)>1:
            candidates=[]
            for i in range(1,len(segment)):
                lhs=sum(lengths[:i])+i-1
                rhs=sum(lengths[i:])+len(segment)-i-1
                if lhs<=maxchars and rhs<=maxchars:
                    candidates.append((abs(lhs-rhs),i))
            if candidates:
                cut=min(candidates)[1]
        # An actual caption plate, not a huge word overlay on the torso.
        # Keep it within x=.09-.91 and baseline y=.82.
        if style in ("clinical_box", "paper_tape"):
            row_length = max((sum(lengths[:cut])+cut-1,
                              sum(lengths[cut:])+len(segment)-cut-1)
                             if cut else [sum(lengths)+len(segment)-1])
            panel_width = min(width*.82, max(width*.19,row_length*font_size*.59+36))
            panel_height = font_size*(2 if cut else 1)*1.30+20
            px = int((width-panel_width)/2)
            rx = int((width+panel_width)/2)
            bottom = int(height-margin_v+10)
            top = int(bottom-panel_height)
            if is_paper:
                outline_points=(f"m {px} {top} l {rx-8} {top+5} "
                                f"l {rx} {bottom-3} l {px+6} {bottom}")
                boxcol=color("FFF0D2")
                alpha="&H0B&"
            else:
                outline_points=(f"m {px+10} {top} l {rx-10} {top} "
                                f"l {rx} {top+10} l {rx} {bottom-10} "
                                f"l {rx-10} {bottom} l {px+10} {bottom} "
                                f"l {px} {bottom-10} l {px} {top+10}")
                boxcol=color("13252A")
                alpha="&H29&"
            lines.append(
                f"Dialogue: 0,{stamp(start)},{stamp(end)},Main,,0,0,0,,"
                "{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c"+boxcol+
                "\\alpha"+alpha+"\\fad(80,100)}"+outline_points
            )
        def parts(active=None):
            rendered=[]
            for i,w in enumerate(segment):
                token=escape(str(w["text"]).strip())
                if style=="neon_karaoke":
                    if active is not None and i==active:
                        token="{\\c"+accent+r"\fscx106\fscy106}"+token+r"{\r}"
                    elif active is not None and i<active:
                        token=r"{\alpha&H28&}"+token+r"{\r}"
                elif i==hero:
                    if is_paper:
                        token="{\\b1\\c"+color("A75533")+"}"+token+r"{\\r}"
                    else:
                        token="{\\c"+accent+r"\b1}"+token+r"{\r}"
                rendered.append(token)
            return " ".join(rendered) if cut is None else (
                " ".join(rendered[:cut])+r"\N"+" ".join(rendered[cut:]))
        if style=="neon_karaoke":
            for i,w in enumerate(segment):
                a=max(start,float(w["start"]))
                b=max(a+.06,float(segment[i+1]["start"]) if i+1<len(segment) else end)
                lines.append(f"Dialogue: 0,{stamp(a)},{stamp(b)},Main,,0,0,0,,{parts(i)}")
        else:
            tms=max(100,min(200,int((end-start)*300)))
            movement=(rf"\fad(80,110)\fscx104\fscy104\t(0,{tms},\fscx100\fscy100)"
                      if style in ("clinical_box","white_punch") else
                      rf"\fad(140,140)")
            if is_paper:
                movement+=r"\bord1\shad0"
            if is_film:
                movement+=r"\fsp1"
            lines.append(f"Dialogue: 1,{stamp(start)},{stamp(end)},Main,,0,0,0,,{{{movement}}}{parts()}")
        timeline.append({"start":round(start,3),"end":round(end,3),
                         "text":plain,"emphasis":segment[hero]["text"] if hero is not None else None,
                         "caption_style":style})
    path.write_text(head+"\n".join(lines)+"\n",encoding="utf-8")
    return timeline
