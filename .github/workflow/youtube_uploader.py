import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path.cwd()
WORK = ROOT / "workspace"
VIDEO = WORK / "uncommonAI_video.mp4"
PACKAGE = WORK / "production_package.json"
TOKEN = WORK / "youtube_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
]

def main():
    if not VIDEO.is_file():
        raise SystemExit(f"Missing video: {VIDEO}")

    token_json = os.environ.get("YOUTUBE_TOKEN_JSON", "").strip()
    if not token_json:
        raise SystemExit("YOUTUBE_TOKEN_JSON secret is missing.")

    TOKEN.write_text(token_json, encoding="utf-8")
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)

    if PACKAGE.exists():
        package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    else:
        package = {}

    title = package.get("chosen_title") or "uncommonAI"
    description = package.get("description") or "uncommonAI — practical AI explained clearly."
    tags = package.get("tags") or ["AI", "uncommonAI"]

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(VIDEO),
        mimetype="video/mp4",
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"UPLOAD PROGRESS: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"UPLOADED PRIVATE: {video_id}")

    updated = youtube.videos().update(
        part="status",
        body={
            "id": video_id,
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        },
    ).execute()

    print("VISIBILITY:", updated["status"]["privacyStatus"])
    print("YOUTUBE URL:", f"https://www.youtube.com/watch?v={video_id}")

if __name__ == "__main__":
    main()
