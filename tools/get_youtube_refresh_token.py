#!/usr/bin/env python3
"""
Разовый скрипт: получить refresh-токен YouTube для GitHub Actions.
Запускается ОДИН раз на своей машине — в облаке браузер открыть негде.

    pip install google-auth-oauthlib
    python3 tools/get_youtube_refresh_token.py

Перед запуском положи рядом с проектом client_secret.json (OAuth client типа Desktop app).
Скрипт откроет браузер, попросит войти в аккаунт канала и напечатает три значения
для секретов репозитория: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.
"""
import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parent.parent
CS = ROOT / "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

if not CS.is_file():
    sys.exit(f"Положи client_secret.json сюда: {CS}")

flow = InstalledAppFlow.from_client_secrets_file(str(CS), SCOPES)
# access_type=offline + prompt=consent — иначе Google не отдаст refresh-токен повторно
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

if not creds.refresh_token:
    sys.exit("Google не вернул refresh_token. Отзови доступ на "
             "myaccount.google.com/permissions и запусти снова.")

data = json.loads(CS.read_text())
client = data.get("installed") or data.get("web")

# показать, к какому каналу привязался токен
try:
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=creds)
    ch = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = ch.get("items", [])
    if items:
        s = items[0]["snippet"]
        st = items[0].get("statistics", {})
        print("\n" + "-" * 64)
        print(f"Токен управляет каналом: {s['title']}")
        print(f"  ID: {items[0]['id']}   подписчиков: {st.get('subscriberCount', '?')}")
        print("  Это НЕ тот канал? Отзови доступ на myaccount.google.com/permissions")
        print("  и запусти скрипт снова — Google даст выбрать канал.")
    else:
        print("\n[!] У этого аккаунта пока НЕТ YouTube-канала.")
        print("    Создай канал на youtube.com, иначе загрузка выдаст ошибку.")
except Exception as e:
    print(f"\n[i] Не удалось проверить канал ({e}). Это не мешает токену работать.")

print("\n" + "=" * 64)
print("Секреты для GitHub → Settings → Secrets and variables → Actions")
print("=" * 64)
print(f"YT_CLIENT_ID       = {client['client_id']}")
print(f"YT_CLIENT_SECRET   = {client['client_secret']}")
print(f"YT_REFRESH_TOKEN   = {creds.refresh_token}")
print("=" * 64)
print("\nВажно: если OAuth-приложение осталось в режиме Testing, refresh-токен")
print("протухнет через 7 дней. Переведи приложение в Production (Publish app)\n"
      "на экране OAuth consent screen — тогда токен живёт бессрочно.")
