#!/usr/bin/env python3
import json
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path.cwd()
WORK = ROOT / "workspace"
VIDEO_DIR = WORK / "video"
PACKAGE_FILE = WORK / "production_package.json"
OUTPUT = WORK / "uncommonAI_video.mp4"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

VOICE = os.getenv("VIDEO_VOICE", "en-US-AriaNeural")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

PALETTE = [
    {"accent": (255,184,77), "accent2": (255,214,128), "bg": (18,17,24), "panel": (37,33,45), "text": (247,247,250), "muted": (173,176,189)},
    {"accent": (62,220,151), "accent2": (145,245,196), "bg": (13,20,19), "panel": (29,43,39), "text": (244,249,246), "muted": (169,187,180)},
    {"accent": (174,105,255), "accent2": (215,170,255), "bg": (20,16,27), "panel": (39,30,51), "text": (248,245,251), "muted": (185,175,197)},
    {"accent": (255,108,88), "accent2": (255,166,150), "bg": (24,17,18), "panel": (45,30,33), "text": (250,246,246), "muted": (190,173,176)},
    {"accent": (65,190,255), "accent2": (145,225,255), "bg": (14,19,25), "panel": (27,39,50), "text": (244,248,250), "muted": (169,184,196)},
    {"accent": (255,88,180), "accent2": (255,160,216), "bg": (25,15,23), "panel": (44,27,42), "text": (250,245,249), "muted": (190,171,185)},
    {"accent": (86,151,255), "accent2": (160,195,255), "bg": (15,18,26), "panel": (24,29,43), "text": (244,247,251), "muted": (170,180,198)},
    {"accent": (190,255,73), "accent2": (220,255,150), "bg": (19,22,14), "panel": (30,35,22), "text": (246,249,240), "muted": (180,189,162)},
]


def run(cmd):
    print("RUN:", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def safe_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def font_fit(draw, text, path, max_size, min_size, max_width):
    from PIL import ImageFont
    for size in range(max_size, min_size - 1, -2):
        f = ImageFont.truetype(path, size)
        if draw.textbbox((0, 0), text, font=f)[2] <= max_width:
            return f
    return ImageFont.truetype(path, min_size)


def wrap(draw, text, font, max_width, max_lines=None):
    words = safe_text(text).split()
    lines, current = [], ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:max_lines] if max_lines else lines


def audio_duration(path):
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True).strip())


def ass_time(seconds):
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_escape(text):
    return safe_text(text).replace("{", "\\{").replace("}", "\\}")


