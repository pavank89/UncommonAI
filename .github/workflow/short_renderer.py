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
SHORTS_DIR = WORK / "shorts"
PACKAGE_FILE = WORK / "production_package.json"
MANIFEST = SHORTS_DIR / "shorts_manifest.json"

SHORTS_DIR.mkdir(parents=True, exist_ok=True)

VOICE = os.getenv("VIDEO_VOICE", "en-US-AriaNeural")

PALETTE = [
    {"accent": (255, 184, 77), "accent2": (255, 214, 128), "bg": (18, 17, 24), "panel": (42, 37, 46), "text": (247, 247, 250), "muted": (178, 180, 193)},
    {"accent": (62, 220, 151), "accent2": (145, 245, 196), "bg": (13, 20, 19), "panel": (31, 43, 40), "text": (244, 249, 246), "muted": (171, 188, 181)},
    {"accent": (174, 105, 255), "accent2": (215, 170, 255), "bg": (20, 16, 27), "panel": (40, 31, 51), "text": (248, 245, 251), "muted": (187, 177, 198)},
    {"accent": (255, 108, 88), "accent2": (255, 166, 150), "bg": (24, 17, 18), "panel": (46, 31, 33), "text": (250, 246, 246), "muted": (191, 174, 176)},
    {"accent": (65, 190, 255), "accent2": (145, 225, 255), "bg": (14, 19, 25), "panel": (28, 39, 50), "text": (244, 248, 250), "muted": (171, 185, 196)},
    {"accent": (255, 88, 180), "accent2": (255, 160, 216), "bg": (25, 15, 23), "panel": (45, 28, 42), "text": (250, 245, 249), "muted": (191, 172, 185)},
]

def run(cmd):
    print("RUN:", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)

def safe_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def fit_font(draw, text, font_path, max_size, min_size, max_width):
    from PIL import ImageFont
    for size in range(max_size, min_size - 1, -2):
        font = ImageFont.truetype(font_path, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    return ImageFont.truetype(font_path, min_size)

def wrap(draw, text, font, max_width, max_lines=None):
    words = safe_text(text).split()
    lines = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:max_lines] if max_lines else lines

def make_srt(text, duration, path):
    words = safe_text(text).split() or ["uncommonAI"]
    chunks = [" ".join(words[i:i+7]) for i in range(0, len(words), 7)]
    slot = max(float(duration), 1.0) / len(chunks)

    def stamp(seconds):
        ms = int(round(seconds * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    out = []
    for i, chunk in enumerate(chunks, 1):
        out += [str(i), f"{stamp((i-1)*slot)} --> {stamp(i*slot)}", chunk, ""]
    path.write_text("\n".join(out), encoding="utf-8")

def audio_duration(audio):
    return float(subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio)
    ], text=True).strip())

def first_sentence(text):
    text = safe_text(text)
    parts = re.split(r"(?<=[.!?])\s+", text)
    return parts[0] if parts else text

def make_hook(title, narration):
    # Use the production scene title when useful; otherwise create a concise hook
    # from the first sentence. Never put the full narration on the card.
    title = safe_text(title)
    if title and len(title) <= 90 and title.lower() not in {"scene 1", "scene 2", "scene 3"}:
        return title
    return first_sentence(narration)[:90].rstrip(" ,.;:") + ("…" if len(first_sentence(narration)) > 90 else "")

def make_takeaway(narration):
    words = safe_text(narration).split()
    if not words:
        return "The key idea"
    # Short, readable phrase; narration remains in audio/captions.
    phrase = " ".join(words[:10]).rstrip(" ,.;:")
    return phrase + ("…" if len(words) > 10 else "")

