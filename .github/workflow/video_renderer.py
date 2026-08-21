#!/usr/bin/env python3
import json
import os
import random
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

# Important: the renderer creates this directory itself.
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

VOICE = os.getenv("VIDEO_VOICE", "en-US-AriaNeural")

# Controlled uncommonAI palette. One palette order is randomly shuffled
# for every production run, while each scene keeps the same design language.
PALETTE = [
    {
        "accent": (255, 184, 77),
        "accent2": (255, 214, 128),
        "bg": (18, 17, 24),
        "panel": (29, 27, 38),
        "text": (245, 245, 248),
        "muted": (175, 178, 190),
    },
    {
        "accent": (62, 220, 151),
        "accent2": (145, 245, 196),
        "bg": (14, 20, 20),
        "panel": (24, 35, 34),
        "text": (244, 248, 246),
        "muted": (169, 187, 181),
    },
    {
        "accent": (174, 105, 255),
        "accent2": (215, 170, 255),
        "bg": (20, 16, 27),
        "panel": (34, 26, 45),
        "text": (247, 244, 250),
        "muted": (186, 176, 197),
    },
    {
        "accent": (255, 108, 88),
        "accent2": (255, 166, 150),
        "bg": (24, 17, 18),
        "panel": (42, 27, 29),
        "text": (250, 246, 246),
        "muted": (191, 174, 176),
    },
    {
        "accent": (65, 190, 255),
        "accent2": (145, 225, 255),
        "bg": (14, 19, 25),
        "panel": (23, 33, 43),
        "text": (244, 248, 250),
        "muted": (170, 184, 195),
    },
    {
        "accent": (255, 88, 180),
        "accent2": (255, 160, 216),
        "bg": (25, 15, 23),
        "panel": (42, 24, 39),
        "text": (250, 245, 249),
        "muted": (191, 172, 185),
    },
    {
        "accent": (86, 151, 255),
        "accent2": (160, 195, 255),
        "bg": (15, 18, 26),
        "panel": (24, 29, 43),
        "text": (244, 247, 251),
        "muted": (171, 181, 199),
    },
    {
        "accent": (190, 255, 73),
        "accent2": (220, 255, 150),
        "bg": (19, 22, 14),
        "panel": (30, 35, 22),
        "text": (246, 249, 240),
        "muted": (181, 190, 162),
    },
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


def wrap_to_width(draw, text, font, max_width):
    words = safe_text(text).split()
    if not words:
        return []

    lines = []
    current = ""

    for word in words:
        candidate = word if not current else f"{current} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font)

        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def make_srt(text, duration, path):
    words = safe_text(text).split() or ["uncommonAI"]
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
        lines.extend([
            str(i),
            f"{stamp(start)} --> {stamp(end)}",
            chunk,
            "",
        ])

    path.write_text("\n".join(lines), encoding="utf-8")


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


def draw_wrapped(draw, lines, x, y, font, fill, line_gap=12):
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def draw_diagram(draw, visual_type, x, y, w, h, accent, accent2, text_color, muted):
    """
    Compact, generic visual language. It intentionally does not depend on
    copyrighted images or external assets.
    """
    from PIL import ImageFont

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    vt = safe_text(visual_type).lower()

    # Keep every diagram inside its assigned panel.
    if any(k in vt for k in ("flow", "process", "pipeline", "workflow")):
        labels = ["INPUT", "AI", "CHECK", "OUTCOME"]
    elif any(k in vt for k in ("compare", "versus", "vs", "split")):
        labels = ["BEFORE", "AI", "AFTER"]
    elif any(k in vt for k in ("warning", "risk", "failure", "bug")):
        labels = ["PROMISE", "FAILURE", "HUMAN CHECK"]
    elif any(k in vt for k in ("metric", "data", "chart", "growth")):
        labels = ["SIGNAL", "CHANGE", "RESULT"]
    else:
        labels = ["QUESTION", "AI", "INSIGHT"]

    gap = 22
    box_w = (w - gap * (len(labels) - 1)) / len(labels)
    box_h = min(170, h * 0.48)
    top = y + (h - box_h) / 2

    label_font = ImageFont.truetype(bold_path, 27)
    small_font = ImageFont.truetype(font_path, 22)

    for i, label in enumerate(labels):
        bx = x + i * (box_w + gap)

        # Panel
        draw.rounded_rectangle(
            (bx, top, bx + box_w, top + box_h),
            radius=22,
            fill=(255, 255, 255, 8),
            outline=accent,
            width=3,
        )

        # Accent marker
        draw.rounded_rectangle(
            (bx + 18, top + 18, bx + 32, top + box_h - 18),
            radius=7,
            fill=accent,
        )

        # Label
        tw = draw.textbbox((0, 0), label, font=label_font)[2]
        draw.text(
            (bx + max(50, (box_w - tw) / 2), top + 48),
            label,
            font=label_font,
            fill=text_color,
        )

        # Small semantic marker
        marker = "→" if i < len(labels) - 1 else "✓"
        mw = draw.textbbox((0, 0), marker, font=small_font)[2]
        draw.text(
            (bx + (box_w - mw) / 2, top + box_h - 58),
            marker,
            font=small_font,
            fill=accent2,
        )

        if i < len(labels) - 1:
            ax = bx + box_w + 5
            ay = top + box_h / 2
            draw.line(
                (ax, ay, ax + gap - 10, ay),
                fill=muted,
                width=3,
            )


def make_scene_card(
    title,
    scene_number,
    narration,
    visual_type,
    palette,
    path,
):
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), palette["bg"])
    draw = ImageDraw.Draw(img)

    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    normal_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    title_font = fit_font(
        draw,
        title,
        bold_path,
        max_size=72,
        min_size=42,
        max_width=1500,
    )
    scene_font = ImageFont.truetype(normal_path, 25)
    label_font = ImageFont.truetype(bold_path, 22)

    # Outer frame
    margin = 55
    draw.rounded_rectangle(
        (margin, margin, W - margin, H - margin),
        radius=28,
        fill=palette["bg"],
        outline=palette["accent"],
        width=3,
    )

    # Top identity row
    draw.text(
        (90, 82),
        "uncommonAI",
        font=label_font,
        fill=palette["text"],
    )
    draw.text(
        (W - 240, 82),
        f"SCENE {scene_number:02d}",
        font=scene_font,
        fill=palette["muted"],
    )

    # Title zone: deliberately short and isolated.
    title_y = 155
    title_lines = wrap_to_width(draw, title, title_font, 1500)
    title_lines = title_lines[:2]
    draw_wrapped(
        draw,
        title_lines,
        90,
        title_y,
        title_font,
        palette["text"],
        line_gap=8,
    )

    # Visual zone. It has its own area and never shares space with subtitles.
    visual_top = 330
    visual_bottom = 820
    draw.rounded_rectangle(
        (90, visual_top, W - 90, visual_bottom),
        radius=30,
        fill=palette["panel"],
        outline=palette["accent"],
        width=2,
    )

    draw_diagram(
        draw,
        visual_type,
        150,
        visual_top + 35,
        W - 300,
        visual_bottom - visual_top - 70,
        palette["accent"],
        palette["accent2"],
        palette["text"],
        palette["muted"],
    )

    # Tiny supporting line, not the narration.
    support_words = safe_text(narration).split()
    support = " ".join(support_words[:12])
    if len(support_words) > 12:
        support += "…"

    support_font = fit_font(
        draw,
        support,
        normal_path,
        max_size=28,
        min_size=20,
        max_width=1500,
    )

    support_lines = wrap_to_width(draw, support, support_font, 1500)[:1]
    if support_lines:
        bbox = draw.textbbox((0, 0), support_lines[0], font=support_font)
        tw = bbox[2] - bbox[0]
        draw.text(
            ((W - tw) / 2, 850),
            support_lines[0],
            font=support_font,
            fill=palette["muted"],
        )

    # Dedicated subtitle-safe area below the visual.
    draw.line(
        (90, 900, W - 90, 900),
        fill=palette["accent"],
        width=2,
    )

    draw.text(
        (90, 925),
        "AI-assisted research • original commentary",
        font=scene_font,
        fill=palette["muted"],
    )

    img.save(path, quality=95)


