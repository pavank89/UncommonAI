#!/usr/bin/env python3
import json
import hashlib
import math#!/usr/bin/env python3
import json
import hashlib
import math
import os
import random
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path.cwd()
WORK = ROOT / "workspace"
VIDEO_DIR = WORK / "video"
PACKAGE_FILE = WORK / "production_package.json"
OUTPUT = WORK / "uncommonAI_video.mp4"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "auto").lower().strip()
EDGE_VOICE = os.getenv("VIDEO_VOICE", "en-US-ChristopherNeural")
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "24"))
VIDEO_PRESET = os.getenv("VIDEO_PRESET", "superfast")
VIDEO_CRF = os.getenv("VIDEO_CRF", "23")
RENDER_CACHE = os.getenv("RENDER_CACHE", "1").lower() not in {"0", "false", "no"}
RENDER_VERSION = "V20"
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2").strip()
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
    """
    Extract useful visual labels from the producer package.

    Priority:
      1. explicit visual_labels/key_points/entities/visual_text
      2. key_phrase/title/heading
      3. visual_prompt
      4. narration

    The previous renderer ignored visual_prompt, which caused many scenes to
    fall back to generic CHECK/RESULT labels even when Gemini had supplied
    scene-specific visual instructions.
    """
    candidates = []

    for key in (
        "visual_labels",
        "key_points",
        "entities",
        "visual_text",
        "key_phrase",
        "heading",
        "title",
    ):
        value = scene.get(key)
        if isinstance(value, list):
            candidates.extend(value)
        elif value:
            candidates.append(value)

    # visual_prompt is deliberately considered after explicit labels so prose
    # prompts do not overwhelm concise labels, but before narration.
    for key in ("visual_prompt", "narration"):
        value = scene.get(key)
        if value:
            candidates.append(value)

    stop = {
        "the", "a", "an", "and", "or", "but", "for", "to", "of", "in", "on",
        "with", "from", "into", "that", "this", "these", "those", "is", "are",
        "was", "were", "be", "by", "as", "at", "it", "its", "their", "than",
        "then", "when", "where", "how", "why", "what", "which", "can", "could",
        "will", "would", "should", "not", "more", "less", "very", "just",
        "show", "shows", "showing", "visual", "diagram", "illustrate",
        "illustrates", "illustrating", "scene", "image", "use", "using",
    }

    labels = []

    def add_label(value):
        value = safe_text(value)
        value = re.sub(
            r"^(fact|point|step|result|example|label|node|box|input|output)\s*[:\-]\s*",
            "",
            value,
            flags=re.I,
        )
        value = re.sub(r"^[•*\-\d.)\s]+", "", value)
        value = value.strip(" ,.;:!?()[]{}\"'")

        if not value:
            return

        words = value.split()
        if len(words) > 6:
            value = " ".join(words[:6])

        if len(words) == 1 and value.lower() in stop:
            return

        normalized = re.sub(r"[^a-z0-9]+", "", value.lower())
        if not normalized:
            return

        existing = {
            re.sub(r"[^a-z0-9]+", "", x.lower())
            for x in labels
        }
        if normalized in existing:
            return

        # Reject renderer filler labels.
        if value.upper() in {
            "CHECK", "RESULT", "SYSTEM", "OUTPUT", "INPUT",
            "TRADE-OFF", "DECISION", "LOW", "HIGH", "RISK", "VALUE",
        }:
            return

        if 1 <= len(value.split()) <= 6 and len(value) <= 42:
            labels.append(value)

    for item in candidates:
        if isinstance(item, str):
            # Explicit short labels should stay intact.
            if len(item.split()) <= 6:
                add_label(item)
                continue

            # For prose, extract meaningful noun-like phrases from common
            # separators used by Gemini visual prompts.
            pieces = re.split(
                r"[|;•\n]|(?:\s+→\s+)|(?:\s+->\s+)|(?:\s+vs\.?\s+)|"
                r"(?:\s+versus\s+)",
                item,
                flags=re.I,
            )

            for piece in pieces:
                piece = re.sub(
                    r"^(show|display|illustrate|illustrating|depict|depicts|"
                    r"create|draw|animate|use)\s+",
                    "",
                    piece.strip(),
                    flags=re.I,
                )
                add_label(piece)

            # If the prompt is still prose, capture compact title-case or
            # uppercase concepts rather than the first arbitrary words.
            phrases = re.findall(
                r"\b(?:[A-Z][A-Za-z0-9/&+-]*(?:\s+[A-Z][A-Za-z0-9/&+-]*){0,4})\b",
                item,
            )
            for phrase in phrases:
                add_label(phrase)

        if len(labels) >= limit:
            break

    # Final fallback: derive compact concepts from the scene title/narration.
    if len(labels) < limit:
        text = safe_text(
            scene.get("title")
            or scene.get("heading")
            or scene.get("key_phrase")
            or scene.get("narration")
        )
        words = [
            re.sub(r"[^A-Za-z0-9/&+-]", "", w)
            for w in text.split()
        ]
        words = [w for w in words if len(w) >= 4 and w.lower() not in stop]

        for word in words:
            add_label(word)
            if len(labels) >= limit:
                break

    return labels[:limit] or ["KEY IDEA", "MECHANISM", "IMPLICATION", "TAKEAWAY"]

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
        # Producer-facing names that must map to an actual renderer.
        "hook": "journey",
        "takeaway": "decision",
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


def draw_glow(draw, center, radius, color, layers=7):
    """Soft radial glow built from translucent circles."""
    from PIL import Image, ImageDraw
    cx, cy = center
    for i in range(layers, 0, -1):
        r = radius * (i / layers)
        alpha = int(10 + 26 * (layers - i + 1) / layers)
        fill = (*color, alpha)
        # Draw on an RGBA layer supplied by caller.
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=fill)


def draw_glass_label(draw, box, text, p, emphasis=False):
    """Frosted-glass callout with restrained neon edge."""
    from PIL import ImageFont
    x1, y1, x2, y2 = box
    fill = (15, 18, 26, 190)
    outline = (*p["accent"], 190 if emphasis else 125)
    draw.rounded_rectangle(
        box, radius=18, fill=fill, outline=outline, width=2
    )
    font = ImageFont.truetype(BOLD if emphasis else FONT, 22 if emphasis else 19)
    text = safe_text(text)[:38]
    bb = draw.textbbox((0, 0), text, font=font)
    tx = (x1 + x2 - (bb[2]-bb[0])) / 2
    ty = (y1 + y2 - (bb[3]-bb[1])) / 2 - 2
    draw.text((tx, ty), text, font=font, fill=p["text"])


def draw_neural_network(draw, area, p, seed, density=24):
    """Organic network: irregular nodes, curved-ish segmented paths, no grid."""
    import math
    rng = random.Random(seed)
    x, y, w, h = area
    cx, cy = x + w * 0.52, y + h * 0.48

    nodes = []
    for i in range(density):
        angle = rng.random() * math.tau
        rr = (0.12 + 0.42 * (rng.random() ** 0.65)) * min(w, h)
        nx = cx + math.cos(angle) * rr * (1.15 if rng.random() > 0.5 else 0.85)
        ny = cy + math.sin(angle) * rr * 0.72
        nx += rng.uniform(-55, 55)
        ny += rng.uniform(-40, 40)
        nx = max(x + 35, min(x + w - 35, nx))
        ny = max(y + 35, min(y + h - 35, ny))
        nodes.append((nx, ny))

    # Connect nearby nodes, producing an organic web rather than a flowchart.
    for i, a in enumerate(nodes):
        nearest = sorted(
            range(len(nodes)),
            key=lambda j: (nodes[j][0]-a[0])**2 + (nodes[j][1]-a[1])**2
        )[1:4]
        for j in nearest:
            if j <= i:
                continue
            b = nodes[j]
            if rng.random() < 0.72:
                # Segmented curves simulate subtle fiber-optic pathways.
                mx = (a[0] + b[0]) / 2 + rng.uniform(-35, 35)
                my = (a[1] + b[1]) / 2 + rng.uniform(-25, 25)
                draw.line(
                    (a[0], a[1], mx, my),
                    fill=(*p["accent"], 42),
                    width=rng.choice([1, 1, 2])
                )
                draw.line(
                    (mx, my, b[0], b[1]),
                    fill=(*p["accent"], 68),
                    width=1
                )

    # A small number of active packets make the system feel alive.
    for i, (nx, ny) in enumerate(nodes):
        r = 3 if i % 4 else 5
        draw.ellipse(
            (nx-r, ny-r, nx+r, ny+r),
            fill=(*p["accent"], 185 if i % 4 else 235)
        )

    return nodes



