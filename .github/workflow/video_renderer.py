#!/usr/bin/env python3
import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

ROOT = Path.cwd()
WORK = ROOT / "workspace"
SHORT_DIR = WORK / "shorts"
PACKAGE = WORK / "production_package.json"
SHORT_DIR.mkdir(parents=True, exist_ok=True)

VOICE = "en-US-AriaNeural"


def run(cmd):
    print("RUN:", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def safe_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def make_srt(text, duration, path):
    words = safe_text(text).split() or ["uncommonAI"]
    chunks = [" ".join(words[i:i + 8]) for i in range(0, len(words), 8)]
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


def make_card(topic, title, number, script, path):
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), (14, 17, 23))
    draw = ImageDraw.Draw(img)
    bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 62)
    normal = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 38)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 25)

    draw.rectangle((45, 45, W-45, H-45), outline=(70, 78, 92), width=3)
    draw.text((75, 85), "uncommonAI", font=bold, fill=(235, 238, 245))
    draw.text((75, 155), f"SHORT {number}", font=small, fill=(145, 154, 170))

    y = 230
    for line in textwrap.wrap(safe_text(title), width=25)[:5]:
        draw.text((75, y), line, font=title_font, fill=(245, 245, 248))
        y += 78

    draw.text((75, y + 45), "QUICK TAKE", font=small, fill=(145, 154, 170))
    y += 105
    for line in textwrap.wrap(safe_text(script), width=38)[:16]:
        draw.text((75, y), line, font=normal, fill=(215, 219, 228))
        y += 55

    draw.text((75, H-120), safe_text(topic)[:85], font=small, fill=(130, 138, 153))
    img.save(path, quality=95)


def main():
    if not PACKAGE.exists():
        raise SystemExit(f"Missing {PACKAGE}")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe") or not shutil.which("edge-tts"):
        raise SystemExit("ffmpeg, ffprobe and edge-tts are required.")

    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    shorts = package.get("shorts", [])
    if len(shorts) != 3:
        raise SystemExit(f"Expected 3 Shorts, found {len(shorts)}")

    topic = safe_text(package.get("chosen_title", "uncommonAI"))
    manifest = []

    for i, short in enumerate(shorts, 1):
        title = safe_text(short.get("title"))
        script = safe_text(short.get("script"))
        if not title or not script:
            raise SystemExit(f"Short {i} is missing title or script.")

        audio = SHORT_DIR / f"short_{i:02d}.mp3"
        image = SHORT_DIR / f"short_{i:02d}.png"
        srt = SHORT_DIR / f"short_{i:02d}.srt"
        video = SHORT_DIR / f"short_{i:02d}.mp4"

        run(["edge-tts", "--voice", VOICE, "--text", script, "--write-media", str(audio)])
        duration = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio)
        ], text=True).strip())

        if duration > 59.5:
            raise SystemExit(f"Short {i} is {duration:.1f}s; keep Shorts under 60s for this pipeline.")

        make_card(topic, title, i, script, image)
        make_srt(script, duration, srt)
        subtitle_path = str(srt).replace("\\", "/").replace(":", "\\:")
        vf = (f"subtitles='{subtitle_path}':force_style="
              "'FontName=DejaVu Sans,FontSize=20,PrimaryColour=&H00FFFFFF,"
              "OutlineColour=&H00000000,Outline=2,Shadow=1,Alignment=2,MarginV=90'")

        run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(image), "-i", str(audio),
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
            "-tune", "stillimage", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-b:a", "128k", "-shortest", "-t", str(duration),
            "-movflags", "+faststart", str(video)
        ])

        manifest.append({"index": i, "title": title, "script": script,
                         "file": str(video), "duration": round(duration, 2)})

    (SHORT_DIR / "shorts_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("SHORTS CREATED")
    for item in manifest:
        print(f"{item['index']}: {item['title']} -> {item['file']} ({item['duration']}s)")


if __name__ == "__main__":
    main()