def draw_icon_diagram(draw, visual_type, x, y, w, h, p):
    from PIL import ImageFont
    bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    normal = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    label_font = ImageFont.truetype(bold, 30)
    small = ImageFont.truetype(normal, 23)

    vt = safe_text(visual_type).lower()
    if any(k in vt for k in ("warning", "risk", "failure", "bug")):
        labels = ["PROMISE", "FAIL", "CHECK"]
        symbols = ["✓", "!", "→"]
    elif any(k in vt for k in ("compare", "versus", "split", "vs")):
        labels = ["BEFORE", "AI", "AFTER"]
        symbols = ["1", "AI", "2"]
    elif any(k in vt for k in ("metric", "data", "chart", "growth")):
        labels = ["SIGNAL", "CHANGE", "RESULT"]
        symbols = ["▁▃▆", "↗", "✓"]
    else:
        labels = ["INPUT", "AI", "RESULT"]
        symbols = ["01", "AI", "✓"]

    box_w = min(260, (w - 40) / 3)
    box_h = min(250, h * 0.72)
    gap = (w - 3 * box_w) / 2
    top = y + (h - box_h) / 2

    for i, label in enumerate(labels):
        bx = x + i * (box_w + gap)
        draw.rounded_rectangle(
            (bx, top, bx + box_w, top + box_h),
            radius=28,
            fill=p["panel"],
            outline=p["accent"],
            width=4,
        )
        symbol = symbols[i]
        sf = fit_font(draw, symbol, bold, 58, 34, box_w - 50)
        sb = draw.textbbox((0,0), symbol, font=sf)
        draw.text((bx + (box_w-(sb[2]-sb[0]))/2, top+55), symbol, font=sf, fill=p["accent2"])
        lb = draw.textbbox((0,0), label, font=label_font)
        draw.text((bx + (box_w-(lb[2]-lb[0]))/2, top+150), label, font=label_font, fill=p["text"])
        if i < 2:
            ax = bx + box_w + 10
            ay = top + box_h/2
            draw.line((ax, ay, ax+gap-20, ay), fill=p["muted"], width=4)

def make_card(title, short_number, narration, visual_type, p, path):
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), p["bg"])
    draw = ImageDraw.Draw(img)

    bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    normal = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    # Fixed design zones. Nothing except subtitles is allowed in the bottom zone.
    draw.rounded_rectangle((40, 40, W-40, H-40), radius=32, outline=p["accent"], width=4)

    top_font = ImageFont.truetype(bold, 32)
    small = ImageFont.truetype(normal, 24)
    draw.text((70, 78), "uncommonAI", font=top_font, fill=p["text"])
    draw.text((W-180, 82), f"{short_number:02d}", font=small, fill=p["muted"])

    # Hook/title zone
    title_font = fit_font(draw, title, bold, 64, 38, 900)
    title_lines = wrap(draw, title, title_font, 900, 3)
    y = 190
    for line in title_lines:
        bbox = draw.textbbox((0,0), line, font=title_font)
        draw.text(((W-(bbox[2]-bbox[0]))/2, y), line, font=title_font, fill=p["text"])
        y += bbox[3]-bbox[1] + 10

    # Visual zone
    visual_top, visual_bottom = 560, 1120
    draw.rounded_rectangle(
        (70, visual_top, W-70, visual_bottom),
        radius=34,
        fill=p["panel"],
        outline=p["accent"],
        width=3,
    )
    draw_icon_diagram(
        draw, visual_type,
        110, visual_top+35, W-220, visual_bottom-visual_top-70, p
    )

    # One short takeaway only. This is not the full script.
    takeaway = make_takeaway(narration)
    tf = fit_font(draw, takeaway, normal, 34, 24, 820)
    lines = wrap(draw, takeaway, tf, 820, 2)
    y = 1220
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=tf)
        draw.text(((W-(bbox[2]-bbox[0]))/2, y), line, font=tf, fill=p["muted"])
        y += bbox[3]-bbox[1] + 6

    # Clear separator before subtitle-safe zone.
    draw.line((70, 1370, W-70, 1370), fill=p["accent"], width=3)

    draw.text(
        (70, 1410),
        "THE TAKEAWAY",
        font=top_font,
        fill=p["accent"],
    )

    # Bottom 420px are intentionally empty for subtitles.
    draw.rounded_rectangle(
        (60, 1480, W-60, H-65),
        radius=28,
        outline=(55, 55, 65),
        width=2,
    )

    img.save(path, quality=95)

