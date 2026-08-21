#!/usr/bin/env python3
import json
import math
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
    {"accent": (64, 224, 255), "accent2": (160, 245, 255), "bg": (7, 10, 16), "panel": (18, 23, 31), "text": (244, 248, 252), "muted": (143, 154, 169)},
    {"accent": (255, 70, 196), "accent2": (255, 165, 230), "bg": (9, 7, 14), "panel": (20, 18, 28), "text": (248, 245, 251), "muted": (151, 143, 164)},
    {"accent": (177, 108, 255), "accent2": (220, 181, 255), "bg": (10, 7, 16), "panel": (21, 18, 30), "text": (247, 245, 251), "muted": (151, 143, 165)},
    {"accent": (255, 184, 72), "accent2": (255, 220, 145), "bg": (13, 10, 7), "panel": (24, 21, 16), "text": (249, 247, 242), "muted": (160, 151, 133)},
    {"accent": (80, 238, 168), "accent2": (166, 250, 210), "bg": (7, 12, 10), "panel": (17, 25, 22), "text": (244, 249, 246), "muted": (142, 161, 153)},
    {"accent": (91, 139, 255), "accent2": (171, 197, 255), "bg": (7, 9, 15), "panel": (17, 21, 31), "text": (244, 247, 252), "muted": (143, 152, 170)},
    {"accent": (255, 101, 101), "accent2": (255, 174, 174), "bg": (13, 8, 9), "panel": (25, 17, 18), "text": (250, 245, 245), "muted": (164, 145, 147)},
    {"accent": (204, 255, 72), "accent2": (226, 255, 154), "bg": (9, 12, 6), "panel": (20, 25, 14), "text": (246, 249, 240), "muted": (153, 164, 134)},
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



def _accent_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _mix(a, b, t):
    return tuple(int(a[i] * (1-t) + b[i] * t) for i in range(3))


def _organic_points(x, y, w, h, count, seed):
    """
    Organic, content-aware anchors. They are deterministic per scene so
    reruns remain stable, but are deliberately irregular rather than grid-snapped.
    """
    rng = random.Random(seed)
    cx, cy = x + w * 0.52, y + h * 0.50
    rx, ry = w * 0.31, h * 0.29
    pts = []
    for i in range(count):
        angle = (i / max(count, 1)) * math.tau + rng.uniform(-0.38, 0.38)
        radius = rng.uniform(0.72, 1.05)
        px = cx + math.cos(angle) * rx * radius
        py = cy + math.sin(angle) * ry * radius
        pts.append((int(px), int(py)))
    return pts


def _rounded_glass(draw, box, fill, outline, radius=22, width=2):
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )


def _draw_glow_line(layer, points, color, width=5, glow=18):
    from PIL import Image, ImageDraw, ImageFilter
    glow_layer = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    gd.line(points, fill=(*color, 75), width=glow, joint="curve")
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(glow / 2))
    layer.alpha_composite(glow_layer)
    ImageDraw.Draw(layer).line(points, fill=(*color, 210), width=width, joint="curve")


def _draw_background_atmosphere(layer, area, p, seed):
    from PIL import Image, ImageDraw, ImageFilter
    rng = random.Random(seed)
    x, y, w, h = area

    # Soft architectural particles live behind the focal composition.
    bg = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    for _ in range(24):
        px = rng.randint(x, x + w)
        py = rng.randint(y, y + h)
        r = rng.choice([2, 3, 4, 6])
        bd.ellipse((px-r, py-r, px+r, py+r), fill=(*p["accent"], rng.randint(20, 65)))

    # Faint grid arcs: atmospheric, not a hard UI grid.
    for radius in (180, 320, 480):
        bd.arc(
            (x+w/2-radius, y+h/2-radius, x+w/2+radius, y+h/2+radius),
            rng.randint(0, 60),
            rng.randint(190, 320),
            fill=(*p["accent2"], 24),
            width=2,
        )

    bg = bg.filter(ImageFilter.GaussianBlur(3.5))
    layer.alpha_composite(bg)


