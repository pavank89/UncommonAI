#!/usr/bin/env python3
import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TOKEN = os.environ["YOUTUBE_TOKEN_JSON"]
WORK = Path.cwd() / "workspace"
MANIFEST = WORK / "shorts" / "shorts_manifest.json"
PACKAGE = WORK / "production_package.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    base_description = str(package.get("description", "")).strip()
    tags = [str(x) for x in package.get("tags", [])][:15]

    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    youtube = build("youtube", "v3", credentials=creds)

    for item in manifest:
        title = str(item["title"])[:100]
        description = (str(item.get("script", "")) + "\n\n" + base_description).strip()
        body = {
            "snippet": {
                "title": title,
                "description": description[:5000],
                "tags": tags,
                "categoryId": "28",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }
        file_path = Path(item["file"])
        media = MediaFileUpload(str(file_path), mimetype="video/mp4", resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            _, response = request.next_chunk()
        video_id = response["id"]
        print(f"SHORT {item['index']} UPLOADED PUBLIC")
        print(f"TITLE: {title}")
        print(f"YOUTUBE URL: https://www.youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    main()