def draw_particles(draw, center, radius, p, seed, count=90):
    """Soft, depth-layered particles for hero/cinematic scenes."""
    rng = random.Random(seed)
    cx, cy = center
    for i in range(count):
        angle = rng.random() * 6.283185
        rr = radius * (rng.random() ** 0.55)
        px = cx + math.cos(angle) * rr
        py = cy + math.sin(angle) * rr * 0.62
        size = rng.choice([1, 1, 2, 2, 3, 4])
        alpha = rng.randint(35, 155)
        draw.ellipse(
            (px-size, py-size, px+size, py+size),
            fill=(*p["accent"], alpha)
        )


def draw_hero(draw, area, p, labels, seed):
    from PIL import ImageFont
    x, y, w, h = area
    cx, cy = x + w*0.56, y + h*0.50
    draw_particles(draw, (cx, cy), min(w, h)*0.47, p, seed, 125)

    # Large cinematic execution core.
    for rr in range(155, 55, -9):
        alpha = max(8, int(70 * (155-rr)/100))
        draw.ellipse(
            (cx-rr, cy-rr, cx+rr, cy+rr),
            outline=(*p["accent"], alpha),
            width=2
        )

    # Fiber-like arcs instead of a diagram.
    for i in range(12):
        offset = (i-6) * 13
        draw.arc(
            (cx-210+offset, cy-150, cx+210+offset, cy+150),
            190+i*4, 355-i*3,
            fill=(*p["accent"], 35+i*8),
            width=2
        )

    draw.ellipse(
        (cx-58, cy-58, cx+58, cy+58),
        fill=(7, 10, 16, 235),
        outline=(*p["accent"], 235),
        width=3
    )
    f = ImageFont.truetype(BOLD, 30)
    label = (labels[0] if labels else "AI").upper()[:14]
    bb = draw.textbbox((0,0), label, font=f)
    draw.text(
        (cx-(bb[2]-bb[0])/2, cy-(bb[3]-bb[1])/2),
        label, font=f, fill=p["text"]
    )

    # One editorial callout, not a cluster.
    if labels:
        bw = min(390, max(230, 22*len(labels[-1])+75))
        bx, by = x+70, y+h-130
        draw_glass_label(draw, (bx, by, bx+bw, by+58), labels[-1], p, True)


def draw_flow(draw, area, p, labels, seed):
    from PIL import ImageFont
    x, y, w, h = area
    rng = random.Random(seed)
    points = []
    for i in range(7):
        px = x + 85 + i*(w-170)/6
        py = y + h*0.52 + math.sin(i*1.25 + seed)*75 + rng.uniform(-24,24)
        points.append((px, py))

    # Smooth-looking segmented flow paths.
    for j in range(4):
        prev = points[0]
        for i in range(1, len(points)):
            px, py = points[i]
            mx = (prev[0]+px)/2
            my = (prev[1]+py)/2 + math.sin(i+j)*18
            draw.line((prev[0],prev[1],mx,my), fill=(*p["accent"],55+j*12), width=2+j%2)
            draw.line((mx,my,px,py), fill=(*p["accent"],80+j*12), width=2)
            prev = (px,py)

    for i, (px, py) in enumerate(points):
        r = 16 if i in (0,6) else 10
        draw.ellipse((px-r,py-r,px+r,py+r), fill=(8,12,18,235), outline=(*p["accent"],220), width=2)
        if i < len(labels):
            bw = min(300, max(190, 18*len(labels[i])+65))
            bx = px-bw/2
            by = py-92 if i%2 == 0 else py+45
            draw_glass_label(draw, (bx,by,bx+bw,by+52), labels[i], p, i==0)


def draw_architecture(draw, area, p, labels, seed):
    from PIL import ImageFont
    x, y, w, h = area
    cx = x+w/2
    layers = [
        (y+h*0.16, w*0.58, labels[0] if labels else "INTERFACE"),
        (y+h*0.38, w*0.72, labels[1] if len(labels)>1 else "ORCHESTRATION"),
        (y+h*0.60, w*0.84, labels[2] if len(labels)>2 else "DATA"),
        (y+h*0.82, w*0.94, labels[3] if len(labels)>3 else "INFRASTRUCTURE"),
    ]
    for i,(yy,ww,label) in enumerate(layers):
        left = cx-ww/2
        right = cx+ww/2
        draw.rounded_rectangle(
            (left,yy,right,yy+78),
            radius=28,
            fill=(10,14,21,155-i*12),
            outline=(*p["accent"],155-i*18),
            width=2
        )
        draw.text(
            (left+30, yy+23),
            label[:30],
            font=ImageFont.truetype(BOLD if i==0 else FONT, 23),
            fill=p["text"]
        )
        if i < len(layers)-1:
            draw.line(
                (cx,yy+78,cx,y+h*([0.38,0.60,0.82][i])),
                fill=(*p["accent"],80),
                width=2
            )


def draw_compare(draw, area, p, labels, seed):
    from PIL import ImageFont
    x, y, w, h = area
    mid = x+w/2
    # Two distinct states, no card grid.
    for side, xx, accent_alpha in [
        ("BEFORE", x+w*0.25, 95),
        ("AFTER", x+w*0.75, 220),
    ]:
        draw.ellipse(
            (xx-105,y+h*0.48-105,xx+105,y+h*0.48+105),
            fill=(8,12,18,220),
            outline=(*p["accent"],accent_alpha),
            width=3
        )
    # Transformation ribbon.
    draw.line(
        (mid-115,y+h*0.48,mid+115,y+h*0.48),
        fill=(*p["accent"],185),
        width=5
    )
    draw.polygon(
        [(mid+115,y+h*0.48),(mid+90,y+h*0.48-15),(mid+90,y+h*0.48+15)],
        fill=(*p["accent"],205)
    )
    if labels:
        draw_glass_label(draw,(x+60,y+40,x+380,y+96),labels[0],p,False)
    if len(labels)>1:
        draw_glass_label(draw,(x+w-380,y+40,x+w-60,y+96),labels[1],p,True)
    for i, lab in enumerate(labels[2:4]):
        bx = x+w*0.34 + i*230
        draw_glass_label(draw,(bx,y+h-95,bx+205,y+h-40),lab,p,False)


def draw_metrics(draw, area, p, labels, seed):
    from PIL import ImageFont
    x, y, w, h = area
    # Minimal editorial chart with no invented numbers.
    left, bottom = x+90, y+h-70
    right, top = x+w-80, y+75
    draw.line((left,top,left,bottom), fill=(*p["muted"],90), width=2)
    draw.line((left,bottom,right,bottom), fill=(*p["muted"],90), width=2)

    pts=[]
    rng=random.Random(seed)
    for i in range(9):
        px=left+(right-left)*i/8
        py=bottom-(bottom-top)*(0.18+0.65*(i/8)**1.15)+rng.uniform(-12,12)
        pts.append((px,py))
    for a,b in zip(pts,pts[1:]):
        draw.line((a[0],a[1],b[0],b[1]),fill=(*p["accent"],205),width=4)
    for i,(px,py) in enumerate(pts):
        r=6 if i not in (4,8) else 9
        draw.ellipse((px-r,py-r,px+r,py+r),fill=(*p["accent"],230))
    if labels:
        draw_glass_label(draw,(x+105,y+80,x+390,y+136),labels[0],p,True)
    if len(labels)>1:
        draw_glass_label(draw,(right-340,top+20,right-55,top+76),labels[1],p,False)