def _draw_callout(layer, center, label, p, seed, scale=1.0, active=True):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    cx, cy = center
    label = safe_text(label)[:34]
    if not label:
        return

    # Adaptive width prevents hard-coded boxes from dominating short labels.
    font = ImageFont.truetype(BOLD, max(22, int(26 * scale)))
    tmp = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    bb = td.textbbox((0, 0), label.upper(), font=font)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    bw = min(max(tw + 62, 190), 430)
    bh = max(78, th + 42)

    box = (int(cx-bw/2), int(cy-bh/2), int(cx+bw/2), int(cy+bh/2))

    # Shadow/depth layer.
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        (box[0]+8, box[1]+12, box[2]+8, box[3]+12),
        radius=20,
        fill=(0, 0, 0, 120),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(11))
    layer.alpha_composite(shadow)

    # Frosted glass panel.
    panel = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    fill = (18, 21, 29, 178)
    outline = (*p["accent"], 205 if active else 105)
    pd.rounded_rectangle(box, radius=20, fill=fill, outline=outline, width=2)

    # Tiny status indicator, deliberately subtle.
    dot_r = 5
    pd.ellipse(
        (box[0]+18, box[1]+18, box[0]+18+dot_r*2, box[1]+18+dot_r*2),
        fill=(*p["accent"], 235 if active else 90),
    )
    pd.text(
        (box[0]+34, box[1]+12),
        "LIVE",
        font=ImageFont.truetype(FONT, 14),
        fill=(*p["muted"], 180),
    )

    # Tracking is simulated with small character spacing on the label.
    text = label.upper()
    spacing = 0.8
    tx = box[0] + (bw-tw)/2
    ty = box[1] + (bh-th)/2 + 8
    pd.text((tx, ty), text, font=font, fill=(*p["text"], 245))

    layer.alpha_composite(panel)


def draw_visual(layer, kind, area, p, scene=None, seed=0):
    """
    Premium documentary visual system.

    Design language:
      - monochrome atmospheric base
      - one neon accent
      - organic anchors instead of card grids
      - blurred depth layer behind crisp foreground labels
      - one active path that explains the relationship
      - frosted-glass callouts rather than presentation-card boxes
    """
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    scene = scene or {}
    x, y, w, h = area
    labels = visual_keywords(scene, 4)
    labels = [safe_text(v) for v in labels if safe_text(v)]

    # If explicit labels exist, prefer them over renderer filler.
    if not labels:
        labels = ["KEY IDEA", "MECHANISM", "IMPLICATION"]

    _draw_background_atmosphere(layer, area, p, seed)

    # Dark focal vignette gives physical depth.
    vignette = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    vd = ImageDraw.Draw(vignette)
    for r, a in ((520, 8), (420, 12), (320, 18)):
        vd.ellipse(
            (x+w/2-r, y+h/2-r, x+w/2+r, y+h/2+r),
            fill=(0, 0, 0, a),
        )
    vignette = vignette.filter(ImageFilter.GaussianBlur(30))
    layer.alpha_composite(vignette)

    count = min(max(len(labels), 3), 4)
    pts = _organic_points(x, y, w, h, count, seed + 97)

    # Conceptual path changes by visual type, but never becomes a rigid grid.
    if kind in ("flow", "timeline", "journey", "steps"):
        ordered = pts
    elif kind == "compare":
        ordered = [
            (x+w*0.29, y+h*0.47),
            (x+w*0.71, y+h*0.53),
        ]
        while len(ordered) < count:
            ordered.append(pts[len(ordered) % len(pts)])
    elif kind == "risk":
        ordered = [
            (x+w*0.50, y+h*0.38),
            (x+w*0.34, y+h*0.68),
            (x+w*0.68, y+h*0.66),
        ][:count]
    elif kind in ("architecture", "matrix"):
        ordered = pts
    else:
        ordered = pts

    # Background nodes: lower contrast, blurred, creating depth.
    depth = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    dd = ImageDraw.Draw(depth)
    rng = random.Random(seed + 211)
    for _ in range(12):
        px = rng.randint(x+40, x+w-40)
        py = rng.randint(y+35, y+h-35)
        rr = rng.randint(5, 13)
        dd.ellipse((px-rr, py-rr, px+rr, py+rr), fill=(*p["accent"], rng.randint(18, 45)))
    depth = depth.filter(ImageFilter.GaussianBlur(7))
    layer.alpha_composite(depth)

    # One luminous route connects the concepts.
    if len(ordered) >= 2:
        path = []
        for i, pt in enumerate(ordered):
            if i == 0:
                path.append(pt)
                continue
            px, py = ordered[i-1]
            qx, qy = pt
            # Smooth cubic-ish interpolation represented by multiple points.
            for t in [0.18, 0.36, 0.54, 0.72, 0.88, 1.0]:
                ease = t*t*(3-2*t)
                bend = math.sin(t*math.pi) * (22 if i % 2 else -18)
                path.append((
                    px + (qx-px)*ease,
                    py + (qy-py)*ease + bend,
                ))
        _draw_glow_line(layer, path, p["accent"], width=4, glow=18)

    # Active point: the conceptual "now".
    active_idx = min(len(ordered)-1, max(0, seed % len(ordered)))
    ax, ay = ordered[active_idx]
    halo = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    for rr, alpha in ((48, 18), (30, 30), (16, 65)):
        hd.ellipse((ax-rr, ay-rr, ax+rr, ay+rr), fill=(*p["accent"], alpha))
    halo = halo.filter(ImageFilter.GaussianBlur(9))
    layer.alpha_composite(halo)
    ImageDraw.Draw(layer).ellipse(
        (ax-7, ay-7, ax+7, ay+7),
        fill=(*p["accent"], 250),
    )

    # Labels float around the path; no rigid equal-width cards.
    for i, label in enumerate(labels[:count]):
        px, py = ordered[i]
        # Slight vertical breathing offset gives asymmetry.
        py += int(math.sin((seed+i)*0.9) * 10)
        _draw_callout(
            layer,
            (px, py),
            label,
            p,
            seed+i,
            scale=1.0 if i == active_idx else 0.94,
            active=(i == active_idx),
        )

    # Minimal scene-type micro label.
    micro = {
        "flow": "SEQUENCE",
        "compare": "CONTRAST",
        "architecture": "SYSTEM MAP",
        "risk": "FAILURE PATH",
        "timeline": "EVOLUTION",
        "journey": "TRAJECTORY",
        "evidence": "EVIDENCE",
        "decision": "DECISION",
        "steps": "MECHANISM",
        "quote": "SIGNAL",
        "metrics": "SIGNAL",
        "matrix": "TRADE-OFF",
    }.get(kind, "SIGNAL")

    mf = ImageFont.truetype(FONT, 16)
    ImageDraw.Draw(layer).text(
        (x+10, y+h-24),
        micro,
        font=mf,
        fill=(*p["muted"], 145),
    )



