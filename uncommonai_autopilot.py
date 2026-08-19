
"""
UNCOMMONAI AUTOPILOT V2
=======================

A single Python application for a faceless AI/technology YouTube channel.

FLOW
----
Research -> score -> choose -> script -> fact-check -> narration ->
AI visuals -> thumbnail -> video assembly -> Shorts -> approval ->
YouTube upload/schedule -> analytics.

The script is intentionally approval-gated before publishing.

REQUIRED
--------
1) Python 3.10+
2) ffmpeg installed and available on PATH
3) Google OAuth Desktop credentials: client_secret.json
4) OPENAI_API_KEY in .env
5) YouTube Data API v3 + YouTube Analytics API enabled

OPTIONAL
--------
- PEXELS_API_KEY for real stock footage/images. If absent, the script uses
  OpenAI-generated visuals.
- ELEVENLABS_API_KEY is NOT required; OpenAI TTS is used.
- SORA is NOT required; this version uses generated stills + motion effects,
  which keeps the workflow cheaper and deterministic.

SECURITY
--------
Never put your Google password into this script.
YouTube uses OAuth 2.0. The first run opens Google's authorization page.
A local token.json is then reused for later runs.

OUTPUT
------
workspace/
  research.json
  package.json
  scenes/
  audio/
  video.mp4
  thumbnail.png
  shorts/
  publish.json

SETUP
-----
pip install -r requirements.txt

Copy .env.example -> .env

Put client_secret.json beside this script.

Run:
    python uncommonai_autopilot.py

The script can create a complete video without recording or manual editing.
You only approve the topic and the final upload.

NOTE
----
AI-generated content can be monetized only if it provides genuine original
value and is not mass-produced/repetitive. The editorial system therefore
requires a unique thesis, sourced research, original synthesis, and a
different experiment/angle for every video.
"""

import os
import sys
import json
import re
import time
import shutil
import subprocess
from pathlib import Path
from datetime import date, timedelta, datetime

import feedparser
from dotenv import load_dotenv
from openai import OpenAI

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError


ROOT = Path(__file__).resolve().parent
WORK = ROOT / "workspace"
SCENES = WORK / "scenes"
AUDIO = WORK / "audio"
SHORTS = WORK / "shorts"
for d in [WORK, SCENES, AUDIO, SHORTS]:
    d.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-2")
TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.getenv("TTS_VOICE", "marin")

CHANNEL_NAME = os.getenv("CHANNEL_NAME", "uncommonAI")
CHANNEL_HANDLE = os.getenv("CHANNEL_HANDLE", "@pavan.kulkarniwaves")
CATEGORY_ID = os.getenv("YOUTUBE_CATEGORY_ID", "28")

CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN_FILE = ROOT / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

RSS_FEEDS = {
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
}

# 8 scenes keeps image-generation cost manageable. Increase to 10-12 for
# richer videos after the workflow is proven.
SCENE_COUNT = int(os.getenv("SCENE_COUNT", "8"))


def require_binary(name):
    if shutil.which(name) is None:
        raise RuntimeError(
            f"{name} was not found on PATH. Install it and restart the terminal."
        )


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


def confirm(prompt):
    while True:
        v = input(f"{prompt} [y/n]: ").strip().lower()
        if v in ("y", "yes"):
            return True
        if v in ("n", "no"):
            return False


def ai():
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing from .env")
    return OpenAI(api_key=OPENAI_API_KEY)


def write_json(path, data):
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def run(cmd):
    print(">", " ".join(map(str, cmd)))
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        print(p.stderr[-5000:])
        raise RuntimeError(f"Command failed: {cmd[0]}")
    return p.stdout


# ---------------------------------------------------------------------------
# GOOGLE / YOUTUBE
# ---------------------------------------------------------------------------

def youtube_services():
    if not CLIENT_SECRET.exists():
        raise FileNotFoundError(
            "client_secret.json is missing. Create a Google OAuth Desktop client."
        )

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET), SCOPES
        )
        creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return (
        build("youtube", "v3", credentials=creds),
        build("youtubeAnalytics", "v2", credentials=creds),
    )


