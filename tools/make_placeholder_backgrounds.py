"""Генерирует запасные фоны (тёмная сцена с боке), если своих фото ещё нет.
   python3 tools/make_placeholder_backgrounds.py"""
from PIL import Image, ImageDraw, ImageFilter
import random, pathlib
W, H = 1080, 1920
OUT = pathlib.Path(__file__).resolve().parent.parent / "backgrounds"
OUT.mkdir(exist_ok=True)

def make(name, base, glow, seed, n=80):
    random.seed(seed)
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(base[i] * (1 - 0.45 * k)) for i in range(3)))
    layer = Image.new("RGB", (W, H), (0, 0, 0)); dl = ImageDraw.Draw(layer)
    for _ in range(n):
        r = random.randint(10, 52); x = random.randint(0, W); y = random.randint(0, int(H * .8))
        dl.ellipse([x - r, y - r, x + r, y + r],
                   fill=tuple(min(255, int(glow[i] * random.uniform(.5, 1.3))) for i in range(3)))
    layer = layer.filter(ImageFilter.GaussianBlur(30))
    img = Image.blend(img, layer, 0.5).filter(ImageFilter.GaussianBlur(2))
    v = Image.new("L", (W, H), 40)
    ImageDraw.Draw(v).ellipse([-W * .5, -H * .3, W * 1.5, H * 1.3], fill=255)
    img = Image.composite(img, Image.new("RGB", (W, H), (0, 0, 0)), v.filter(ImageFilter.GaussianBlur(200)))
    img.save(OUT / f"{name}.jpg", quality=90)
    print("→", OUT / f"{name}.jpg")

make("stage_blue", (48, 58, 92), (90, 130, 230), 1)
make("stage_warm", (70, 52, 40), (230, 165, 90), 7)
make("stage_dark", (42, 42, 50), (140, 145, 170), 13)
