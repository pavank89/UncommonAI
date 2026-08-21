#!/usr/bin/env python3
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
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

PACKAGE_FILE = WORK / "production_package.json"
OUTPUT = WORK / "uncommonAI_video.mp4"

VOICE = os.getenv("VIDEO_VOICE", "en-US-AriaNeural")

def run(cmd):
    print("RUN:", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)

def safe_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def make_srt(text, duration, path):
    words = safe_text(text).split()
    if not words:
        words = ["uncommonAI"]

    # Approximate word timing; captions are intentionally simple and robust.
    chunks = []
    for i in range(0, len(words), 10):
        chunks.append(" ".join(words[i:i + 10]))

    total = max(float(duration), 1.0)
    slot = total / len(chunks)

    def stamp(seconds):
        ms = int(round(seconds * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, chunk in enumerate(chunks, 1):
        start = i - 1
        end = i
        lines += [str(i), f"{stamp(start * slot)} --> {stamp(end * slot)}", chunk, ""]
    path.write_text("\n".join(lines), encoding="utf-8")

def make_card(title, scene_number, narration, path):
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), (14, 17, 23))
    draw = ImageDraw.Draw(img)

    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    bold = ImageFont.truetype(font_paths[0], 64)
    normal = ImageFont.truetype(font_paths[1], 34)
    small = ImageFont.truetype(font_paths[1], 25)

    # Minimal branded layout; no copyrighted visual assets.
    draw.rectangle((80, 80, 1840, 1000), outline=(70, 78, 92), width=3)
    draw.text((120, 115), "uncommonAI", font=bold, fill=(235, 238, 245))
    draw.text((120, 205), f"SCENE {scene_number}", font=small, fill=(145, 154, 170))
    draw.text((120, 255), title[:80], font=bold, fill=(245, 245, 248))

    wrapped = textwrap.wrap(safe_text(narration), width=72)
    y = 390
    for line in wrapped[:10]:
        draw.text((125, y), line, font=normal, fill=(215, 219, 228))
        y += 52

    draw.text(
        (125, 930),
        "AI-assisted research • original commentary • uncommonAI",
        font=small,
        fill=(130, 138, 153),
    )
    img.save(path, quality=95)

def main():
    if not PACKAGE_FILE.exists():
        raise SystemExit(f"Missing {PACKAGE_FILE}")

    package = json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))
    title = safe_text(package.get("chosen_title", "uncommonAI"))

    scenes = package.get("scenes", [])
    if len(scenes) != 8:
        raise SystemExit(f"Expected 8 scenes, found {len(scenes)}")

    # Edge TTS is used for a natural neural voice without requiring another API key.
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is not installed.")
    if not shutil.which("edge-tts"):
        raise SystemExit("edge-tts is not installed.")

    segments = []

    for i, scene in enumerate(scenes, 1):
        narration = safe_text(scene.get("narration"))
        if not narration:
            raise SystemExit(f"Scene {i} has no narration.")

        audio = VIDEO_DIR / f"scene_{i:02d}.mp3"
        image = VIDEO_DIR / f"scene_{i:02d}.png"
        srt = VIDEO_DIR / f"scene_{i:02d}.srt"
        segment = VIDEO_DIR / f"segment_{i:02d}.mp4"

        run([
            "edge-tts",
            "--voice", VOICE,
            "--text", narration,
            "--write-media", str(audio),
        ])

        # Obtain the generated audio duration.
        probe = subprocess.check_output([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio)
        ], text=True).strip()
        duration = float(probe)

        make_card(title, i, narration, image)
        make_srt(narration, duration, srt)

        # Burn captions directly into the scene. The subtitles file is generated
        # from the exact narration, so it remains synchronized with the voice.
        subtitle_path = str(srt).replace("\\", "/").replace(":", "\\:")
        vf = (
            f"subtitles='{subtitle_path}':"
            "force_style='FontName=DejaVu Sans,FontSize=22,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=2,Shadow=1,Alignment=2,MarginV=55'"
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
            "-b:a", "192k",
            "-shortest",
            "-t", str(duration),
            str(segment),
        ])

        segments.append(segment)

    concat_file = VIDEO_DIR / "segments.txt"
    concat_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in segments),
        encoding="utf-8",
    )

    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(OUTPUT),
    ])

    # Basic output validation.
    subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-show_entries", "stream=codec_name",
        "-of", "default=noprint_wrappers=1",
        str(OUTPUT),
    ], check=True)

    print(f"VIDEO CREATED: {OUTPUT}")
    print(f"SIZE BYTES: {OUTPUT.stat().st_size}")

if __name__ == "__main__":
    main()