def channel_snapshot(youtube):
    r = youtube.channels().list(
        part="snippet,statistics,contentDetails",
        mine=True,
    ).execute()

    if not r.get("items"):
        raise RuntimeError("No channel found for the authorized Google account.")

    c = r["items"][0]
    s = c.get("statistics", {})
    sn = c.get("snippet", {})

    return {
        "id": c["id"],
        "title": sn.get("title"),
        "description": sn.get("description", ""),
        "subscribers": int(s.get("subscriberCount", 0)),
        "views": int(s.get("viewCount", 0)),
        "videos": int(s.get("videoCount", 0)),
        "uploads_playlist": c.get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads"),
    }


def recent_videos(youtube, playlist_id, limit=15):
    if not playlist_id:
        return []

    p = youtube.playlistItems().list(
        part="snippet,contentDetails",
        playlistId=playlist_id,
        maxResults=limit,
    ).execute()

    ids = [x["contentDetails"]["videoId"] for x in p.get("items", [])]
    if not ids:
        return []

    r = youtube.videos().list(
        part="snippet,statistics",
        id=",".join(ids),
    ).execute()

    out = []
    for v in r.get("items", []):
        st = v.get("statistics", {})
        out.append({
            "id": v["id"],
            "title": v["snippet"].get("title", ""),
            "published": v["snippet"].get("publishedAt", ""),
            "views": int(st.get("viewCount", 0)),
            "likes": int(st.get("likeCount", 0)),
            "comments": int(st.get("commentCount", 0)),
        })
    return out


def analytics_28d(api):
    end = date.today()
    start = end - timedelta(days=28)

    r = api.reports().query(
        ids="channel==MINE",
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics="views,estimatedMinutesWatched,averageViewDuration,"
                "likes,comments,subscribersGained",
        dimensions="day",
        sort="day",
    ).execute()

    totals = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "views": 0,
        "watch_minutes": 0,
        "likes": 0,
        "comments": 0,
        "subscribers_gained": 0,
    }

    for row in r.get("rows", []):
        totals["views"] += int(row[1])
        totals["watch_minutes"] += int(row[2])
        totals["likes"] += int(row[4])
        totals["comments"] += int(row[5])
        totals["subscribers_gained"] += int(row[6])

    return totals


# ---------------------------------------------------------------------------
# RESEARCH
# ---------------------------------------------------------------------------

def rss_signals():
    result = []

    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:12]:
                title = e.get("title", "").strip()
                summary = re.sub(
                    r"\s+",
                    " ",
                    re.sub("<[^>]+>", " ", e.get("summary", "")),
                ).strip()

                if title:
                    result.append({
                        "source": source,
                        "title": title,
                        "summary": summary[:900],
                        "link": e.get("link", ""),
                        "published": e.get("published", e.get("updated", "")),
                    })
        except Exception as exc:
            print("RSS warning:", source, exc)

    return result


def web_research(client, signals):
    prompt = f"""
You are the research editor for uncommonAI.

Channel:
AI. Agents. Experiments. No hype.

Audience:
Experienced software engineers, QA/SDET engineers, DevOps/infrastructure
professionals, technical leads and technology professionals.

Use web search to investigate current AI developments and identify stories
that can become ORIGINAL practical YouTube experiments.

Current RSS signals:
{json.dumps(signals, indent=2)}

Research requirements:
- Find recent developments from primary sources whenever possible.
- Prefer AI agents, coding agents, model releases, AI engineering,
  evaluations, safety/reliability, developer tools and career impact.
- Avoid generic "AI is changing the world" stories.
- Find facts that can be demonstrated, tested, compared or reproduced.
- Provide source URLs.
- Clearly separate facts from your suggested interpretation.

Return 15 candidate stories, each with:
title
why_now
primary_sources
key_facts
experiment_angle
audience
risk_or_caveat
"""
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        tools=[{"type": "web_search"}],
    )
    return response.output_text


# ---------------------------------------------------------------------------
# STRATEGY
# ---------------------------------------------------------------------------

