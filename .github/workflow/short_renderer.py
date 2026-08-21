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
def kind(value,index):
 v=safe(value).lower()
 if any(k in v for k in ("warning","risk","failure","bug","problem")):return "risk"
 if any(k in v for k in ("compare","versus","before","after","split","vs")):return "compare"
 if any(k in v for k in ("metric","data","chart","growth","trend")):return "metrics"
 if any(k in v for k in ("timeline","sequence","steps")):return "timeline"
 return ["flow","compare","risk","metrics","timeline","flow"][index-1 if index<=6 else (index-1)%6]
def center(draw,text,box,font,fill):
 x1,y1,x2,y2=box; b=draw.textbbox((0,0),text,font=font); draw.text(((x1+x2-b[2]+b[0])/2,(y1+y2-b[3]+b[1])/2),text,font=font,fill=fill)
def visual(draw,k,x,y,w,h,p):
 from PIL import ImageFont
 lf=ImageFont.truetype(BOLD,27); bf=ImageFont.truetype(BOLD,52); sf=ImageFont.truetype(FONT,22)
 if k=="risk":
  cx=x+w/2; cy=y+h/2; draw.polygon([(cx,cy-155),(cx-155,cy+115),(cx+155,cy+115)],fill=p["panel"],outline=p["accent"]); center(draw,"!",(cx-65,cy-100,cx+65,cy+45),ImageFont.truetype(BOLD,105),p["accent"]); center(draw,"VERIFY",(cx-160,cy+55,cx+160,cy+115),lf,p["text"]); return
 labels={"compare":["BEFORE","AI","AFTER"],"metrics":["SIGNAL","CHANGE","RESULT"],"timeline":["START","TEST","LEARN"],"flow":["INPUT","AI","RESULT"]}[k]
 n=len(labels); gap=25; bw=(w-gap*(n-1))/n; by=y+h*.24
 for i,t in enumerate(labels):
  bx=x+i*(bw+gap); draw.rounded_rectangle((bx,by,bx+bw,by+230),radius=26,fill=p["panel"],outline=p["accent"],width=4); center(draw,t,(bx,by+30,bx+bw,by+105),lf,p["text"]); center(draw,["01","AI","✓"][i] if n==3 else str(i+1),(bx,by+110,bx+bw,by+205),bf,p["accent2"])
  if i<n-1: draw.line((bx+bw+5,by+115,bx+bw+gap-8,by+115),fill=p["muted"],width=4)
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
 title=safe(scene.get("title") or scene.get("heading") or scene.get("key_phrase") or f"Short {index}"); tf=fit(d,title,BOLD,60,36,850); yy=175
 for line in wrap(d,title,tf,850,3):
  b=d.textbbox((0,0),line,font=tf); d.text(((W-b[2]+b[0])/2,yy),line,font=tf,fill=p["text"]); yy+=b[3]-b[1]+8
 # Visual zone
 topv=505; botv=1100; d.rounded_rectangle((65,topv,W-65,botv),radius=34,fill=p["panel"],outline=p["accent"],width=3)
 visual(d,kind(scene.get("visual_type") or scene.get("visual") or scene.get("diagram"),index),110,topv+35,W-220,botv-topv-70,p)
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
 for i,scene in enumerate(scenes[:3],1):
  out,dur=render(i,scene,palettes[i-1])
  title=safe(scene.get("title") or scene.get("heading") or scene.get("key_phrase") or f"uncommonAI — Short {i}")
  manifest.append({"index":i,"title":f"uncommonAI — Short {i}","script":safe(scene.get("narration")),"file":str(out),"duration":round(dur,2)})
 MANIFEST.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8")
 print("V3 SHORTS CREATED")
 for i in range(1,4):
  p=SHORTS_DIR/f"short_{i:02d}.mp4"; print(f"{p} | {p.stat().st_size} bytes")
if __name__=="__main__":main()