def render_short(number, title, narration, visual_type, p):
    audio = SHORTS_DIR / f"short_{number:02d}.mp3"
    image = SHORTS_DIR / f"short_{number:02d}.png"
    srt = SHORTS_DIR / f"short_{number:02d}.srt"
    output = SHORTS_DIR / f"short_{number:02d}.mp4"

    narration = safe_text(narration)
    if not narration:
        raise SystemExit(f"Short {number} has empty narration.")

    run([
        "edge-tts", "--voice", VOICE,
        "--text", narration,
        "--write-media", str(audio)
    ])

    duration = audio_duration(audio)
    make_card(title, number, narration, visual_type, p, image)
    make_srt(narration, duration, srt)

    subtitle_path = str(srt).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    # Motion first. Subtitles are applied last so they cannot be distorted.
    motion = (
        "scale=1120:1991,"
        "zoompan=z='min(zoom+0.00015,1.025)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920:fps=30"
    )

    # Dedicated subtitle zone: 2 lines max, smaller type, no card text below it.
    subtitles = (
        f"subtitles='{subtitle_path}':"
        "force_style='FontName=DejaVu Sans,"
        "FontSize=22,"
        "Bold=0,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BackColour=&HE60B0D12,"
        "BorderStyle=3,"
        "Outline=0,"
        "Shadow=0,"
        "Alignment=2,"
        "MarginL=85,"
        "MarginR=85,"
        "MarginV=105,"
        "WrapStyle=2,"
        "PlayResX=1080,"
        "PlayResY=1920'"
    )

    run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image),
        "-i", str(audio),
        "-vf", f"{motion},{subtitles}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-t", str(duration),
        "-movflags", "+faststart",
        str(output)
    ])

    if not output.exists() or output.stat().st_size == 0:
        raise SystemExit(f"Short {number} was not created correctly.")

    return output, duration

def main():
    if not PACKAGE_FILE.exists():
        raise SystemExit(f"Missing {PACKAGE_FILE}")
    for tool in ("ffmpeg", "ffprobe", "edge-tts"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} is not installed.")

    package = json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))
    base_title = safe_text(package.get("chosen_title") or package.get("title") or "uncommonAI")
    scenes = package.get("scenes", [])
    if len(scenes) < 3:
        raise SystemExit(f"Expected at least 3 scenes for Shorts, found {len(scenes)}")

    for item in SHORTS_DIR.iterdir():
        if item.is_file():
            item.unlink()

    palettes = PALETTE.copy()
    random.SystemRandom().shuffle(palettes)

    manifest = []

    # If the package contains explicit Shorts, use them; otherwise use first 3 scenes.
    explicit = package.get("shorts")
    if isinstance(explicit, list) and len(explicit) >= 3:
        source_items = explicit[:3]
        for i, item in enumerate(source_items, 1):
            narration = safe_text(item.get("script") or item.get("narration"))
            hook = safe_text(item.get("title") or item.get("hook") or f"{base_title} — Short {i}")
            visual = safe_text(item.get("visual_type") or item.get("visual") or "workflow")
            out, _ = render_short(i, hook, narration, visual, palettes[i-1])
            manifest.append({
                "index": i,
                "title": hook[:100],
                "script": narration,
                "file": str(out.resolve()),
            })
    else:
        for i, scene in enumerate(scenes[:3], 1):
            narration = safe_text(scene.get("narration"))
            if not narration:
                raise SystemExit(f"Scene {i} has no narration.")

            scene_title = safe_text(
                scene.get("title")
                or scene.get("heading")
                or scene.get("key_phrase")
            )
            hook = make_hook(scene_title, narration)
            visual = safe_text(
                scene.get("visual_type")
                or scene.get("visual")
                or scene.get("diagram")
                or "workflow"
            )

            out, _ = render_short(i, hook, narration, visual, palettes[i-1])
            manifest.append({
                "index": i,
                "title": f"uncommonAI — Short {i}",
                "script": narration,
                "file": str(out.resolve()),
            })

    MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("===== SHORTS V2 CREATED =====")
    for i in range(1, 4):
        path = SHORTS_DIR / f"short_{i:02d}.mp4"
        print(f"{path} | {path.stat().st_size} bytes")
    print(f"MANIFEST: {MANIFEST}")

if __name__ == "__main__":
    main()