def strategy(client, channel, videos, analytics, research):
    prompt = f"""
You are the chief YouTube strategist for uncommonAI.

Positioning:
AI. Agents. Experiments. No hype.

Audience:
Experienced engineers and technology professionals.

Channel data:
{json.dumps(channel, indent=2)}

Recent videos:
{json.dumps(videos, indent=2)}

28-day analytics:
{json.dumps(analytics, indent=2)}

Research:
{research}

Score every candidate:
curiosity 25
demand 20
novelty 15
expertise advantage 15
visual/demo potential 10
monetization potential 10
evergreen value 5

Select the top 5.

For each:
- score
- title
- thumbnail text <= 4 words
- 20-second hook
- original experiment
- expected audience
- why this channel should make it
- monetization angle
- next-video opportunity

Then choose ONE winner.

Do not invent results. The video must be based on facts and/or an actual
demonstration the script can perform.
"""
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
    )
    return response.output_text


# ---------------------------------------------------------------------------
# SCRIPT PACKAGE
# ---------------------------------------------------------------------------

def make_package(client, chosen):
    prompt = f"""
Create the complete production package for this approved uncommonAI concept:

{chosen}

Channel style:
AI. Agents. Experiments. No hype.

Audience:
Experienced technology professionals.

Create JSON with these fields:
title
alternate_titles (4)
thumbnail_prompt
description
tags (12)
script
scenes (exactly {SCENE_COUNT} objects)
shorts (3 objects)

Each scene must contain:
- scene_number
- narration
- visual_prompt
- on_screen_text

Rules:
- 8-15 minute main video.
- Strong hook in first 20 seconds.
- Every 45-90 seconds introduces a new fact, visual, test, comparison,
  surprise, or conclusion.
- Original analysis, not generic AI news.
- Use source URLs in the description.
- Never fabricate experimental results.
- If a result needs to be performed, mark [RUN EXPERIMENT] and describe
  what the narrator should say only after the result is known.
- Visual prompts should avoid copyrighted logos/characters unless essential.
- No text-heavy generated images.
- Shorts should each be 30-60 seconds and have their own hook.

Return valid JSON only.
"""
    r = client.responses.create(model=OPENAI_MODEL, input=prompt)
    text = r.output_text.strip()

    # Handle accidental markdown fences.
    text = re.sub(r"^```json\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # One repair pass.
        repair = client.responses.create(
            model=OPENAI_MODEL,
            input=(
                "Convert the following into valid JSON only. Preserve all "
                "content and use the requested keys.\n\n" + text
            ),
        )
        return json.loads(re.sub(
            r"^```json\s*|\s*```$",
            "",
            repair.output_text.strip(),
            flags=re.I,
        ))


# ---------------------------------------------------------------------------
# FACT / QUALITY GATE
# ---------------------------------------------------------------------------

def quality_gate(client, package):
    prompt = f"""
You are the final editorial and monetization safety editor for uncommonAI.

Evaluate this package:
{json.dumps(package, indent=2)}

Return JSON:
{{
  "pass": true/false,
  "originality": 0-100,
  "evidence": 0-100,
  "viewer_value": 0-100,
  "repetition_risk": 0-100,
  "copyright_risk": 0-100,
  "ypp_risk": 0-100,
  "required_fixes": [],
  "reason": ""
}}

Fail if:
- the script is generic filler
- claims lack evidence
- it imitates a template too closely
- it depends on fabricated results
- it is primarily a summary of other people's material
- it looks mass-produced/repetitive
"""
    r = client.responses.create(model=OPENAI_MODEL, input=prompt)
    text = re.sub(r"^```json\s*|\s*```$", "", r.output_text.strip(), flags=re.I)
    return json.loads(text)


# ---------------------------------------------------------------------------
# AUDIO
# ---------------------------------------------------------------------------

def tts(client, text, out_path):
    speech = client.audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=text,
    )
    speech.stream_to_file(out_path)


def audio_duration(path):
    out = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    return float(out.strip())


# ---------------------------------------------------------------------------
# IMAGE GENERATION
# ---------------------------------------------------------------------------

def generate_image(client, prompt, out_path, size="1536x1024"):
    result = client.images.generate(
        model=IMAGE_MODEL,
        prompt=(
            "Create a cinematic editorial technology image for a premium "
            "YouTube documentary about artificial intelligence. "
            "No text, no captions, no watermarks. "
            + prompt
        ),
        size=size,
    )

    image = result.data[0]

    # SDK may expose base64 or a URL depending on configuration.
    if getattr(image, "b64_json", None):
        import base64
        out_path.write_bytes(base64.b64decode(image.b64_json))
    elif getattr(image, "url", None):
        import requests
        out_path.write_bytes(requests.get(image.url, timeout=60).content)
    else:
        raise RuntimeError("Image API returned neither b64_json nor url.")