def render_segment(
    scene_number,
    title,
    narration,
    visual_type,
    palette,
):
    audio = VIDEO_DIR / f"scene_{scene_number:02d}.mp3"
    image = VIDEO_DIR / f"scene_{scene_number:02d}.png"
    srt = VIDEO_DIR / f"scene_{scene_number:02d}.srt"
    segment = VIDEO_DIR / f"segment_{scene_number:02d}.mp4"

    narration = safe_text(narration)

    if not narration:
        raise SystemExit(
            f"Scene {scene_number} has empty narration. "
            "Cannot generate audio."
        )

    # Generate narration.
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
        visual_type,
        palette,
        image,
    )

    make_srt(narration, duration, srt)

    subtitle_path = (
        str(srt)
        .replace("\\", "/")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )

    # Captions are confined to a dedicated bottom zone.
    vf = (
        f"subtitles='{subtitle_path}':"
        "force_style='FontName=DejaVu Sans,"
        "FontSize=25,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "Outline=3,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginL=170,"
        "MarginR=170,"
        "MarginV=70'"
    )

    # Very subtle zoom gives the otherwise static card a little life.
    # The image itself remains visually stable and readable.
    vf += (
        ",scale=1920:1080,"
        "zoompan=z='min(zoom+0.00025,1.035)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=1:s=1920x1080:fps=30"
    )

    run([
        "ffmpeg",
        "-y",
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

    if not segment.exists() or segment.stat().st_size == 0:
        raise SystemExit(
            f"Scene {scene_number} was not rendered correctly."
        )

    print(
        f"SCENE {scene_number} CREATED: "
        f"{segment} ({segment.stat().st_size} bytes)"
    )

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

    package = json.loads(
        PACKAGE_FILE.read_text(encoding="utf-8")
    )

    title = safe_text(
        package.get("chosen_title")
        or package.get("title")
        or "uncommonAI"
    )

    scenes = package.get("scenes", [])

    if len(scenes) != 8:
        raise SystemExit(
            f"Expected 8 scenes, found {len(scenes)}"
        )

    # Clean only generated renderer files.
    for item in VIDEO_DIR.iterdir():
        if item.is_file():
            item.unlink()

    # New color ordering on every production run.
    palettes = PALETTE.copy()
    random.SystemRandom().shuffle(palettes)

    segments = []

    for scene_number, scene in enumerate(scenes, 1):
        narration = safe_text(scene.get("narration"))

        if not narration:
            raise SystemExit(
                f"Scene {scene_number} has no narration."
            )

        # Support both the current and older package field names.
        scene_title = safe_text(
            scene.get("title")
            or scene.get("heading")
            or scene.get("key_phrase")
            or f"Scene {scene_number}"
        )

        visual_type = safe_text(
            scene.get("visual_type")
            or scene.get("visual")
            or scene.get("diagram")
            or "workflow"
        )

        segments.append(
            render_segment(
                scene_number,
                scene_title,
                narration,
                visual_type,
                palettes[scene_number - 1],
            )
        )

    concat_file = VIDEO_DIR / "segments.txt"

    concat_file.write_text(
        "\n".join(
            f"file '{p.resolve()}'"
            for p in segments
        ),
        encoding="utf-8",
    )

    run([
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(OUTPUT),
    ])

    if not OUTPUT.exists() or OUTPUT.stat().st_size == 0:
        raise SystemExit("Final MP4 was not created correctly.")

    subprocess.run([
        "ffprobe",
        "-v", "error",
        "-show_entries",
        "format=duration,size",
        "-show_entries",
        "stream=codec_name,width,height",
        "-of", "default=noprint_wrappers=1",
        str(OUTPUT),
    ], check=True)

    print("========================================")
    print("V8 VIDEO CREATED")
    print(f"OUTPUT: {OUTPUT}")
    print(f"SIZE BYTES: {OUTPUT.stat().st_size}")
    print("========================================")


if __name__ == "__main__":
    main()