def make_card(scene, index, title, p, path, visual_path=None):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), p["bg"])
    draw = ImageDraw.Draw(img)

    # Premium cinematic frame: almost no hard UI chrome.
    draw.rectangle((0, 0, W, H), fill=p["bg"])
    draw.rounded_rectangle(
        (48, 48, W-48, H-48),
        radius=34,
        fill=p["bg"],
        outline=(*p["accent"], 90),
        width=2,
    )

    top = ImageFont.truetype(BOLD, 24)
    meta = ImageFont.truetype(FONT, 19)
    draw.text((88, 78), "uncommonAI", font=top, fill=p["text"])
    draw.text((W-260, 82), f"{index:02d} / 08", font=meta, fill=p["muted"])

    # Fine progress line, intentionally understated.
    draw.rounded_rectangle((88, 118, W-88, 121), radius=2, fill=p["panel"])
    draw.rounded_rectangle(
        (88, 118, 88 + int((W-176) * min(index/8, 1.0)), 121),
        radius=2,
        fill=p["accent"],
    )

    # Title is editorial context, not the hero object.
    title_f = font_fit(draw, title, BOLD, 54, 36, 1420)
    title_lines = wrap(draw, title, title_f, 1420, 2)
    yy = 153
    for line in title_lines:
        bb = draw.textbbox((0, 0), line, font=title_f)
        draw.text(
            ((W-(bb[2]-bb[0]))/2, yy),
            line,
            font=title_f,
            fill=p["text"],
        )
        yy += bb[3]-bb[1]+6

    # Large atmospheric stage. Keep lower region clean for subtitles.
    stage = (95, 325, W-190, 545)
    stage_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sl = ImageDraw.Draw(stage_layer)

    # Frosted stage boundary, not a rigid panel.
    sl.rounded_rectangle(
        (stage[0], stage[1], stage[0]+stage[2], stage[1]+stage[3]),
        radius=32,
        fill=(*p["panel"], 110),
        outline=(*p["accent"], 80),
        width=1,
    )

    kind = scene.get("_renderer_visual_kind") or visual_kind(scene, index)
    draw_visual(
        stage_layer,
        kind,
        (stage[0]+34, stage[1]+28, stage[2]-68, stage[3]-56),
        p,
        scene,
        seed=index*101,
    )

    # Soft mask at stage edges so the visual fades naturally into the void.
    stage_layer.save(visual_path)

    # Main card intentionally contains no duplicated diagram; the visual
    # layer is composited independently and animated in render_scene.
    draw.line((95, 895, W-95, 895), fill=(*p["accent"], 70), width=1)

    foot = ImageFont.truetype(FONT, 18)
    draw.text(
        (95, 918),
        "AI-assisted research  •  original analysis",
        font=foot,
        fill=p["muted"],
    )

    img.save(path, quality=95)