# ---------------------------------------------------------------------------
# VIDEO ASSEMBLY
# ---------------------------------------------------------------------------

def make_scene_video(image_path, audio_path, output_path):
    duration = audio_duration(audio_path)

    # Subtle Ken Burns motion. Each scene is a clean 16:9 visual.
    vf = (
        "scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,"
        "zoompan=z='min(zoom+0.0008,1.08)':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        "d=1:s=1920x1080:fps=30"
    )

    run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-i", str(audio_path),
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path),
    ])


def concat_videos(paths, output):
    manifest = WORK / "concat.txt"
    manifest.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in paths),
        encoding="utf-8",
    )

    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(manifest),
        "-c", "copy",
        str(output),
    ])


def make_thumbnail(client, package):
    prompt = package["thumbnail_prompt"] + (
        "\nYouTube thumbnail, 16:9, extremely readable composition, "
        "one dominant visual idea, high contrast, no tiny details."
    )

    path = WORK / "thumbnail.png"
    generate_image(client, prompt, path, size="1536x1024")
    return path


# ---------------------------------------------------------------------------
# SHORTS
# ---------------------------------------------------------------------------

def make_short(client, short_spec, index):
    text = short_spec["script"]
    narration = AUDIO / f"short_{index}.mp3"

    tts(client, text, narration)

    # One generated visual for each short.
    image = SCENES / f"short_{index}.png"
    generate_image(
        client,
        short_spec.get(
            "visual_prompt",
            "abstract AI engineering experiment, vertical editorial image"
        ),
        image,
        size="1024x1536",
    )

    duration = audio_duration(narration)
    output = SHORTS / f"short_{index}.mp4"

    run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image),
        "-i", str(narration),
        "-t", f"{duration:.3f}",
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan=z='min(zoom+0.001,1.08)':"
        "d=1:s=1080x1920:fps=30",
        "-r", "30",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output),
    ])

    return output


# ---------------------------------------------------------------------------
# YOUTUBE PUBLISH
# ---------------------------------------------------------------------------

