#!/usr/bin/env python3
"""
Один прогон конвейера: тема → монолог → видео → обложка → метаданные → (загрузка).

    python3 run.py --slot morning                 # собрать ролик, не публиковать
    python3 run.py --slot evening --upload        # собрать и выложить
    python3 run.py --slot morning --topic "Money" --set text.font_size=72

Результат складывается в out/<дата>-<слот>-<тема>/
"""
import argparse
import json
import shutil
from pathlib import Path

import generate
import metadata
import render

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="morning",
                    help="имя слота из config.publish.slots")
    ap.add_argument("--topic", default=None)
    ap.add_argument("--background", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--upload", action="store_true", help="выложить на YouTube и TikTok")
    ap.add_argument("--set", nargs="*", dest="overrides")
    a = ap.parse_args()

    cfg = render.apply_overrides(render.load_config(a.config), a.overrides)

    data = generate.generate(cfg, a.slot, a.topic)
    meta = metadata.build(data, cfg)

    outdir = ROOT / "out" / meta["slug"]
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "script.txt").write_text(data["script"], encoding="utf-8")

    info = render.render(data["script"], data["topic_label_ru"],
                         outdir / "video.mp4", cfg, a.background)
    thumb = metadata.make_thumbnail(data, cfg, info["background"], outdir / "thumbnail.jpg")

    bundle = {"generated": data, "render": info, "publish": meta, "thumbnail": thumb}
    (outdir / "metadata.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✓ {outdir}")
    print(f"  видео: {info['duration_sec']} с, {info['lines']} строк, темп {info['seconds_per_line']} с/строка")
    print(f"  заголовок: {meta['youtube']['title']}")

    if a.upload:
        results = {}
        if cfg["publish"]["youtube"]["enabled"]:
            try:
                import upload_youtube
                results["youtube"] = upload_youtube.upload(outdir, cfg)
            except Exception as e:
                results["youtube"] = f"ошибка: {e}"
        if cfg["publish"]["tiktok"]["enabled"]:
            try:
                import upload_tiktok
                results["tiktok"] = upload_tiktok.upload(outdir, cfg)
            except Exception as e:
                results["tiktok"] = f"ошибка: {e}"
        bundle["upload"] = results
        (outdir / "metadata.json").write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        print("  загрузка:", json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
