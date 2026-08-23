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

Read it out loud with the countdown. Say every word, keep going, don't stop to fix mistakes —
that is how speaking gets easier.

TOPIC: {topic}
LEVEL: {level}
HOW TO PRACTISE
1. Wait for the 3-2-1 countdown.
2. Read aloud, out loud — not in your head.
3. Watch again and record yourself.
4. Say it once more in your own words.

Become confident speaking English. New video every day — {handle}

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


def _fit_wrap(text, max_w, max_size, min_size, t, render, max_lines=2):
    """Подбирает размер и переносит текст максимум на max_lines строк по ширине max_w."""
    words = text.split()
    best = None
    for size in range(max_size, min_size - 1, -4):
        f = render.font_for(text, size, t)
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if not cur or f.getbbox(trial)[2] <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) <= max_lines and all(f.getbbox(l)[2] <= max_w for l in lines):
            return f, lines
        best = (f, lines)
    return best  # не влезло идеально — вернём самый мелкий вариант


def make_thumbnail(data, cfg, bg_path, out_path):
    """Вертикальная обложка 1080x1920 под Shorts, в фирменном стиле канала."""
    import render  # переиспользуем поиск шрифтов и тени
    W, H = 1080, 1920
    accent = cfg["brand"]["accent_color"]

    # фон: тот же кадр, вписан по вертикали (без кривой обрезки в ленту)
    if bg_path and Path(bg_path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        img = Image.open(bg_path).convert("RGB")
        r = max(W / img.width, H / img.height)
        img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
        x0, y0 = (img.width - W) // 2, (img.height - H) // 2
        img = img.crop((x0, y0, x0 + W, y0 + H)).filter(ImageFilter.GaussianBlur(4))
    else:
        img = Image.new("RGB", (W, H), (16, 18, 26))
    canvas = img.convert("RGBA")

    # равномерный скрим + усиление сверху и снизу для читаемости текста
    canvas.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 120)))
    col = Image.new("L", (1, H), 0)
    px = col.load()
    for y in range(H):
        top_a = max(0, 150 * (1 - y / (H * 0.42)))
        bot_a = max(0, 170 * (1 - (H - y) / (H * 0.40)))
        px[0, y] = int(min(220, top_a + bot_a))
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    grad.putalpha(col.resize((W, H)))
    canvas.alpha_composite(grad)

    t = dict(cfg["text"])
    accent_style = dict(t); accent_style["color"] = accent

    def center(text, font, y, style=t):
        bb = font.getbbox(text)
        render.draw_text_with_effects(canvas, ((W - (bb[2] - bb[0])) // 2 - bb[0], y),
                                      text, font, style)

    # верхняя плашка-тэглайн
    tag = "SPEAK IT OUT LOUD"
    center(tag, render.font_for(tag, 56, t), 430, accent_style)

    # крупная тема, перенос до 2 строк
    topic = data["topic_en"].upper()
    f_title, lines = _fit_wrap(topic, W - 150, 150, 60, t, render, max_lines=2)
    line_h = int(f_title.size * 1.12)
    block_h = line_h * len(lines)
    y = H // 2 - block_h // 2 - 40
    for i, ln in enumerate(lines):
        center(ln, f_title, y + i * line_h)

    # акцентная черта под темой
    d = ImageDraw.Draw(canvas)
    ly = y + block_h + 34
    d.rounded_rectangle([(W - 140) // 2, ly, (W + 140) // 2, ly + 10], radius=5,
                        fill=render.hex_rgb(accent) + (255,))

    # футер: уровень • хендл
    foot = f"{data.get('level') or cfg['content']['level']}   •   {cfg['brand']['handle']}"
    center(foot, render.font_for(foot, 46, t), H - 250)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, quality=92)
    return str(out_path)


if __name__ == "__main__":
    import sys
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(build(data, cfg), ensure_ascii=False, indent=2))
