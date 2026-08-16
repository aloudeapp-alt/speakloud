# SpeakLoud — конвейер роликов-суфлёров для практики английского

Дважды в день: генерирует монолог, собирает вертикальное видео с отсчётом 3-2-1 и текстом,
ползущим снизу вверх, делает обложку, пишет заголовок/описание/теги и выкладывает на YouTube и TikTok.

## Быстрый старт

```bash
pip install pillow fonttools --break-system-packages     # рендер
pip install google-api-python-client google-auth-oauthlib # только если нужен YouTube

python3 tools/preview.py            # 3 кадра, чтобы примерить шрифт и скорость
python3 run.py --slot morning       # собрать ролик, никуда не выкладывая
python3 run.py --slot evening --upload
```

Нужен установленный `ffmpeg` (`brew install ffmpeg` / `winget install ffmpeg` / `apt install ffmpeg`).

## Свои фоны

Кидай `.jpg`, `.png`, `.mp4` в папку `backgrounds/` — вертикальные 1080×1920 или любые,
они обрезаются по центру. Три заготовки уже лежат там; удали их, когда появятся свои.

В `config.json` → `background`:

| Настройка | Что делает |
|---|---|
| `mode: "random"` | случайный фон на каждый ролик |
| `mode: "rotate"` | по кругу, очередь помнится в `state.json` |
| `mode: "fixed"` + `file: "stage_blue.jpg"` | всегда один фон |
| `darken: 0.28` | затемнение под текст, 0–1 |
| `blur: 0` | размытие фона в пикселях |

Разовый фон мимо конфига: `--background backgrounds/stage_warm.jpg`

## Настройки текста и прокрутки

Всё в `config.json`, код трогать не нужно. Любое значение переопределяется на лету:
`--set text.font_size=78 scroll.seconds_per_line=1.2`

| Параметр | По умолчанию | Что делает |
|---|---|---|
| `text.font` | `Poppins-Bold` | шрифт из `fonts/` или системный. В референсе — он же |
| `text.font_fallback` | `Lato-Bold` | автоподмена там, где в основном шрифте нет кириллицы |
| `text.font_size` | `66` | размер шрифта |
| `text.line_spacing` | `1.75` | воздух между строками, в долях размера |
| `text.max_words_per_line` | `4` | сколько слов помещается в строку |
| `text.side_margin` | `90` | поля слева/справа |
| `text.align` | `center` | `center` / `left` / `right` |
| `text.color`, `shadow`, `outline_width` | белый, тень вкл | цвет, тень, обводка |
| `text.uppercase` | `false` | весь текст капсом |
| `scroll.seconds_per_line` | `1.6` | **темп чтения** — главный регулятор скорости. Меньше = быстрее |
| `scroll.pixels_per_second` | `72` | альтернатива: скорость в пикселях (`scroll.mode: "pixels_per_second"`) |
| `scroll.tail_seconds` | `1.5` | пауза после последней строки |
| `countdown.tip_text` | ГОВОРИ ГРОМКО И ЧЁТКО | подсказка над цифрой |
| `countdown.digits` | `[3,2,1]` | сам отсчёт |
| `outro.line1/line2` | Now say it again… | финальный кадр с призывом |
| `progress_bar.enabled` | `true` | верхний бар: подпись + таймер + полоса с бегунком |
| `progress_bar.label` | `YOUR PROGRESS` | подпись слева над полосой |
| `progress_bar.margin_top` | `70` | отступ бара от верха кадра |
| `progress_bar.knob_radius` | `14` | радиус круглого бегунка (0 = без него) |
| `progress_bar.color` | `#FFD34D` | цвет заполнения и бегунка |
| `top_fade.enabled` | `true` | плавное затухание текста сверху под баром |
| `top_fade.follow_progress_bar` | `true` | высота затухания сама следует за `margin_top` бара |
| `top_fade.feather` | `90` | высота мягкого перехода в пикселях |
| `top_fade.strength` | `0.95` | плотность (1 = текст исчезает полностью) |
| `audio.music_volume` | `0.12` | громкость фоновой музыки из `music/` |
| `audio.intro_folder` | `music_intro` | папка с треком на время отсчёта 3-2-1 |
| `audio.intro_volume` | `0.5` | громкость интро-музыки (обычно громче фона) |

