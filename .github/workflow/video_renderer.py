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



def visual_keywords(scene, limit=4):
    """Extract concise labels from supplied scene data; never invent facts."""
    candidates = []
    for key in ("visual_labels", "key_points", "entities", "visual_text", "key_phrase", "heading", "title"):
        value = scene.get(key)
        if isinstance(value, list):
            candidates.extend(value)
        elif value:
            candidates.append(value)

    if not candidates:
        candidates = re.split(r"(?<=[.!?])\s+", safe_text(scene.get("narration")))

    labels = []
    for item in candidates:
        item = safe_text(item)
        item = re.sub(r"^(fact|point|step|result|example)\s*[:\-]\s*", "", item, flags=re.I)
        if not item or item.upper() in {x.upper() for x in labels}:
            continue
        if len(item.split()) > 8:
            item = " ".join(item.split()[:8])
        if 1 <= len(item.split()) <= 8:
            labels.append(item[:46])
        if len(labels) >= limit:
            break

    return labels or ["INPUT", "SYSTEM", "CHECK", "RESULT"]


def visual_kind(scene, index, previous=None):
    """Choose a visual treatment from scene meaning, while preventing adjacent repeats."""
    explicit = safe_text(scene.get("visual_type") or scene.get("visual") or scene.get("diagram")).lower()
    aliases = {
        "comparison": "compare", "process": "flow", "workflow": "flow",
        "system": "architecture", "stack": "architecture", "steps": "steps",
        "data": "metrics", "chart": "metrics", "trend": "metrics",
        "warning": "risk", "failure": "risk", "fact": "evidence",
        "claim": "evidence", "quote": "quote", "timeline": "timeline",
        "journey": "journey", "decision": "decision", "matrix": "matrix",
    }
    for key, value in aliases.items():
        if key in explicit:
            return value

    text = safe_text(scene.get("title")) + " " + safe_text(scene.get("heading")) + " " + safe_text(scene.get("narration"))
    text = text.lower()
    candidates = []
    if any(k in text for k in ("before", "after", "versus", " vs ", "compare", "compared")):
        candidates.append("compare")
    if any(k in text for k in ("risk", "failure", "broke", "broken", "danger", "problem", "missed")):
        candidates.append("risk")
    if any(k in text for k in ("step", "workflow", "process", "pipeline", "first", "then", "finally")):
        candidates.append("flow")
    if any(k in text for k in ("architecture", "system", "stack", "component", "layer")):
        candidates.append("architecture")
    if any(k in text for k in ("metric", "data", "percentage", "%", "rate", "latency", "score", "growth")):
        candidates.append("metrics")
    if any(k in text for k in ("timeline", "over time", "evolution", "history")):
        candidates.append("timeline")
    if any(k in text for k in ("evidence", "fact", "source", "study", "research")):
        candidates.append("evidence")
    if any(k in text for k in ("decision", "choose", "tradeoff", "should")):
        candidates.append("decision")

    rotation = ["flow", "compare", "architecture", "risk", "journey", "evidence", "metrics", "decision", "steps", "timeline", "quote", "matrix"]
    for kind in candidates + rotation:
        if kind != previous:
            return kind
    return rotation[index % len(rotation)]


def draw_header(draw, text, area, p, font):
    x, y, w, h = area
    draw.text((x, y), safe_text(text).upper()[:44], font=font, fill=p["accent"])


