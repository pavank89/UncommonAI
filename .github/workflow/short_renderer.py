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
SHORTS_DIR = WORK / "shorts"
PACKAGE_FILE = WORK / "production_package.json"
MANIFEST_FILE = SHORTS_DIR / "shorts_manifest.json"

SHORTS_DIR.mkdir(parents=True, exist_ok=True)
VOICE = os.getenv("VIDEO_VOICE", "en-US-AriaNeural")
W, H = 1080, 1920

# Same Short card geometry/typography for brand consistency.
# Palette changes per Short and per production topic.
PALETTES = [
    {"bg": (8, 20, 30), "panel": (16, 40, 56), "accent": (0, 220, 255), "muted": (140, 185, 200)},
    {"bg": (28, 9, 22), "panel": (54, 16, 42), "accent": (255, 70, 160), "muted": (210, 145, 185)},
    {"bg": (27, 19, 7), "panel": (56, 38, 12), "accent": (255, 190, 45), "muted": (215, 180, 115)},
    {"bg": (7, 27, 19), "panel": (13, 55, 38), "accent": (45, 230, 145), "muted": (130, 195, 165)},
    {"bg": (20, 8, 31), "panel": (42, 18, 62), "accent": (190, 90, 255), "muted": (175, 140, 210)},
    {"bg": (30, 13, 8), "panel": (61, 26, 13), "accent": (255, 105, 45), "muted": (215, 150, 120)},
    {"bg": (9, 19, 31), "panel": (16, 39, 60), "accent": (55, 175, 255), "muted": (135, 175, 205)},
    {"bg": (29, 8, 13), "panel": (58, 17, 26), "accent": (255, 75, 75), "muted": (215, 145, 145)},
]

def run(cmd):
    print("RUN:", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)

def safe_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def font(path, size):
    from PIL import ImageFont
    return ImageFont.truetype(path, size)

def palette_for_run(package):
    seed = safe_text(package.get("visual_run_id") or package.get("title") or package.get("chosen_title") or "uncommonAI")
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    offset = int.from_bytes(digest[:2], "big") % len(PALETTES)
    return [PALETTES[(offset + i) % len(PALETTES)] for i in range(3)]

def audio_duration(audio):
    return float(subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio),
    ], text=True).strip())

def make_srt(text, duration, path):
    words = safe_text(text).split() or ["uncommonAI"]
    chunks = [" ".join(words[i:i + 7]) for i in range(0, len(words), 7)]
    slot = max(float(duration), 1.0) / len(chunks)

    def stamp(seconds):
        ms = int(round(seconds * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, chunk in enumerate(chunks, 1):
        lines += [str(i), f"{stamp((i-1)*slot)} --> {stamp(i*slot)}", chunk, ""]
    path.write_text("\n".join(lines), encoding="utf-8")

def make_card(title, number, hook, narration, path, palette):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), palette["bg"])
    draw = ImageDraw.Draw(img)

    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    normal_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    brand = font(bold_path, 58)
    hero = font(bold_path, 68)
    body = font(normal_path, 36)
    small = font(normal_path, 25)

    # UNIFORM SHORT CARD SYSTEM.
    draw.rectangle((42, 42, W - 42, H - 42), outline=palette["accent"], width=3)
    draw.rectangle((42, 42, W - 42, 275), fill=palette["panel"])

    draw.text((75, 82), "uncommonAI", font=brand, fill=(242, 244, 248))
    draw.text((75, 165), f"SHORT {number}  •  AI / TECH",
              font=small, fill=palette["muted"])

    hook_lines = textwrap.wrap(safe_text(hook)[:145], width=25)
    y = 340
    for line in hook_lines[:4]:
        draw.text((75, y), line, font=hero, fill=(250, 250, 252))
        y += 82

    draw.rounded_rectangle(
        (72, 760, W - 72, 1190),
        radius=28,
        fill=palette["panel"],
        outline=palette["accent"],
        width=3,
    )
    draw.text((105, 800), "THE TAKEAWAY", font=small, fill=palette["muted"])

    body_lines = textwrap.wrap(safe_text(narration), width=38)
    y = 865
    for line in body_lines[:7]:
        draw.text((105, y), line, font=body, fill=(220, 224, 232))
        y += 53

    # Uniform progress strip.
    for i in range(3):
        x1 = 72 + i * 300
        draw.rounded_rectangle(
            (x1, 1330, x1 + 250, 1346),
            radius=8,
            fill=palette["accent"] if i == number - 1 else palette["panel"],
            outline=palette["muted"],
            width=1,
        )

    draw.text(
        (72, 1400),
        "Original commentary • uncommonAI",
        font=small,
        fill=palette["muted"],
    )
    img.save(path, quality=95)

def render_short(index, title, hook, script, palette):
    audio = SHORTS_DIR / f"short_{index:02d}.mp3"
    image = SHORTS_DIR / f"short_{index:02d}.png"
    srt = SHORTS_DIR / f"short_{index:02d}.srt"
    output = SHORTS_DIR / f"short_{index:02d}.mp4"

    run([
        "edge-tts", "--voice", VOICE,
        "--text", script,
        "--write-media", str(audio),
    ])

    duration = audio_duration(audio)
    make_card(title, index, hook, script, image, palette)
    make_srt(script, duration, srt)

    subtitle_path = str(srt).replace("\\", "/").replace(":", "\\:")
    vf = (
        f"subtitles='{subtitle_path}':"
        "force_style='FontName=DejaVu Sans,FontSize=19,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "Outline=2,Shadow=1,Alignment=2,MarginV=95'"
    )

    run([
        "ffmpeg", "-y", "-loop", "1",
        "-i", str(image), "-i", str(audio),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast",
        "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-t", str(duration),
        "-movflags", "+faststart",
        str(output),
    ])

    if not output.exists() or output.stat().st_size == 0:
        raise SystemExit(f"Short {index} was not created correctly.")

    print(f"SHORT CREATED: {output}")
    print(f"DURATION: {duration:.2f}s")
    return output

def main():
    if not PACKAGE_FILE.exists():
        raise SystemExit(f"Missing {PACKAGE_FILE}")

    for command in ("ffmpeg", "ffprobe", "edge-tts"):
        if not shutil.which(command):
            raise SystemExit(f"{command} is not installed.")

    package = json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))
    title = safe_text(package.get("title") or package.get("chosen_title") or "uncommonAI")
    shorts = package.get("shorts", [])

    if len(shorts) != 3:
        raise SystemExit(f"Expected exactly 3 Shorts, found {len(shorts)}")

    for item in SHORTS_DIR.iterdir():
        if item.is_file():
            item.unlink()

    palettes = palette_for_run(package)
    manifest = []

    for index, short in enumerate(shorts, 1):
        short_title = safe_text(short.get("title"))
        script = safe_text(short.get("script"))
        if not short_title or not script:
            raise SystemExit(f"Short {index} is missing title or script.")

        hook = safe_text(short.get("hook")) or short_title
        visual_prompt = safe_text(short.get("visual_prompt"))

        output = render_short(index, title, hook, script, palettes[index - 1])

        manifest.append({
            "index": index,
            "title": short_title[:100],
            "script": script,
            "visual_prompt": visual_prompt,
            "file": str(output).replace("\\", "/"),
        })

    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("===== SHORTS MANIFEST =====")
    print(MANIFEST_FILE.read_text(encoding="utf-8"))

if __name__ == "__main__":
    main()