def draw_risk(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    rng=random.Random(seed)
    cx=x+w*0.50
    # Stable left side becomes a branching fracture toward the right.
    start=(x+100,y+h*0.52)
    end=(x+w-100,y+h*0.52)
    draw.line((start[0],start[1],end[0],end[1]),fill=(*p["accent"],110),width=4)
    for i in range(6):
        px=x+w*(0.35+i*0.08)
        py=y+h*0.52+rng.uniform(-25,25)
        draw.line((px,py,px+rng.uniform(55,100),py+rng.uniform(-90,90)),fill=(*p["accent"],100),width=3)
        draw.ellipse((px-7,py-7,px+7,py+7),fill=(*p["accent"],220))
    draw.ellipse((start[0]-30,start[1]-30,start[0]+30,start[1]+30),fill=(8,12,18,235),outline=(*p["accent"],180),width=2)
    draw.ellipse((end[0]-42,end[1]-42,end[0]+42,end[1]+42),fill=(8,12,18,235),outline=(*p["accent"],240),width=3)
    if labels:
        draw_glass_label(draw,(x+45,y+80,x+350,y+136),labels[0],p,False)
    if len(labels)>1:
        draw_glass_label(draw,(x+w-390,y+h-135,x+w-70,y+h-79),labels[1],p,True)


def draw_timeline(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    yline=y+h*0.55
    # Curved-ish timeline using short segments.
    pts=[]
    for i in range(7):
        px=x+100+i*(w-200)/6
        py=yline+math.sin(i*0.9+seed)*65
        pts.append((px,py))
    for a,b in zip(pts,pts[1:]):
        draw.line((a[0],a[1],b[0],b[1]),fill=(*p["accent"],185),width=4)
    for i,(px,py) in enumerate(pts):
        r=13 if i%2 else 17
        draw.ellipse((px-r,py-r,px+r,py+r),fill=(8,12,18,235),outline=(*p["accent"],220),width=2)
        if i<len(labels):
            bw=min(270,max(175,17*len(labels[i])+65))
            by=py-88 if i%2==0 else py+45
            draw_glass_label(draw,(px-bw/2,by,px+bw/2,by+52),labels[i],p,i==0)


def draw_evidence(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    # One source ribbon + supporting evidence markers, avoiding card walls.
    draw.rounded_rectangle(
        (x+90,y+110,x+w-90,y+h-115),
        radius=34,
        fill=(9,13,20,150),
        outline=(*p["accent"],130),
        width=2
    )
    f=ImageFont.truetype(BOLD,31)
    quote=(labels[0] if labels else "SOURCE")[:54]
    draw.text((x+145,y+160), "EVIDENCE",font=f,fill=(*p["accent"],210))
    body=ImageFont.truetype(FONT,27)
    lines=wrap(draw,quote,body,w-320,3)
    yy=y+225
    for line in lines:
        draw.text((x+145,yy),line,font=body,fill=p["text"])
        yy+=38
    for i,lab in enumerate(labels[1:4]):
        bx=x+150+i*390
        draw_glass_label(draw,(bx,y+h-185,bx+330,y+h-130),lab,p,i==0)


def draw_decision(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    cx=x+w*0.48
    root=(x+120,y+h*0.50)
    junction=(cx,y+h*0.50)
    draw.line((root[0],root[1],junction[0],junction[1]),fill=(*p["accent"],200),width=4)
    draw.ellipse((root[0]-22,root[1]-22,root[0]+22,root[1]+22),fill=(8,12,18,235),outline=(*p["accent"],210),width=3)
    for i in range(3):
        yy=y+h*(0.24+i*0.26)
        end=(x+w-120,yy)
        draw.line((junction[0],junction[1],end[0],end[1]),fill=(*p["accent"],100+i*40),width=3)
        draw.ellipse((end[0]-18,end[1]-18,end[0]+18,end[1]+18),fill=(8,12,18,235),outline=(*p["accent"],170+i*25),width=2)
        if i<len(labels):
            bw=min(300,max(190,18*len(labels[i])+65))
            draw_glass_label(draw,(end[0]-bw-25,yy-28,end[0]-25,yy+28),labels[i],p,i==2)


def draw_steps(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    count=min(5,max(3,len(labels)))
    x0=x+170
    for i in range(count):
        yy=y+80+i*(h-160)/max(count-1,1)
        draw.ellipse((x0-18,yy-18,x0+18,yy+18),fill=(8,12,18,235),outline=(*p["accent"],210),width=3)
        if i<count-1:
            next_y=y+80+(i+1)*(h-160)/max(count-1,1)
            draw.line((x0,next_y-18,x0,yy+18),fill=(*p["accent"],110),width=3)
        if i<len(labels):
            draw_glass_label(draw,(x0+55,yy-28,x0+55+min(520,max(260,20*len(labels[i])+80)),yy+28),labels[i],p,i==0)


def draw_quote(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    f=ImageFont.truetype(BOLD,48)
    quote=(labels[0] if labels else "THE KEY INSIGHT")
    lines=wrap(draw,quote,f,w-300,3)
    yy=y+120
    draw.text((x+115,y+75),"“",font=ImageFont.truetype(BOLD,90),fill=(*p["accent"],210))
    for line in lines:
        draw.text((x+175,yy),line,font=f,fill=p["text"])
        yy+=62
    draw.line((x+175,yy+20,x+w-190,yy+20),fill=(*p["accent"],130),width=2)
    if len(labels)>1:
        draw.text((x+175,yy+45),labels[1][:48],font=ImageFont.truetype(FONT,24),fill=(*p["muted"],190))


def draw_matrix(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    cx=x+w*0.5
    cy=y+h*0.5
    size=min(w*0.55,h*0.68)
    left=cx-size/2
    top=cy-size/2
    draw.rounded_rectangle((left,top,left+size,top+size),radius=30,fill=(9,13,20,135),outline=(*p["accent"],120),width=2)
    draw.line((cx,top+25,cx,top+size-25),fill=(*p["accent"],85),width=2)
    draw.line((left+25,cy,left+size-25,cy),fill=(*p["accent"],85),width=2)
    positions=[
        (left+size*0.16,top+size*0.16),
        (left+size*0.55,top+size*0.16),
        (left+size*0.16,top+size*0.60),
        (left+size*0.55,top+size*0.60),
    ]
    for i,(px,py) in enumerate(positions):
        lab=labels[i] if i<len(labels) else f"OPTION {i+1}"
        draw.text((px,py),lab[:22],font=ImageFont.truetype(BOLD if i==0 else FONT,21),fill=p["text"] if i==0 else (*p["muted"],200))


def draw_visual_v19(draw, kind, area, p, scene=None, seed=1):
    from PIL import ImageFont
    """
    V19 visual grammar router.

    Each scene gets a deliberately different visual language instead of
    reusing the same central-circle/network composition.
    """
    scene = scene or {}
    labels = visual_keywords(scene, 5)

    # Guarantee meaningful labels for the specialized grammars.
    if len(labels) < 3:
        labels = (labels + ["MECHANISM", "IMPLICATION", "OUTCOME"])[:5]

    dispatch = {
        "journey": draw_hero,
        "flow": draw_flow,
        "architecture": draw_architecture,
        "compare": draw_compare,
        "metrics": draw_metrics,
        "risk": draw_risk,
        "timeline": draw_timeline,
        "evidence": draw_evidence,
        "decision": draw_decision,
        "steps": draw_steps,
        "quote": draw_quote,
        "matrix": draw_matrix,
    }

    fn = dispatch.get(kind, draw_hero)
    fn(draw, area, p, labels, seed)


def draw_visual(draw, kind, area, p, scene=None, seed=1):
    # V19: deliberately varied visual grammar per scene.
    draw_visual_v19(draw, kind, area, p, scene, seed)

def make_card(scene, index, title, p, path, visual_path=None):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    W, H = 1920, 1080
    img = Image.new("RGBA", (W, H), (*p["bg"], 255))
    draw = ImageDraw.Draw(img, "RGBA")

    # Atmospheric vignette / grain — intentionally subtle.
    rng = random.Random(4000 + index)
    for _ in range(420):
        px = rng.randrange(W)
        py = rng.randrange(H)
        a = rng.randrange(4, 16)
        draw.point((px, py), fill=(*p["accent"], a))

    # Soft horizon glow gives the frame depth without a visible card.
    for r in range(520, 80, -30):
        alpha = max(2, int(22 * (520-r) / 440))
        draw.ellipse(
            (W*0.5-r, H*0.48-r, W*0.5+r, H*0.48+r),
            outline=(*p["accent"], alpha),
            width=3
        )

    # Editorial header: small, quiet, premium.
    top = ImageFont.truetype(BOLD, 24)
    scene_f = ImageFont.truetype(FONT, 20)
    draw.text((78, 62), "uncommonAI", font=top, fill=(*p["text"], 215))
    draw.text(
        (W-220, 64),
        f"{index:02d} / 08",
        font=scene_f,
        fill=(*p["accent"], 180),
    )

    # Kinetic-style title: compact and left aligned rather than a centered card.
    title_f = font_fit(draw, title, BOLD, 54, 36, 900)
    title_lines = wrap(draw, title, title_f, 900, 2)
    yy = 108
    for line in title_lines:
        draw.text((82, yy), line, font=title_f, fill=(*p["text"], 242))
        bb = draw.textbbox((0, 0), line, font=title_f)
        yy += bb[3]-bb[1] + 6

    # Thin accent trace instead of the old progress bar.
    draw.line(
        (82, yy+12, min(820, 82+len(title)*15), yy+12),
        fill=(*p["accent"], 200),
        width=3
    )

    # Visual field is intentionally borderless.
    if visual_path:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer, "RGBA")
        kind = scene.get("_renderer_visual_kind") or visual_kind(scene, index)
        draw_visual(
            ld,
            kind,
            (95, 275, W-190, 575),
            p,
            scene,
            seed=7000 + index * 31,
        )
        layer.save(visual_path)

    # Keep the lower region deliberately quiet for subtitles.
    draw.line(
        (82, 900, W-82, 900),
        fill=(*p["accent"], 55),
        width=1,
    )
    foot = ImageFont.truetype(FONT, 18)
    draw.text(
        (82, 925),
        "AI-assisted research  ·  original commentary",
        font=foot,
        fill=(*p["muted"], 145),
    )

    img.convert("RGB").save(path, quality=95)



def generate_voice(text, output_path):
    """
    Generate narration using the selected voice backend.

    VOICE_PROVIDER:
      auto        -> ElevenLabs when credentials are present, otherwise Edge TTS
      elevenlabs  -> require ElevenLabs credentials
      edge        -> always use Edge TTS

    This keeps the renderer backward-compatible while allowing a personal
    ElevenLabs voice clone to be introduced without changing the renderer.
    """
    output_path = Path(output_path)

    use_eleven = (
        VOICE_PROVIDER == "elevenlabs"
        or (
            VOICE_PROVIDER == "auto"
            and ELEVENLABS_API_KEY
            and ELEVENLABS_VOICE_ID
        )
    )

    if use_eleven:
        if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
            raise SystemExit(
                "VOICE_PROVIDER=elevenlabs requires "
                "ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID."
            )

        url = (
            "https://api.elevenlabs.io/v1/text-to-speech/"
            f"{ELEVENLABS_VOICE_ID}"
        )

        payload = {
            "text": safe_text(text),
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": 0.48,
                "similarity_boost": 0.82,
                "style": 0.18,
                "use_speaker_boost": True,
            },
        }

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                output_path.write_bytes(response.read())
            print(f"TTS: ElevenLabs voice clone -> {output_path}")
            return
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if VOICE_PROVIDER == "elevenlabs":
                print("ELEVENLABS API ERROR:")
                print(body[:4000])
                raise SystemExit(
                    f"ElevenLabs narration failed with HTTP {exc.code}."
                )
            print(
                f"ElevenLabs unavailable (HTTP {exc.code}); "
                "falling back to Edge TTS."
            )
        except Exception as exc:
            if VOICE_PROVIDER == "elevenlabs":
                raise SystemExit(
                    f"ElevenLabs narration failed: {exc}"
                )
            print(
                f"ElevenLabs unavailable ({exc}); "
                "falling back to Edge TTS."
            )

    run([
        "edge-tts",
        "--voice",
        EDGE_VOICE,
        "--text",
        safe_text(text),
        "--write-media",
        str(output_path),
    ])
    print(f"TTS: Edge TTS ({EDGE_VOICE}) -> {output_path}")



def cache_key(*parts):
    h = hashlib.sha256()
    for part in parts:
        if isinstance(part, bytes):
            data = part
        else:
            data = str(part).encode("utf-8")
        h.update(data)
        h.update(b"\0")
    return h.hexdigest()[:20]


def cache_valid(path, key):
    if not RENDER_CACHE or not path.exists() or path.stat().st_size == 0:
        return False
    marker = path.with_suffix(path.suffix + ".cache")
    try:
        return marker.read_text(encoding="utf-8").strip() == key
    except Exception:
        return False


def write_cache_marker(path, key):
    path.with_suffix(path.suffix + ".cache").write_text(key, encoding="utf-8")


def render_scene(index, scene, title, p):
    audio=VIDEO_DIR/f"scene_{index:02d}.mp3"
    image=VIDEO_DIR/f"scene_{index:02d}.png"
    visual_layer=VIDEO_DIR/f"scene_{index:02d}_visual.png"
    ass=VIDEO_DIR/f"scene_{index:02d}.ass"
    out=VIDEO_DIR/f"segment_{index:02d}.mp4"

    narration=safe_text(scene.get("narration"))
    if not narration:
        raise SystemExit(f"Scene {index} has no narration.")
    scene_title=safe_text(
        scene.get("title")
        or scene.get("heading")
        or scene.get("key_phrase")
        or f"Scene {index}"
    )

    # Cache keys prevent expensive Edge TTS and PIL regeneration on reruns.
    voice_key = cache_key(
        RENDER_VERSION, "voice", VOICE_PROVIDER, EDGE_VOICE,
        ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL, narration
    )
    visual_key = cache_key(
        RENDER_VERSION, "visual", index, scene_title,
        json.dumps(scene, sort_keys=True, ensure_ascii=False),
        json.dumps(p, sort_keys=True),
    )
    duration_key = None

    if not cache_valid(audio, voice_key):
        generate_voice(narration, audio)
        write_cache_marker(audio, voice_key)
    else:
        print(f"CACHE: narration scene {index} -> {audio}")

    duration=audio_duration(audio)
    duration_key = cache_key(RENDER_VERSION, "ass", narration, round(duration, 3))

    if not cache_valid(image, visual_key):
        make_card(scene,index,scene_title,p,image,visual_layer)
        write_cache_marker(image, visual_key)
        write_cache_marker(visual_layer, visual_key)
    else:
        print(f"CACHE: visuals scene {index}")

    if not cache_valid(ass, duration_key):
        make_ass(narration,duration,ass)
        write_cache_marker(ass, duration_key)
    else:
        print(f"CACHE: subtitles scene {index}")

    ass_path=str(ass).replace("\\","/").replace(":","\\:").replace("'","\\'")

    # V20 performance optimization:
    # - 24 fps is cinematic and cuts ~20% of encoded frames vs 30 fps.
    # - No zoompan: it was one of the most expensive filters in V19.
    # - Cheap crop-based micro-drift preserves motion without frame synthesis.
    # - superfast x264 keeps GitHub Actions runtime reasonable.
    # - subtitles remain burned in, so no change to the output design.
    vf = (
        f"[0:v]"
        f"scale=1960:1102:flags=fast_bilinear,"
        f"crop=1920:1080:"
        f"x='20+8*sin(t/9)':"
        f"y='11+5*cos(t/11)',"
        f"fps={VIDEO_FPS}[base];"
        f"[2:v]format=rgba,"
        f"scale=1960:1102:flags=fast_bilinear,"
        f"crop=1920:1080:"
        f"x='20+10*sin(t/10)':"
        f"y='11+6*cos(t/12)',"
        f"fps={VIDEO_FPS},"
        f"fade=t=in:st=0:d=0.5:alpha=1[vl];"
        f"[base][vl]"
        f"overlay=x='2*sin(t/8)':y='2*cos(t/9)':shortest=1,"
        f"drawbox=x='82':y='250':w='1756':h='2':"
        f"color=white@0.12:t=fill,"
        f"subtitles='{ass_path}'[vout]"
    )

    segment_key = cache_key(
        RENDER_VERSION, "segment", index, narration, scene_title,
        visual_key, duration, VIDEO_FPS, VIDEO_PRESET, VIDEO_CRF
    )
    if cache_valid(out, segment_key):
        print(f"CACHE: encoded segment {index} -> {out}")
    else:
        run([
            "ffmpeg","-y",
            "-loop","1","-framerate",str(VIDEO_FPS),"-i",str(image),
            "-i",str(audio),
            "-loop","1","-framerate",str(VIDEO_FPS),"-i",str(visual_layer),
            "-filter_complex",vf,
            "-map","[vout]","-map","1:a",
            "-c:v","libx264",
            "-preset",VIDEO_PRESET,
            "-crf",VIDEO_CRF,
            "-tune","stillimage",
            "-pix_fmt","yuv420p",
            "-r",str(VIDEO_FPS),
            "-c:a","aac","-b:a","160k",
            "-shortest","-t",str(duration),
            "-movflags","+faststart",
            str(out)
        ])
        if out.exists() and out.stat().st_size > 0:
            write_cache_marker(out, segment_key)

    if not out.exists() or out.stat().st_size==0:
        raise SystemExit(f"Scene {index} was not created correctly.")
    return out



def main():
    if not PACKAGE_FILE.exists(): raise SystemExit(f"Missing {PACKAGE_FILE}")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} is not installed.")

    # Edge TTS remains available as the safe fallback in auto mode.
    use_eleven_only = VOICE_PROVIDER == "elevenlabs"
    if not use_eleven_only and not shutil.which("edge-tts"):
        if not (ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID):
            raise SystemExit(
                "Neither Edge TTS nor a configured ElevenLabs voice is available."
            )
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
    print(f"V20 FAST PREMIUM VIDEO CREATED: {OUTPUT} | {OUTPUT.stat().st_size} bytes")

if __name__ == "__main__":
    main()
import os
import random
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path.cwd()
WORK = ROOT / "workspace"
VIDEO_DIR = WORK / "video"
PACKAGE_FILE = WORK / "production_package.json"
OUTPUT = WORK / "uncommonAI_video.mp4"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "auto").lower().strip()
EDGE_VOICE = os.getenv("VIDEO_VOICE", "en-US-ChristopherNeural")
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "24"))
VIDEO_PRESET = os.getenv("VIDEO_PRESET", "superfast")
VIDEO_CRF = os.getenv("VIDEO_CRF", "23")
RENDER_CACHE = os.getenv("RENDER_CACHE", "1").lower() not in {"0", "false", "no"}
RENDER_VERSION = "V20"
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2").strip()
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
    """
    Extract useful visual labels from the producer package.

    Priority:
      1. explicit visual_labels/key_points/entities/visual_text
      2. key_phrase/title/heading
      3. visual_prompt
      4. narration

    The previous renderer ignored visual_prompt, which caused many scenes to
    fall back to generic CHECK/RESULT labels even when Gemini had supplied
    scene-specific visual instructions.
    """
    candidates = []

    for key in (
        "visual_labels",
        "key_points",
        "entities",
        "visual_text",
        "key_phrase",
        "heading",
        "title",
    ):
        value = scene.get(key)
        if isinstance(value, list):
            candidates.extend(value)
        elif value:
            candidates.append(value)

    # visual_prompt is deliberately considered after explicit labels so prose
    # prompts do not overwhelm concise labels, but before narration.
    for key in ("visual_prompt", "narration"):
        value = scene.get(key)
        if value:
            candidates.append(value)

    stop = {
        "the", "a", "an", "and", "or", "but", "for", "to", "of", "in", "on",
        "with", "from", "into", "that", "this", "these", "those", "is", "are",
        "was", "were", "be", "by", "as", "at", "it", "its", "their", "than",
        "then", "when", "where", "how", "why", "what", "which", "can", "could",
        "will", "would", "should", "not", "more", "less", "very", "just",
        "show", "shows", "showing", "visual", "diagram", "illustrate",
        "illustrates", "illustrating", "scene", "image", "use", "using",
    }

    labels = []

    def add_label(value):
        value = safe_text(value)
        value = re.sub(
            r"^(fact|point|step|result|example|label|node|box|input|output)\s*[:\-]\s*",
            "",
            value,
            flags=re.I,
        )
        value = re.sub(r"^[•*\-\d.)\s]+", "", value)
        value = value.strip(" ,.;:!?()[]{}\"'")

        if not value:
            return

        words = value.split()
        if len(words) > 6:
            value = " ".join(words[:6])

        if len(words) == 1 and value.lower() in stop:
            return

        normalized = re.sub(r"[^a-z0-9]+", "", value.lower())
        if not normalized:
            return

        existing = {
            re.sub(r"[^a-z0-9]+", "", x.lower())
            for x in labels
        }
        if normalized in existing:
            return

        # Reject renderer filler labels.
        if value.upper() in {
            "CHECK", "RESULT", "SYSTEM", "OUTPUT", "INPUT",
            "TRADE-OFF", "DECISION", "LOW", "HIGH", "RISK", "VALUE",
        }:
            return

        if 1 <= len(value.split()) <= 6 and len(value) <= 42:
            labels.append(value)

    for item in candidates:
        if isinstance(item, str):
            # Explicit short labels should stay intact.
            if len(item.split()) <= 6:
                add_label(item)
                continue

            # For prose, extract meaningful noun-like phrases from common
            # separators used by Gemini visual prompts.
            pieces = re.split(
                r"[|;•\n]|(?:\s+→\s+)|(?:\s+->\s+)|(?:\s+vs\.?\s+)|"
                r"(?:\s+versus\s+)",
                item,
                flags=re.I,
            )

            for piece in pieces:
                piece = re.sub(
                    r"^(show|display|illustrate|illustrating|depict|depicts|"
                    r"create|draw|animate|use)\s+",
                    "",
                    piece.strip(),
                    flags=re.I,
                )
                add_label(piece)

            # If the prompt is still prose, capture compact title-case or
            # uppercase concepts rather than the first arbitrary words.
            phrases = re.findall(
                r"\b(?:[A-Z][A-Za-z0-9/&+-]*(?:\s+[A-Z][A-Za-z0-9/&+-]*){0,4})\b",
                item,
            )
            for phrase in phrases:
                add_label(phrase)

        if len(labels) >= limit:
            break

    # Final fallback: derive compact concepts from the scene title/narration.
    if len(labels) < limit:
        text = safe_text(
            scene.get("title")
            or scene.get("heading")
            or scene.get("key_phrase")
            or scene.get("narration")
        )
        words = [
            re.sub(r"[^A-Za-z0-9/&+-]", "", w)
            for w in text.split()
        ]
        words = [w for w in words if len(w) >= 4 and w.lower() not in stop]

        for word in words:
            add_label(word)
            if len(labels) >= limit:
                break

    return labels[:limit] or ["KEY IDEA", "MECHANISM", "IMPLICATION", "TAKEAWAY"]

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
        # Producer-facing names that must map to an actual renderer.
        "hook": "journey",
        "takeaway": "decision",
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


def draw_glow(draw, center, radius, color, layers=7):
    """Soft radial glow built from translucent circles."""
    from PIL import Image, ImageDraw
    cx, cy = center
    for i in range(layers, 0, -1):
        r = radius * (i / layers)
        alpha = int(10 + 26 * (layers - i + 1) / layers)
        fill = (*color, alpha)
        # Draw on an RGBA layer supplied by caller.
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=fill)