def draw_visual(draw, kind, area, p, scene=None):
    from PIL import ImageFont
    x, y, w, h = area
    scene = scene or {}
    labels = visual_keywords(scene, 4)
    title_font = ImageFont.truetype(BOLD, 28)
    label_font = ImageFont.truetype(BOLD, 24)
    body_font = ImageFont.truetype(FONT, 21)
    big_font = ImageFont.truetype(BOLD, 58)

    # Use the scene's own words rather than generic filler whenever possible.
    if kind == "flow":
        steps = (labels + ["CHECK", "RESULT"])[:4]
        bw = (w - 75) / 4
        by = y + 125
        for i, text in enumerate(steps):
            bx = x + i * (bw + 25)
            rect(draw, (bx, by, bx + bw, by + 220), p["panel"], p["accent"], 3, 24)
            center_text(draw, f"{i+1:02d}", (bx, by+18, bx+bw, by+70), label_font, p["accent"])
            center_text(draw, text.upper()[:25], (bx+18, by+75, bx+bw-18, by+180), label_font, p["text"])
            if i < 3:
                draw.line((bx+bw+5, by+110, bx+bw+18, by+110), fill=p["accent2"], width=5)
                draw.polygon([(bx+bw+18,by+110),(bx+bw+4,by+100),(bx+bw+4,by+120)], fill=p["accent2"])

    elif kind == "compare":
        pairs = labels[:3] if len(labels) >= 3 else ["BEFORE", "AI", "AFTER"]
        bw, gap = 420, 35
        total = 3*bw + 2*gap
        start = x + (w-total)/2
        by = y + 105
        for i, text in enumerate(pairs):
            bx = start + i*(bw+gap)
            rect(draw, (bx, by, bx+bw, by+300), p["panel"], p["accent"], 3, 26)
            center_text(draw, ["A", "B", "C"][i], (bx, by+22, bx+bw, by+78), big_font, p["accent"])
            center_text(draw, text.upper()[:24], (bx+25, by+105, bx+bw-25, by+215), label_font, p["text"])
            if i < 2:
                draw.line((bx+bw+4, by+150, bx+bw+gap-8, by+150), fill=p["muted"], width=4)

    elif kind == "architecture":
        nodes = (labels + ["SYSTEM", "OUTPUT"])[:4]
        bw = 330
        gap = 55
        total = 4*bw + 3*gap
        start = x + (w-total)/2
        cy = y + 235
        for i, text in enumerate(nodes):
            bx = start + i*(bw+gap)
            rect(draw, (bx, cy-100, bx+bw, cy+100), p["panel"], p["accent"], 3, 25)
            center_text(draw, f"{i+1}", (bx, cy-80, bx+bw, cy-25), label_font, p["accent"])
            center_text(draw, text.upper()[:22], (bx+15, cy-5, bx+bw-15, cy+70), label_font, p["text"])
            if i < 3:
                draw.line((bx+bw+6, cy, bx+bw+gap-10, cy), fill=p["accent2"], width=5)
                draw.polygon([(bx+bw+gap-10,cy),(bx+bw+gap-28,cy-11),(bx+bw+gap-28,cy+11)], fill=p["accent2"])

    elif kind == "risk":
        cx, cy = x+w/2, y+h/2
        draw.polygon([(cx,cy-175),(cx-170,cy+125),(cx+170,cy+125)], fill=p["panel"], outline=p["accent"])
        center_text(draw, "!", (cx-80,cy-115,cx+80,cy+50), ImageFont.truetype(BOLD,125), p["accent"])
        risk_label = labels[0] if labels else "RISK"
        center_text(draw, risk_label.upper()[:25], (x+150,cy+40,x+w-150,cy+105), label_font, p["text"])
        center_text(draw, "HUMAN REVIEW", (x+180,y+h-75,x+w-180,y+h-20), body_font, p["accent2"])

    elif kind == "metrics":
        # Qualitative visualization only unless actual numeric data is supplied.
        bars = labels[:3] if len(labels) >= 3 else ["SIGNAL", "CHANGE", "RESULT"]
        bx, by, bw = x+170, y+110, w-340
        for i, text in enumerate(bars):
            yy = by + i*105
            draw.text((bx, yy), text.upper()[:28], font=label_font, fill=p["text"])
            for dot in range(5):
                px = bx + bw - 180 + dot*36
                fill = p["accent"] if dot <= i else p["bg"]
                draw.ellipse((px-9, yy+46, px+9, yy+64), fill=fill, outline=p["muted"])
        draw.text((bx, by+345), "QUALITATIVE SIGNAL — NO INVENTED NUMBERS", font=body_font, fill=p["muted"])

    elif kind == "timeline":
        events = (labels + ["NEXT"])[:4]
        yy = y + 230
        x1, x2 = x+130, x+w-130
        draw.line((x1,yy,x2,yy), fill=p["muted"], width=5)
        for i, text in enumerate(events):
            px = x1 + i*(x2-x1)/max(1,len(events)-1)
            draw.ellipse((px-25,yy-25,px+25,yy+25), fill=p["accent"])
            center_text(draw, f"{i+1}", (px-25,yy-25,px+25,yy+25), label_font, p["bg"])
            center_text(draw, text.upper()[:22], (px-115,yy+55,px+115,yy+110), body_font, p["text"])

    elif kind == "journey":
        events = (labels + ["OUTCOME"])[:4]
        for i, text in enumerate(events):
            bx = x + 90 + i*((w-180)/4)
            cy = y + 225 + (25 if i % 2 else -25)
            draw.ellipse((bx-52,cy-52,bx+52,cy+52), fill=p["panel"], outline=p["accent"], width=4)
            center_text(draw, str(i+1), (bx-40,cy-40,bx+40,cy+40), big_font, p["accent"])
            center_text(draw, text.upper()[:18], (bx-100,cy+70,bx+100,cy+120), body_font, p["text"])
            if i < len(events)-1:
                nx = x + 90 + (i+1)*((w-180)/4)
                draw.line((bx+58,cy,nx-58,cy), fill=p["muted"], width=4)

    elif kind == "evidence":
        claim = safe_text(scene.get("key_claim") or scene.get("claim") or (labels[0] if labels else "KEY FINDING"))
        source = safe_text(scene.get("source") or scene.get("citation") or "SOURCE / EVIDENCE")
        rect(draw,(x+100,y+75,x+w-100,y+h-65),p["panel"],p["accent"],3,30)
        draw.text((x+150,y+120),"EVIDENCE",font=title_font,fill=p["accent"])
        lines = wrap(draw, claim, label_font, w-350, 3)
        yy=y+190
        for line in lines:
            center_text(draw,line,(x+150,yy,x+w-150,yy+55),label_font,p["text"]); yy+=65
        draw.line((x+150,y+h-175,x+w-150,y+h-175),fill=p["muted"],width=2)
        center_text(draw,source[:60],(x+150,y+h-150,x+w-150,y+h-95),body_font,p["muted"])

    elif kind == "decision":
        options = (labels + ["TRADE-OFF", "DECISION"])[:3]
        for i,text in enumerate(options):
            bx=x+120+i*430; by=y+135
            rect(draw,(bx,by,bx+350,by+210),p["panel"],p["accent"] if i==2 else p["muted"],3,26)
            center_text(draw,str(i+1),(bx,by+20,bx+350,by+80),big_font,p["accent"] if i==2 else p["muted"])
            center_text(draw,text.upper()[:20],(bx+20,by+95,bx+330,by+165),label_font,p["text"])
            if i<2:
                draw.line((bx+355,by+105,bx+420,by+105),fill=p["muted"],width=4)
        center_text(draw,"CHOOSE BASED ON CONTEXT",(x+200,y+h-75,x+w-200,y+h-25),body_font,p["accent2"])

    elif kind == "steps":
        steps = (labels + ["CHECK", "RESULT"])[:4]
        bw=(w-60)/2; gapx,gapy=60,45; by=y+35
        for i,text in enumerate(steps):
            row,col=divmod(i,2); bx=x+col*(bw+gapx); yy=by+row*(155+gapy)
            rect(draw,(bx,yy,bx+bw,yy+155),p["panel"],p["accent"],3,24)
            center_text(draw,f"{i+1}",(bx+18,yy+18,bx+80,yy+75),label_font,p["accent"])
            center_text(draw,text.upper()[:25],(bx+70,yy+35,bx+bw-20,yy+120),label_font,p["text"])

    elif kind == "quote":
        quote = safe_text(scene.get("quote") or scene.get("key_claim") or (labels[0] if labels else "KEY IDEA"))
        rect(draw,(x+150,y+70,x+w-150,y+h-70),p["panel"],p["accent"],3,30)
        center_text(draw,'“',(x+210,y+85,x+330,y+220),ImageFont.truetype(BOLD,105),p["accent"])
        lines=wrap(draw,quote,label_font,w-420,4); yy=y+220
        for line in lines:
            center_text(draw,line,(x+220,yy,x+w-220,yy+52),label_font,p["text"]); yy+=60
        center_text(draw,"ORIGINAL COMMENTARY",(x+250,y+h-145,x+w-250,y+h-90),body_font,p["muted"])

    else:  # matrix
        size=165; gap=30; gx=x+w/2-size-gap/2; gy=y+95
        labels2=(labels+["LOW","HIGH","RISK","VALUE"])[:4]
        for r in range(2):
            for c in range(2):
                bx=gx+c*(size+gap); by=gy+r*(size+gap)
                rect(draw,(bx,by,bx+size,by+size),p["panel"],p["accent"],3)
                center_text(draw,labels2[r*2+c].upper()[:14],(bx+10,by+35,bx+size-10,by+125),label_font,p["text"])

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
    draw.rounded_rectangle((85,118,W-85,128),radius=5,fill=p["panel"])
    draw.rounded_rectangle((85,118,85+int((W-170)*min(index/8,1.0)),128),radius=5,fill=p["accent"])

    title_f = font_fit(draw,title,BOLD,68,42,1580)
    title_lines = wrap(draw,title,title_f,1580,2)
    yy=155
    for line in title_lines:
        bb=draw.textbbox((0,0),line,font=title_f)
        draw.text(((W-(bb[2]-bb[0]))/2,yy),line,font=title_f,fill=p["text"])
        yy += bb[3]-bb[1]+8

    # Large visual zone; no text is allowed in subtitle zone below 900.
    rect(draw,(90,340,W-90,870),p["panel"],p["accent"],2,30)
    kind=scene.get("_renderer_visual_kind") or visual_kind(scene,index)
    draw_visual(draw,kind,(145,385,W-290,450),p,scene)

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
    previous_kind = None
    for i,scene in enumerate(scenes,1):
        chosen_kind = visual_kind(scene, i, previous_kind)
        scene = dict(scene)
        scene["_renderer_visual_kind"] = chosen_kind
        previous_kind = chosen_kind
        segments.append(render_scene(i,scene,package.get("chosen_title") or package.get("title") or "uncommonAI",palettes[(i-1)%len(palettes)]))
    concat=VIDEO_DIR/"segments.txt"
    concat.write_text("\n".join(f"file '{p.resolve()}'" for p in segments)+"\n",encoding="utf-8")
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy","-movflags","+faststart",str(OUTPUT)])
    if not OUTPUT.exists() or OUTPUT.stat().st_size==0: raise SystemExit("Final MP4 was not created correctly.")
    subprocess.run(["ffprobe","-v","error","-show_entries","format=duration,size","-show_entries","stream=codec_name,width,height","-of","default=noprint_wrappers=1",str(OUTPUT)],check=True)
    print(f"V12 VIDEO CREATED: {OUTPUT} | {OUTPUT.stat().st_size} bytes")

if __name__ == "__main__":
    main()
