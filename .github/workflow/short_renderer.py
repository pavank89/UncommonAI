#!/usr/bin/env python3
import json
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

ROOT=Path.cwd(); WORK=ROOT/"workspace"; SHORTS_DIR=WORK/"shorts"; PACKAGE_FILE=WORK/"production_package.json"; MANIFEST=SHORTS_DIR/"shorts_manifest.json"
SHORTS_DIR.mkdir(parents=True,exist_ok=True)
VOICE=os.getenv("VIDEO_VOICE","en-US-AriaNeural")
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"; BOLD="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PALETTE=[
 {"accent":(255,184,77),"accent2":(255,214,128),"bg":(18,17,24),"panel":(40,34,46),"text":(247,247,250),"muted":(174,177,189)},
 {"accent":(62,220,151),"accent2":(145,245,196),"bg":(13,20,19),"panel":(30,43,39),"text":(244,249,246),"muted":(169,187,180)},
 {"accent":(174,105,255),"accent2":(215,170,255),"bg":(20,16,27),"panel":(40,30,51),"text":(248,245,251),"muted":(185,175,197)},
 {"accent":(255,108,88),"accent2":(255,166,150),"bg":(24,17,18),"panel":(46,30,33),"text":(250,246,246),"muted":(190,173,176)},
 {"accent":(65,190,255),"accent2":(145,225,255),"bg":(14,19,25),"panel":(28,39,50),"text":(244,248,250),"muted":(169,184,196)},
 {"accent":(255,88,180),"accent2":(255,160,216),"bg":(25,15,23),"panel":(44,27,42),"text":(250,245,249),"muted":(190,171,185)},
]

def run(cmd): print("RUN:"," ".join(str(x) for x in cmd)); subprocess.run(cmd,check=True)
def safe(v): return re.sub(r"\s+"," ",str(v or "")).strip()
def fit(draw,text,path,max_size,min_size,max_width):
 from PIL import ImageFont
 for s in range(max_size,min_size-1,-2):
  f=ImageFont.truetype(path,s)
  if draw.textbbox((0,0),text,font=f)[2]<=max_width:return f
 return ImageFont.truetype(path,min_size)
def wrap(draw,text,font,max_width,max_lines=None):
 words=safe(text).split(); lines=[]; cur=""
 for w in words:
  c=w if not cur else cur+" "+w
  if draw.textbbox((0,0),c,font=font)[2]<=max_width:cur=c
  else:
   if cur:lines.append(cur)
   cur=w
 if cur:lines.append(cur)
 return lines[:max_lines] if max_lines else lines
def duration(p): return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)],text=True).strip())
def atime(s):
 cs=int(round(s*100)); h,cs=divmod(cs,360000); m,cs=divmod(cs,6000); sec,cs=divmod(cs,100); return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"