Свой шрифт: положи `.ttf` в `fonts/` и укажи имя файла без расширения в `text.font`.

## Что генерируется

`generate.py` берёт тему из `topics.json` (утро — бытовые темы, вечер — рабочие; очередь не
повторяется), просит Claude написать монолог под уровень из `config.json` → `content.level`
и сразу вернуть заголовок, хук, теги и русскую подпись темы.

Ключ кладётся в файл `.env` рядом:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Без ключа конвейер не падает — берёт заготовку из `fallback_scripts.json`.

## Публикация

**YouTube.** Инструкция по OAuth — в шапке `upload_youtube.py`. Ролики короче 3 минут и
вертикальные, поэтому уходят в Shorts; `#Shorts` добавляется в заголовок автоматически.
Квота API — 10 000 единиц в день, одна загрузка ≈ 1600, то есть до 6 роликов в сутки.

**TikTok.** Content Posting API. Важный нюанс: **прямая публикация доступна только после аудита
приложения в TikTok** — проверка идёт неделями. До аудита работает режим `inbox`: ролик с готовым
описанием прилетает в черновики аккаунта, публикация — один тап в приложении. Режим переключается
в `.env`: `TIKTOK_MODE=inbox` или `direct`.

## Автозапуск

**Рекомендуемый способ — GitHub Actions:** пошаговая инструкция в [GITHUB.md](GITHUB.md).
Свой компьютер держать включённым не нужно, расписание задаётся в `config.json` → `publish.slots`
и в `.github/workflows/publish.yml`.

Слот описывается так:

```json
{"name": "morning", "cron": "0 6 * * *", "local": "09:00 МСК", "pool": "morning", "level": "B1-B2"}
```

`pool` — раздел из `topics.json`, `level` переопределяет уровень английского для этого слота.
Так утренний ролик может быть проще вечернего.

**Локально, macOS / Linux** (`crontab -e`):

```
0 9  * * * cd /путь/к/speakloud && /usr/bin/python3 run.py --slot morning --upload >> log.txt 2>&1
0 19 * * * cd /путь/к/speakloud && /usr/bin/python3 run.py --slot evening --upload >> log.txt 2>&1
```

**Windows** — Планировщик заданий, действие `python.exe C:\путь\speakloud\run.py --slot morning --upload`,
триггер ежедневно в 09:00 (и второе задание на 19:00).

## Брендинг

```bash
python3 tools/make_brand.py
```

Кладёт в `brand/`: аватарку 800×800 и 200×200, баннер YouTube 2560×1440 (текст в безопасной зоне),
обложку профиля TikTok. Название, цвет акцента и хендл берутся из `config.json` → `brand`.

## Структура

```
GITHUB.md            развёртывание на GitHub Actions
BRANDING.md          идеи названия и визуального стиля
config.json          все настройки
topics.json          банк тем (утро/вечер)
fallback_scripts.json заготовки на случай недоступности API
render.py            сборка видео
generate.py          монолог + метаданные через Claude
metadata.py          заголовки, описания, теги, обложка
run.py               весь конвейер одной командой
upload_youtube.py    загрузка на YouTube
upload_tiktok.py     загрузка в TikTok
tools/preview.py     быстрая примерка настроек
tools/make_brand.py  аватарка, баннер, обложка профиля
backgrounds/         твои фоны
fonts/               твои шрифты
music/               фоновая музыка (опционально)
music_intro/         музыка на отсчёт 3-2-1 (опционально)
out/                 готовые ролики: video.mp4, thumbnail.jpg, script.txt, metadata.json
```

## Права на контент

Фоны и музыка должны быть твои или с лицензией, разрешающей коммерческое использование.
Заготовки в `backgrounds/` сгенерированы процедурно — их можно использовать свободно.