def make_ass(text, duration, path):
    words = safe_text(text).split() or ["uncommonAI"]
    chunks = [" ".join(words[i:i + 7]) for i in range(0, len(words), 7)]
    slot = max(float(duration), 1.0) / len(chunks)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Subtitle,DejaVu Sans,34,&H00FFFFFF,&H00FFFFFF,&H00101010,&H99000000,0,0,0,0,100,100,0,0,3,10,0,2,180,180,55,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for i, chunk in enumerate(chunks):
        start, end = i * slot, min((i + 1) * slot, duration)
        # Force a soft two-line layout without changing the content.
        if len(chunk) > 42:
            parts = chunk.split()
            mid = len(parts) // 2
            chunk = " ".join(parts[:mid]) + "\\N" + " ".join(parts[mid:])
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Subtitle,,0,0,55,,{ass_escape(chunk)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def rect(draw, box, fill, outline=None, width=1, radius=22):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center_text(draw, text, box, font, fill):
    x1, y1, x2, y2 = box
    bb = draw.textbbox((0, 0), text, font=font)
    draw.text(((x1+x2-(bb[2]-bb[0]))/2, (y1+y2-(bb[3]-bb[1]))/2), text, font=font, fill=fill)


def visual_kind(value, index):
    vt = safe_text(value).lower()
    if any(k in vt for k in ("warning", "risk", "failure", "bug", "problem")): return "risk"
    if any(k in vt for k in ("compare", "versus", "split", "before", "after", "vs")): return "compare"
    if any(k in vt for k in ("metric", "data", "chart", "growth", "trend")): return "metrics"
    if any(k in vt for k in ("timeline", "sequence", "steps")): return "timeline"
    if any(k in vt for k in ("quote", "fact", "claim")): return "quote"
    if any(k in vt for k in ("matrix", "grid")): return "matrix"
    kinds = ["flow", "compare", "risk", "metrics", "timeline", "matrix", "quote", "flow"]
    return kinds[(index - 1) % len(kinds)]


def draw_visual(draw, kind, area, p):
    from PIL import ImageFont
    x, y, w, h = area
    label = ImageFont.truetype(BOLD, 26)
    big = ImageFont.truetype(BOLD, 46)
    small = ImageFont.truetype(FONT, 22)

    if kind == "flow":
        labels = ["INPUT", "AI", "CHECK", "RESULT"]
        gap = 20
        bw = (w - gap*3) / 4
        by = y + h*0.30
        for i, text in enumerate(labels):
            bx = x + i*(bw+gap)
            rect(draw, (bx, by, bx+bw, by+190), p["panel"], p["accent"], 3)
            center_text(draw, text, (bx, by+35, bx+bw, by+110), label, p["text"])
            center_text(draw, "✓" if i == 3 else str(i+1), (bx, by+105, bx+bw, by+175), big, p["accent2"])
            if i < 3:
                draw.line((bx+bw+4, by+95, bx+bw+gap-8, by+95), fill=p["muted"], width=4)

    elif kind == "compare":
        cards = [("BEFORE", "Manual"), ("AI", "Fast"), ("AFTER", "Verified")]
        bw, gap = 400, 45
        start = x + (w - (3*bw+2*gap))/2
        by = y + 125
        for i, (a, b) in enumerate(cards):
            bx = start+i*(bw+gap)
            rect(draw, (bx, by, bx+bw, by+250), p["panel"], p["accent"], 3)
            center_text(draw, a, (bx, by+30, bx+bw, by+100), label, p["accent"])
            center_text(draw, b, (bx, by+105, bx+bw, by+205), big, p["text"])

    elif kind == "risk":
        cx, cy = x+w/2, y+h/2
        draw.polygon([(cx,cy-150),(cx-145,cy+110),(cx+145,cy+110)], fill=p["panel"], outline=p["accent"])
        center_text(draw, "!", (cx-70,cy-85,cx+70,cy+55), ImageFont.truetype(BOLD,110), p["accent"])
        center_text(draw, "HUMAN CHECK", (x+180,y+h-110,x+w-180,y+h-55), label, p["text"])

    elif kind == "metrics":
        base = y+h-120
        left = x+220
        draw.line((left, base, x+w-150, base), fill=p["muted"], width=3)
        pts = [(left,base-40),(left+150,base-90),(left+300,base-170),(left+470,base-260),(left+650,base-330)]
        draw.line(pts, fill=p["accent"], width=8)
        for px, py in pts:
            draw.ellipse((px-10,py-10,px+10,py+10), fill=p["accent2"])
        center_text(draw, "SIGNAL → CHANGE → RESULT", (x+200,y+45,x+w-200,y+110), label, p["text"])

    elif kind == "timeline":
        yy = y+h/2
        x1, x2 = x+170, x+w-170
        draw.line((x1,yy,x2,yy), fill=p["muted"], width=5)
        labels = ["START","TEST","BREAK","LEARN"]
        for i, t in enumerate(labels):
            px = x1 + i*(x2-x1)/3
            draw.ellipse((px-22,yy-22,px+22,yy+22), fill=p["accent"])
            center_text(draw, t, (px-85,yy+42,px+85,yy+85), small, p["text"])

    elif kind == "matrix":
        gx, gy = x+260, y+45
        size = 155
        for r in range(2):
            for c in range(2):
                bx, by = gx+c*(size+30), gy+r*(size+30)
                rect(draw,(bx,by,bx+size,by+size),p["panel"],p["accent"],3)
        center_text(draw,"LOW",(gx,gy,gx+size,gy+size),small,p["muted"])
        center_text(draw,"HIGH",(gx+size+30,gy,gx+2*size+30,gy+size),label,p["text"])
        center_text(draw,"RISK",(gx,gy+size+30,gx+size,gy+2*size+30),label,p["text"])
        center_text(draw,"VALUE",(gx+size+30,gy+size+30,gx+2*size+30,gy+2*size+30),label,p["accent2"])

    else:  # quote
        rect(draw,(x+190,y+85,x+w-190,y+h-85),p["panel"],p["accent"],3,32)
        center_text(draw,'“', (x+240,y+100,x+330,y+210), ImageFont.truetype(BOLD,100), p["accent"])
        center_text(draw,"FACT / CLAIM", (x+330,y+150,x+w-260,y+260), label, p["text"])
        center_text(draw,"VERIFY BEFORE TRUST", (x+250,y+h-210,x+w-250,y+h-130), small, p["muted"])


def make_card(scene, index, title, p, path):
    from PIL import Image, ImageDraw, ImageFont
    W,H = 1920,1080
    img = Image.new("RGB", (W,H), p["bg"])
    draw = ImageDraw.Draw(img)
    rect(draw,(45,45,W-45,H-45),p["bg"],p["accent"],3,28)
    top = ImageFont.truetype(BOLD, 25)
    scene_f = ImageFont.truetype(FONT, 23)
    draw.text((85,82),"uncommonAI",font=top,fill=p["text"])
    draw.text((W-245,85),f"SCENE {index:02d}",font=scene_f,fill=p["muted"])

    title_f = font_fit(draw,title,BOLD,68,42,1580)
    title_lines = wrap(draw,title,title_f,1580,2)
    yy=155
    for line in title_lines:
        bb=draw.textbbox((0,0),line,font=title_f)
        draw.text(((W-(bb[2]-bb[0]))/2,yy),line,font=title_f,fill=p["text"])
        yy += bb[3]-bb[1]+8

    # Large visual zone; no text is allowed in subtitle zone below 900.
    rect(draw,(90,340,W-90,870),p["panel"],p["accent"],2,30)
    kind=visual_kind(scene.get("visual_type") or scene.get("visual") or scene.get("diagram"),index)
    draw_visual(draw,kind,(145,385,W-290,450),p)

    # Tiny branded footer only above the subtitle-safe zone.
    draw.line((90,900,W-90,900),fill=p["accent"],width=2)
    foot=ImageFont.truetype(FONT,21)
    draw.text((90,922),"AI-assisted research • original commentary",font=foot,fill=p["muted"])
    img.save(path,quality=95)


def render_scene(index, scene, title, p):
    audio=VIDEO_DIR/f"scene_{index:02d}.mp3"
    image=VIDEO_DIR/f"scene_{index:02d}.png"
    ass=VIDEO_DIR/f"scene_{index:02d}.ass"
    out=VIDEO_DIR/f"segment_{index:02d}.mp4"
    narration=safe_text(scene.get("narration"))
    if not narration: raise SystemExit(f"Scene {index} has no narration.")
    scene_title=safe_text(scene.get("title") or scene.get("heading") or scene.get("key_phrase") or f"Scene {index}")
    run(["edge-tts","--voice",VOICE,"--text",narration,"--write-media",str(audio)])
    duration=audio_duration(audio)
    make_card(scene,index,scene_title,p,image)
    make_ass(narration,duration,ass)
    ass_path=str(ass).replace("\\","/").replace(":","\\:").replace("'","\\'")
    # Motion is applied to the card first; ASS subtitles are applied last.
    vf=("scale=1970:1108," 
        "zoompan=z='min(zoom+0.00012,1.02)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=30," 
        f"subtitles='{ass_path}'")
    run(["ffmpeg","-y","-loop","1","-i",str(image),"-i",str(audio),"-vf",vf,"-c:v","libx264","-preset","veryfast","-tune","stillimage","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-shortest","-t",str(duration),"-movflags","+faststart",str(out)])
    if not out.exists() or out.stat().st_size==0: raise SystemExit(f"Scene {index} was not created correctly.")
    return out


def main():
    if not PACKAGE_FILE.exists(): raise SystemExit(f"Missing {PACKAGE_FILE}")
    for tool in ("ffmpeg","ffprobe","edge-tts"):
        if not shutil.which(tool): raise SystemExit(f"{tool} is not installed.")
    package=json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))
    scenes=package.get("scenes",[])
    if len(scenes)<3: raise SystemExit(f"Expected at least 3 scenes, found {len(scenes)}")
    for item in VIDEO_DIR.iterdir():
        if item.is_file(): item.unlink()
    palettes=PALETTE.copy(); random.SystemRandom().shuffle(palettes)
    segments=[]
    for i,scene in enumerate(scenes,1):
        segments.append(render_scene(i,scene,package.get("chosen_title") or package.get("title") or "uncommonAI",palettes[i-1] if i-1<len(palettes) else palettes[(i-1)%len(palettes)]))
    concat=VIDEO_DIR/"segments.txt"
    concat.write_text("\n".join(f"file '{p.resolve()}'" for p in segments)+"\n",encoding="utf-8")
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy","-movflags","+faststart",str(OUTPUT)])
    if not OUTPUT.exists() or OUTPUT.stat().st_size==0: raise SystemExit("Final MP4 was not created correctly.")
    subprocess.run(["ffprobe","-v","error","-show_entries","format=duration,size","-show_entries","stream=codec_name,width,height","-of","default=noprint_wrappers=1",str(OUTPUT)],check=True)
    print(f"V11 VIDEO CREATED: {OUTPUT} | {OUTPUT.stat().st_size} bytes")

if __name__ == "__main__":
    main()
