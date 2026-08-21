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
PACKAGE_FILE = WORK / "production_package.json"
OUTPUT = WORK / "uncommonAI_video.mp4"

VOICE = os.getenv("VIDEO_VOICE", "en-US-AriaNeural")

W, H = 1920, 1080


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


def make_scene_card(title, scene_number, narration, key_phrase, visual_type, path):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), (9, 12, 18))
    draw = ImageDraw.Draw(img)

    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    normal_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    title_font = font(bold_path, 62)
    hero_font = font(bold_path, 76)
    body_font = font(normal_path, 34)
    small_font = font(normal_path, 24)

    # Header and frame.
    draw.rectangle((55, 55, W - 55, H - 55), outline=(65, 75, 95), width=3)
    draw.rectangle((55, 55, W - 55, 185), fill=(17, 23, 33))

    draw.text((95, 82), "uncommonAI", font=title_font, fill=(240, 243, 248))
    draw.text(
        (95, 148),
        f"SCENE {scene_number}  •  {visual_type.upper()}",
        font=small_font,
        fill=(145, 157, 177),
    )

    # Main visual area.
    left = 105
    right = W - 105
    top = 250
    bottom = 800

    # Vary the visual composition by scene type.
    if visual_type == "comparison":
        draw.rounded_rectangle((left, top, 900, bottom), radius=28,
                               outline=(75, 90, 115), width=3)
        draw.rounded_rectangle((1020, top, right, bottom), radius=28,
                               outline=(75, 90, 115), width=3)
        draw.text((155, 315), "BEFORE", font=small_font, fill=(145, 157, 177))
        draw.text((1070, 315), "AFTER", font=small_font, fill=(145, 157, 177))
        draw.text((155, 395), "Human-only", font=hero_font, fill=(230, 233, 239))
        draw.text((1070, 395), "AI-assisted", font=hero_font, fill=(230, 233, 239))
        draw.line((900, 520, 1020, 520), fill=(150, 160, 178), width=6)
        draw.polygon([(1010, 500), (1050, 520), (1010, 540)], fill=(150, 160, 178))

    elif visual_type == "process":
        labels = ["INPUT", "AI", "CHECK", "OUTCOME"]
        xs = [130, 590, 1050, 1510]
        for i, label in enumerate(labels):
            draw.rounded_rectangle((xs[i], 420, xs[i] + 280, 610), radius=25,
                                   outline=(75, 90, 115), width=3)
            draw.text((xs[i] + 55, 490), label, font=title_font, fill=(235, 238, 245))
            if i < 3:
                draw.line((xs[i] + 280, 515, xs[i + 1], 515),
                          fill=(145, 157, 177), width=5)
                draw.polygon([(xs[i + 1] - 20, 495),
                              (xs[i + 1] + 15, 515),
                              (xs[i + 1] - 20, 535)],
                             fill=(145, 157, 177))

    elif visual_type == "timeline":
        draw.line((180, 540, 1740, 540), fill=(120, 132, 150), width=6)
        points = [260, 700, 1140, 1580]
        labels = ["THEN", "CHANGE", "NOW", "NEXT"]
        for x, label in zip(points, labels):
            draw.ellipse((x - 28, 512, x + 28, 568), fill=(210, 218, 230))
            draw.text((x - 70, 410), label, font=small_font, fill=(150, 163, 184))

    elif visual_type == "evidence":
        draw.rounded_rectangle((250, 310, 1670, 720), radius=28,
                               outline=(75, 90, 115), width=3)
        draw.text((330, 370), "EVIDENCE", font=small_font, fill=(150, 163, 184))
        quote = textwrap.wrap(
            "What we can verify matters more than what the headline claims.",
            width=43,
        )
        y = 455
        for line in quote:
            draw.text((330, y), line, font=hero_font, fill=(235, 238, 245))
            y += 90

    elif visual_type == "warning":
        draw.polygon([(960, 270), (1450, 760), (470, 760)], outline=(175, 183, 198))
        draw.text((855, 440), "!", font=hero_font, fill=(245, 245, 248))
        draw.text((710, 790), "THE CATCH", font=small_font, fill=(150, 163, 184))

    elif visual_type == "takeaway":
        draw.rounded_rectangle((260, 310, 1660, 720), radius=35,
                               outline=(95, 110, 135), width=4)
        draw.text((350, 390), "BOTTOM LINE", font=small_font, fill=(150, 163, 184))
        lines = textwrap.wrap(key_phrase[:80], width=30)
        y = 485
        for line in lines[:3]:
            draw.text((350, y), line, font=hero_font, fill=(242, 244, 248))
            y += 92

    else:  # hook
        draw.rounded_rectangle((220, 300, 1700, 740), radius=35,
                               outline=(85, 100, 125), width=4)
        draw.text((330, 385), "THE QUESTION", font=small_font, fill=(150, 163, 184))
        lines = textwrap.wrap(key_phrase[:100], width=28)
        y = 475
        for line in lines[:3]:
            draw.text((330, y), line, font=hero_font, fill=(242, 244, 248))
            y += 92

    # Narration excerpt / context.
    excerpt = textwrap.wrap(safe_text(narration), width=92)
    y = 835
    for line in excerpt[:3]:
        draw.text((105, y), line, font=body_font, fill=(205, 211, 221))
        y += 43

    draw.text(
        (105, 965),
        "Original commentary • uncommonAI",
        font=small_font,
        fill=(130, 140, 158),
    )

    img.save(path, quality=95)


def render_segment(scene_number, title, narration, key_phrase, visual_type):
    audio = VIDEO_DIR / f"scene_{scene_number:02d}.mp3"
    image = VIDEO_DIR / f"scene_{scene_number:02d}.png"
    srt = VIDEO_DIR / f"scene_{scene_number:02d}.srt"
    segment = VIDEO_DIR / f"segment_{scene_number:02d}.mp4"

    run([
        "edge-tts",
        "--voice", VOICE,
        "--text", narration,
        "--write-media", str(audio),
    ])

    duration = audio_duration(audio)

    make_scene_card(
        title,
        scene_number,
        narration,
        key_phrase,
        visual_type,
        image,
    )
    make_srt(narration, duration, srt)

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
        "-movflags", "+faststart",
        str(segment),
    ])

    return segment


def main():
    if not PACKAGE_FILE.exists():
        raise SystemExit(f"Missing {PACKAGE_FILE}")

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is not installed.")
    if not shutil.which("ffprobe"):
        raise SystemExit("ffprobe is not installed.")
    if not shutil.which("edge-tts"):
        raise SystemExit("edge-tts is not installed.")

    package = json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))
    title = safe_text(package.get("title") or package.get("chosen_title") or "uncommonAI")
    scenes = package.get("scenes", [])

    if len(scenes) != 8:
        raise SystemExit(f"Expected 8 scenes, found {len(scenes)}")

    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    segments = []

    for index, scene in enumerate(scenes, 1):
        narration = safe_text(scene.get("narration"))
        if not narration:
            raise SystemExit(f"Scene {index} has no narration.")

        key_phrase = safe_text(scene.get("key_phrase"))
        visual_type = safe_text(scene.get("visual_type")) or "hook"

        if visual_type not in {
            "hook", "comparison", "process", "timeline",
            "evidence", "warning", "takeaway"
        }:
            visual_type = "hook"

        segments.append(
            render_segment(
                index,
                title,
                narration,
                key_phrase or title,
                visual_type,
            )
        )

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
