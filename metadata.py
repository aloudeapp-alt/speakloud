#!/usr/bin/env python3
"""Заголовки, описания, теги и обложка для YouTube и TikTok."""
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent

BASE_TAGS = [
    "english speaking practice", "public speaking", "learn english", "speak english fluently",
    "english monologue", "esl", "english pronunciation", "shadowing english",
    "english teleprompter", "daily english practice",
]

YT_DESC = """{hook}

Read this monologue out loud, following the text on screen. Speak clearly, keep your pace steady,
and finish every sentence — that is the whole exercise.

TOPIC: {topic}
LEVEL: {level}
HOW TO PRACTISE
1. Wait for the 3-2-1 countdown.
2. Read aloud, out loud — not in your head.
3. Watch again and record yourself.
4. Third time: say it in your own words, without reading.

New monologues every day. Subscribe and practise with us — {handle}

{hashtags}"""

TT_CAPTION = """{hook} 🎤 Read it out loud with the countdown.

{hashtags}"""


def slugify(s, n=60):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:n]


def build(data, cfg):
    """data — результат generate.generate()"""
    topic = data["topic_en"]
    level = data.get("level") or cfg["content"]["level"]
    tags = list(dict.fromkeys([t.lower().lstrip("#") for t in data.get("tags", [])] + BASE_TAGS))[:25]
    hashtags_yt = " ".join("#" + re.sub(r"\W+", "", t.title()) for t in tags[:6]) + " #Shorts"
    hashtags_tt = " ".join("#" + re.sub(r"\W+", "", t) for t in tags[:10]) + " #learnenglish #fyp"

    title = data.get("title") or f"{topic}: 1-minute English speaking practice"
    if len(title) > 95:
        title = title[:92] + "..."
    if "#shorts" not in title.lower():
        title = f"{title} #Shorts"

    desc = YT_DESC.format(
        hook=data.get("hook", "Practise speaking English out loud."),
        topic=topic, level=level,
        handle=cfg["brand"]["handle"],
        hashtags=hashtags_yt,
    )
    return {
        "youtube": {
            "title": title,
            "description": desc,
            "tags": tags,
            "categoryId": cfg["publish"]["youtube"]["category_id"],
            "privacyStatus": cfg["publish"]["youtube"]["privacy"],
            "madeForKids": cfg["publish"]["youtube"]["made_for_kids"],
        },
        "tiktok": {
            "caption": TT_CAPTION.format(
                hook=data.get("hook", "Speak English out loud"), hashtags=hashtags_tt)[:2150],
            "privacy": cfg["publish"]["tiktok"]["privacy"],
        },
        "slug": f"{data['generated_at'][:10]}-{data['slot']}-{slugify(topic)}",
    }


def make_thumbnail(data, cfg, bg_path, out_path):
    """Обложка 1280x720 для YouTube в фирменном стиле канала."""
    import render  # переиспользуем поиск шрифтов и тени
    W, H = 1280, 720
    if bg_path and Path(bg_path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        img = Image.open(bg_path).convert("RGB")
        r = max(W / img.width, H / img.height)
        img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
        img = img.crop(((img.width - W) // 2, (img.height - H) // 2,
                        (img.width - W) // 2 + W, (img.height - H) // 2 + H))
        img = img.filter(ImageFilter.GaussianBlur(3))
    else:
        img = Image.new("RGB", (W, H), (20, 22, 32))
    img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.45)
    canvas = img.convert("RGBA")

    t = dict(cfg["text"])
    topic = data["topic_en"].upper()
    f_big = render.font_for(topic, 92, t)
    while f_big.getbbox(topic)[2] > W - 140 and f_big.size > 44:
        f_big = render.font_for(topic, f_big.size - 4, t)
    bb = f_big.getbbox(topic)
    render.draw_text_with_effects(canvas, ((W - (bb[2] - bb[0])) // 2 - bb[0], 250), topic, f_big, t)

    top = "SPEAK IT OUT LOUD"
    f_top = render.font_for(top, 44, t)
    st = dict(t); st["color"] = cfg["brand"]["accent_color"]
    bbt = f_top.getbbox(top)
    render.draw_text_with_effects(canvas, ((W - (bbt[2] - bbt[0])) // 2 - bbt[0], 160), top, f_top, st)

    foot = f"{data.get('level') or cfg['content']['level']}  •  {cfg['brand']['handle']}"
    f_f = render.font_for(foot, 38, t)
    bbf = f_f.getbbox(foot)
    render.draw_text_with_effects(canvas, ((W - (bbf[2] - bbf[0])) // 2 - bbf[0], 430), foot, f_f, t)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, quality=92)
    return str(out_path)


if __name__ == "__main__":
    import sys
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(build(data, cfg), ensure_ascii=False, indent=2))