def draw_glass_label(draw, box, text, p, emphasis=False):
    """Frosted-glass callout with restrained neon edge."""
    from PIL import ImageFont
    x1, y1, x2, y2 = box
    fill = (15, 18, 26, 190)
    outline = (*p["accent"], 190 if emphasis else 125)
    draw.rounded_rectangle(
        box, radius=18, fill=fill, outline=outline, width=2
    )
    font = ImageFont.truetype(BOLD if emphasis else FONT, 22 if emphasis else 19)
    text = safe_text(text)[:38]
    bb = draw.textbbox((0, 0), text, font=font)
    tx = (x1 + x2 - (bb[2]-bb[0])) / 2
    ty = (y1 + y2 - (bb[3]-bb[1])) / 2 - 2
    draw.text((tx, ty), text, font=font, fill=p["text"])


def draw_neural_network(draw, area, p, seed, density=24):
    """Organic network: irregular nodes, curved-ish segmented paths, no grid."""
    import math
    rng = random.Random(seed)
    x, y, w, h = area
    cx, cy = x + w * 0.52, y + h * 0.48

    nodes = []
    for i in range(density):
        angle = rng.random() * math.tau
        rr = (0.12 + 0.42 * (rng.random() ** 0.65)) * min(w, h)
        nx = cx + math.cos(angle) * rr * (1.15 if rng.random() > 0.5 else 0.85)
        ny = cy + math.sin(angle) * rr * 0.72
        nx += rng.uniform(-55, 55)
        ny += rng.uniform(-40, 40)
        nx = max(x + 35, min(x + w - 35, nx))
        ny = max(y + 35, min(y + h - 35, ny))
        nodes.append((nx, ny))

    # Connect nearby nodes, producing an organic web rather than a flowchart.
    for i, a in enumerate(nodes):
        nearest = sorted(
            range(len(nodes)),
            key=lambda j: (nodes[j][0]-a[0])**2 + (nodes[j][1]-a[1])**2
        )[1:4]
        for j in nearest:
            if j <= i:
                continue
            b = nodes[j]
            if rng.random() < 0.72:
                # Segmented curves simulate subtle fiber-optic pathways.
                mx = (a[0] + b[0]) / 2 + rng.uniform(-35, 35)
                my = (a[1] + b[1]) / 2 + rng.uniform(-25, 25)
                draw.line(
                    (a[0], a[1], mx, my),
                    fill=(*p["accent"], 42),
                    width=rng.choice([1, 1, 2])
                )
                draw.line(
                    (mx, my, b[0], b[1]),
                    fill=(*p["accent"], 68),
                    width=1
                )

    # A small number of active packets make the system feel alive.
    for i, (nx, ny) in enumerate(nodes):
        r = 3 if i % 4 else 5
        draw.ellipse(
            (nx-r, ny-r, nx+r, ny+r),
            fill=(*p["accent"], 185 if i % 4 else 235)
        )

    return nodes