def render_scene(index, scene, title, p):
    audio = VIDEO_DIR / f"scene_{index:02d}.mp3"
    image = VIDEO_DIR / f"scene_{index:02d}.png"
    visual_layer = VIDEO_DIR / f"scene_{index:02d}_visual.png"
    ass = VIDEO_DIR / f"scene_{index:02d}.ass"
    out = VIDEO_DIR / f"segment_{index:02d}.mp4"

    narration = safe_text(scene.get("narration"))
    if not narration:
        raise SystemExit(f"Scene {index} has no narration.")

    scene_title = safe_text(
        scene.get("title")
        or scene.get("heading")
        or scene.get("key_phrase")
        or f"Scene {index}"
    )

    run([
        "edge-tts",
        "--voice", VOICE,
        "--text", narration,
        "--write-media", str(audio),
    ])

    duration = audio_duration(audio)
    make_card(scene, index, scene_title, p, image, visual_layer)
    make_ass(narration, duration, ass)

    ass_path = str(ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    # Two independent looping inputs:
    #   0 = cinematic background card
    #   1 = narration
    #   2 = transparent visual layer
    #
    # The visual gets:
    #   - gentle scale-in
    #   - upward drift
    #   - fade-in
    #   - no bouncy easing
    #
    # The card gets an almost imperceptible camera drift.
    vf = (
        "[0:v]"
        "scale=1970:1108,"
        "zoompan="
        "z='1.0+0.010*min(on/(30*4.0),1)':"
        "x='iw/2-(iw/zoom/2)+3*sin(on/85)':"
        "y='ih/2-(ih/zoom/2)+2*cos(on/97)':"
        "d=1:s=1920x1080:fps=30"
        "[base];"

        "[2:v]"
        "format=rgba,"
        "scale=1970:1108,"
        "zoompan="
        "z='0.965+0.035*min(on/(30*0.85),1)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)+10*(1-min(on/(30*0.85),1))':"
        "d=1:s=1970x1108:fps=30,"
        "fade=t=in:st=0:d=0.65:alpha=1"
        "[visual];"

        "[base][visual]"
        "overlay=x=0:y=0:format=auto"
        "[comp];"

        # A thin accent sweep assembles at the top of the visual stage.
        "[comp]"
        "drawbox="
        "x='96+min(t/0.9,1)*(iw-192)':"
        "y=315:w=170:h=2:"
        "color=white@0.42:t=fill,"
        "fade=t=in:st=0:d=0.35,"
        f"subtitles='{ass_path}'"
        "[vout]"
    )

    run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image),
        "-i", str(audio),
        "-loop", "1", "-i", str(visual_layer),
        "-filter_complex", vf,
        "-map", "[vout]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-t", str(duration),
        "-movflags", "+faststart",
        str(out),
    ])

    if not out.exists() or out.stat().st_size == 0:
        raise SystemExit(f"Scene {index} was not created correctly.")

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
    print(f"V14 VIDEO CREATED: {OUTPUT} | {OUTPUT.stat().st_size} bytes")

if __name__ == "__main__":
    main()
