"""Self-contained original FX asset pack, rendered ONCE PER JOB to alpha movies.

Included looks: scribbles, animated paper folds, shutter/slats, clicks, lens
flares, sunlight, light leaks, film burns, dust/scratches, film leaders, stickers
and minimal technical lines. Assets are genuine picture layers, not subtitles.

No font downloads, stock footage, remote requests or copyrighted media.
"""
from __future__ import annotations

import hashlib
import math
import random
import shutil
import subprocess
from pathlib import Path

from agency_director import EFFECT_DURATIONS

FPS=12
W,H=360,640
MAX_EVENTS=16

def rgba(hexcode: str, alpha: int=255):
    v=hexcode.lstrip("#")
    return tuple(int(v[i:i+2],16) for i in (0,2,4))+(max(0,min(255,alpha)),)

def font(bold=True, size=36):
    from PIL import ImageFont
    paths=(["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"]
           if bold else ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    for path in paths:
        if Path(path).is_file():
            return ImageFont.truetype(path,size)
    return ImageFont.load_default()

def smooth(p:float):
    p=max(0,min(1,p))
    return p*p*(3-2*p)

def visibility(p:float, enter=.14, exit=.2):
    return min(1,smooth(p/max(enter,.01)),smooth((1-p)/max(exit,.01)))

def pathscribble(cx,cy,rx,ry,count=28):
    path=[]
    for i in range(count):
        a=(i/max(1,count-1))*math.pi*1.8-math.pi*.24
        x=cx+math.cos(a)*rx*(1+ .06*math.sin(6*a))
        y=cy+math.sin(a)*ry*(1+ .1*math.cos(3*a))
        path.append((int(x),int(y)))
    return path

def make_frame(event:dict, progress:float, w=W, h=H):
    from PIL import Image, ImageDraw, ImageFilter
    kind=event["kind"]
    # Hash-based consistent appearance; vary only frame/timing, not visual identity.
    seed=int.from_bytes(hashlib.sha256(
        f'{kind}:{event.get("at",0)}:{event.get("profile","")}'.encode()).digest()[:4],"big")
    rnd=random.Random(seed)
    image=Image.new("RGBA",(w,h),(0,0,0,0))
    d=ImageDraw.Draw(image,"RGBA")
    p=max(0,min(1,progress))
    fade=visibility(p)
    primary={
        "clinical_pro":"#67E7D7","paper_story":"#FBC466",
        "film_retro":"#FFB97A","neon_agency":"#B4FF45",
    }.get(event.get("profile","clinical_pro"),"#68E7D7")
    col=rgba(primary,round(238*fade))
    zone=event.get("zone","upper-left")
    left=(zone=="upper-left")
    x=int(w*(.28 if left else .72))
    y=int(h*.18)
    # top placement chosen deliberately: not the caption strip at y=.77-.91.
    if kind in {"scribble","diagram_lines","click","sticker"}:
        if kind=="scribble":
            points=pathscribble(x,y,int(w*.16),int(h*.058))
            n=max(2,round(len(points)*smooth(min(1,p/.35))))
            d.line(points[:n],fill=col,width=5,joint="curve")
            if n>3:
                tip=points[n-1]
                d.ellipse((tip[0]-3,tip[1]-3,tip[0]+3,tip[1]+3),fill=col)
        elif kind=="click":
            t=smooth(min(1,p/.55))
            for k in range(3):
                radius=round((8+k*16)*t)
                alpha=round((190-k*38)*(1-t*.65)*fade)
                d.ellipse((x-radius,y-radius,x+radius,y+radius),
                          outline=rgba(primary,alpha),width=3)
            d.ellipse((x-4,y-4,x+4,y+4),fill=rgba("#FFFFFF",round(245*fade)))
            for k in range(8):
                a=(k*math.pi/4)
                r=round(50*t)
                d.line(((x+math.cos(a)*(r-9),y+math.sin(a)*(r-9)),
                        (x+math.cos(a)*r,y+math.sin(a)*r)),fill=col,width=3)
        elif kind=="diagram_lines":
            stem_y=y+round(h*.08)
            t=smooth(min(1,p/.55))
            x0=int(w*.10 if left else w*.55)
            x1=int(w*.45 if left else w*.90)
            d.line(((x0,stem_y),(x0+(x1-x0)*t,stem_y)),fill=col,width=3)
            d.line(((x0,stem_y-17*t),(x0,stem_y+17*t)),fill=col,width=3)
            d.ellipse((x1-7,stem_y-7,x1+7,stem_y+7),outline=col,width=3)
            label=event.get("word","")
            if label:
                f=font(True,min(31,max(15,int(w*.65/max(len(label)*.59,1)))))
                d.text((x0,stem_y-15),label,font=f,fill=col,anchor="lb")
        else:
            cx,cy=x,y
            s=round(45*smooth(min(1,p/.3)))
            d.rounded_rectangle((cx-s,cy-s,cx+s,cy+s),radius=10,
                                fill=rgba("#FFF7DB",round(225*fade)),
                                outline=rgba("#7A512E",round(200*fade)),width=3)
            d.arc((cx-s+7,cy-s+7,cx+s-7,cy+s-7),30,260,fill=rgba(primary,round(250*fade)),width=4)
    elif kind=="paper_corner":
        # Folded ivory note wipes across top quadrant, not the speaker's captions.
        frac=smooth(min(1,p/.45))
        margin=round(w*.48*frac)
        start=0 if left else w
        edge=start+margin if left else start-margin
        pts=([(0,0),(edge,0),(edge-round(24*frac),round(h*.28)),(0,round(h*.28))]
             if left else [(w,0),(edge,0),(edge+round(24*frac),round(h*.28)),(w,round(h*.28))])
        d.polygon(pts,fill=rgba("#F9EDCE",round(218*fade)))
        d.line(pts[1:3],fill=rgba("#BAA484",round(210*fade)),width=3)
        fold=round(36*frac)
        d.polygon([(edge-fold,0),(edge,0),(edge,fold)] if left else
                  [(edge+fold,0),(edge,0),(edge,fold)],
                  fill=rgba("#D7BA86",round(190*fade)))
        if frac>.5:
            text=(event.get("word") or "NOTE")[:12]
            d.text((int(w*.18 if left else w*.81),round(h*.14)),text,font=font(True,20),
                   fill=rgba("#42372C",round(235*fade)),anchor="mm")
    elif kind=="paper_fold":
        # Transient full-frame physical-paper wipe: rises, reveals a folded edge, retreats.
        sweep=smooth(min(1,p*2)) if p<.5 else smooth(min(1,(1-p)*2))
        edge=round(sweep*w*1.07)
        d.polygon([(0,0),(edge,0),(max(0,edge-30),h),(0,h)],
                  fill=rgba("#F0E2C4",round(244*fade)))
        d.polygon([(max(0,edge-31),0),(edge,0),
                   (max(0,edge-30),h),(max(0,edge-60),h)],
                  fill=rgba("#AC9475",round(160*fade)))
        for k in range(7):
            a=rnd.randint(0,max(0,edge-40))
            b=rnd.randint(0,h)
            d.line((a,b,a+rnd.randint(20,90),b+rnd.randint(-18,18)),
                   fill=rgba("#B9A78C",round(25*fade)),width=1)
    elif kind=="shutter":
        # Mechanical camera blades as brief transition, avoids persistent black bars.
        cover=math.sin(math.pi*p)**1.8
        band=round(h*.19*cover)
        for k in range(6):
            origin=round(h*k/6)
            d.rectangle((0,origin,w,origin+band),fill=rgba("#07090C",round(248*fade)))
            if band>4:
                d.line((0,origin+band,w,origin+band),fill=rgba("#E2EDF3",round(105*fade)),width=2)
    elif kind=="flash":
        strength=max(0,1-abs(p-.36)/.38)
        d.rectangle((0,0,w,h),fill=rgba("#FFFBE9",round(215*strength*fade)))
        center=int(w*.3)
        d.ellipse((center-130,int(h*.36)-130,center+130,int(h*.36)+130),
                  fill=rgba("#FFFFFF",round(100*strength*fade)))
    elif kind=="countdown":
        # Vintage film leader: short, transparent amber-grey dial.
        cx,cy=w//2,int(h*.25)
        radius=round(w*.22)
        d.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),
                  fill=rgba("#15191A",round(170*fade)),
                  outline=rgba("#F6EEE4",round(215*fade)),width=3)
        dial_angle=p*math.tau*1.9
        d.line((cx,cy,cx+math.cos(dial_angle)*radius,cy+math.sin(dial_angle)*radius),
               fill=rgba("#F8E8D1",round(230*fade)),width=4)
        digit=str(max(1,3-int(p*3)))
        d.text((cx,cy),digit,font=font(True,58),fill=rgba("#FFF5DF",round(245*fade)),anchor="mm")
        d.line((cx-radius-15,cy,cx+radius+15,cy),fill=rgba("#FFFFFF",round(70*fade)),width=1)
    elif kind in {"film_grain","light_rays","light_leak","film_burn"}:
        # Software-generated optical overlays (actual RGBA pixels).
        from PIL import Image
        tiny_w,tiny_h=90,160
        grid=Image.new("RGBA",(tiny_w,tiny_h),(0,0,0,0))
        px=grid.load()
        time_bucket=int(p*30)
        rnd2=random.Random(seed+time_bucket*283)
        if kind=="film_grain":
            for k in range(320):
                a,b=rnd2.randrange(tiny_w),rnd2.randrange(tiny_h)
                value=rnd2.choice([0,255,238])
                px[a,b]=(value,value,value,rnd2.randrange(7,38))
        else:
            cx=(-.12 if left else 1.13)*tiny_w
            cy=(.22+.15*math.sin(p*5))*tiny_h
            for j in range(tiny_h):
                for i in range(tiny_w):
                    nx=(i-cx)/tiny_w
                    ny=(j-cy)/tiny_h
                    dist=math.hypot(nx,ny)
                    if kind=="light_leak":
                        strength=max(0,1-dist/1.10)**2
                        amount=round(135*strength*fade)
                        px[i,j]=(255,131+int(50*p),52,amount)
                    elif kind=="film_burn":
                        ring=max(0,1-abs(dist-(.15+p*.90))/.26)
                        amount=round(168*ring*fade)
                        px[i,j]=(255,152,54,amount)
                    else:
                        angle=math.atan2(ny,nx)
                        beam=max(0,math.cos(angle*8+p*2))**15
                        strength=max(0,1-dist/1.4)*beam
                        px[i,j]=(255,242,184,round(130*strength*fade))
        enlarged=grid.resize((w,h),Image.Resampling.BILINEAR)
        image=Image.alpha_composite(image,enlarged)
        d=ImageDraw.Draw(image,"RGBA")
        if kind=="film_grain":
            rng=random.Random(seed+time_bucket)
            for _ in range(6):
                sx=rng.randrange(w)
                d.line((sx,0,sx+rng.randint(-4,4),h),
                       fill=(245,238,220,rng.randint(17,38)),width=1)
    else:
        raise ValueError(f"Unknown effect {kind}")
    return image