def draw_particles(draw, center, radius, p, seed, count=90):
    """Soft, depth-layered particles for hero/cinematic scenes."""
    rng = random.Random(seed)
    cx, cy = center
    for i in range(count):
        angle = rng.random() * 6.283185
        rr = radius * (rng.random() ** 0.55)
        px = cx + math.cos(angle) * rr
        py = cy + math.sin(angle) * rr * 0.62
        size = rng.choice([1, 1, 2, 2, 3, 4])
        alpha = rng.randint(35, 155)
        draw.ellipse(
            (px-size, py-size, px+size, py+size),
            fill=(*p["accent"], alpha)
        )


def draw_hero(draw, area, p, labels, seed):
    from PIL import ImageFont
    x, y, w, h = area
    cx, cy = x + w*0.56, y + h*0.50
    draw_particles(draw, (cx, cy), min(w, h)*0.47, p, seed, 125)

    # Large cinematic execution core.
    for rr in range(155, 55, -9):
        alpha = max(8, int(70 * (155-rr)/100))
        draw.ellipse(
            (cx-rr, cy-rr, cx+rr, cy+rr),
            outline=(*p["accent"], alpha),
            width=2
        )

    # Fiber-like arcs instead of a diagram.
    for i in range(12):
        offset = (i-6) * 13
        draw.arc(
            (cx-210+offset, cy-150, cx+210+offset, cy+150),
            190+i*4, 355-i*3,
            fill=(*p["accent"], 35+i*8),
            width=2
        )

    draw.ellipse(
        (cx-58, cy-58, cx+58, cy+58),
        fill=(7, 10, 16, 235),
        outline=(*p["accent"], 235),
        width=3
    )
    f = ImageFont.truetype(BOLD, 30)
    label = (labels[0] if labels else "AI").upper()[:14]
    bb = draw.textbbox((0,0), label, font=f)
    draw.text(
        (cx-(bb[2]-bb[0])/2, cy-(bb[3]-bb[1])/2),
        label, font=f, fill=p["text"]
    )

    # One editorial callout, not a cluster.
    if labels:
        bw = min(390, max(230, 22*len(labels[-1])+75))
        bx, by = x+70, y+h-130
        draw_glass_label(draw, (bx, by, bx+bw, by+58), labels[-1], p, True)


