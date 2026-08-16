#!/usr/bin/env python3
"""
Рендер вертикального ролика-суфлёра: отсчёт 3-2-1 + текст, ползущий снизу вверх.

Использование:
    python3 render.py --script script.txt --topic "Fashion" --out out/video.mp4
    python3 render.py --script script.txt --topic "Fashion" --background backgrounds/stage.jpg
    python3 render.py --script script.txt --topic "Fashion" --set text.font_size=72 scroll.seconds_per_line=1.2

Любой параметр из config.json переопределяется через --set путь=значение.
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
FONT_DIRS = [
    ROOT / "fonts",
    Path("/usr/share/fonts"),
    Path.home() / ".fonts",
    Path("C:/Windows/Fonts"),
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path.home() / "Library/Fonts",
]
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}


# ---------------------------------------------------------------- утилиты

def load_config(path=None):
    cfg_path = Path(path) if path else ROOT / "config.json"
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)


def apply_overrides(cfg, overrides):
    """--set text.font_size=72 -> cfg['text']['font_size'] = 72"""
    for item in overrides or []:
        key, _, raw = item.partition("=")
        node = cfg
        parts = key.strip().split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            val = raw
        node[parts[-1]] = val
    return cfg


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def find_font(name):
    """Ищет шрифт по имени файла в fonts/ и системных папках."""
    p = Path(name)
    if p.is_file():
        return str(p)
    for d in FONT_DIRS:
        if not d.is_dir():
            continue
        for ext in (".ttf", ".otf", ".TTF", ".OTF", ""):
            cand = d / f"{name}{ext}"
            if cand.is_file():
                return str(cand)
        # рекурсивный поиск без учёта регистра
        for f in d.rglob("*"):
            if f.suffix.lower() in (".ttf", ".otf") and f.stem.lower() == name.lower():
                return str(f)
    raise SystemExit(
        f"Шрифт '{name}' не найден. Положи .ttf в папку fonts/ и укажи имя файла в config.json → text.font"
    )


_cmap_cache = {}


def _has_glyphs(font_path, text):
    """Есть ли в шрифте все символы строки (важно для кириллицы:
    Poppins и большинство латинских Google-шрифтов её не содержат)."""
    if font_path not in _cmap_cache:
        try:
            from fontTools.ttLib import TTFont
            _cmap_cache[font_path] = set(TTFont(font_path, fontNumber=0).getBestCmap())
        except Exception:
            _cmap_cache[font_path] = None
    cmap = _cmap_cache[font_path]
    if cmap is None:  # fontTools не установлен — грубая эвристика
        return all(ord(ch) < 0x0400 for ch in text)
    return all(ord(ch) in cmap or ch.isspace() for ch in text)


def font_for(text, size, cfg_text):
    """Основной шрифт, а если в нём нет нужных символов — запасной."""
    main = find_font(cfg_text["font"])
    if text and not _has_glyphs(main, text):
        fb = cfg_text.get("font_fallback")
        if fb:
            return ImageFont.truetype(find_font(fb), size)
    return ImageFont.truetype(main, size)


# ------------------------------------------------- разбивка текста на строки

def split_into_lines(text, font, max_width, max_words):
    """Режет монолог на короткие фразы: по предложениям, потом по запятым,
    потом по числу слов и по ширине кадра."""
    text = " ".join(text.split())
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    for s in sentences:
        if not s.strip():
            continue
        for part in re.split(r"(?<=,)\s+", s):
            part = part.strip()
            if part:
                chunks.append(part)

    lines = []
    for chunk in chunks:
        words = chunk.split()
        cur = []
        for w in words:
            trial = cur + [w]
            too_many = len(trial) > max_words
            too_wide = font.getbbox(" ".join(trial))[2] > max_width
            if cur and (too_many or too_wide):
                lines.append(" ".join(cur))
                cur = [w]
            else:
                cur = trial
        if cur:
            lines.append(" ".join(cur))
    return lines


def draw_text_with_effects(base, xy, text, font, cfg_text):
    """Рисует строку с тенью/обводкой на RGBA-слое."""
    x, y = xy
    color = hex_rgb(cfg_text["color"])
    if cfg_text.get("shadow"):
        off = int(cfg_text.get("shadow_offset", 4))
        blur = int(cfg_text.get("shadow_blur", 8))
        op = float(cfg_text.get("shadow_opacity", 0.75))
        sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((x + off, y + off), text, font=font,
                                fill=(0, 0, 0, int(255 * op)))
        if blur:
            sh = sh.filter(ImageFilter.GaussianBlur(blur))
        base.alpha_composite(sh)
    d = ImageDraw.Draw(base)
    ow = int(cfg_text.get("outline_width", 0))
    if ow:
        d.text((x, y), text, font=font, fill=color + (255,),
               stroke_width=ow, stroke_fill=hex_rgb(cfg_text["outline_color"]) + (255,))
    else:
        d.text((x, y), text, font=font, fill=color + (255,))


def build_text_strip(lines, cfg, tmp):
    """Одна высокая прозрачная PNG со всем текстом монолога."""
    t = cfg["text"]
    W = cfg["video"]["width"]
    font = font_for("".join(lines), t["font_size"], t)
    line_h = int(t["font_size"] * t["line_spacing"])
    pad = line_h  # воздух сверху и снизу полосы
    height = pad * 2 + line_h * len(lines)

    strip = Image.new("RGBA", (W, height), (0, 0, 0, 0))
    margin = t["side_margin"]
    for i, line in enumerate(lines):
        txt = line.upper() if t.get("uppercase") else line
        bbox = font.getbbox(txt)
        w = bbox[2] - bbox[0]
        if t["align"] == "left":
            x = margin
        elif t["align"] == "right":
            x = W - margin - w
        else:
            x = (W - w) // 2
        y = pad + i * line_h
        draw_text_with_effects(strip, (x - bbox[0], y), txt, font, t)

    path = tmp / "strip.png"
    strip.save(path)
    return path, line_h, height


def build_countdown_frames(digits, topic, cfg, tmp):
    """Кадры отсчёта: подсказка сверху, крупная цифра, тема снизу."""
    c = cfg["countdown"]
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    t = cfg["text"]
    tip_text = (c.get("tip_text") or "").upper()
    topic_text = (topic or "").upper()
    f_digit = font_for("0123456789", c["digit_size"], t)
    f_tip = font_for(tip_text, c["tip_size"], t)
    f_topic = font_for(topic_text, c["topic_label_size"], t)
    paths = []
    for d in digits:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if c.get("extra_darken"):
            img.alpha_composite(Image.new("RGBA", (W, H),
                                          (0, 0, 0, int(255 * c["extra_darken"]))))
        tip = tip_text
        if tip:
            bb = f_tip.getbbox(tip)
            draw_text_with_effects(img, ((W - (bb[2] - bb[0])) // 2 - bb[0],
                                         int(H * c["tip_y"])), tip, f_tip, t)
        ds = str(d)
        bb = f_digit.getbbox(ds)
        dy = int(H * c["tip_y"]) + c["tip_size"] + 60
        draw_text_with_effects(img, ((W - (bb[2] - bb[0])) // 2 - bb[0], dy - bb[1]),
                               ds, f_digit, t)
        if topic_text:
            tl = topic_text
            bb2 = f_topic.getbbox(tl)
            topic_style = dict(t)
            topic_style["color"] = c["topic_label_color"]
            draw_text_with_effects(img, ((W - (bb2[2] - bb2[0])) // 2 - bb2[0],
                                         dy + c["digit_size"] + 20),
                                   tl, f_topic, topic_style)
        p = tmp / f"cd_{d}.png"
        img.save(p)
        paths.append(p)
    return paths


def build_outro(cfg, tmp):
    o = cfg["outro"]
    if not o.get("enabled"):
        return None
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    t = cfg["text"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 110)))
    f = font_for(o.get("line1", "") + o.get("line2", ""), int(t["font_size"] * 1.05), t)
    for i, line in enumerate([o.get("line1", ""), o.get("line2", "")]):
        if not line:
            continue
        bb = f.getbbox(line)
        y = H // 2 - 80 + i * int(t["font_size"] * 1.6)
        draw_text_with_effects(img, ((W - (bb[2] - bb[0])) // 2 - bb[0], y), line, f, t)
    if o.get("handle_footer"):
        h = cfg["brand"]["handle"]
        fh = font_for(h, 44, t)
        bb = fh.getbbox(h)
        style = dict(t)
        style["color"] = cfg["brand"]["accent_color"]
        draw_text_with_effects(img, ((W - (bb[2] - bb[0])) // 2 - bb[0], H - 320), h, fh, style)
    p = tmp / "outro.png"
    img.save(p)
    return p


# ---------------------------------------------------------------- фон

def pick_background(cfg, explicit=None):
    b = cfg["background"]
    if explicit:
        return Path(explicit)
    folder = ROOT / b["folder"]
    folder.mkdir(exist_ok=True)
    files = sorted(p for p in folder.iterdir()
                   if p.suffix.lower() in IMAGE_EXT | VIDEO_EXT)
    if not files:
        return None
    mode = b.get("mode", "random")
    if mode == "fixed" and b.get("file"):
        return folder / b["file"]
    if mode == "rotate":
        state_p = ROOT / "state.json"
        state = json.loads(state_p.read_text()) if state_p.is_file() else {}
        idx = state.get("bg_index", 0) % len(files)
        state["bg_index"] = idx + 1
        state_p.write_text(json.dumps(state, indent=2))
        return files[idx]
    return random.choice(files)


def make_fallback_background(cfg, tmp):
    """Тёмный градиент, если папка backgrounds пустая."""
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    top, bot = (24, 26, 34), (8, 8, 12)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)],
               fill=tuple(int(top[i] + (bot[i] - top[i]) * k) for i in range(3)))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([-200, -400, W + 200, 700], fill=(40, 52, 88))
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    img = Image.blend(img, glow, 0.35)
    p = tmp / "bg_fallback.png"
    img.save(p)
    return p


AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".ogg"}


def pick_music(cfg):
    folder = ROOT / cfg["audio"]["music_folder"]
    if not folder.is_dir():
        return None
    tracks = [p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT]
    return random.choice(tracks) if tracks else None


def pick_intro_music(cfg):
    """Трек, который играет во время отсчёта 3-2-1.
    Берётся из папки audio.intro_folder (по умолчанию music_intro)."""
    a = cfg["audio"]
    if a.get("intro_file"):
        p = ROOT / a["intro_file"]
        return p if p.is_file() else None
    folder = ROOT / a.get("intro_folder", "music_intro")
    if not folder.is_dir():
        return None
    tracks = [p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT]
    return random.choice(tracks) if tracks else None


def make_knob(radius, color_hex, tmp):
    """Круглый бегунок прогресс-бара."""
    r = int(radius)
    pad = 4
    d = 2 * r + 2 * pad
    img = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.ellipse([pad, pad, pad + 2 * r, pad + 2 * r], fill=hex_rgb(color_hex) + (255,))
    p = tmp / "knob.png"
    img.save(p)
    return p, pad


def add_progress_bar(filters, inputs, idx, last, cfg, tmp, cd_dur, scroll_dur, W, H):
    """Верхний прогресс-бар: подпись слева, таймер MM:SS/MM:SS справа,
    полоса с круглым бегунком. Прогресс идёт по времени чтения (после отсчёта)."""
    pb = cfg["progress_bar"]
    mx = int(pb.get("side_margin", 60))
    mt = int(pb.get("margin_top", 70))
    ls = int(pb.get("label_size", 30))
    th = int(pb.get("height", 8))
    gap = int(pb.get("gap", 24))
    r = int(pb.get("knob_radius", 14))
    accent = pb.get("color", "#FFD34D")
    track = pb.get("track_color", "#FFFFFF")
    track_a = float(pb.get("track_opacity", 0.25))
    fontfile = find_font(cfg["text"]["font"])

    x0, x1 = mx, W - mx
    bar_w = x1 - x0
    bar_y = mt + ls + gap
    knob_cy = bar_y + th / 2

    TOT = max(0.1, scroll_dur)
    CD = cd_dur
    # секунд прочитано: 0 во время отсчёта, дальше растёт до TOT
    E = f"min(max(t-{CD:.3f},0),{TOT:.3f})"
    prog = f"({E})/{TOT:.3f}"

    fill_col = "0x" + accent.lstrip("#")
    track_col = "0x" + track.lstrip("#")

    # подпись + таймер
    label = pb.get("label", "YOUR PROGRESS")
    tot_str = f"{int(TOT) // 60:02d}\\:{int(TOT) % 60:02d}"
    mm = f"floor(({E})/60)"
    ss = f"mod(floor({E}),60)"
    timer_txt = f"%{{eif\\:{mm}\\:d\\:2}}\\:%{{eif\\:{ss}\\:d\\:2}} / {tot_str}"

    chain = (
        f"[{last}]"
        f"drawtext=fontfile='{fontfile}':text='{label}':fontcolor={accent}:"
        f"fontsize={ls}:x={x0}:y={mt},"
        f"drawtext=fontfile='{fontfile}':text='{timer_txt}':fontcolor=white:"
        f"fontsize={ls}:x={x1}-tw:y={mt},"
        f"drawbox=x={x0}:y={bar_y}:w={bar_w}:h={th}:color={track_col}@{track_a}:t=fill,"
        f"drawbox=x={x0}:y={bar_y}:w='{bar_w}*{prog}':h={th}:color={fill_col}:t=fill"
        f"[v_pbbox]"
    )
    filters.append(chain)

    knob_path, pad = make_knob(r, accent, tmp)
    inputs += ["-i", str(knob_path)]
    knob_idx = idx
    idx += 1
    kx = f"{x0}-{pad}-{r}+{bar_w}*{prog}"
    ky = int(knob_cy - r - pad)
    filters.append(f"[v_pbbox][{knob_idx}:v]overlay=x='{kx}':y={ky}[v_pb]")
    return "v_pb", idx


# ---------------------------------------------------------------- рендер

def render(script_text, topic, out_path, cfg, background=None):
    tmp = Path(tempfile.mkdtemp(prefix="speakloud_"))
    try:
        W, H = cfg["video"]["width"], cfg["video"]["height"]
        t = cfg["text"]
        font = ImageFont.truetype(find_font(t["font"]), t["font_size"])
        max_w = W - 2 * t["side_margin"]
        lines = split_into_lines(script_text, font, max_w, t["max_words_per_line"])
        strip_path, line_h, strip_h = build_text_strip(lines, cfg, tmp)

        # скорость
        s = cfg["scroll"]
        if s.get("mode") == "pixels_per_second":
            speed = float(s["pixels_per_second"])
        else:
            speed = line_h / float(s["seconds_per_line"])

        scroll_dur = (H + strip_h) / speed + float(s.get("tail_seconds", 1.0))
        outro_dur = cfg["outro"]["seconds"] if cfg["outro"].get("enabled") else 0
        total = scroll_dur + outro_dur

        # длительность отсчёта — нужна и прогресс-бару, и музыке
        cd = cfg["countdown"]
        cd_dur = (len(cd["digits"]) * float(cd["seconds_per_digit"])) if cd.get("enabled") else 0.0

        bg = background or pick_background(cfg)
        bg_is_video = bg is not None and Path(bg).suffix.lower() in VIDEO_EXT
        if bg is None:
            bg = make_fallback_background(cfg, tmp)

        inputs, filters, idx = [], [], 0
        if bg_is_video:
            inputs += ["-stream_loop", "-1", "-i", str(bg)]
        else:
            inputs += ["-loop", "1", "-i", str(bg)]
        bg_idx = idx
        idx += 1

        b = cfg["background"]
        chain = (f"[{bg_idx}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                 f"crop={W}:{H},setsar=1")
        if b.get("blur"):
            chain += f",gblur=sigma={b['blur']}"
        if b.get("darken"):
            chain += f",eq=brightness=-{float(b['darken']):.3f}"
        chain += f",fps={cfg['video']['fps']}[bg]"
        filters.append(chain)

        inputs += ["-i", str(strip_path)]
        strip_idx = idx
        idx += 1
        start_y = H - float(s.get("start_offset_lines", 0)) * line_h
        filters.append(
            f"[bg][{strip_idx}:v]overlay=x=(W-w)/2:y='{start_y}-{speed:.4f}*t'"
            f":enable='lt(t,{scroll_dur:.3f})'[v_scroll]")
        last = "v_scroll"

        if cfg["countdown"].get("enabled"):
            cds = build_countdown_frames(cfg["countdown"]["digits"], topic, cfg, tmp)
            per = float(cfg["countdown"]["seconds_per_digit"])
            for i, p in enumerate(cds):
                inputs += ["-i", str(p)]
                a, bnd = i * per, (i + 1) * per
                filters.append(f"[{last}][{idx}:v]overlay=0:0:"
                               f"enable='between(t,{a:.3f},{bnd:.3f})'[cd{i}]")
                last = f"cd{i}"
                idx += 1

        outro_p = build_outro(cfg, tmp)
        if outro_p:
            inputs += ["-i", str(outro_p)]
            filters.append(f"[{last}][{idx}:v]overlay=0:0:"
                           f"enable='gte(t,{scroll_dur:.3f})'[vout]")
            last = "vout"
            idx += 1

        # ---- прогресс-бар сверху (рисуется поверх всего) ----
        pb = cfg.get("progress_bar", {})
        if pb.get("enabled"):
            last, idx = add_progress_bar(filters, inputs, idx, last, cfg, tmp,
                                         cd_dur, scroll_dur, W, H)

        # ---- звук: музыка отсчёта → фоновая ----
        fo = cfg["audio"]["fade_out_seconds"]
        intro = pick_intro_music(cfg)
        music = pick_music(cfg)
        amap = []
        aparts = []
        intro_idx = bg_a_idx = None
        if intro and cd_dur > 0:
            inputs += ["-i", str(intro)]
            intro_idx = idx
            idx += 1
        if music:
            inputs += ["-stream_loop", "-1", "-i", str(music)]
            bg_a_idx = idx
            idx += 1

        if intro_idx is not None:
            iv = float(cfg["audio"].get("intro_volume", 0.5))
            aparts.append(f"[{intro_idx}:a]atrim=0:{cd_dur:.3f},asetpts=PTS-STARTPTS,"
                          f"volume={iv},afade=t=out:st={max(0, cd_dur - 0.4):.2f}:d=0.4[aintro]")
        if bg_a_idx is not None:
            vol = cfg["audio"]["music_volume"]
            delay = int(cd_dur * 1000) if intro_idx is not None else 0
            seg = f"[{bg_a_idx}:a]volume={vol},atrim=0:{max(0.1, total - cd_dur if intro_idx is not None else total):.3f},asetpts=PTS-STARTPTS"
            if delay:
                seg += f",adelay={delay}|{delay}"
            seg += "[abg]"
            aparts.append(seg)

        src = None
        if intro_idx is not None and bg_a_idx is not None:
            aparts.append("[aintro][abg]amix=inputs=2:normalize=0:dropout_transition=0[amixed]")
            src = "[amixed]"
        elif intro_idx is not None:
            src = "[aintro]"
        elif bg_a_idx is not None:
            src = "[abg]"

        if src:
            aparts.append(f"{src}afade=t=out:st={max(0, total - fo):.2f}:d={fo}[aout]")
            filters += aparts
            amap = ["-map", "[aout]", "-c:a", "aac", "-b:a", "128k"]
            idx += 1

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = (["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + inputs +
               ["-filter_complex", ";".join(filters),
                "-map", f"[{last}]"] + amap +
               ["-t", f"{total:.3f}", "-r", str(cfg["video"]["fps"]),
                "-c:v", "libx264", "-preset", "medium",
                "-crf", str(cfg["video"]["quality_crf"]),
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)])
        subprocess.run(cmd, check=True)

        return {
            "video": str(out_path),
            "duration_sec": round(total, 2),
            "lines": len(lines),
            "words": len(script_text.split()),
            "background": str(bg),
            "scroll_px_per_sec": round(speed, 2),
            "seconds_per_line": round(line_h / speed, 2),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True, help="txt-файл с монологом или сам текст")
    ap.add_argument("--topic", default="", help="тема, показывается под цифрой отсчёта")
    ap.add_argument("--out", default="out/video.mp4")
    ap.add_argument("--background", default=None, help="конкретный файл фона")
    ap.add_argument("--config", default=None)
    ap.add_argument("--set", nargs="*", dest="overrides",
                    help="переопределить настройки: --set text.font_size=72")
    a = ap.parse_args()

    cfg = apply_overrides(load_config(a.config), a.overrides)
    text = Path(a.script).read_text(encoding="utf-8") if Path(a.script).is_file() else a.script
    info = render(text, a.topic, a.out, cfg, a.background)
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
