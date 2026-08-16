#!/usr/bin/env python3
"""
Быстрая примерка настроек: три кадра (отсчёт, прокрутка, финал) вместо полного рендера.

    python3 tools/preview.py
    python3 tools/preview.py --set text.font_size=78 text.line_spacing=1.5 scroll.seconds_per_line=1.2
    python3 tools/preview.py --background backgrounds/stage_warm.jpg --font Poppins-Bold

Кадры кладутся в out/preview/.
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import render  # noqa: E402

SAMPLE = ("Good afternoon, everyone. Today, I would like to talk about fashion. "
          "For some people, fashion is very important. For others, it is just something practical. "
          "I think fashion is more than clothes. It is a way to express your personality.")

ap = argparse.ArgumentParser()
ap.add_argument("--background", default=None)
ap.add_argument("--topic", default="МОДА")
ap.add_argument("--font", default=None)
ap.add_argument("--text", default=SAMPLE)
ap.add_argument("--set", nargs="*", dest="overrides")
a = ap.parse_args()

cfg = render.apply_overrides(render.load_config(), a.overrides)
if a.font:
    cfg["text"]["font"] = a.font

out = ROOT / "out" / "preview"
out.mkdir(parents=True, exist_ok=True)
tmp = out / "_tmp.mp4"
info = render.render(a.text, a.topic, tmp, cfg, a.background)

marks = {"1_countdown": 1.2,
         "2_scroll": min(info["duration_sec"] * 0.45, info["duration_sec"] - 4),
         "3_outro": max(0.1, info["duration_sec"] - 1.0)}
for name, t in marks.items():
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", f"{t:.2f}", "-i", str(tmp), "-frames:v", "1",
                    str(out / f"{name}.png")], check=True)
try:
    tmp.unlink(missing_ok=True)
except OSError:
    pass
print(f"→ {out}  ({info['lines']} строк, {info['duration_sec']} с, "
      f"темп {info['seconds_per_line']} с/строка, скорость {info['scroll_px_per_sec']} px/с)")