def upload(youtube, video_path, package, thumbnail, mode):
    title = package["title"]
    description = package["description"]
    tags = package.get("tags", [])

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:15],
            "categoryId": CATEGORY_ID,
        },
        "status": {
            "privacyStatus": mode,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=8 * 1024 * 1024,
    )

    req = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"Upload: {int(status.progress()*100)}%")

    video_id = response["id"]

    if thumbnail and thumbnail.exists():
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(
                str(thumbnail),
                mimetype="image/png",
            ),
        ).execute()

    return video_id


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("\n" + "="*80)
    print("UNCOMMONAI AUTOPILOT V2")
    print("="*80)

    require_binary("ffmpeg")
    require_binary("ffprobe")

    client = ai()
    youtube, analytics_api = youtube_services()

    channel = channel_snapshot(youtube)
    videos = recent_videos(
        youtube,
        channel["uploads_playlist"],
    )
    analytics = analytics_28d(analytics_api)

    print(
        f"\nChannel: {channel['title']} | "
        f"Subscribers: {channel['subscribers']} | "
        f"Videos: {channel['videos']}"
    )

    # Research.
    signals = rss_signals()
    print(f"Collected {len(signals)} RSS signals.")

    print("\nRunning current web research...")
    research = web_research(client, signals)
    (WORK / "research.md").write_text(research, encoding="utf-8")

    # Strategy.
    print("\nScoring opportunities...")
    strategy_text = strategy(
        client,
        channel,
        videos,
        analytics,
        research,
    )
    (WORK / "strategy.md").write_text(strategy_text, encoding="utf-8")

    print("\n" + strategy_text)

    if not confirm("\nDo you want to approve a video concept?"):
        print("Stopped.")
        return

    chosen = input(
        "\nPaste the concept/title you want to approve:\n> "
    ).strip()

    if not chosen:
        print("Nothing selected.")
        return

    # Production package.
    print("\nGenerating production package...")
    package = make_package(client, chosen)
    write_json(WORK / "package.json", package)

    print("\nTITLE:", package["title"])
    print("\nTHUMBNAIL:", package["thumbnail_prompt"])
    print("\nDESCRIPTION PREVIEW:\n", package["description"][:2500])

    # Editorial gate.
    print("\nRunning originality/evidence/YPP-risk gate...")
    gate = quality_gate(client, package)
    write_json(WORK / "quality_gate.json", gate)
    print(json.dumps(gate, indent=2))

    if not gate.get("pass"):
        print(
            "\nEditorial gate FAILED. The script will not render/publish this "
            "video. Review workspace/quality_gate.json."
        )
        return

    if not confirm("\nApprove the script and start automatic production?"):
        print("Stopped before production.")
        return

    # Main narration.
    full_script = package["script"]
    main_audio = AUDIO / "main.mp3"

    print("\nGenerating narration...")
    tts(client, full_script, main_audio)

    # Scene production.
    scene_videos = []

    scenes = package["scenes"][:SCENE_COUNT]

    for i, scene in enumerate(scenes, start=1):
        print(f"\nScene {i}/{len(scenes)}")

        image = SCENES / f"scene_{i}.png"
        audio = AUDIO / f"scene_{i}.mp3"
        scene_video = SCENES / f"scene_{i}.mp4"

        print("  Generating visual...")
        generate_image(client, scene["visual_prompt"], image)

        print("  Generating narration...")
        tts(client, scene["narration"], audio)

        print("  Rendering scene...")
        make_scene_video(image, audio, scene_video)

        scene_videos.append(scene_video)

    # Main video.
    main_video = WORK / "video.mp4"
    print("\nAssembling main video...")
    concat_videos(scene_videos, main_video)

    # Thumbnail.
    print("\nGenerating thumbnail...")
    thumbnail = make_thumbnail(client, package)

    # Shorts.
    print("\nGenerating Shorts...")
    short_paths = []
    for i, short_spec in enumerate(package.get("shorts", [])[:3], start=1):
        short_paths.append(make_short(client, short_spec, i))

    # Local manifest.
    manifest = {
        "channel": channel,
        "title": package["title"],
        "video": str(main_video),
        "thumbnail": str(thumbnail),
        "shorts": [str(x) for x in short_paths],
        "quality_gate": gate,
    }
    write_json(WORK / "production_manifest.json", manifest)

    print("\nPRODUCTION COMPLETE")
    print("Main video:", main_video)
    print("Thumbnail:", thumbnail)
    print("Shorts:", short_paths)

    # Final approval.
    if not confirm("\nFINAL APPROVAL: upload the main video to YouTube?"):
        print("Everything is saved locally. Nothing uploaded.")
        return

    mode = ask(
        "Publish mode: public, private, or schedule",
        "private",
    ).lower()

    publish_at = None

    if mode == "schedule":
        publish_at = ask(
            "Schedule time in ISO-8601 UTC, e.g. 2026-08-25T12:00:00Z"
        )
        # YouTube requires publishAt with privacyStatus=private.
        body_mode = "private"
    elif mode in ("public", "private", "unlisted"):
        body_mode = mode
    else:
        body_mode = "private"

    # The current uploader handles immediate public/private. For scheduling,
    # upload privately first and then update the status in a second API call.
    if mode == "schedule":
        video_id = upload(
            youtube,
            main_video,
            package,
            thumbnail,
            "private",
        )

        youtube.videos().update(
            part="status",
            body={
                "id": video_id,
                "status": {
                    "privacyStatus": "private",
                    "publishAt": publish_at,
                    "selfDeclaredMadeForKids": False,
                },
            },
        ).execute()
    else:
        video_id = upload(
            youtube,
            main_video,
            package,
            thumbnail,
            body_mode,
        )

    url = f"https://www.youtube.com/watch?v={video_id}"

    result = {
        "video_id": video_id,
        "url": url,
        "title": package["title"],
        "mode": mode,
        "scheduled_at": publish_at,
        "date": date.today().isoformat(),
    }

    write_json(WORK / f"published_{video_id}.json", result)

    print("\n" + "="*80)
    print("PUBLISHED / SCHEDULED")
    print("="*80)
    print(url)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
    except Exception as exc:
        print("\nERROR:", exc)
        sys.exit(1)
