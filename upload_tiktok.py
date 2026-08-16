#!/usr/bin/env python3
"""
Загрузка ролика в TikTok через Content Posting API.

Два режима, выбирается автоматически:
  • direct  — ролик сразу публикуется. Доступен ТОЛЬКО после аудита приложения в TikTok
              (проверка занимает недели и требует показать TikTok свой UX).
  • inbox   — ролик уходит в черновики аккаунта, вы дожимаете публикацию в приложении
              одним тапом. Работает сразу, без аудита. Это режим по умолчанию.

Разовая настройка:
  1. developers.tiktok.com → создать приложение → продукт "Content Posting API"
  2. Права: video.upload (черновики) и video.publish (прямая публикация, после аудита)
  3. Пройти OAuth, положить в .env:
        TIKTOK_CLIENT_KEY=...
        TIKTOK_CLIENT_SECRET=...
        TIKTOK_REFRESH_TOKEN=...
  4. python3 upload_tiktok.py out/<папка_ролика>

Access token живёт 24 часа и обновляется здесь автоматически по refresh-токену.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://open.tiktokapis.com"


def _load_env():
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _post(url, payload, token=None, extra_headers=None):
    headers = {"Content-Type": "application/json; charset=UTF-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.update(extra_headers or {})
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def access_token():
    _load_env()
    need = ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        raise SystemExit("Нет переменных в .env: " + ", ".join(missing))
    body = urllib.parse.urlencode({
        "client_key": os.environ["TIKTOK_CLIENT_KEY"],
        "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
    }).encode()
    req = urllib.request.Request(f"{API}/v2/oauth/token/", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    if "access_token" not in data:
        raise SystemExit(f"TikTok OAuth не дал токен: {data}")
    return data["access_token"]


def _upload_file(upload_url, video_path):
    size = video_path.stat().st_size
    data = video_path.read_bytes()
    req = urllib.request.Request(upload_url, data=data, method="PUT", headers={
        "Content-Type": "video/mp4",
        "Content-Length": str(size),
        "Content-Range": f"bytes 0-{size - 1}/{size}",
    })
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.status


def upload(outdir, cfg=None, mode=None):
    outdir = Path(outdir)
    meta = json.loads((outdir / "metadata.json").read_text(encoding="utf-8"))
    tt = meta["publish"]["tiktok"]
    video = outdir / "video.mp4"
    size = video.stat().st_size

    mode = mode or os.environ.get("TIKTOK_MODE", "inbox")
    token = access_token()
    source_info = {"source": "FILE_UPLOAD", "video_size": size,
                   "chunk_size": size, "total_chunk_count": 1}

    if mode == "direct":
        # прямая публикация — только для приложений, прошедших аудит
        info = _post(f"{API}/v2/post/publish/creator_info/query/", {}, token)
        nickname = info.get("data", {}).get("creator_nickname")
        payload = {
            "post_info": {
                "title": tt["caption"],
                "privacy_level": tt["privacy"],
                "disable_duet": False, "disable_comment": False, "disable_stitch": False,
            },
            "source_info": source_info,
        }
        res = _post(f"{API}/v2/post/publish/video/init/", payload, token)
        print(f"  TikTok (direct, {nickname})")
    else:
        res = _post(f"{API}/v2/post/publish/inbox/video/init/",
                    {"source_info": source_info}, token)
        print("  TikTok (черновик — дожми публикацию в приложении)")

    data = res.get("data") or {}
    if not data.get("upload_url"):
        raise SystemExit(f"TikTok не вернул upload_url: {res}")
    _upload_file(data["upload_url"], video)

    status = _post(f"{API}/v2/post/publish/status/fetch/",
                   {"publish_id": data["publish_id"]}, token)
    return {"mode": mode, "publish_id": data["publish_id"],
            "status": status.get("data", {}).get("status"),
            "caption_ready": tt["caption"]}


if __name__ == "__main__":
    import urllib.parse  # noqa: F401
    print(json.dumps(upload(sys.argv[1]), ensure_ascii=False, indent=2))