def make_ass(text,dur,path):
 words=safe(text).split() or ["uncommonAI"]; chunks=[" ".join(words[i:i+7]) for i in range(0,len(words),7)]; slot=max(dur,1)/len(chunks)
 out=["[Script Info]","ScriptType: v4.00+","PlayResX: 1080","PlayResY: 1920","WrapStyle: 2","ScaledBorderAndShadow: yes","","[V4+ Styles]","Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding","Style: Subtitle,DejaVu Sans,26,&H00FFFFFF,&H00FFFFFF,&H00101010,&HB0000000,0,0,0,0,100,100,0,0,3,8,0,2,75,75,105,1","","[Events]","Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
 for i,c in enumerate(chunks):
  st=i*slot; en=min((i+1)*slot,dur)
  if len(c)>38:
   parts=c.split(); mid=len(parts)//2; c=" ".join(parts[:mid])+"\\N"+" ".join(parts[mid:])
  out.append(f"Dialogue: 0,{atime(st)},{atime(en)},Subtitle,,0,0,105,,{c.replace('{','\\{').replace('}','\\}')}")
 path.write_text("\n".join(out)+"\n",encoding="utf-8")

def visual_keywords(scene, limit=3):
    candidates=[]
    for key in ("visual_labels","key_points","entities","visual_text","key_phrase","heading","title"):
        value=scene.get(key)
        if isinstance(value,list): candidates.extend(value)
        elif value: candidates.append(value)
    if not candidates:
        candidates=re.split(r"(?<=[.!?])\s+",safe(scene.get("narration")))
    labels=[]
    for item in candidates:
        item=safe(item)
        if not item: continue
        if len(item.split())>6: item=" ".join(item.split()[:6])
        if item.upper() not in {x.upper() for x in labels}:
            labels.append(item[:30])
        if len(labels)>=limit: break
    return labels or ["INPUT","SYSTEM","RESULT"]

def kind(scene,index,previous=None):
    text=(safe(scene.get("visual_type") or scene.get("visual") or scene.get("diagram"))+" "+safe(scene.get("title"))+" "+safe(scene.get("narration"))).lower()
    aliases=[("compare","compare"),("versus","compare"),("risk","risk"),("failure","risk"),("workflow","flow"),("process","flow"),("architecture","architecture"),("system","architecture"),("metric","metrics"),("data","metrics"),("timeline","timeline"),("evidence","evidence"),("fact","evidence"),("decision","decision"),("steps","steps")]
    for needle,result in aliases:
        if needle in text and result!=previous:return result
    rotation=["flow","compare","architecture","risk","journey","evidence","metrics","decision","steps","timeline"]
    for result in rotation:
        if result!=previous:return result
    return "flow"

def center(draw,text,box,font,fill):
    x1,y1,x2,y2=box;b=draw.textbbox((0,0),text,font=font);draw.text(((x1+x2-b[2]+b[0])/2,(y1+y2-b[3]+b[1])/2),text,font=font,fill=fill)

def visual(draw,k,x,y,w,h,p,scene=None):
    from PIL import ImageFont
    scene=scene or {}; labels=visual_keywords(scene,3)
    lf=ImageFont.truetype(BOLD,27); bf=ImageFont.truetype(BOLD,48); sf=ImageFont.truetype(FONT,21)
    if k=="flow":
        labels=(labels+["CHECK","RESULT"])[:3]; bw=(w-50)/3; by=y+95
        for i,text in enumerate(labels):
            bx=x+i*(bw+25); draw.rounded_rectangle((bx,by,bx+bw,by+245),radius=26,fill=p["panel"],outline=p["accent"],width=3); center(draw,str(i+1),(bx,by+20,bx+bw,by+75),bf,p["accent"]); center(draw,text.upper(),(bx+15,by+100,bx+bw-15,by+180),lf,p["text"])
            if i<2: draw.line((bx+bw+4,by+122,bx+bw+18,by+122),fill=p["accent2"],width=4)
    elif k=="compare":
        labels=(labels+["AI","RESULT"])[:3]; bw=(w-50)/3; by=y+95
        for i,text in enumerate(labels):
            bx=x+i*(bw+25); draw.rounded_rectangle((bx,by,bx+bw,by+245),radius=26,fill=p["panel"],outline=p["accent"],width=3); center(draw,["A","B","C"][i],(bx,by+20,bx+bw,by+75),bf,p["accent"]); center(draw,text.upper(),(bx+15,by+100,bx+bw-15,by+180),lf,p["text"])
    elif k=="architecture":
        labels=(labels+["SYSTEM","OUTPUT"])[:3]; bw=(w-55)/3; by=y+105
        for i,text in enumerate(labels):
            bx=x+i*(bw+27.5); draw.rounded_rectangle((bx,by,bx+bw,by+230),radius=25,fill=p["panel"],outline=p["accent"],width=3); center(draw,f"0{i+1}",(bx,by+18,bx+bw,by+70),sf,p["accent"]); center(draw,text.upper()[:18],(bx+10,by+85,bx+bw-10,by+165),lf,p["text"])
    elif k=="risk":
        cx=x+w/2; cy=y+h/2; draw.polygon([(cx,cy-150),(cx-150,cy+110),(cx+150,cy+110)],fill=p["panel"],outline=p["accent"]); center(draw,"!",(cx-70,cy-100,cx+70,cy+35),ImageFont.truetype(BOLD,105),p["accent"]); center(draw,(labels[0] if labels else "RISK").upper()[:20],(x+120,cy+45,x+w-120,cy+105),lf,p["text"])
    elif k=="metrics":
        labels=(labels+["SIGNAL","CHANGE","RESULT"])[:3]; bx=x+90; bw=w-180
        for i,text in enumerate(labels):
            yy=y+75+i*120; draw.text((bx,yy),text.upper(),font=lf,fill=p["text"])
            for dot in range(5):
                px=bx+bw-180+dot*36; fill=p["accent"] if dot<=i else p["bg"]; draw.ellipse((px-9,yy+48,px+9,yy+66),fill=fill,outline=p["muted"])
        center(draw,"QUALITATIVE — NO INVENTED NUMBERS",(x+70,y+h-80,x+w-70,y+h-30),sf,p["muted"])
    elif k=="timeline":
        labels=(labels+["NEXT"])[:3]; yy=y+220; x1=x+80; x2=x+w-80; draw.line((x1,yy,x2,yy),fill=p["muted"],width=5)
        for i,text in enumerate(labels):
            px=x1+i*(x2-x1)/2; draw.ellipse((px-25,yy-25,px+25,yy+25),fill=p["accent"]); center(draw,str(i+1),(px-25,yy-25,px+25,yy+25),sf,p["bg"]); center(draw,text.upper()[:18],(px-100,yy+50,px+100,yy+100),sf,p["text"])
    elif k=="journey":
        labels=(labels+["OUTCOME"])[:3]
        for i,text in enumerate(labels):
            bx=x+120+i*(w-240)/2; cy=y+210+(30 if i%2 else -30); draw.ellipse((bx-55,cy-55,bx+55,cy+55),fill=p["panel"],outline=p["accent"],width=4); center(draw,str(i+1),(bx-40,cy-40,bx+40,cy+40),bf,p["accent"]); center(draw,text.upper()[:16],(bx-100,cy+65,bx+100,cy+110),sf,p["text"])
    elif k=="evidence":
        claim=safe(scene.get("key_claim") or scene.get("claim") or (labels[0] if labels else "KEY FINDING")); rect=(x+65,y+55,x+w-65,y+h-55); draw.rounded_rectangle(rect,radius=30,fill=p["panel"],outline=p["accent"],width=3); center(draw,"EVIDENCE",(x+100,y+85,x+w-100,y+135),lf,p["accent"]); lines=wrap(draw,claim,lf,w-220,4); yy=y+180
        for line in lines: center(draw,line,(x+100,yy,x+w-100,yy+55),lf,p["text"]); yy+=62
    elif k=="decision":
        labels=(labels+["TRADE-OFF","DECISION"])[:3]
        for i,text in enumerate(labels):
            bx=x+65+i*(w-130)/3; draw.rounded_rectangle((bx,y+120,bx+(w-190)/3,y+330),radius=24,fill=p["panel"],outline=p["accent"] if i==2 else p["muted"],width=3); center(draw,str(i+1),(bx,y+145,bx+(w-190)/3,y+205),bf,p["accent"] if i==2 else p["muted"]); center(draw,text.upper()[:14],(bx+10,y+220,bx+(w-190)/3-10,y+300),sf,p["text"])
    else:  # steps
        labels=(labels+["CHECK","RESULT"])[:3]; bw=(w-45)/2
        for i,text in enumerate(labels):
            bx=x+(i%2)*(bw+45); yy=y+80+(i//2)*160; draw.rounded_rectangle((bx,yy,bx+bw,yy+125),radius=22,fill=p["panel"],outline=p["accent"],width=3); center(draw,str(i+1),(bx,yy+15,bx+55,yy+60),sf,p["accent"]); center(draw,text.upper()[:20],(bx+45,yy+30,bx+bw-10,yy+95),lf,p["text"])

def takeaway(scene,narration):
 for key in ("takeaway","key_takeaway","summary","lesson"):
  if safe(scene.get(key)): return safe(scene[key])
 parts=re.split(r"(?<=[.!?])\s+",safe(narration));
 return parts[-1][:110].rstrip(" ,.;:") if parts else "Key takeaway"
def make_card(scene,index,narration,p,path):
 from PIL import Image,ImageDraw,ImageFont
 W,H=1080,1920; img=Image.new("RGB",(W,H),p["bg"]); d=ImageDraw.Draw(img)
 d.rounded_rectangle((38,38,W-38,H-38),radius=34,outline=p["accent"],width=4)
 top=ImageFont.truetype(BOLD,30); small=ImageFont.truetype(FONT,23)
 d.text((70,75),"uncommonAI",font=top,fill=p["text"]); d.text((W-155,80),f"{index:02d}",font=small,fill=p["muted"])
 d.rounded_rectangle((70,120,W-70,128),radius=4,fill=p["panel"])
 d.rounded_rectangle((70,120,70+int((W-140)*min(index/8,1.0)),128),radius=4,fill=p["accent"])
 title=safe(scene.get("title") or scene.get("heading") or scene.get("key_phrase") or f"Short {index}"); tf=fit(d,title,BOLD,60,36,850); yy=175
 for line in wrap(d,title,tf,850,3):
  b=d.textbbox((0,0),line,font=tf); d.text(((W-b[2]+b[0])/2,yy),line,font=tf,fill=p["text"]); yy+=b[3]-b[1]+8
 # Visual zone
 topv=505; botv=1100; d.rounded_rectangle((65,topv,W-65,botv),radius=34,fill=p["panel"],outline=p["accent"],width=3)
 visual(d,scene.get("_renderer_visual_kind") or kind(scene,index),110,topv+35,W-220,botv-topv-70,p,scene)
 # Meaningful takeaway card, not an empty heading.
 tk=takeaway(scene,narration); ttf=fit(d,tk,BOLD,38,25,820); lines=wrap(d,tk,ttf,820,3)
 d.text((70,1160),"THE TAKEAWAY",font=top,fill=p["accent"]); yy=1215
 d.rounded_rectangle((65,1195,W-65,1445),radius=28,fill=p["panel"],outline=p["accent"],width=3)
 for line in lines:
  b=d.textbbox((0,0),line,font=ttf); d.text(((W-b[2]+b[0])/2,yy),line,font=ttf,fill=p["text"]); yy+=b[3]-b[1]+5
 # Subtitle-safe area starts at 1490. Nothing else is drawn there.
 d.line((65,1480,W-65,1480),fill=p["accent"],width=3); d.text((70,1510),"",font=small,fill=p["muted"])
 img.save(path,quality=95)
def render(i,scene,p):
 audio=SHORTS_DIR/f"short_{i:02d}.mp3"; image=SHORTS_DIR/f"short_{i:02d}.png"; ass=SHORTS_DIR/f"short_{i:02d}.ass"; out=SHORTS_DIR/f"short_{i:02d}.mp4"
 narration=safe(scene.get("narration"));
 if not narration:raise SystemExit(f"Scene {i} has no narration")
 run(["edge-tts","--voice",VOICE,"--text",narration,"--write-media",str(audio)]); dur=duration(audio); make_card(scene,i,narration,p,image); make_ass(narration,dur,ass)
 ap=str(ass).replace("\\","/").replace(":","\\:").replace("'","\\'")
 vf=("scale=1110:1973,zoompan=z='min(zoom+0.00012,1.025)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30," f"subtitles='{ap}'")
 run(["ffmpeg","-y","-loop","1","-i",str(image),"-i",str(audio),"-vf",vf,"-c:v","libx264","-preset","veryfast","-tune","stillimage","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k","-shortest","-t",str(dur),"-movflags","+faststart",str(out)])
 if not out.exists() or out.stat().st_size==0:raise SystemExit(f"Short {i} failed")
 return out,dur
def main():
 if not PACKAGE_FILE.exists():raise SystemExit(f"Missing {PACKAGE_FILE}")
 for t in ("ffmpeg","ffprobe","edge-tts"):
  if not shutil.which(t):raise SystemExit(f"{t} is not installed")
 package=json.loads(PACKAGE_FILE.read_text(encoding="utf-8")); scenes=package.get("scenes",[])
 if len(scenes)<3:raise SystemExit(f"Expected at least 3 scenes, found {len(scenes)}")
 for x in SHORTS_DIR.iterdir():
  if x.is_file():x.unlink()
 palettes=PALETTE.copy(); random.SystemRandom().shuffle(palettes); manifest=[]
 previous_kind=None
 for i,scene in enumerate(scenes[:3],1):
  scene=dict(scene)
  chosen=kind(scene,i,previous_kind)
  scene["_renderer_visual_kind"]=chosen
  previous_kind=chosen
  out,dur=render(i,scene,palettes[(i-1)%len(palettes)])
  title=safe(scene.get("title") or scene.get("heading") or scene.get("key_phrase") or f"uncommonAI — Short {i}")
  manifest.append({"index":i,"title":f"uncommonAI — Short {i}","script":safe(scene.get("narration")),"file":str(out),"duration":round(dur,2)})
 MANIFEST.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8")
 print("V5 SHORTS CREATED")
 for i in range(1,4):
  p=SHORTS_DIR/f"short_{i:02d}.mp4"; print(f"{p} | {p.stat().st_size} bytes")
if __name__=="__main__":main()
