"""TRPG予告ポスターメーカー trpgposter

立ち絵・タイトル・キャッチコピー・次回予告の一文から、
1200x630 の「次回予告」風ポスター PNG を合成するツール。
日本語フォントは実行時に公開 URL から取得して /tmp にキャッシュする。
単一ファイル Flask（DB なし）。
"""
import io
import os
import urllib.request

from PIL import Image, ImageDraw, ImageFont
from flask import Flask, jsonify, render_template_string, request, send_file

app = Flask(__name__)

POSTER_W, POSTER_H = 1200, 630
FONT_URL = "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf"
FONT_CACHE = os.path.join("/tmp", "trpgposter_font.otf")

THEMES = {
    "黒": ((17, 17, 17), (255, 255, 255), (200, 200, 200)),
    "赤": ((122, 13, 13), (255, 255, 255), (255, 210, 210)),
    "青": ((13, 42, 122), (255, 255, 255), (200, 220, 255)),
    "金": ((40, 32, 4), (255, 215, 0), (255, 240, 190)),
}


class FontUnavailable(Exception):
    pass


def fetch_font_file():
    """フォントファイルを /tmp に用意する（なければダウンロード）。"""
    if os.path.exists(FONT_CACHE) and os.path.getsize(FONT_CACHE) > 100000:
        return FONT_CACHE
    try:
        req = urllib.request.Request(FONT_URL, headers={"User-Agent": "trpgposter"})
        with urllib.request.urlopen(req, timeout=30) as res:
            data = res.read()
    except Exception as e:
        raise FontUnavailable(str(e))
    if len(data) < 100000:
        raise FontUnavailable("downloaded font looks too small")
    with open(FONT_CACHE, "wb") as fh:
        fh.write(data)
    return FONT_CACHE


def get_font(size):
    """テストから差し替え可能にするため関数に切り出している。"""
    path = fetch_font_file()
    return ImageFont.truetype(path, size)


def wrap_text(draw, text, font, max_width):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def build_poster(title, catch, line, theme, tachie_img):
    bg, title_color, sub_color = THEMES.get(theme, THEMES["黒"])
    img = Image.new("RGB", (POSTER_W, POSTER_H), bg)
    draw = ImageDraw.Draw(img)

    text_area_w = POSTER_W - 80
    if tachie_img is not None:
        tachie = tachie_img.convert("RGBA")
        scale = POSTER_H / tachie.height
        tachie = tachie.resize((int(tachie.width * scale), POSTER_H))
        x = POSTER_W - tachie.width
        img.paste(tachie, (x, 0), tachie)
        draw = ImageDraw.Draw(img)
        text_area_w = max(x - 40, 400)

    title_font = get_font(72)
    catch_font = get_font(44)
    line_font = get_font(36)

    y = 70
    for ln in wrap_text(draw, title, title_font, text_area_w)[:3]:
        draw.text((40, y), ln, font=title_font, fill=title_color)
        y += 88
    y += 20
    for ln in wrap_text(draw, catch, catch_font, text_area_w)[:3]:
        draw.text((40, y), ln, font=catch_font, fill=sub_color)
        y += 58

    band_y = POSTER_H - 110
    draw.rectangle([0, band_y, POSTER_W, POSTER_H], fill=(0, 0, 0))
    for i, ln in enumerate(wrap_text(draw, line, line_font, POSTER_W - 80)[:2]):
        draw.text((40, band_y + 18 + i * 44), ln, font=line_font, fill=(255, 255, 255))
    return img


PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TRPG予告ポスターメーカー</title>
<style>body{font-family:sans-serif;max-width:640px;margin:2em auto;padding:0 1em}
input[type=text]{width:100%}.err{color:#b00}</style>
</head><body>
<h1>TRPG予告ポスターメーカー</h1>
<p>TRPG セッションの「次回予告」風ポスター画像（1200x630）を作ります。</p>
{% if error %}<p class="err">{{ error }}</p>{% endif %}
<form method="post" action="{{ url_for('poster') }}" enctype="multipart/form-data">
  <label>タイトル <input type="text" name="title" required placeholder="例：闇に消えた村"></label><br>
  <label>キャッチコピー <input type="text" name="catch" placeholder="例：その扉を開けてはならない"></label><br>
  <label>次回予告の一文 <input type="text" name="line" placeholder="例：次回、探索者たちは地下室で何を見るのか"></label><br>
  <label>テーマ色
    <select name="theme">{% for t in themes %}<option>{{ t }}</option>{% endfor %}</select></label><br>
  <label>立ち絵画像（任意、PNG/JPEG/WebP）<input type="file" name="tachie" accept=".png,.jpg,.jpeg,.webp"></label><br>
  <button type="submit">ポスターを作る</button>
</form>
</body></html>"""


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return render_template_string(PAGE, themes=list(THEMES.keys()), error=None)


@app.route("/poster", methods=["POST"])
def poster():
    title = (request.form.get("title") or "").strip()
    if not title:
        return render_template_string(PAGE, themes=list(THEMES.keys()), error="タイトルを入力してください。"), 400
    catch = (request.form.get("catch") or "").strip()
    line = (request.form.get("line") or "").strip()
    theme = request.form.get("theme", "黒")
    if theme not in THEMES:
        theme = "黒"
    tachie = None
    f = request.files.get("tachie")
    if f is not None and f.filename:
        try:
            tachie = Image.open(io.BytesIO(f.read()))
            tachie.load()
        except Exception:
            return render_template_string(PAGE, themes=list(THEMES.keys()), error="立ち絵画像を読み込めませんでした。"), 400
    try:
        img = build_poster(title, catch, line, theme, tachie)
    except FontUnavailable:
        return (
            render_template_string(
                PAGE, themes=list(THEMES.keys()),
                error="日本語フォントの取得に失敗しました。ネットワーク環境を確認して、もう一度お試しください。",
            ),
            500,
        )
    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return send_file(out, mimetype="image/png", download_name="poster.png", as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
