#!/usr/bin/env python3
import hashlib
import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

ROOT = Path.cwd()
WORK = ROOT / "workspace"
VIDEO_DIR = WORK / "video"
PACKAGE_FILE = WORK / "production_package.json"
OUTPUT = WORK / "uncommonAI_video.mp4"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

VOICE = os.getenv("VIDEO_VOICE", "en-US-AriaNeural")
W, H = 1920, 1080

# Consistent card system: same geometry, typography, spacing and branding.
# Only the accent/background palette changes from scene to scene/run.
PALETTES = [
    {"bg": (10, 18, 28), "panel": (18, 34, 50), "accent": (0, 210, 255), "muted": (135, 178, 195)},
    {"bg": (25, 12, 22), "panel": (48, 20, 38), "accent": (255, 74, 150), "muted": (208, 150, 182)},
    {"bg": (20, 17, 10), "panel": (48, 36, 16), "accent": (255, 184, 45), "muted": (205, 178, 115)},
    {"bg": (9, 25, 20), "panel": (16, 52, 39), "accent": (50, 225, 150), "muted": (135, 190, 165)},
    {"bg": (22, 12, 31), "panel": (43, 22, 62), "accent": (181, 90, 255), "muted": (173, 140, 205)},
    {"bg": (30, 16, 9), "panel": (60, 28, 14), "accent": (255, 105, 45), "muted": (210, 150, 125)},
    {"bg": (10, 22, 31), "panel": (18, 43, 58), "accent": (50, 180, 255), "muted": (135, 175, 205)},
    {"bg": (27, 10, 14), "panel": (55, 20, 28), "accent": (255, 75, 75), "muted": (210, 145, 145)},
]

def run(cmd):
    print("RUN:", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)

def safe_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def audio_duration(audio):
    value = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio),
    ], text=True).strip()
    return float(value)

