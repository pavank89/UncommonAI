#!/usr/bin/env python3
import json
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


def draw_visual(draw, kind, area, p, scene=None, seed=1):
    """
    Premium documentary visual language.

    Design rules:
      - no rigid multi-card grids
      - one dominant accent on a dark atmospheric field
      - organic network geometry
      - frosted-glass callouts
      - layered depth and restrained typography
      - visual_prompt/labels drive the content
    """
    from PIL import ImageFont, ImageFilter, Image
    import math

    x, y, w, h = area
    scene = scene or {}
    labels = visual_keywords(scene, 5)
    title_font = ImageFont.truetype(BOLD, 28)
    label_font = ImageFont.truetype(BOLD, 22)
    body_font = ImageFont.truetype(FONT, 19)

    # Atmospheric background texture.
    rng = random.Random(seed)
    for _ in range(90):
        px = rng.uniform(x, x+w)
        py = rng.uniform(y, y+h)
        r = rng.choice([1, 1, 2, 3])
        draw.ellipse(
            (px-r, py-r, px+r, py+r),
            fill=(*p["accent"], rng.randint(8, 24))
        )

    # Large soft focus node behind the primary subject.
    cx, cy = x + w*0.52, y + h*0.49
    draw_glow(draw, (cx, cy), min(w, h)*0.26, p["accent"], layers=8)

    # Organic network is the common visual grammar across all scene types.
    nodes = draw_neural_network(
        draw,
        (x+80, y+40, w-160, h-80),
        p,
        seed=seed * 97 + len(kind),
        density=26 if kind in {"architecture", "flow", "metrics"} else 20,
    )

    # Central hero object: luminous "AI execution core".
    core_r = 86 if kind not in {"risk", "quote"} else 70
    for rr in range(core_r+36, core_r, -8):
        alpha = int(12 + 38 * (core_r+36-rr) / 36)
        draw.ellipse(
            (cx-rr, cy-rr, cx+rr, cy+rr),
            outline=(*p["accent"], alpha),
            width=2
        )
    draw.ellipse(
        (cx-core_r, cy-core_r, cx+core_r, cy+core_r),
        fill=(9, 12, 18, 220),
        outline=(*p["accent"], 230),
        width=3
    )

    # Active pulse ring and directional execution trace.
    phase = (seed % 7) * 0.22
    for i in range(3):
        rr = core_r + 20 + i*18
        draw.arc(
            (cx-rr, cy-rr, cx+rr, cy+rr),
            start=int(25 + phase*90 + i*65),
            end=int(105 + phase*90 + i*65),
            fill=(*p["accent"], 165-i*25),
            width=4 if i == 0 else 2,
        )

    core_text = {
        "flow": "EXECUTE",
        "architecture": "SYSTEM",
        "metrics": "SIGNAL",
        "risk": "RISK",
        "compare": "SHIFT",
        "timeline": "EVOLVE",
        "evidence": "EVIDENCE",
        "decision": "DECIDE",
        "journey": "ADAPT",
        "steps": "PROCESS",
        "quote": "INSIGHT",
        "matrix": "TRADE-OFF",
    }.get(kind, "AI")
    bb = draw.textbbox((0,0), core_text, font=title_font)
    draw.text(
        (cx-(bb[2]-bb[0])/2, cy-(bb[3]-bb[1])/2),
        core_text,
        font=title_font,
        fill=p["text"]
    )

    # Place callouts organically around the core, with deterministic jitter.
    base_positions = [
        (0.08, 0.12), (0.69, 0.10), (0.03, 0.68),
        (0.70, 0.69), (0.38, 0.02)
    ]
    for i, label in enumerate(labels[:5]):
        bx = x + w*base_positions[i][0] + rng.uniform(-22, 22)
        by = y + h*base_positions[i][1] + rng.uniform(-12, 16)
        bw = min(360, max(210, 22*len(label)+75))
        bh = 58
        # Keep callouts inside the visual safe area.
        bx = max(x+12, min(x+w-bw-12, bx))
        by = max(y+12, min(y+h-bh-12, by))
        draw_glass_label(
            draw,
            (bx, by, bx+bw, by+bh),
            label,
            p,
            emphasis=(i == 0),
        )
        # Fine connector line, deliberately not snapped to a grid.
        tx = bx+bw/2
        ty = by+bh/2
        dx, dy = cx-tx, cy-ty
        length = max(math.hypot(dx, dy), 1)
        sx = tx + dx/length*30
        sy = ty + dy/length*30
        ex = cx - dx/length*core_r
        ey = cy - dy/length*core_r
        draw.line(
            (sx, sy, ex, ey),
            fill=(*p["accent"], 70 if i else 115),
            width=2
        )

    # Minimal live-status line; no invented quantitative values.
    status = {
        "flow": "EXECUTION PATH ACTIVE",
        "architecture": "DEPENDENCY GRAPH ACTIVE",
        "metrics": "SIGNAL MONITORING",
        "risk": "FAILURE SURFACE",
        "compare": "CONTRASTING STATES",
        "timeline": "SEQUENCE IN MOTION",
        "evidence": "SOURCE-BASED CLAIM",
        "decision": "CONTEXTUAL DECISION",
        "journey": "ADAPTIVE SYSTEM",
        "steps": "PROCESS STATE",
        "quote": "ORIGINAL COMMENTARY",
        "matrix": "TRADE-OFF SPACE",
    }.get(kind, "AI SYSTEM ACTIVE")
    draw.text(
        (x+18, y+h-28),
        "●  " + status,
        font=body_font,
        fill=(*p["accent"], 190)
    )



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


