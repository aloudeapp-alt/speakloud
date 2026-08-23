#!/usr/bin/env python3
"""
Загрузка ролика на YouTube (Data API v3) с заголовком, описанием, тегами и обложкой.

Разовая настройка:
  1. console.cloud.google.com → новый проект → включить "YouTube Data API v3"
  2. OAuth consent screen → External → добавить себя в Test users
  3. Credentials → OAuth client ID → Desktop app → скачать JSON → положить рядом как client_secret.json
  4. pip install google-api-python-client google-auth-oauthlib
  5. python3 upload_youtube.py out/<папка_ролика>   ← первый раз откроет браузер, дальше молча

Квота: одна загрузка ≈ 1600 единиц из дневных 10000, то есть до 6 роликов в день. Двух хватает.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN = ROOT / "youtube_token.json"
CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN_URI = "https://oauth2.googleapis.com/token"


def _env_credentials():
    """В GitHub Actions браузера нет — собираем доступ из секретов
    YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN."""
    cid = os.environ.get("YT_CLIENT_ID")
    csec = os.environ.get("YT_CLIENT_SECRET")
    rtok = os.environ.get("YT_REFRESH_TOKEN")
    if not (cid and csec and rtok):
        return None
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    creds = Credentials(None, refresh_token=rtok, token_uri=TOKEN_URI,
                        client_id=cid, client_secret=csec, scopes=SCOPES)
    creds.refresh(Request())
    return creds


def get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = _env_credentials()
    if creds:
        return build("youtube", "v3", credentials=creds)
    if TOKEN.is_file():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.is_file():
                raise RuntimeError("Нет client_secret.json и нет YT_* секретов — см. инструкцию")
            creds = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET), SCOPES).run_local_server(port=0)
        TOKEN.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload(outdir, cfg=None):
    from googleapiclient.http import MediaFileUpload

    outdir = Path(outdir)
    meta = json.loads((outdir / "metadata.json").read_text(encoding="utf-8"))
    yt = meta["publish"]["youtube"]
    video = outdir / "video.mp4"

    svc = get_service()
    body = {
        "snippet": {
            "title": yt["title"],
            "description": yt["description"],
            "tags": yt["tags"],
            "categoryId": yt["categoryId"],
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": yt["privacyStatus"],
            "selfDeclaredMadeForKids": yt["madeForKids"],
        },
    }
    media = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024,
                            resumable=True, mimetype="video/mp4")
    req = svc.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"  YouTube: {int(status.progress() * 100)}%")
    vid = response["id"]

    thumb = outdir / "thumbnail.jpg"
    if thumb.is_file():
        try:
            svc.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
        except Exception as e:
            print(f"  обложка не встала (нужен подтверждённый аккаунт): {e}")

    url = f"https://youtube.com/watch?v={vid}"
    print("  ✓", url)
    return {"video_id": vid, "url": url}


if __name__ == "__main__":
    print(json.dumps(upload(sys.argv[1]), ensure_ascii=False, indent=2))