def make_srt(text, duration, path):
    words = safe_text(text).split() or ["uncommonAI"]
    chunks = [" ".join(words[i:i + 9]) for i in range(0, len(words), 9)]
    slot = max(float(duration), 1.0) / len(chunks)

    def stamp(seconds):
        ms = int(round(seconds * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, chunk in enumerate(chunks, 1):
        lines.extend([
            str(i),
            f"{stamp((i - 1) * slot)} --> {stamp(i * slot)}",
            chunk,
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")

def font(path, size):
    from PIL import ImageFont
    return ImageFont.truetype(path, size)

def palette_for_run(package):
    # Stable for a topic/package, so rerendering the same package does not
    # randomly change its appearance.
    seed = safe_text(
        package.get("visual_run_id")
        or package.get("title")
        or package.get("chosen_title")
        or "uncommonAI"
    )
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    offset = int.from_bytes(digest[:2], "big") % len(PALETTES)
    return [PALETTES[(offset + i) % len(PALETTES)] for i in range(8)]

def make_scene_card(title, scene_number, narration, key_phrase, visual_type, path, palette):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), palette["bg"])
    draw = ImageDraw.Draw(img)

    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    normal_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    title_font = font(bold_path, 62)
    hero_font = font(bold_path, 76)
    body_font = font(normal_path, 34)
    small_font = font(normal_path, 24)

    # UNIFORM CARD SYSTEM
    draw.rectangle((55, 55, W - 55, H - 55), outline=palette["accent"], width=3)
    draw.rectangle((55, 55, W - 55, 185), fill=palette["panel"])

    draw.text((95, 82), "uncommonAI", font=title_font, fill=(242, 244, 248))
    draw.text(
        (95, 148),
        f"SCENE {scene_number}  •  {visual_type.upper()}",
        font=small_font,
        fill=palette["muted"],
    )

    left, right, top, bottom = 105, W - 105, 250, 800

    # Same visual layout language; content varies by scene type.
    if visual_type == "comparison":
        for x1, x2, label in [(left, 900, "BEFORE"), (1020, right, "AFTER")]:
            draw.rounded_rectangle((x1, top, x2, bottom), radius=28,
                                   fill=palette["panel"], outline=palette["accent"], width=3)
            draw.text((x1 + 50, 315), label, font=small_font, fill=palette["muted"])
        draw.text((155, 395), "Human-only", font=hero_font, fill=(235, 238, 245))
        draw.text((1070, 395), "AI-assisted", font=hero_font, fill=(235, 238, 245))
        draw.line((900, 520, 1020, 520), fill=palette["accent"], width=6)

    elif visual_type == "process":
        labels = ["INPUT", "AI", "CHECK", "OUTCOME"]
        xs = [130, 590, 1050, 1510]
        for i, label in enumerate(labels):
            draw.rounded_rectangle((xs[i], 420, xs[i] + 280, 610), radius=25,
                                   fill=palette["panel"], outline=palette["accent"], width=3)
            draw.text((xs[i] + 55, 490), label, font=title_font, fill=(235, 238, 245))
            if i < 3:
                draw.line((xs[i] + 280, 515, xs[i + 1], 515),
                          fill=palette["accent"], width=5)

    elif visual_type == "timeline":
        draw.line((180, 540, 1740, 540), fill=palette["accent"], width=6)
        points = [260, 700, 1140, 1580]
        labels = ["THEN", "CHANGE", "NOW", "NEXT"]
        for x, label in zip(points, labels):
            draw.ellipse((x - 28, 512, x + 28, 568), fill=palette["accent"])
            draw.text((x - 70, 410), label, font=small_font, fill=palette["muted"])

    elif visual_type == "evidence":
        draw.rounded_rectangle((250, 310, 1670, 720), radius=28,
                               fill=palette["panel"], outline=palette["accent"], width=3)
        draw.text((330, 370), "EVIDENCE", font=small_font, fill=palette["muted"])
        quote = textwrap.wrap(
            "What we can verify matters more than what the headline claims.",
            width=43,
        )
        y = 455
        for line in quote:
            draw.text((330, y), line, font=hero_font, fill=(235, 238, 245))
            y += 90

    elif visual_type == "warning":
        draw.polygon([(960, 270), (1450, 760), (470, 760)],
                     outline=palette["accent"], width=5)
        draw.text((855, 440), "!", font=hero_font, fill=palette["accent"])
        draw.text((710, 790), "THE CATCH", font=small_font, fill=palette["muted"])

    elif visual_type == "takeaway":
        draw.rounded_rectangle((260, 310, 1660, 720), radius=35,
                               fill=palette["panel"], outline=palette["accent"], width=4)
        draw.text((350, 390), "BOTTOM LINE", font=small_font, fill=palette["muted"])
        lines = textwrap.wrap(key_phrase[:80], width=30)
        y = 485
        for line in lines[:3]:
            draw.text((350, y), line, font=hero_font, fill=(242, 244, 248))
            y += 92

    else:
        draw.rounded_rectangle((220, 300, 1700, 740), radius=35,
                               fill=palette["panel"], outline=palette["accent"], width=4)
        draw.text((330, 385), "THE QUESTION", font=small_font, fill=palette["muted"])
        lines = textwrap.wrap(key_phrase[:100], width=28)
        y = 475
        for line in lines[:3]:
            draw.text((330, y), line, font=hero_font, fill=(242, 244, 248))
            y += 92

    excerpt = textwrap.wrap(safe_text(narration), width=92)
    y = 835
    for line in excerpt[:3]:
        draw.text((105, y), line, font=body_font, fill=(205, 211, 221))
        y += 43

    draw.text(
        (105, 965),
        "Original commentary • uncommonAI",
        font=small_font,
        fill=palette["muted"],
    )

    img.save(path, quality=95)

def render_segment(scene_number, title, narration, key_phrase, visual_type, palette):
    audio = VIDEO_DIR / f"scene_{scene_number:02d}.mp3"
    image = VIDEO_DIR / f"scene_{scene_number:02d}.png"
    srt = VIDEO_DIR / f"scene_{scene_number:02d}.srt"
    segment = VIDEO_DIR / f"segment_{scene_number:02d}.mp4"

    run([
        "edge-tts", "--voice", VOICE,
        "--text", narration,
        "--write-media", str(audio),
    ])

    duration = audio_duration(audio)
    make_scene_card(title, scene_number, narration, key_phrase, visual_type, image, palette)
    make_srt(narration, duration, srt)

    subtitle_path = str(srt).replace("\\", "/").replace(":", "\\:")
    vf = (
        f"subtitles='{subtitle_path}':"
        "force_style='FontName=DejaVu Sans,FontSize=22,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "Outline=2,Shadow=1,Alignment=2,MarginV=55'"
    )

    run([
        "ffmpeg", "-y", "-loop", "1",
        "-i", str(image), "-i", str(audio),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast",
        "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-t", str(duration),
        "-movflags", "+faststart",
        str(segment),
    ])
    return segment

def main():
    if not PACKAGE_FILE.exists():
        raise SystemExit(f"Missing {PACKAGE_FILE}")
    for command in ("ffmpeg", "ffprobe", "edge-tts"):
        if not shutil.which(command):
            raise SystemExit(f"{command} is not installed.")

    package = json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))
    title = safe_text(package.get("title") or package.get("chosen_title") or "uncommonAI")
    scenes = package.get("scenes", [])

    if len(scenes) != 8:
        raise SystemExit(f"Expected 8 scenes, found {len(scenes)}")

    palettes = palette_for_run(package)
    segments = []

    for index, scene in enumerate(scenes, 1):
        narration = safe_text(scene.get("narration"))
        if not narration:
            raise SystemExit(f"Scene {index} has no narration.")

        visual_type = safe_text(scene.get("visual_type")) or "hook"
        if visual_type not in {"hook", "comparison", "process", "timeline",
                               "evidence", "warning", "takeaway"}:
            visual_type = "hook"

        segments.append(render_segment(
            index, title, narration,
            safe_text(scene.get("key_phrase")) or title,
            visual_type, palettes[index - 1],
        ))

    concat_file = VIDEO_DIR / "segments.txt"
    concat_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in segments),
        encoding="utf-8",
    )

    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy", "-movflags", "+faststart",
        str(OUTPUT),
    ])

    subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size",
        "-show_entries", "stream=codec_name",
        "-of", "default=noprint_wrappers=1",
        str(OUTPUT),
    ], check=True)

    print(f"VIDEO CREATED: {OUTPUT}")
    print(f"SIZE BYTES: {OUTPUT.stat().st_size}")

if __name__ == "__main__":
    main()