def render_scene(index, scene, title, p):
    audio=VIDEO_DIR/f"scene_{index:02d}.mp3"
    image=VIDEO_DIR/f"scene_{index:02d}.png"
    visual_layer=VIDEO_DIR/f"scene_{index:02d}_visual.png"
    ass=VIDEO_DIR/f"scene_{index:02d}.ass"
    out=VIDEO_DIR/f"segment_{index:02d}.mp4"
    narration=safe_text(scene.get("narration"))
    if not narration: raise SystemExit(f"Scene {index} has no narration.")
    scene_title=safe_text(scene.get("title") or scene.get("heading") or scene.get("key_phrase") or f"Scene {index}")
    generate_voice(narration, audio)
    duration=audio_duration(audio)
    make_card(scene,index,scene_title,p,image,visual_layer)
    make_ass(narration,duration,ass)
    ass_path=str(ass).replace("\\","/").replace(":","\\:").replace("'","\\'")
    # Premium motion system:
    # - slow exponential camera drift
    # - subtle breathing scale
    # - visual layer floats independently
    # - no hard slide-in / grid snapping
    base = (
        "scale=1970:1108,"
        "zoompan=z='1.0+0.012*(1-exp(-on/55))':"
        "x='iw/2-(iw/zoom/2)+10*sin(on/95)':"
        "y='ih/2-(ih/zoom/2)+7*cos(on/117)':"
        "d=1:s=1920x1080:fps=30"
        "[base]"
    )
    vf = (
        f"[0:v]{base};"
        "[2:v]format=rgba,setpts=PTS-STARTPTS,"
        "scale=1970:1108,"
        "zoompan=z='1.0+0.022*(1-exp(-on/28))':"
        "x='iw/2-(iw/zoom/2)+5*sin(on/71)':"
        "y='ih/2-(ih/zoom/2)+4*cos(on/83)':"
        "d=1:s=1970x1108:fps=30,"
        "fade=t=in:st=0:d=0.75:alpha=1[vl];"
        "[base][vl]"
        "overlay=x='2*sin(t/8)':"
        "y='2*cos(t/9)':"
        "format=auto[composite];"
        "[composite]"
        "drawbox="
        "x='82':y='250':w='1756':h='2':"
        "color=white@0.12:t=fill,"
        "fade=t=in:st=0:d=0.35,"
        f"subtitles='{ass_path}'[vout]"
    )
    run([
        "ffmpeg","-y",
        "-loop","1","-i",str(image),
        "-i",str(audio),
        "-loop","1","-i",str(visual_layer),
        "-filter_complex",vf,
        "-map","[vout]",
        "-map","1:a",
        "-c:v","libx264",
        "-preset","veryfast",
        "-tune","stillimage",
        "-pix_fmt","yuv420p",
        "-c:a","aac",
        "-b:a","192k",
        "-shortest",
        "-t",str(duration),
        "-movflags","+faststart",
        str(out)
    ])
    if not out.exists() or out.stat().st_size==0: raise SystemExit(f"Scene {index} was not created correctly.")
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
    print(f"V17 PREMIUM VIDEO CREATED: {OUTPUT} | {OUTPUT.stat().st_size} bytes")

if __name__ == "__main__":
    main()
