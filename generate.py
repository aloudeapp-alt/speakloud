#!/usr/bin/env python3
"""
Генерация монолога + метаданных для площадок через Claude API.

    python3 generate.py --slot morning
    python3 generate.py --topic "Public speaking fear" --slot evening

Нужен ключ в переменной окружения ANTHROPIC_API_KEY (или в файле .env рядом).
Если ключа нет — берётся заготовка из fallback_scripts.json, чтобы конвейер не падал.
"""
import argparse
import json
import os
import random
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state.json"
API_URL = "https://api.anthropic.com/v1/messages"

PROMPT = """You write short monologues for an English public-speaking practice channel.
Viewers read the text aloud from a teleprompter that scrolls upward, so the text must sound
natural when spoken out loud, not written.

Topic: {topic}
CEFR level: {level}
Target length: about {words} words.

Rules:
- Open the way a speaker opens a talk to a room ("Good afternoon, everyone." style), then develop
  one clear idea, then land on a closing thought. No lists, no headings, no emoji, no stage directions.
- Short sentences. Most of them under 12 words. This matters: each sentence becomes 2-4 lines on screen.
- Simple, high-frequency vocabulary for the level. No idioms a learner would stumble on.
- Vary the opening from these recently used ones so the channel does not feel repetitive: {recent}
- Include a couple of natural pauses using commas and full stops, so the speaker can breathe.

Also write the publishing metadata. The title must work as a hook in a feed, mention the topic, and
stay under 70 characters. Tags: 15 lowercase keywords, no '#'.

Return ONLY one line of minified valid JSON, no markdown fence, no text before or after.
Inside string values use no real line breaks — keep each value as one continuous string.
{{"script": "...", "title": "...", "hook": "one short line, max 8 words", "summary": "one sentence about the topic in English", "tags": ["..."], "topic_label_ru": "тема одним-двумя словами по-русски, ЗАГЛАВНЫМИ"}}"""


def load_env():
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def read_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {}


def write_state(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def slot_def(cfg, slot):
    """Описание слота из config.publish.slots; если слот не описан — разумные умолчания."""
    for s in cfg["publish"]["slots"]:
        if s["name"] == slot:
            return s
    return {"name": slot, "pool": slot, "level": cfg["content"]["level"]}


def pick_topic(cfg, slot, explicit=None):
    topics = json.loads((ROOT / cfg["content"]["topics_file"]).read_text(encoding="utf-8"))
    pool_name = slot_def(cfg, slot).get("pool", slot)
    pool = topics.get(pool_name) or topics.get("morning")
    if explicit:
        for t in pool:
            if t["en"].lower() == explicit.lower():
                return t
        return {"en": explicit, "ru": explicit.upper()}
    st = read_state()
    key = f"topic_index_{slot}"
    i = st.get(key, 0) % len(pool)
    st[key] = i + 1
    write_state(st)
    return pool[i]


def call_claude(prompt, model, max_tokens=2000):
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().strip('"').strip("'")
    if not key:
        raise RuntimeError("нет ANTHROPIC_API_KEY")
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "content-type": "application/json",
        "accept": "application/json",
        "accept-encoding": "identity",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"HTTP {e.code} от Anthropic: {detail}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"ответ API не JSON: {raw[:200]!r}")
    if data.get("type") == "error":
        raise RuntimeError(f"API вернул ошибку: {data.get('error')}")
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if not text.strip():
        raise RuntimeError(f"пустой ответ модели: {str(data)[:200]}")
    return text


def parse_json_loose(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    candidate = m.group(0) if m else text
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # частая беда: живые переводы строк внутри строковых значений — экранируем и пробуем снова
        fixed = re.sub(r'(?<!\\)\n', r'\\n', candidate)
        return json.loads(fixed)


def fallback(topic, cfg):
    p = ROOT / "fallback_scripts.json"
    raw = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    bank = {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict)}
    if not bank:
        raise SystemExit("Нет ни API-ключа, ни заготовок в fallback_scripts.json")
    key = topic["en"] if topic["en"] in bank else random.choice(list(bank))
    item = dict(bank[key])
    # тема берётся из самой заготовки, иначе подпись и заголовок разъедутся с текстом
    item["topic_en"] = key
    fallback_label = topic.get("label") or topic.get("ru") or topic["en"]
    item.setdefault("topic_label_ru", str(fallback_label).upper())
    return item


def generate(cfg, slot, explicit_topic=None):
    load_env()
    topic = pick_topic(cfg, slot, explicit_topic)
    level = slot_def(cfg, slot).get("level", cfg["content"]["level"])
    st = read_state()
    recent = st.get("recent_openings", [])[-6:]
    prompt = PROMPT.format(
        topic=topic["en"],
        level=level,
        words=cfg["content"]["words_target"],
        recent="; ".join(recent) or "none yet",
    )
    source = "fallback"
    data = None
    try:
        raw = call_claude(prompt, cfg["content"]["model"])
    except Exception as e:
        print(f"[generate] Claude недоступен ({e}); беру заготовку")
    else:
        try:
            data = parse_json_loose(raw)
            source = "claude"
        except Exception as e:
            # видно сырой ответ модели — по нему понятно, что пошло не так
            print(f"[generate] не разобрал ответ модели ({e}); беру заготовку")
            print(f"[generate] сырой ответ (первые 300 симв.): {raw[:300]!r}")
    if data is None:
        data = fallback(topic, cfg)

    data.setdefault("topic_en", topic["en"])
    # Подпись под отсчётом. Язык выбирается один раз в config → content.topic_label_source:
    #   "en" — английское название (поле en), одинаково для всех тем;
    #   "ru"/"label" — то, что вписано в topics.json (поле label, иначе ru).
    # Значение из ответа Claude игнорируем, чтобы на экране было предсказуемо.
    label_src = cfg["content"].get("topic_label_source", "en")
    if source == "fallback":
        base_en = data.get("topic_en", topic["en"])
        base_field = data.get("topic_label_ru") or base_en
    else:
        base_en = topic["en"]
        base_field = topic.get("label") or topic.get("ru") or topic["en"]
    label = base_en if label_src == "en" else base_field
    data["topic_label"] = str(label).upper()
    data["topic_label_ru"] = data["topic_label"]  # обратная совместимость
    data["slot"] = slot
    data["level"] = level
    data["generated_at"] = datetime.now().isoformat(timespec="seconds")
    data["source"] = source

    opening = " ".join(data["script"].split()[:6])
    st["recent_openings"] = (st.get("recent_openings", []) + [opening])[
        -cfg["content"]["avoid_repeat_last"]:]
    write_state(st)
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="morning")
    ap.add_argument("--topic", default=None)
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    cfg = json.loads(Path(a.config or ROOT / "config.json").read_text(encoding="utf-8"))
    print(json.dumps(generate(cfg, a.slot, a.topic), ensure_ascii=False, indent=2))