def draw_flow(draw, area, p, labels, seed):
    from PIL import ImageFont
    x, y, w, h = area
    rng = random.Random(seed)
    points = []
    for i in range(7):
        px = x + 85 + i*(w-170)/6
        py = y + h*0.52 + math.sin(i*1.25 + seed)*75 + rng.uniform(-24,24)
        points.append((px, py))

    # Smooth-looking segmented flow paths.
    for j in range(4):
        prev = points[0]
        for i in range(1, len(points)):
            px, py = points[i]
            mx = (prev[0]+px)/2
            my = (prev[1]+py)/2 + math.sin(i+j)*18
            draw.line((prev[0],prev[1],mx,my), fill=(*p["accent"],55+j*12), width=2+j%2)
            draw.line((mx,my,px,py), fill=(*p["accent"],80+j*12), width=2)
            prev = (px,py)

    for i, (px, py) in enumerate(points):
        r = 16 if i in (0,6) else 10
        draw.ellipse((px-r,py-r,px+r,py+r), fill=(8,12,18,235), outline=(*p["accent"],220), width=2)
        if i < len(labels):
            bw = min(300, max(190, 18*len(labels[i])+65))
            bx = px-bw/2
            by = py-92 if i%2 == 0 else py+45
            draw_glass_label(draw, (bx,by,bx+bw,by+52), labels[i], p, i==0)


def draw_architecture(draw, area, p, labels, seed):
    from PIL import ImageFont
    x, y, w, h = area
    cx = x+w/2
    layers = [
        (y+h*0.16, w*0.58, labels[0] if labels else "INTERFACE"),
        (y+h*0.38, w*0.72, labels[1] if len(labels)>1 else "ORCHESTRATION"),
        (y+h*0.60, w*0.84, labels[2] if len(labels)>2 else "DATA"),
        (y+h*0.82, w*0.94, labels[3] if len(labels)>3 else "INFRASTRUCTURE"),
    ]
    for i,(yy,ww,label) in enumerate(layers):
        left = cx-ww/2
        right = cx+ww/2
        draw.rounded_rectangle(
            (left,yy,right,yy+78),
            radius=28,
            fill=(10,14,21,155-i*12),
            outline=(*p["accent"],155-i*18),
            width=2
        )
        draw.text(
            (left+30, yy+23),
            label[:30],
            font=ImageFont.truetype(BOLD if i==0 else FONT, 23),
            fill=p["text"]
        )
        if i < len(layers)-1:
            draw.line(
                (cx,yy+78,cx,y+h*([0.38,0.60,0.82][i])),
                fill=(*p["accent"],80),
                width=2
            )


def draw_compare(draw, area, p, labels, seed):
    from PIL import ImageFont
    x, y, w, h = area
    mid = x+w/2
    # Two distinct states, no card grid.
    for side, xx, accent_alpha in [
        ("BEFORE", x+w*0.25, 95),
        ("AFTER", x+w*0.75, 220),
    ]:
        draw.ellipse(
            (xx-105,y+h*0.48-105,xx+105,y+h*0.48+105),
            fill=(8,12,18,220),
            outline=(*p["accent"],accent_alpha),
            width=3
        )
    # Transformation ribbon.
    draw.line(
        (mid-115,y+h*0.48,mid+115,y+h*0.48),
        fill=(*p["accent"],185),
        width=5
    )
    draw.polygon(
        [(mid+115,y+h*0.48),(mid+90,y+h*0.48-15),(mid+90,y+h*0.48+15)],
        fill=(*p["accent"],205)
    )
    if labels:
        draw_glass_label(draw,(x+60,y+40,x+380,y+96),labels[0],p,False)
    if len(labels)>1:
        draw_glass_label(draw,(x+w-380,y+40,x+w-60,y+96),labels[1],p,True)
    for i, lab in enumerate(labels[2:4]):
        bx = x+w*0.34 + i*230
        draw_glass_label(draw,(bx,y+h-95,bx+205,y+h-40),lab,p,False)


def draw_metrics(draw, area, p, labels, seed):
    from PIL import ImageFont
    x, y, w, h = area
    # Minimal editorial chart with no invented numbers.
    left, bottom = x+90, y+h-70
    right, top = x+w-80, y+75
    draw.line((left,top,left,bottom), fill=(*p["muted"],90), width=2)
    draw.line((left,bottom,right,bottom), fill=(*p["muted"],90), width=2)

    pts=[]
    rng=random.Random(seed)
    for i in range(9):
        px=left+(right-left)*i/8
        py=bottom-(bottom-top)*(0.18+0.65*(i/8)**1.15)+rng.uniform(-12,12)
        pts.append((px,py))
    for a,b in zip(pts,pts[1:]):
        draw.line((a[0],a[1],b[0],b[1]),fill=(*p["accent"],205),width=4)
    for i,(px,py) in enumerate(pts):
        r=6 if i not in (4,8) else 9
        draw.ellipse((px-r,py-r,px+r,py+r),fill=(*p["accent"],230))
    if labels:
        draw_glass_label(draw,(x+105,y+80,x+390,y+136),labels[0],p,True)
    if len(labels)>1:
        draw_glass_label(draw,(right-340,top+20,right-55,top+76),labels[1],p,False)


