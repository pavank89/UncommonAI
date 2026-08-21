#!/usr/bin/env python3
import json
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

VOICE = "en-US-AriaNeural"


def run(cmd):
    print("RUN:", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def safe_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def audio_duration(audio):
    value = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio),
        ],
        text=True,
    ).strip()
    return float(value)


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
        lines.extend([
            str(i),
            f"{stamp((i - 1) * slot)} --> {stamp(i * slot)}",
            chunk,
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def make_card(title, short_number, hook, narration, path):
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), (9, 12, 18))
    draw = ImageDraw.Draw(img)

    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    normal_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    bold = ImageFont.truetype(bold_path, 58)
    hero = ImageFont.truetype(bold_path, 70)
    normal = ImageFont.truetype(normal_path, 37)
    small = ImageFont.truetype(normal_path, 25)

    # High-contrast editorial layout.
    draw.rectangle((42, 42, W - 42, H - 42), outline=(65, 75, 95), width=3)
    draw.rectangle((42, 42, W - 42, 270), fill=(18, 24, 34))

    draw.text((72, 78), "uncommonAI", font=bold, fill=(240, 243, 248))
    draw.text(
        (72, 160),
        f"SHORT {short_number}  •  AI / TECH",
        font=small,
        fill=(145, 157, 177),
    )

    # Hook is the visual focal point.
    hook_lines = textwrap.wrap(safe_text(hook)[:145], width=25)
    y = 345
    for line in hook_lines[:4]:
        draw.text((72, y), line, font=hero, fill=(250, 250, 252))
        y += 88

    # A simple "insight" panel makes the card less like a slideshow.
    draw.rounded_rectangle(
        (72, 735, W - 72, 1160),
        radius=28,
        outline=(80, 92, 116),
        width=3,
    )
    draw.text(
        (105, 775),
        "THE TAKEAWAY",
        font=small,
        fill=(150, 163, 184),
    )

    body = textwrap.wrap(safe_text(narration), width=38)
    y = 840
    for line in body[:7]:
        draw.text((105, y), line, font=normal, fill=(220, 224, 232))
        y += 55

    # Progress markers encourage completion and make each Short feel designed.
    for i in range(3):
        x1 = 72 + i * 300
        x2 = x1 + 250
        draw.rounded_rectangle(
            (x1, 1300, x2, 1316),
            radius=8,
            fill=(50, 58, 72) if i else (205, 213, 225),
        )

    draw.text(
        (72, 1370),
        "Watch to the end for the practical takeaway.",
        font=small,
        fill=(160, 170, 188),
    )

    draw.text(
        (72, H - 135),
        "Original commentary • uncommonAI",
        font=small,
        fill=(130, 140, 158),
    )

    img.save(path, quality=95)


def render_short(index, title, hook, script):
    audio = SHORTS_DIR / f"short_{index:02d}.mp3"
    image = SHORTS_DIR / f"short_{index:02d}.png"
    srt = SHORTS_DIR / f"short_{index:02d}.srt"
    output = SHORTS_DIR / f"short_{index:02d}.mp4"

    run([
        "edge-tts",
        "--voice", VOICE,
        "--text", script,
        "--write-media", str(audio),
    ])

    duration = audio_duration(audio)

    # Keep Shorts in the useful 20-60 second range.
    if duration > 59:
        print(f"WARNING: Short {index} is {duration:.1f}s; target is under 60s.")

    make_card(title, index, hook, script, image)
    make_srt(script, duration, srt)

    subtitle_path = str(srt).replace("\\", "/").replace(":", "\\:")
    vf = (
        f"subtitles='{subtitle_path}':"
        "force_style='FontName=DejaVu Sans,FontSize=19,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "Outline=2,Shadow=1,Alignment=2,MarginV=95'"
    )

    run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image),
        "-i", str(audio),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-t", str(duration),
        "-movflags", "+faststart",
        str(output),
    ])

    if not output.exists() or output.stat().st_size == 0:
        raise SystemExit(f"Short {index} was not created correctly.")

    print(f"SHORT CREATED: {output}")
    print(f"DURATION: {duration:.2f}s")
    print(f"SIZE BYTES: {output.stat().st_size}")

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
        raise SystemExit(
            f"Expected exactly 3 dedicated Shorts in production_package.json, found {len(shorts)}"
        )

    # Clean stale files so old manifests cannot be uploaded accidentally.
    for item in SHORTS_DIR.iterdir():
        if item.is_file():
            item.unlink()

    manifest = []

    for index, short in enumerate(shorts, 1):
        short_title = safe_text(short.get("title"))
        script = safe_text(short.get("script"))
        visual_prompt = safe_text(short.get("visual_prompt"))

        if not short_title or not script:
            raise SystemExit(f"Short {index} is missing title or script.")

        # The renderer doesn't need the visual prompt to be executable, but we
        # retain it in the manifest for auditability/future visual upgrades.
        hook = short_title

        output = render_short(index, title, hook, script)

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

    print("===== SHORTS CREATED =====")
    for index in range(1, 4):
        path = SHORTS_DIR / f"short_{index:02d}.mp4"
        print(f"{path} | {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
