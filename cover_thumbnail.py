#!/usr/bin/env python3
"""
Брендовая обложка в стиле референса: шапка с логотипом, крупный заголовок
с жёлтыми акцентами, стрелка, плашка #Shorts, фото по теме снизу.

Вёрстка полностью автоматическая. Фотореалистичную картинку по теме
кладёт вызывающий код (из ИИ-генератора или из папки subjects/).

Заголовок принимает разметку: слова в *звёздочках* красятся акцентным цветом.
Пример: "Why reading books can *change your life*"
"""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# палитры боке-фона; выбираются по теме, чтобы обложки различались
_BOKEH_PALETTES = [
    ((22, 28, 46), (70, 120, 230)),   # синий
    ((40, 26, 20), (230, 150, 70)),   # тёплый
    ((20, 34, 28), (60, 200, 130)),   # мятный
    ((34, 20, 34), (200, 90, 190)),   # пурпур
    ((30, 30, 34), (150, 150, 170)),  # графит
]


def make_bokeh(W, H, seed=0):
    """Размытый цветной фон (боке) — если нет фото по теме."""
    import random
    rnd = random.Random(seed)
    base, glow = _BOKEH_PALETTES[seed % len(_BOKEH_PALETTES)]
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(base[i] * (1 - 0.5 * k)) for i in range(3)))
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    dl = ImageDraw.Draw(layer)
    for _ in range(90):
        r = rnd.randint(20, 90)
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        c = tuple(min(255, int(glow[i] * rnd.uniform(.5, 1.3))) for i in range(3))
        dl.ellipse([x - r, y - r, x + r, y + r], fill=c)
    layer = layer.filter(ImageFilter.GaussianBlur(55))
    return Image.blend(img, layer, 0.5).filter(ImageFilter.GaussianBlur(6))


def _font(name, size):
    import render
    return ImageFont.truetype(render.find_font(name), size)


def _sound_mark(d, cx, cy, r, color):
    """Мини-логотип: точка-капсюль и дуги звука."""
    d.ellipse([cx - r * .16, cy - r * .16, cx + r * .16, cy + r * .16], fill=color)
    for i in (1, 2, 3):
        rr = r * (0.16 + 0.24 * i)
        w = max(2, int(r * .09))
        d.arc([cx - rr, cy - rr, cx + rr, cy + rr], -55, 55, fill=color, width=w)
        d.arc([cx - rr, cy - rr, cx + rr, cy + rr], 125, 235, fill=color, width=w)


