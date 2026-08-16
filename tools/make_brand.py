#!/usr/bin/env python3
"""
Брендинг канала: аватарка, баннер YouTube, обложка TikTok-профиля.
    python3 tools/make_brand.py
Кладёт результат в brand/. Цвета и название берутся из config.json → brand.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import render  # noqa: E402

cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BRAND, T = cfg["brand"], cfg["text"]
OUT = ROOT / "brand"
OUT.mkdir(exist_ok=True)
ACCENT = render.hex_rgb(BRAND["accent_color"])


def backdrop(W, H, dark=(16, 18, 26)):
    img = Image.new("RGB", (W, H), dark)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse([-W * .2, -H * .6, W * .8, H * .8], fill=(38, 52, 96))
    d.ellipse([W * .45, H * .2, W * 1.3, H * 1.6], fill=(70, 52, 20))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(int(W / 6))), 0.55)
    return img.convert("RGBA")


def sound_waves(draw, cx, cy, r, color, bars=None):
    """Иконка «голос»: микрофон-точка и дуги звука."""
    draw.ellipse([cx - r * .18, cy - r * .18, cx + r * .18, cy + r * .18], fill=color)
    for i in (1, 2, 3):
        rr = r * (0.18 + 0.26 * i)
        draw.arc([cx - rr, cy - rr, cx + rr, cy + rr], start=-55, end=55,
                 fill=color, width=max(3, int(r * .07)))
        draw.arc([cx - rr, cy - rr, cx + rr, cy + rr], start=125, end=235,
                 fill=color, width=max(3, int(r * .07)))


def avatar():
    S = 800
    img = backdrop(S, S)
    d = ImageDraw.Draw(img)
    sound_waves(d, S // 2, int(S * .40), int(S * .26), ACCENT + (255,))
    name = BRAND["channel_name"].split()[0].upper()
    f = render.font_for(name, 120, T)
    while f.getbbox(name)[2] > S - 90 and f.size > 50:
        f = render.font_for(name, f.size - 4, T)
    bb = f.getbbox(name)
    render.draw_text_with_effects(img, ((S - (bb[2] - bb[0])) // 2 - bb[0], int(S * .66)), name, f, T)
    img.convert("RGB").save(OUT / "avatar_800.png")
    img.resize((200, 200), Image.LANCZOS).convert("RGB").save(OUT / "avatar_200.png")
    print("→ brand/avatar_800.png, brand/avatar_200.png")


def banner():
    """2560x1440, безопасная зона по центру 1546x423 — видна на всех устройствах."""
    W, H = 2560, 1440
    img = backdrop(W, H)
    d = ImageDraw.Draw(img)
    sound_waves(d, W // 2 - 1010, H // 2, 130, ACCENT + (200,))
    sound_waves(d, W // 2 + 1010, H // 2, 130, ACCENT + (200,))
    title = BRAND["channel_name"].upper()
    f = render.font_for(title, 140, T)
    while f.getbbox(title)[2] > 1500 and f.size > 70:
        f = render.font_for(title, f.size - 4, T)
    bb = f.getbbox(title)
    render.draw_text_with_effects(img, ((W - (bb[2] - bb[0])) // 2 - bb[0], H // 2 - 150), title, f, T)
    sub = "Read it out loud. Twice a day."
    fs = render.font_for(sub, 66, T)
    st = dict(T); st["color"] = BRAND["accent_color"]
    bbs = fs.getbbox(sub)
    render.draw_text_with_effects(img, ((W - (bbs[2] - bbs[0])) // 2 - bbs[0], H // 2 + 40), sub, fs, st)
    times = " & ".join(s.get("local", s["name"]) for s in cfg["publish"]["slots"])
    foot = f"{cfg['content']['level']}  •  new monologue at {times}"
    ff = render.font_for(foot, 44, T)
    bbf = ff.getbbox(foot)
    render.draw_text_with_effects(img, ((W - (bbf[2] - bbf[0])) // 2 - bbf[0], H // 2 + 150), foot, ff, T)
    img.convert("RGB").save(OUT / "youtube_banner_2560x1440.png")
    print("→ brand/youtube_banner_2560x1440.png")


def tiktok_cover():
    W, H = 1080, 1920
    img = backdrop(W, H)
    d = ImageDraw.Draw(img)
    sound_waves(d, W // 2, int(H * .35), 240, ACCENT + (255,))
    for i, line in enumerate(["SPEAK", "OUT LOUD"]):
        f = render.font_for(line, 150, T)
        bb = f.getbbox(line)
        render.draw_text_with_effects(img, ((W - (bb[2] - bb[0])) // 2 - bb[0],
                                            int(H * .58) + i * 180), line, f, T)
    img.convert("RGB").save(OUT / "tiktok_cover_1080x1920.png")
    print("→ brand/tiktok_cover_1080x1920.png")


if __name__ == "__main__":
    avatar(); banner(); tiktok_cover()
