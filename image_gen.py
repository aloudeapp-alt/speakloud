#!/usr/bin/env python3
"""
Генерация фонового изображения по теме ролика через OpenAI Images API.
Картинка потом уходит фоном в брендовую обложку (cover_thumbnail).

Ключ берётся из переменной окружения OPENAI_API_KEY (или из файла .env рядом).
Если ключа нет или запрос упал — возвращаем None, и обложка строится на боке-фоне.
"""
import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API_URL = "https://api.openai.com/v1/images/generations"


def _load_env():
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def build_prompt(scene, cfg):
    """scene — короткое описание сцены по теме (от Claude или шаблонное).
    Оборачиваем в единый фирменный стиль + требования к композиции под текст."""
    ic = cfg.get("image", {})
    style = ic.get("style", "cinematic photograph, dramatic soft lighting, shallow depth of field, "
                            "dark moody background, professional, high detail, photorealistic")
    composition = ic.get("composition",
                         "vertical 9:16 composition, subject placed in the lower half, "
                         "upper third dark and uncluttered to leave room for a title, "
                         "no text, no words, no letters, no watermark, no logo")
    return f"{scene}. {style}. {composition}."


def generate_image(scene, cfg, out_path):
    """Генерит фон и сохраняет PNG. Возвращает путь или None при любой ошибке."""
    _load_env()
    ic = cfg.get("image", {})
    if not ic.get("enabled"):
        return None
    key = (os.environ.get("OPENAI_API_KEY") or "").strip().strip('"').strip("'")
    if not key:
        print("[image] нет OPENAI_API_KEY — фон будет боке")
        return None

    prompt = build_prompt(scene, cfg)
    # печатаем полный запрос в лог и кладём рядом с картинкой — чтобы можно было посмотреть/поправить
    print(f"[image] GPT-запрос: {prompt}")
    try:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(str(Path(out_path).with_suffix("")) + ".prompt.txt").write_text(prompt, encoding="utf-8")
    except Exception:
        pass
    body = json.dumps({
        "model": ic.get("model", "gpt-image-1"),
        "prompt": prompt,
        "size": ic.get("size", "1024x1536"),
        "quality": ic.get("quality", "medium"),
        "n": 1,
    }).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"[image] OpenAI HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        return None
    except Exception as e:
        print(f"[image] ошибка запроса: {e}")
        return None

    try:
        item = data["data"][0]
        if item.get("b64_json"):
            raw = base64.b64decode(item["b64_json"])
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(raw)
        elif item.get("url"):
            with urllib.request.urlopen(item["url"], timeout=120) as im:
                Path(out_path).write_bytes(im.read())
        else:
            print(f"[image] неожиданный ответ: {str(data)[:200]}")
            return None
    except Exception as e:
        print(f"[image] не удалось сохранить картинку: {e}")
        return None
    return str(out_path)


if __name__ == "__main__":
    import sys
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg.setdefault("image", {})["enabled"] = True
    scene = sys.argv[1] if len(sys.argv) > 1 else \
        "a young man looking anxious before speaking, blurred conference room behind him"
    print(generate_image(scene, cfg, "out/test_bg.png"))