def draw_risk(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    rng=random.Random(seed)
    cx=x+w*0.50
    # Stable left side becomes a branching fracture toward the right.
    start=(x+100,y+h*0.52)
    end=(x+w-100,y+h*0.52)
    draw.line((start[0],start[1],end[0],end[1]),fill=(*p["accent"],110),width=4)
    for i in range(6):
        px=x+w*(0.35+i*0.08)
        py=y+h*0.52+rng.uniform(-25,25)
        draw.line((px,py,px+rng.uniform(55,100),py+rng.uniform(-90,90)),fill=(*p["accent"],100),width=3)
        draw.ellipse((px-7,py-7,px+7,py+7),fill=(*p["accent"],220))
    draw.ellipse((start[0]-30,start[1]-30,start[0]+30,start[1]+30),fill=(8,12,18,235),outline=(*p["accent"],180),width=2)
    draw.ellipse((end[0]-42,end[1]-42,end[0]+42,end[1]+42),fill=(8,12,18,235),outline=(*p["accent"],240),width=3)
    if labels:
        draw_glass_label(draw,(x+45,y+80,x+350,y+136),labels[0],p,False)
    if len(labels)>1:
        draw_glass_label(draw,(x+w-390,y+h-135,x+w-70,y+h-79),labels[1],p,True)


def draw_timeline(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    yline=y+h*0.55
    # Curved-ish timeline using short segments.
    pts=[]
    for i in range(7):
        px=x+100+i*(w-200)/6
        py=yline+math.sin(i*0.9+seed)*65
        pts.append((px,py))
    for a,b in zip(pts,pts[1:]):
        draw.line((a[0],a[1],b[0],b[1]),fill=(*p["accent"],185),width=4)
    for i,(px,py) in enumerate(pts):
        r=13 if i%2 else 17
        draw.ellipse((px-r,py-r,px+r,py+r),fill=(8,12,18,235),outline=(*p["accent"],220),width=2)
        if i<len(labels):
            bw=min(270,max(175,17*len(labels[i])+65))
            by=py-88 if i%2==0 else py+45
            draw_glass_label(draw,(px-bw/2,by,px+bw/2,by+52),labels[i],p,i==0)


def draw_evidence(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    # One source ribbon + supporting evidence markers, avoiding card walls.
    draw.rounded_rectangle(
        (x+90,y+110,x+w-90,y+h-115),
        radius=34,
        fill=(9,13,20,150),
        outline=(*p["accent"],130),
        width=2
    )
    f=ImageFont.truetype(BOLD,31)
    quote=(labels[0] if labels else "SOURCE")[:54]
    draw.text((x+145,y+160), "EVIDENCE",font=f,fill=(*p["accent"],210))
    body=ImageFont.truetype(FONT,27)
    lines=wrap(draw,quote,body,w-320,3)
    yy=y+225
    for line in lines:
        draw.text((x+145,yy),line,font=body,fill=p["text"])
        yy+=38
    for i,lab in enumerate(labels[1:4]):
        bx=x+150+i*390
        draw_glass_label(draw,(bx,y+h-185,bx+330,y+h-130),lab,p,i==0)


def draw_decision(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    cx=x+w*0.48
    root=(x+120,y+h*0.50)
    junction=(cx,y+h*0.50)
    draw.line((root[0],root[1],junction[0],junction[1]),fill=(*p["accent"],200),width=4)
    draw.ellipse((root[0]-22,root[1]-22,root[0]+22,root[1]+22),fill=(8,12,18,235),outline=(*p["accent"],210),width=3)
    for i in range(3):
        yy=y+h*(0.24+i*0.26)
        end=(x+w-120,yy)
        draw.line((junction[0],junction[1],end[0],end[1]),fill=(*p["accent"],100+i*40),width=3)
        draw.ellipse((end[0]-18,end[1]-18,end[0]+18,end[1]+18),fill=(8,12,18,235),outline=(*p["accent"],170+i*25),width=2)
        if i<len(labels):
            bw=min(300,max(190,18*len(labels[i])+65))
            draw_glass_label(draw,(end[0]-bw-25,yy-28,end[0]-25,yy+28),labels[i],p,i==2)


def draw_steps(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    count=min(5,max(3,len(labels)))
    x0=x+170
    for i in range(count):
        yy=y+80+i*(h-160)/max(count-1,1)
        draw.ellipse((x0-18,yy-18,x0+18,yy+18),fill=(8,12,18,235),outline=(*p["accent"],210),width=3)
        if i<count-1:
            next_y=y+80+(i+1)*(h-160)/max(count-1,1)
            draw.line((x0,next_y-18,x0,yy+18),fill=(*p["accent"],110),width=3)
        if i<len(labels):
            draw_glass_label(draw,(x0+55,yy-28,x0+55+min(520,max(260,20*len(labels[i])+80)),yy+28),labels[i],p,i==0)


def draw_quote(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    f=ImageFont.truetype(BOLD,48)
    quote=(labels[0] if labels else "THE KEY INSIGHT")
    lines=wrap(draw,quote,f,w-300,3)
    yy=y+120
    draw.text((x+115,y+75),"“",font=ImageFont.truetype(BOLD,90),fill=(*p["accent"],210))
    for line in lines:
        draw.text((x+175,yy),line,font=f,fill=p["text"])
        yy+=62
    draw.line((x+175,yy+20,x+w-190,yy+20),fill=(*p["accent"],130),width=2)
    if len(labels)>1:
        draw.text((x+175,yy+45),labels[1][:48],font=ImageFont.truetype(FONT,24),fill=(*p["muted"],190))


def draw_matrix(draw, area, p, labels, seed):
    from PIL import ImageFont
    x,y,w,h=area
    cx=x+w*0.5
    cy=y+h*0.5
    size=min(w*0.55,h*0.68)
    left=cx-size/2
    top=cy-size/2
    draw.rounded_rectangle((left,top,left+size,top+size),radius=30,fill=(9,13,20,135),outline=(*p["accent"],120),width=2)
    draw.line((cx,top+25,cx,top+size-25),fill=(*p["accent"],85),width=2)
    draw.line((left+25,cy,left+size-25,cy),fill=(*p["accent"],85),width=2)
    positions=[
        (left+size*0.16,top+size*0.16),
        (left+size*0.55,top+size*0.16),
        (left+size*0.16,top+size*0.60),
        (left+size*0.55,top+size*0.60),
    ]
    for i,(px,py) in enumerate(positions):
        lab=labels[i] if i<len(labels) else f"OPTION {i+1}"
        draw.text((px,py),lab[:22],font=ImageFont.truetype(BOLD if i==0 else FONT,21),fill=p["text"] if i==0 else (*p["muted"],200))


def draw_visual_v19(draw, kind, area, p, scene=None, seed=1):
    from PIL import ImageFont
    """
    V19 visual grammar router.

    Each scene gets a deliberately different visual language instead of
    reusing the same central-circle/network composition.
    """
    scene = scene or {}
    labels = visual_keywords(scene, 5)

    # Guarantee meaningful labels for the specialized grammars.
    if len(labels) < 3:
        labels = (labels + ["MECHANISM", "IMPLICATION", "OUTCOME"])[:5]

    dispatch = {
        "journey": draw_hero,
        "flow": draw_flow,
        "architecture": draw_architecture,
        "compare": draw_compare,
        "metrics": draw_metrics,
        "risk": draw_risk,
        "timeline": draw_timeline,
        "evidence": draw_evidence,
        "decision": draw_decision,
        "steps": draw_steps,
        "quote": draw_quote,
        "matrix": draw_matrix,
    }

    fn = dispatch.get(kind, draw_hero)
    fn(draw, area, p, labels, seed)


def draw_visual(draw, kind, area, p, scene=None, seed=1):
    # V19: deliberately varied visual grammar per scene.
    draw_visual_v19(draw, kind, area, p, scene, seed)

def make_card(scene, index, title, p, path, visual_path=None):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    W, H = 1920, 1080
    img = Image.new("RGBA", (W, H), (*p["bg"], 255))
    draw = ImageDraw.Draw(img, "RGBA")

    # Atmospheric vignette / grain — intentionally subtle.
    rng = random.Random(4000 + index)
    for _ in range(420):
        px = rng.randrange(W)
        py = rng.randrange(H)
        a = rng.randrange(4, 16)
        draw.point((px, py), fill=(*p["accent"], a))

    # Soft horizon glow gives the frame depth without a visible card.
    for r in range(520, 80, -30):
        alpha = max(2, int(22 * (520-r) / 440))
        draw.ellipse(
            (W*0.5-r, H*0.48-r, W*0.5+r, H*0.48+r),
            outline=(*p["accent"], alpha),
            width=3
        )

    # Editorial header: small, quiet, premium.
    top = ImageFont.truetype(BOLD, 24)
    scene_f = ImageFont.truetype(FONT, 20)
    draw.text((78, 62), "uncommonAI", font=top, fill=(*p["text"], 215))
    draw.text(
        (W-220, 64),
        f"{index:02d} / 08",
        font=scene_f,
        fill=(*p["accent"], 180),
    )

    # Kinetic-style title: compact and left aligned rather than a centered card.
    title_f = font_fit(draw, title, BOLD, 54, 36, 900)
    title_lines = wrap(draw, title, title_f, 900, 2)
    yy = 108
    for line in title_lines:
        draw.text((82, yy), line, font=title_f, fill=(*p["text"], 242))
        bb = draw.textbbox((0, 0), line, font=title_f)
        yy += bb[3]-bb[1] + 6

    # Thin accent trace instead of the old progress bar.
    draw.line(
        (82, yy+12, min(820, 82+len(title)*15), yy+12),
        fill=(*p["accent"], 200),
        width=3
    )

    # Visual field is intentionally borderless.
    if visual_path:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer, "RGBA")
        kind = scene.get("_renderer_visual_kind") or visual_kind(scene, index)
        draw_visual(
            ld,
            kind,
            (95, 275, W-190, 575),
            p,
            scene,
            seed=7000 + index * 31,
        )
        layer.save(visual_path)

    # Keep the lower region deliberately quiet for subtitles.
    draw.line(
        (82, 900, W-82, 900),
        fill=(*p["accent"], 55),
        width=1,
    )
    foot = ImageFont.truetype(FONT, 18)
    draw.text(
        (82, 925),
        "AI-assisted research  ·  original commentary",
        font=foot,
        fill=(*p["muted"], 145),
    )

    img.convert("RGB").save(path, quality=95)



def generate_voice(text, output_path):
    """
    Generate narration using the selected voice backend.

    VOICE_PROVIDER:
      auto        -> ElevenLabs when credentials are present, otherwise Edge TTS
      elevenlabs  -> require ElevenLabs credentials
      edge        -> always use Edge TTS

    This keeps the renderer backward-compatible while allowing a personal
    ElevenLabs voice clone to be introduced without changing the renderer.
    """
    output_path = Path(output_path)

    use_eleven = (
        VOICE_PROVIDER == "elevenlabs"
        or (
            VOICE_PROVIDER == "auto"
            and ELEVENLABS_API_KEY
            and ELEVENLABS_VOICE_ID
        )
    )

    if use_eleven:
        if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
            raise SystemExit(
                "VOICE_PROVIDER=elevenlabs requires "
                "ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID."
            )

        url = (
            "https://api.elevenlabs.io/v1/text-to-speech/"
            f"{ELEVENLABS_VOICE_ID}"
        )

        payload = {
            "text": safe_text(text),
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": 0.48,
                "similarity_boost": 0.82,
                "style": 0.18,
                "use_speaker_boost": True,
            },
        }

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                output_path.write_bytes(response.read())
            print(f"TTS: ElevenLabs voice clone -> {output_path}")
            return
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if VOICE_PROVIDER == "elevenlabs":
                print("ELEVENLABS API ERROR:")
                print(body[:4000])
                raise SystemExit(
                    f"ElevenLabs narration failed with HTTP {exc.code}."
                )
            print(
                f"ElevenLabs unavailable (HTTP {exc.code}); "
                "falling back to Edge TTS."
            )
        except Exception as exc:
            if VOICE_PROVIDER == "elevenlabs":
                raise SystemExit(
                    f"ElevenLabs narration failed: {exc}"
                )
            print(
                f"ElevenLabs unavailable ({exc}); "
                "falling back to Edge TTS."
            )

    run([
        "edge-tts",
        "--voice",
        EDGE_VOICE,
        "--text",
        safe_text(text),
        "--write-media",
        str(output_path),
    ])
    print(f"TTS: Edge TTS ({EDGE_VOICE}) -> {output_path}")



def cache_key(*parts):
    h = hashlib.sha256()
    for part in parts:
        if isinstance(part, bytes):
            data = part
        else:
            data = str(part).encode("utf-8")
        h.update(data)
        h.update(b"\0")
    return h.hexdigest()[:20]


def cache_valid(path, key):
    if not RENDER_CACHE or not path.exists() or path.stat().st_size == 0:
        return False
    marker = path.with_suffix(path.suffix + ".cache")
    try:
        return marker.read_text(encoding="utf-8").strip() == key
    except Exception:
        return False


def write_cache_marker(path, key):
    path.with_suffix(path.suffix + ".cache").write_text(key, encoding="utf-8")


def render_scene(index, scene, title, p):
    audio=VIDEO_DIR/f"scene_{index:02d}.mp3"
    image=VIDEO_DIR/f"scene_{index:02d}.png"
    visual_layer=VIDEO_DIR/f"scene_{index:02d}_visual.png"
    ass=VIDEO_DIR/f"scene_{index:02d}.ass"
    out=VIDEO_DIR/f"segment_{index:02d}.mp4"

    narration=safe_text(scene.get("narration"))
    if not narration:
        raise SystemExit(f"Scene {index} has no narration.")
    scene_title=safe_text(
        scene.get("title")
        or scene.get("heading")
        or scene.get("key_phrase")
        or f"Scene {index}"
    )

    # Cache keys prevent expensive Edge TTS and PIL regeneration on reruns.
    voice_key = cache_key(
        RENDER_VERSION, "voice", VOICE_PROVIDER, EDGE_VOICE,
        ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL, narration
    )
    visual_key = cache_key(
        RENDER_VERSION, "visual", index, scene_title,
        json.dumps(scene, sort_keys=True, ensure_ascii=False),
        json.dumps(p, sort_keys=True),
    )
    duration_key = None

    if not cache_valid(audio, voice_key):
        generate_voice(narration, audio)
        write_cache_marker(audio, voice_key)
    else:
        print(f"CACHE: narration scene {index} -> {audio}")

    duration=audio_duration(audio)
    duration_key = cache_key(RENDER_VERSION, "ass", narration, round(duration, 3))

    if not cache_valid(image, visual_key):
        make_card(scene,index,scene_title,p,image,visual_layer)
        write_cache_marker(image, visual_key)
        write_cache_marker(visual_layer, visual_key)
    else:
        print(f"CACHE: visuals scene {index}")

    if not cache_valid(ass, duration_key):
        make_ass(narration,duration,ass)
        write_cache_marker(ass, duration_key)
    else:
        print(f"CACHE: subtitles scene {index}")

    ass_path=str(ass).replace("\\","/").replace(":","\\:").replace("'","\\'")

    # V20 performance optimization:
    # - 24 fps is cinematic and cuts ~20% of encoded frames vs 30 fps.
    # - No zoompan: it was one of the most expensive filters in V19.
    # - Cheap crop-based micro-drift preserves motion without frame synthesis.
    # - superfast x264 keeps GitHub Actions runtime reasonable.
    # - subtitles remain burned in, so no change to the output design.
    vf = (
        f"[0:v]"
        f"scale=1960:1102:flags=fast_bilinear,"
        f"crop=1920:1080:"
        f"x='20+8*sin(t/9)':"
        f"y='11+5*cos(t/11)',"
        f"fps={VIDEO_FPS}[base];"
        f"[2:v]format=rgba,"
        f"scale=1960:1102:flags=fast_bilinear,"
        f"crop=1920:1080:"
        f"x='20+10*sin(t/10)':"
        f"y='11+6*cos(t/12)',"
        f"fps={VIDEO_FPS},"
        f"fade=t=in:st=0:d=0.5:alpha=1[vl];"
        f"[base][vl]"
        f"overlay=x='2*sin(t/8)':y='2*cos(t/9)':shortest=1,"
        f"drawbox=x='82':y='250':w='1756':h='2':"
        f"color=white@0.12:t=fill,"
        f"subtitles='{ass_path}'[vout]"
    )

    segment_key = cache_key(
        RENDER_VERSION, "segment", index, narration, scene_title,
        visual_key, duration, VIDEO_FPS, VIDEO_PRESET, VIDEO_CRF
    )
    if cache_valid(out, segment_key):
        print(f"CACHE: encoded segment {index} -> {out}")
    else:
        run([
            "ffmpeg","-y",
            "-loop","1","-framerate",str(VIDEO_FPS),"-i",str(image),
            "-i",str(audio),
            "-loop","1","-framerate",str(VIDEO_FPS),"-i",str(visual_layer),
            "-filter_complex",vf,
            "-map","[vout]","-map","1:a",
            "-c:v","libx264",
            "-preset",VIDEO_PRESET,
            "-crf",VIDEO_CRF,
            "-tune","stillimage",
            "-pix_fmt","yuv420p",
            "-r",str(VIDEO_FPS),
            "-c:a","aac","-b:a","160k",
            "-shortest","-t",str(duration),
            "-movflags","+faststart",
            str(out)
        ])
        if out.exists() and out.stat().st_size > 0:
            write_cache_marker(out, segment_key)

    if not out.exists() or out.stat().st_size==0:
        raise SystemExit(f"Scene {index} was not created correctly.")
    return out



def main():
    if not PACKAGE_FILE.exists(): raise SystemExit(f"Missing {PACKAGE_FILE}")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} is not installed.")

    # Edge TTS remains available as the safe fallback in auto mode.
    use_eleven_only = VOICE_PROVIDER == "elevenlabs"
    if not use_eleven_only and not shutil.which("edge-tts"):
        if not (ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID):
            raise SystemExit(
                "Neither Edge TTS nor a configured ElevenLabs voice is available."
            )
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
    print(f"V20 FAST PREMIUM VIDEO CREATED: {OUTPUT} | {OUTPUT.stat().st_size} bytes")

if __name__ == "__main__":
    main()
