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


def make_card(title, short_number, narration, path):
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), (14, 17, 23))
    draw = ImageDraw.Draw(img)

    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    normal_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    bold = ImageFont.truetype(bold_path, 58)
    normal = ImageFont.truetype(normal_path, 38)
    small = ImageFont.truetype(normal_path, 27)

    draw.rectangle(
        (45, 45, W - 45, H - 45),
        outline=(70, 78, 92),
        width=3,
    )

    draw.text(
        (75, 85),
        "uncommonAI",
        font=bold,
        fill=(235, 238, 245),
    )

    draw.text(
        (75, 175),
        f"SHORT {short_number}",
        font=small,
        fill=(145, 154, 170),
    )

    wrapped_title = textwrap.wrap(title[:100], width=27)
    y = 260
    for line in wrapped_title[:4]:
        draw.text(
            (75, y),
            line,
            font=bold,
            fill=(245, 245, 248),
        )
        y += 72

    wrapped = textwrap.wrap(narration, width=39)
    y = 650

    for line in wrapped[:20]:
        draw.text(
            (75, y),
            line,
            font=normal,
            fill=(215, 219, 228),
        )
        y += 54

    draw.text(
        (75, H - 135),
        "AI-assisted research • uncommonAI",
        font=small,
        fill=(130, 138, 153),
    )

    img.save(path, quality=95)


def audio_duration(audio):
    value = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio),
        ],
        text=True,
    ).strip()

    return float(value)


def make_srt(text, duration, path):
    words = safe_text(text).split()

    if not words:
        words = ["uncommonAI"]

    chunks = [
        " ".join(words[i:i + 9])
        for i in range(0, len(words), 9)
    ]

    slot = max(float(duration), 1.0) / len(chunks)

    def stamp(seconds):
        ms = int(round(seconds * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []

    for i, chunk in enumerate(chunks, 1):
        start = (i - 1) * slot
        end = i * slot

        lines.extend(
            [
                str(i),
                f"{stamp(start)} --> {stamp(end)}",
                chunk,
                "",
            ]
        )

    path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def render_short(short_number, title, narration):
    audio = SHORTS_DIR / f"short_{short_number:02d}.mp3"
    image = SHORTS_DIR / f"short_{short_number:02d}.png"
    srt = SHORTS_DIR / f"short_{short_number:02d}.srt"
    output = SHORTS_DIR / f"short_{short_number:02d}.mp4"

    run(
        [
            "edge-tts",
            "--voice",
            VOICE,
            "--text",
            narration,
            "--write-media",
            str(audio),
        ]
    )

    duration = audio_duration(audio)

    make_card(
        title,
        short_number,
        narration,
        image,
    )

    make_srt(
        narration,
        duration,
        srt,
    )

    subtitle_path = (
        str(srt)
        .replace("\\", "/")
        .replace(":", "\\:")
    )

    vf = (
        f"subtitles='{subtitle_path}':"
        "force_style='FontName=DejaVu Sans,FontSize=20,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "Outline=2,Shadow=1,Alignment=2,MarginV=90'"
    )

    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image),
            "-i",
            str(audio),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-tune",
            "stillimage",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-t",
            str(duration),
            "-movflags",
            "+faststart",
            str(output),
        ]
    )

    if not output.exists() or output.stat().st_size == 0:
        raise SystemExit(
            f"Short {short_number} was not created correctly."
        )

    print(f"SHORT CREATED: {output}")
    print(f"SIZE BYTES: {output.stat().st_size}")

    return output


def main():
    if not PACKAGE_FILE.exists():
        raise SystemExit(f"Missing {PACKAGE_FILE}")

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is not installed.")

    if not shutil.which("ffprobe"):
        raise SystemExit("ffprobe is not installed.")

    if not shutil.which("edge-tts"):
        raise SystemExit("edge-tts is not installed.")

    package = json.loads(
        PACKAGE_FILE.read_text(encoding="utf-8")
    )

    base_title = safe_text(
        package.get("chosen_title", "uncommonAI")
    )

    scenes = package.get("scenes", [])

    if len(scenes) < 3:
        raise SystemExit(
            f"Expected at least 3 scenes for Shorts, found {len(scenes)}"
        )

    # Remove files from a previous Shorts run.
    for item in SHORTS_DIR.iterdir():
        if item.is_file():
            item.unlink()

    manifest = []

    for short_number, scene in enumerate(scenes[:3], 1):
        narration = safe_text(scene.get("narration"))

        if not narration:
            raise SystemExit(
                f"Scene {short_number} has no narration."
            )

        # Keep each Short concise.
        words = narration.split()

        if len(words) > 75:
            narration = (
                " ".join(words[:75])
                .rstrip(" ,.;:")
                + "."
            )

        scene_title = safe_text(
            scene.get("title")
            or scene.get("heading")
            or scene.get("hook")
        )

        if scene_title:
            short_title = scene_title
        else:
            short_title = f"{base_title} — Short {short_number}"

        output = render_short(
            short_number,
            base_title,
            narration,
        )

        # The uploader runs from the repository root, so use a path
        # relative to the root exactly as its Path(item["file"]) expects.
        manifest.append(
            {
                "index": short_number,
                "title": short_title[:100],
                "script": narration,
                "file": str(output).replace("\\", "/"),
            }
        )

    MANIFEST_FILE.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("===== SHORTS MANIFEST =====")
    print(MANIFEST_FILE)
    print(MANIFEST_FILE.read_text(encoding="utf-8"))

    print("===== SHORTS CREATED =====")

    for number in range(1, 4):
        path = SHORTS_DIR / f"short_{number:02d}.mp4"
        print(
            f"{path} | {path.stat().st_size} bytes"
        )


if __name__ == "__main__":
    main()