def render_fx(events:list[dict], folder:Path, size:tuple[int,int]=(W,H),
              timeout:int=90) -> list[dict]:
    """Encode each event as a real transparent video layer and remove PNG frames."""
    if len(events)>MAX_EVENTS:
        raise ValueError("Exceeded bounded FX event limit")
    from PIL import Image
    width,height=size
    layers=[]
    for idx,event in enumerate(events):
        dur=float(event.get("duration",EFFECT_DURATIONS[event["kind"]]))
        count=max(3,round(dur*FPS))
        frames=folder/f"fx_frames_{idx:02d}"
        frames.mkdir(exist_ok=True)
        path=folder/f"fx_asset_{idx:02d}.mov"
        try:
            for k in range(count):
                frame=make_frame(event,k/max(1,count-1),width,height)
                frame.save(frames/f"f_{k:04d}.png",optimize=False)
            cmd=["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
                 "-framerate",str(FPS),"-i",str(frames/"f_%04d.png"),
                 "-c:v","qtrle","-pix_fmt","argb",str(path)]
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
            if result.returncode or not path.exists():
                raise RuntimeError("FX encode failed: "+result.stderr[-700:])
            layers.append({"path":path,"at":float(event["at"]),
                           "kind":event["kind"],"role":event.get("role","effect")})
        finally:
            shutil.rmtree(frames,ignore_errors=True)
    return layers