def _draw_header(canvas, cfg, y=70):
    """SPEAK STAGE ENGLISH со значком-микрофоном, среднее слово — акцентом."""
    W = canvas.width
    accent = _rgb(cfg["brand"]["accent_color"])
    white = (255, 255, 255)
    words = cfg["brand"]["channel_name"].upper().split()
    d = ImageDraw.Draw(canvas)
    _sound_mark(d, W // 2, y + 18, 40, accent + (255,))

    f = _font(cfg["text"]["font"], 46)
    # среднее слово — жёлтым, остальные белые
    hi = 1 if len(words) >= 3 else -1
    total = sum(f.getbbox(w + " ")[2] for w in words)
    x = (W - total) // 2
    ty = y + 74
    for i, w in enumerate(words):
        col = accent if i == hi else white
        d.text((x, ty), w, font=f, fill=col + (255,))
        x += f.getbbox(w + " ")[2]
    # тонкая подпись-разрядка под словом-логотипом (как в референсе — "ENGLISH")
    return ty + 60


def _wrap(draw, tokens, font, max_w):
    """tokens: [(word, is_accent)]. Возвращает строки из токенов по ширине."""
    lines, cur, cw = [], [], 0
    space = font.getbbox(" ")[2]
    for word, acc in tokens:
        ww = font.getbbox(word)[2]
        if cur and cw + space + ww > max_w:
            lines.append(cur)
            cur, cw = [], 0
        cur.append((word, acc, ww))
        cw += (space if len(cur) > 1 else 0) + ww
    if cur:
        lines.append(cur)
    return lines


def _parse_title(title):
    """'*a b* c' -> [('a',True),('b',True),('c',False)]"""
    out = []
    for chunk, acc in re.findall(r"\*([^*]+)\*|([^*]+)", title):
        seg = chunk or acc
        is_acc = bool(chunk)
        for w in seg.split():
            out.append((w, is_acc))
    return out


def _draw_arrow(canvas, x, y, color, scale=1.0):
    """Жёлтая рисованная стрелка-дуга вниз-вправо, как в референсе."""
    d = ImageDraw.Draw(canvas)
    w = max(6, int(10 * scale))
    pts = [(x, y), (x + 60 * scale, y + 10 * scale),
           (x + 95 * scale, y + 45 * scale), (x + 105 * scale, y + 100 * scale)]
    # сглаженная кривая по точкам
    for i in range(len(pts) - 1):
        d.line([pts[i], pts[i + 1]], fill=color + (255,), width=w, joint="curve")
    # наконечник
    ex, ey = pts[-1]
    d.line([(ex, ey), (ex - 22 * scale, ey - 26 * scale)], fill=color + (255,), width=w)
    d.line([(ex, ey), (ex + 24 * scale, ey - 20 * scale)], fill=color + (255,), width=w)


def make_cover(title, subject_path, cfg, out_path, highlight=None):
    """title — с *звёздочками* для акцента, либо highlight=строка/список слов."""
    import render
    W, H = 1080, 1920
    accent = _rgb(cfg["brand"]["accent_color"])
    tfont = cfg["text"]["font"]

    # фон — фото по теме (cover-crop) либо цветной боке-фон
    if subject_path and Path(subject_path).is_file():
        img = Image.open(subject_path).convert("RGB")
        r = max(W / img.width, H / img.height)
        img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
        x0, y0 = (img.width - W) // 2, (img.height - H) // 2
        img = img.crop((x0, y0, x0 + W, y0 + H))
    else:
        seed = abs(hash(re.sub(r"\*", "", title))) % 1000
        img = make_bokeh(W, H, seed)
    canvas = img.convert("RGBA")

    # затемняющий градиент: сильнее сверху (под заголовок) и снизу (под плашку)
    col = Image.new("L", (1, H), 0)
    px = col.load()
    for y in range(H):
        top_a = 235 * max(0, 1 - y / (H * 0.52))
        bot_a = 210 * max(0, 1 - (H - y) / (H * 0.22))
        px[0, y] = int(min(245, max(70, top_a) + bot_a))
    grad = Image.new("RGBA", (W, H), (5, 6, 10, 255))
    grad.putalpha(col.resize((W, H)))
    canvas.alpha_composite(grad)

    # шапка
    title_top = _draw_header(canvas, cfg, y=70)

    # заголовок с акцентами
    if highlight:
        hl = highlight if isinstance(highlight, (list, set)) else str(highlight).split()
        hl = {w.lower().strip(".,!?") for w in hl}
        tokens = [(w, w.lower().strip(".,!?") in hl) for w in re.sub(r"\*", "", title).split()]
    else:
        tokens = _parse_title(title)

    words_upper = [(w.upper(), a) for w, a in tokens]
    max_w = W - 130
    size = 108
    while size > 52:
        f = _font(tfont, size)
        lines = _wrap(ImageDraw.Draw(canvas), words_upper, f, max_w)
        if len(lines) <= 4:
            break
        size -= 4
    line_h = int(size * 1.12)
    y = title_top + 40
    d = ImageDraw.Draw(canvas)
    for line in lines:
        lw = sum(t[2] for t in line) + f.getbbox(" ")[2] * (len(line) - 1)
        x = (W - lw) // 2
        for word, acc, ww in line:
            col_ = accent if acc else (255, 255, 255)
            # лёгкая тень для читаемости
            d.text((x + 3, y + 3), word, font=f, fill=(0, 0, 0, 180))
            d.text((x, y), word, font=f, fill=col_ + (255,))
            x += ww + f.getbbox(" ")[2]
        y += line_h

    # стрелка справа под заголовком
    _draw_arrow(canvas, W - 250, y + 6, accent, scale=1.3)

    # плашка #Shorts снизу
    pill = "#Shorts"
    fp = _font(tfont, 40)
    bb = fp.getbbox(pill)
    pw, ph = bb[2] - bb[0] + 70, 74
    pxx, pyy = (W - pw) // 2, H - 150
    d.rounded_rectangle([pxx, pyy, pxx + pw, pyy + ph], radius=ph // 2,
                        fill=accent + (255,))
    d.text((pxx + 35 - bb[0], pyy + (ph - (bb[3] - bb[1])) // 2 - bb[1]), pill,
           font=fp, fill=(10, 10, 12, 255))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, quality=92)
    return str(out_path)


if __name__ == "__main__":
    import json
    import sys
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    title = sys.argv[1] if len(sys.argv) > 1 else "Why reading books can *change your life*"
    subj = sys.argv[2] if len(sys.argv) > 2 else None
    print(make_cover(title, subj, cfg, "out/cover_demo.jpg"))
