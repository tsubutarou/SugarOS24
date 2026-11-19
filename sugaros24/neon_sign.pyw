# -*- coding: utf-8 -*-
"""
ドットネオン街 ver.1.5（NEON.EXE）  —  SugarOS 24 の「眺める」担当
香港の夜みたいな看板を、デスクトップに浮かべる。看板1枚が小さなウィンドウ1つ。

看板の種類:
  ネオン管     … 文字をネオン管で描いて、ぼんやり光らせる
                 管のかたち（ふちだけ / ぬりつぶし / 二重）、ふち（丸 / 二重 / 流れる点線）、
                 マーク（ハート・星・矢印・カップ・カクテル・月）、動き（ずっと / 順番に点く / 点滅）、ちらつき
  LED          … 丸い LED が並んだ電光看板。入りきらない文字は流れる（1色 / 虹色 / 点滅）
  ライトアップ … 絵を描いた板。ランプで照らす / 内側から光る（行灯）。まわりの電球が順番に光る
  どれも 横長 / 縦長（縦書き）を選べる。

おまかせで並べる:
  右クリック →「おまかせで並べる」で、看板 5〜6 枚を、種類・言葉・色・形・場所をばらばらにして並べなおす。
  「もとに戻す」で、ひとつ前の並びに戻せる。設定で「開くたびにおまかせで並べる」もできる。

背景「ポップアップ広告風」（透けない）:
  一昔前のポップアップ広告みたいなウィンドウ（タイトルバー・派手な模様・点滅する NEW! と「今すぐクリック！」）の中で、
  看板が光る。ほかのウィンドウと重なっても変に見えない。× ボタンでその看板を閉じる（「もとに戻す」で戻せる）。

背景「ごちゃまぜポータル」（透けない）:
  90年代のごちゃごちゃしたメニュー画面みたいに、看板のまわりに小さなロゴやボタンがぎっしり並ぶ。
  ロゴは1つずつ、書体・色・ふちどり・立体の影・虹色・傾きがばらばら。いくつかは点滅する。
  右クリック →「ポータルをおまかせで組みなおす」で、並びが変わる。

画像の広告（透けない）:
  neon_ads フォルダに入れた絵を、そのままポップアップ広告のウィンドウとして出す。
  ときどきピカッと光ったり、画面がザザッと乱れたりする。右上の × のあたりをクリックすると閉じる。
  絵は neon_ads に PNG などを入れるだけで増やせる（右クリック →「画像のフォルダを開く」）。

※ ver.1.5 から「壁紙になじませる（透けて見える風）」は、いったんお休み中。
  ほかのウィンドウと重なると変に見えるので、メニューとおまかせから外してある。
  前に置いていた透ける看板は、開いたときに「まっくら」の背景になる。
  もとに戻したいときは、プログラムの SHOW_WALL = False を True にする。

半透明っぽく見せるしくみ（お休み中）:
  Windows の壁紙と同じ画像を読み込んで、看板の「後ろにあるはずの壁紙の部分」をウィンドウに描く。
  その上に光を重ねるので、光が壁紙ににじんで、ウィンドウが透けているように見える。
  （デスクトップのアイコンやほかのウィンドウは透けない。壁紙を変えると、数秒で追いかける）

操作:
  ドラッグ       … 看板を動かす
  ダブルクリック … 文字を変える（画像の広告では、次の絵にかえる）
  右クリック     … メニュー（看板を増やす / おまかせで並べる / 文字 / 種類 / 向き / 色 / 書体 / 大きさ / 背景 など）

設定は neon_sign_config.json に自動で保存される。
必要なもの: pip install pillow
"""
import ctypes
import math
import os
import random
import time
import tkinter as tk
from tkinter import filedialog

# Windows の画面拡大率（125% など）で、壁紙と看板の位置がずれないようにする。Tk を作る前に呼ぶ
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageTk

from mushiboshi_ui import (PixelMenu, ask_text, is_night_time, load_json, load_now_playing, log_errors, mix, px_text,
                           px_text_w, save_json)

APP_VERSION = "1.5"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "neon_sign_config.json")

P = 2            # 1ドット = 2px
GLOW = 12        # 光がにじむぶんの、看板のまわりの余白（ドット）

NEON = {   # 光の色
    "pink": ("ピンク", (255, 70, 170)), "red": ("赤", (255, 46, 56)), "orange": ("オレンジ", (255, 140, 36)),
    "amber": ("こはく", (255, 176, 50)), "yellow": ("きいろ", (255, 226, 70)), "green": ("みどり", (70, 255, 120)),
    "cyan": ("水色", (60, 226, 255)), "blue": ("青", (70, 110, 255)), "purple": ("むらさき", (190, 90, 255)),
    "white": ("白", (240, 240, 255)),
}
PANEL = {  # ライトアップの板の色
    "cream": ("クリーム", (246, 234, 204)), "red": ("赤", (190, 34, 40)), "yellow": ("きいろ", (248, 202, 56)),
    "navy": ("紺", (28, 36, 86)), "black": ("黒", (24, 22, 28)), "green": ("みどり", (22, 106, 74)),
    "white": ("白", (240, 240, 234)), "sky": ("水色", (150, 214, 240)), "pink": ("ピンク", (250, 176, 200)),
}
RAINBOW = [(255, 60, 70), (255, 150, 40), (255, 230, 70), (80, 255, 120), (60, 210, 255), (180, 100, 255)]
KINDS = [("ネオン管", "neon"), ("LED", "led"), ("ライトアップ", "board")]
SIZES = [("小", "S"), ("中", "M"), ("大", "L")]
FONT_PX = {"S": 18, "M": 26, "L": 36}
LED_LEN = {"S": 40, "M": 56, "L": 80}    # LED の横の数（縦長のときは縦の数）
SHOW_WALL = False   # 「壁紙になじませる（透けて見える風）」を使うかどうか（いまはお休み）
BGS = [("壁紙になじませる（透けて見える風）", "wall"), ("ポップアップ広告風（透けない）", "ad"),
       ("ごちゃまぜポータル（透けない）", "portal"),
       ("夜のレンガの壁", "brick"), ("まっくら", "dark")]
if not SHOW_WALL:
    BGS = BGS[1:]
PLAIN_BG = "dark"   # 透ける背景のかわりに使う背景
SOURCES = [("自分の言葉", "text"), ("時計", "clock"), ("いま流れている曲", "music")]
TUBE_STYLES = [("ふちだけ", "outline"), ("ぬりつぶし", "solid"), ("二重", "double")]
BORDER_STYLES = [("丸い枠", "round"), ("二重の枠", "double"), ("流れる点線", "dash")]
ANIMS = [("ずっと点いている", "steady"), ("順番に点く", "chase"), ("ときどき点滅", "blink")]
LED_STYLES = [("1色", "single"), ("虹色", "rainbow"), ("点滅", "blink")]
LIGHTS = [("ランプで照らす", "lamp"), ("内側から光る（行灯）", "box")]

# ネオンのマーク（0〜1 の座標の折れ線）
def _star():
    pts = []
    for i in range(11):
        r = 0.46 if i % 2 == 0 else 0.2
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((0.5 + r * math.cos(a), 0.54 + r * math.sin(a)))
    return [pts]


def _moon():
    outer = [(0.5 + 0.4 * math.cos(a / 10 * math.pi * 1.4 + 0.3 * math.pi), 0.5 + 0.4 * math.sin(a / 10 * math.pi * 1.4 + 0.3 * math.pi)) for a in range(11)]
    inner = [(0.62 + 0.3 * math.cos(a / 10 * math.pi * 1.4 + 0.3 * math.pi), 0.42 + 0.3 * math.sin(a / 10 * math.pi * 1.4 + 0.3 * math.pi)) for a in range(11)]
    return [outer + inner[::-1] + outer[:1]]


MARKS = {
    "heart": [[(0.5, 0.86), (0.12, 0.46), (0.12, 0.24), (0.3, 0.12), (0.5, 0.27), (0.7, 0.12), (0.88, 0.24), (0.88, 0.46), (0.5, 0.86)]],
    "star": _star(),
    "arrow": [[(0.08, 0.5), (0.86, 0.5)], [(0.58, 0.24), (0.88, 0.5), (0.58, 0.76)]],
    "cup": [[(0.14, 0.34), (0.74, 0.34), (0.68, 0.84), (0.2, 0.84), (0.14, 0.34)], [(0.74, 0.44), (0.9, 0.48), (0.88, 0.64), (0.71, 0.68)],
            [(0.34, 0.24), (0.4, 0.06)], [(0.52, 0.24), (0.58, 0.06)]],
    "cocktail": [[(0.1, 0.16), (0.9, 0.16), (0.5, 0.56), (0.1, 0.16)], [(0.5, 0.56), (0.5, 0.86)], [(0.28, 0.88), (0.72, 0.88)],
                 [(0.66, 0.16), (0.8, 0.02)]],
    "moon": _moon(),
}
MARK_NAMES = [("なし", "none"), ("ハート", "heart"), ("星", "star"), ("矢印", "arrow"), ("カップ", "cup"),
              ("カクテル", "cocktail"), ("月", "moon")]

_FONT_DIRS = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")]
_GOTHIC = ["HGRSGU.TTC", "BIZ-UDGothicB.ttc", "YuGothB.ttc", "meiryob.ttc", "msgothic.ttc"]
FONTS = {   # 書体：上から順に、入っているものを使う（HG〜 は Office についてくる書体）
    "gothic": ("ゴシック", _GOTHIC),
    "pop": ("ポップ", ["HGRPP1.TTC"] + _GOTHIC),
    "brush": ("筆", ["HGRGY.TTC", "HGRKK.TTC", "BIZ-UDMinchoM.ttc", "yumindb.ttf"] + _GOTHIC),
    "mincho": ("明朝", ["HGRME.TTC", "BIZ-UDMinchoM.ttc", "yumindb.ttf"] + _GOTHIC),
}
LED_FONT = ["DotGothic16-Regular.ttf", "msgothic.ttc", "BIZ-UDGothicR.ttc"]
ROTATE_V = set("ー－―—〜~…‥()（）「」『』[]【】<>＜＞-=＝→←")   # 縦書きのとき、横に寝かせる文字

DEFAULT_CONFIG = {"wall": "auto", "night_only": False, "topmost": False, "open_random": False, "signs": [],
                  "prev_signs": [], "random_bg": "mix"}
RANDOM_BGS = [("壁紙になじませる", "wall"), ("ポップアップ広告風", "ad"), ("ごちゃまぜポータル", "portal"),
              ("画像の広告", "image"), ("まぜる", "mix")]
if not SHOW_WALL:
    RANDOM_BGS = RANDOM_BGS[1:]
ADS_DIR = os.path.join(APP_DIR, "neon_ads")   # 画像の広告の置き場（ここに入れた絵が候補になる）
IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
IMG_FX = [("動かない", "none"), ("ときどきピカッと光る", "flash"), ("ときどき画面が乱れる", "glitch"),
          ("光る＋乱れる", "both")]
IMG_SCALE = {"S": 0.75, "M": 1.0, "L": 1.3}
SIGN_DEFAULT = dict(kind="neon", text="SUGAR", source="text", vertical=False, color="pink", color2="cyan",
                    size="M", font="gothic", bg="wall" if SHOW_WALL else PLAIN_BG, flicker=True, bulbs=True, speed=4, x=200, y=200,
                    style="outline", border="round", anim="steady", mark="none", led_style="single", light="lamp",
                    ad_skin="classic", ad_bg="burst", ad_pal=0, ad_title=0, ad_cta=0, ad_badge=0, portal_seed=0,
                    image="", img_fx="flash")
STARTER = [
    dict(kind="neon", text="喫茶シュガー", color="pink", color2="cyan", size="L", mark="cup"),
    dict(kind="led", text="SugarRoom24　きょうも営業中　いらっしゃいませ", color="amber", size="M"),
    dict(kind="board", text="甘味処", vertical=True, color="red", color2="cream", font="brush", size="L"),
    dict(kind="neon", text="夜市", vertical=True, color="cyan", color2="none", font="brush", size="L"),
]
# おまかせで並べるときの言葉
WORDS_SHORT = ["夜市", "麻雀", "酒場", "飯店", "薬局", "金魚", "質", "茶室", "甘味", "糖果", "甜品", "占い", "銭湯", "旅館",
               "理髪", "電器", "古書", "骨董", "時計", "喫茶", "餃子", "拉麺", "按摩", "當舖", "涼茶", "粥麵", "BAR", "CAFE",
               "OPEN", "24H", "LIVE", "CLUB", "HOTEL", "SUGAR"]
WORDS_LONG = ["喫茶シュガー", "純喫茶ゆめ", "スナック星屑", "糖果専門店", "SUGAR CAFE", "ミルクホール", "カラオケ", "ラーメン",
              "甜品屋", "夜のレコード", "ドット電器", "シュガー飯店", "旅館あめ玉", "ROOM 24", "NIGHT MARKET", "金魚すくい",
              "占いの館", "中西薬房", "大飯店", "歓迎光臨"]
WORDS_LED = ["いらっしゃいませ　本日も営業中", "SugarRoom24　OPEN 24H", "歓迎光臨　WELCOME", "ただいま満席　すこしお待ちください",
             "本日のおすすめ　いちごパフェ", "SUGAR TOWN へようこそ", "雨の日はポイント2倍", "閉店まであと少し　またきてね",
             "NOW ON SALE", "まいどおおきに"]
NEON_THEME = dict(face=(28, 24, 40), out=(10, 8, 16), light=(70, 62, 96), title=(80, 30, 90), title2=(170, 50, 140),
                  title_text=(255, 220, 245), accent=(255, 70, 170), sub=(150, 140, 180), text=(240, 232, 255),
                  field=(16, 14, 24), select=(255, 70, 170), select_text=(255, 255, 255))
FLICK = [1, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 1]   # ちらつくときの、つく(1)・消える(0) のならび（60ms ずつ）


# ---------- 壁紙 ----------

def wallpaper_info():
    """いまの Windows の壁紙の (画像の場所, 並べ方, 並べ方(タイル), 背景色)。"""
    path = ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.user32.SystemParametersInfoW(0x73, 1024, buf, 0)   # 0x73 = いまの壁紙の場所を聞く
        path = buf.value
    except Exception:
        pass
    if not path or not os.path.exists(path):
        t = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Themes", "TranscodedWallpaper")
        path = t if os.path.exists(t) else ""
    style, tile, bgcol = "10", "0", (0, 0, 0)
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
            style = str(winreg.QueryValueEx(k, "WallpaperStyle")[0])
            tile = str(winreg.QueryValueEx(k, "TileWallpaper")[0])
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Colors") as k:
            bgcol = tuple(int(v) for v in str(winreg.QueryValueEx(k, "Background")[0]).split()[:3])
    except Exception:
        pass
    return path, style, tile, bgcol


def screen_wallpaper(path, sw, sh, style="10", tile="0", bgcol=(0, 0, 0)):
    """壁紙を、Windows と同じ並べ方で画面の大きさの絵にする。"""
    out = Image.new("RGB", (sw, sh), bgcol)
    try:
        with Image.open(path) as f:
            im = f.convert("RGB")
    except (OSError, ValueError):
        return None
    iw, ih = im.size
    if tile == "1":
        for y in range(0, sh, ih):
            for x in range(0, sw, iw):
                out.paste(im, (x, y))
    elif style in ("10", "22"):   # ページ幅に合わせる（はみ出しは切る）
        s = max(sw / iw, sh / ih)
        nw, nh = max(sw, round(iw * s)), max(sh, round(ih * s))
        im = im.resize((nw, nh), Image.LANCZOS)
        out.paste(im, (-(nw - sw) // 2, -(nh - sh) // 2))
    elif style == "6":            # 画面に合わせる（すきまは背景色）
        s = min(sw / iw, sh / ih)
        nw, nh = round(iw * s), round(ih * s)
        out.paste(im.resize((nw, nh), Image.LANCZOS), ((sw - nw) // 2, (sh - nh) // 2))
    elif style == "2":            # 拡大して表示
        out = im.resize((sw, sh), Image.LANCZOS)
    else:                         # 中央に表示
        out.paste(im, ((sw - iw) // 2, (sh - ih) // 2))
    return out


# ---------- 文字 ----------
_font_cache = {}


def load_font(names, size):
    key = (tuple(names), size)
    if key not in _font_cache:
        font = None
        for n in names:
            for d in _FONT_DIRS:
                try:
                    font = ImageFont.truetype(os.path.join(d, n), size)
                    break
                except OSError:
                    continue
            if font:
                break
        _font_cache[key] = font or ImageFont.load_default()
    return _font_cache[key]


def layout_chars(text, font, size, vertical):
    """1文字ずつの形（白黒の絵）と置き場所。[(mask, x, y), ...], 全体の幅, 高さ。"""
    chars = []
    b = font.getbbox("国")
    hc = round(size * 1.15)
    oy = (hc - (b[3] - b[1])) // 2 - b[1]
    if not vertical:
        x = 0
        for ch in text:
            adv = max(1, round(font.getlength(ch)))
            if ch.strip():
                m = Image.new("L", (adv + 2, hc), 0)
                d = ImageDraw.Draw(m)
                d.fontmode = "1"
                d.text((0, oy), ch, font=font, fill=255)
                chars.append((m, x, 0))
            x += adv + max(1, size // 16)
        return chars, max(1, x), hc
    cw, chh = size + 2, round(size * 1.08)
    y = 0
    for ch in text:
        if not ch.strip():
            y += chh // 2
            continue
        adv = max(1, round(font.getlength(ch)))
        g = Image.new("L", (adv + 2, hc), 0)
        d = ImageDraw.Draw(g)
        d.fontmode = "1"
        d.text((0, oy), ch, font=font, fill=255)
        if ch in ROTATE_V:
            g = g.rotate(-90, expand=True)
        m = Image.new("L", (cw, chh), 0)
        m.paste(g, ((cw - g.width) // 2, (chh - g.height) // 2))
        chars.append((m, 0, y))
        y += chh
    return chars, cw, max(1, y)


def mark_mask(name, size):
    """マーク（ハートなど）を、ネオン管の線で描いた白黒の絵。"""
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    w = 1 if size < 24 else 2
    for line in MARKS.get(name, []):
        d.line([(1 + x * (size - 3), 1 + y * (size - 3)) for x, y in line], fill=255, width=w)
    return m


def erode(m, n):
    for _ in range(n):
        m = m.filter(ImageFilter.MinFilter(3))
    return m


def one_line(text):
    return " ".join(text.split())


def rounded_path(x0, y0, x1, y1, r=4):
    """角の丸い四角の、ふちにそった点のならび（1ドットずつ）。"""
    pts = []
    for x in range(x0 + r, x1 - r):
        pts.append((x, y0))
    for i in range(r):
        a = -math.pi / 2 + (i + 1) / r * math.pi / 2
        pts.append((round(x1 - r + r * math.cos(a)), round(y0 + r + r * math.sin(a))))
    for y in range(y0 + r, y1 - r):
        pts.append((x1, y))
    for i in range(r):
        a = (i + 1) / r * math.pi / 2
        pts.append((round(x1 - r + r * math.cos(a)), round(y1 - r + r * math.sin(a))))
    for x in range(x1 - r, x0 + r, -1):
        pts.append((x, y1))
    for i in range(r):
        a = math.pi / 2 + (i + 1) / r * math.pi / 2
        pts.append((round(x0 + r + r * math.cos(a)), round(y1 - r + r * math.sin(a))))
    for y in range(y1 - r, y0 + r, -1):
        pts.append((x0, y))
    for i in range(r):
        a = math.pi + (i + 1) / r * math.pi / 2
        pts.append((round(x0 + r + r * math.cos(a)), round(y0 + r + r * math.sin(a))))
    return pts


# ---------- 背景 ----------

def brick_wall(w, h):
    """夜のレンガの壁（ドットの大きさで描く）。"""
    im = Image.new("RGB", (w, h), (20, 16, 22))
    d = ImageDraw.Draw(im)
    bw, bh = 12, 6
    for row in range(h // bh + 1):
        off = (bw // 2) * (row % 2)
        for col in range(-1, w // bw + 2):
            x0, y0 = col * bw + off, row * bh
            shade = 34 + (col * 7 + row * 13) % 9
            d.rectangle([x0 + 1, y0 + 1, x0 + bw - 1, y0 + bh - 1], fill=(shade + 6, shade - 6, shade))
            d.line([(x0 + 1, y0 + 1), (x0 + bw - 2, y0 + 1)], fill=(shade + 14, shade, shade + 6))
    return im


def soft_dark(w, h, inner, strength):
    """看板のまわりを少しだけ暗くするための、ふちで 0 になるなめらかなマスク（ドットの大きさ）。"""
    m = Image.new("L", (w, h), 0)
    x0, y0, x1, y1 = inner
    ImageDraw.Draw(m).rounded_rectangle([x0, y0, x1, y1], radius=6, fill=int(255 * strength))
    return m.filter(ImageFilter.GaussianBlur(GLOW / 2.2))


_feather = {}


def edge_feather(w, h):
    """ふちに向かって 0 になるマスク。ふちでは壁紙そのものになるので、境目が見えない。"""
    if (w, h) not in _feather:
        m = Image.new("L", (w, h), 0)
        e = 5 * P
        for i in range(e):
            ImageDraw.Draw(m).rectangle([i, i, w - 1 - i, h - 1 - i], outline=int(255 * (i + 1) / e))
        ImageDraw.Draw(m).rectangle([e, e, w - 1 - e, h - 1 - e], fill=255)
        _feather[(w, h)] = m
    return _feather[(w, h)]


def glow_of(src, strong=1.0):
    """光っている部分から、ぼんやりした光を作る（ドットの大きさで計算して、あとで拡大する）。"""
    a = src.filter(ImageFilter.GaussianBlur(1.6))
    b = src.filter(ImageFilter.GaussianBlur(5.0))
    g = ImageChops.add(a, b)
    if strong != 1.0:
        g = g.point(lambda v: min(255, int(v * strong)))
    return g


# ---------- ポップアップ広告風 ----------
AD_B, AD_TB, AD_CTA = 2, 11, 14      # ふち・タイトルバー・下の「クリック！」の帯（ドット）
AD_SKINS = {
    "classic": dict(face=(192, 192, 192), light=(255, 255, 255), shade=(128, 128, 128), dark=(0, 0, 0),
                    t1=(0, 0, 128), t2=(16, 132, 208), ttext=(255, 255, 255), close=(192, 192, 192), xcol=(0, 0, 0)),
    "xp": dict(face=(0, 84, 227), light=(80, 150, 255), shade=(0, 50, 160), dark=(0, 24, 90),
               t1=(0, 70, 220), t2=(70, 150, 255), ttext=(255, 255, 255), close=(224, 67, 22), xcol=(255, 255, 255)),
    "y2k": dict(face=(30, 26, 40), light=(150, 140, 190), shade=(16, 12, 24), dark=(0, 0, 0),
                t1=(200, 30, 160), t2=(40, 200, 255), ttext=(255, 255, 255), close=(255, 60, 140), xcol=(255, 255, 255)),
}
AD_SKIN_NAMES = [("むかしのグレー", "classic"), ("あおいまど", "xp"), ("きらきら黒", "y2k")]
AD_BG_NAMES = [("集中線", "burst"), ("チェック", "checker"), ("グラデーション", "grad"), ("星空", "stars"), ("ななめしま", "stripes")]
AD_PALETTES = [((20, 10, 60), (90, 20, 140)), ((10, 10, 10), (110, 10, 30)), ((60, 0, 70), (10, 0, 30)),
               ((0, 30, 70), (0, 90, 140)), ((40, 10, 10), (140, 60, 0)), ((0, 40, 30), (0, 110, 80))]
AD_TITLES = ["HOT NEON!!! - SUGAR EXPLORER", "WINNER!!!.HTML", "FREE GIFT - POPUP", "CLICK HERE NOW!",
             "SUGARTOWN.EXE", "YOU WON!!!", "BEST NIGHT 2000", "SPECIAL OFFER!!"]
AD_CTAS = ["今すぐクリック！", "あなたが当選しました！", "限定100名様！", "無料でネオン！", "ここを押してね！", "本日かぎり！",
           "おめでとうございます！", "いますぐ入店！"]
AD_BADGES = ["NEW!", "HOT!", "SALE", "FREE", "WOW!", "24H"]


def ad_pattern(kind, w, h, pal):
    """広告の中身の、派手な模様（ドットの大きさ）。"""
    c1, c2 = pal
    im = Image.new("RGB", (w, h), c1)
    d = ImageDraw.Draw(im)
    if kind == "burst":
        cx, cy, r = w / 2, h / 2, max(w, h)
        for i in range(0, 24, 2):
            a0, a1 = i / 24 * 2 * math.pi, (i + 1) / 24 * 2 * math.pi
            d.polygon([(cx, cy), (cx + r * math.cos(a0), cy + r * math.sin(a0)), (cx + r * math.cos(a1), cy + r * math.sin(a1))], fill=c2)
    elif kind == "checker":
        for y in range(0, h, 8):
            for x in range((y // 8) % 2 * 8, w, 16):
                d.rectangle([x, y, x + 7, y + 7], fill=c2)
    elif kind == "stars":
        rnd = random.Random(w * 7 + h)
        for _ in range(w * h // 60):
            x, y = rnd.randrange(w), rnd.randrange(h)
            d.point((x, y), fill=mix(c2, (255, 255, 255), rnd.random() * 0.8))
    elif kind == "stripes":
        for k in range(-h, w, 10):
            d.polygon([(k, 0), (k + 5, 0), (k + 5 + h, h), (k + h, h)], fill=c2)
    else:
        for y in range(h):
            t = y / max(1, h - 1)
            for x in range(w):
                d.point((x, y), fill=c2 if ((x % 4) * 4 + y % 4) / 16 < t else c1)
    return im


def starburst(size, fill, out):
    m = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(m)
    pts = []
    for i in range(24):
        r = size / 2 - 0.5 if i % 2 == 0 else size / 2 * 0.72
        a = i / 24 * 2 * math.pi
        pts.append((size / 2 + r * math.cos(a), size / 2 + r * math.sin(a)))
    d.polygon(pts, fill=fill + (255,), outline=out + (255,))
    return m


# ---------- ごちゃまぜポータル ----------
PT_B, PT_HEAD, PT_SIDE, PT_TOP, PT_BOTTOM = 2, 15, 50, 24, 38   # ふち・見出し・左右・上・下の帯（ドット）
PT_WORDS = ["電子郵件", "MAIL", "掲示板", "BBS", "本日特価", "HAPPY HOUR", "歓迎光臨", "WELCOME", "SUGAR NET", "糖果網",
            "交友", "FRIENDS", "天気予報", "WEATHER", "占い", "FORTUNE", "音楽", "MUSIC", "ゲーム", "GAMES", "資料庫",
            "DATABASE", "新着", "NEW!", "人気", "HOT", "ランキング", "RANK", "下載", "DOWNLOAD", "LINK", "リンク集",
            "聊天室", "CHAT", "お知らせ", "NEWS", "会員登録", "MEMBER", "SUGAR TV", "夜市情報", "甜品", "CAFE", "24H",
            "OPEN", "無料", "FREE", "当選", "WINNER", "糖分補給", "ROOM 24", "電脳街", "CYBER", "おやつ", "SNACK",
            "金魚", "旅行", "TRAVEL", "通販", "SHOP", "写真館", "PHOTO", "日記", "DIARY", "相談室", "HELP", "地図", "MAP"]
PT_SHORT = ["NEW", "HOT", "特価", "無料", "!!", "24H", "UP", "★", "♪", "得"]
PT_SITES = ["SUGAR NET", "糖果網", "TOWN LINK", "夜市NET", "24 NET", "甘味網"]
PT_FONTS = [_GOTHIC, ["HGRPP1.TTC"] + _GOTHIC, ["HGRGY.TTC"] + _GOTHIC, ["HGRME.TTC", "BIZ-UDMinchoM.ttc"] + _GOTHIC,
            ["HGRGE.TTC"] + _GOTHIC, ["HGRSMP.TTF"] + _GOTHIC, ["UDDigiKyokashoN-B.ttc"] + _GOTHIC,
            ["HGRMB.TTC"] + _GOTHIC, ["BIZ-UDGothicR.ttc"] + _GOTHIC, ["DotGothic16-Regular.ttf"] + _GOTHIC]
PT_COLORS = [(220, 20, 40), (20, 60, 200), (0, 150, 60), (240, 140, 0), (160, 0, 180), (0, 160, 200), (230, 0, 120),
             (40, 40, 40), (200, 170, 0), (120, 60, 20)]
PT_BGS = [(255, 255, 255), (255, 250, 232), (236, 244, 255), (255, 238, 246), (240, 240, 240)]
PT_HEADS = [((0, 0, 140), (0, 120, 220)), ((150, 0, 40), (255, 80, 60)), ((0, 90, 60), (40, 180, 120)),
            ((70, 0, 120), (200, 60, 200)), ((20, 20, 20), (90, 90, 110))]


def _txt(text, font, color, stroke=0, stroke_col=(0, 0, 0)):
    """文字だけの絵（にじませない）。"""
    b = font.getbbox(text, stroke_width=stroke)
    w, h = max(1, b[2] - b[0] + 1), max(1, b[3] - b[1] + 1)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    d.text((-b[0], -b[1]), text, font=font, fill=color + (255,), stroke_width=stroke, stroke_fill=stroke_col + (255,))
    return im


def make_tile(rnd, max_w, h):
    """ポータルのロゴを1つ。書体・色・飾り・傾きがばらばら。入らなければ None。"""
    deco = rnd.choices(["plain", "outline", "shadow", "rainbow", "box", "button", "badge", "pair"],
                       [3, 3, 3, 2, 2, 2, 1, 2])[0]
    font_names = rnd.choice(PT_FONTS)
    col = rnd.choice(PT_COLORS)
    col2 = rnd.choice([c for c in PT_COLORS if c != col])
    for _ in range(8):
        if deco == "badge":
            word, size = rnd.choice(PT_SHORT), max(7, h - 7)
        elif deco == "pair":
            word, size = rnd.choice(PT_WORDS), max(7, h // 2 - 1)
        else:
            word, size = rnd.choice(PT_WORDS), max(8, h - rnd.choice([2, 3, 4]))
        font = load_font(font_names, size)
        if deco in ("plain", "rainbow"):
            t = _txt(word, font, col)
            if deco == "rainbow":   # 虹色のグラデーション
                g = Image.new("RGBA", t.size)
                gd = ImageDraw.Draw(g)
                for x in range(t.width):
                    c = RAINBOW[int(x / max(1, t.width) * len(RAINBOW)) % len(RAINBOW)]
                    gd.line([(x, 0), (x, t.height)], fill=mix(c, (0, 0, 0), 0.15) + (255,))
                g.putalpha(t.getchannel("A"))
                t = g
        elif deco == "outline":
            t = _txt(word, font, rnd.choice([(255, 255, 255), (255, 240, 80), col]), 1, col2)
        elif deco == "shadow":   # 立体の影
            front = _txt(word, font, col)
            back = _txt(word, font, mix(col2, (0, 0, 0), 0.5))
            depth = 2
            t = Image.new("RGBA", (front.width + depth, front.height + depth), (0, 0, 0, 0))
            for k in range(depth, 0, -1):
                t.paste(back, (k, k), back)
            t.paste(front, (0, 0), front)
        elif deco == "box":
            tx = _txt(word, font, rnd.choice([(255, 255, 255), (255, 240, 80)]))
            t = Image.new("RGBA", (tx.width + 6, tx.height + 4), col + (255,))
            ImageDraw.Draw(t).rectangle([0, 0, t.width - 1, t.height - 1], outline=(0, 0, 0, 255))
            t.paste(tx, (3, 2), tx)
        elif deco == "button":   # 立体のボタン
            face = rnd.choice([(200, 200, 200), (255, 230, 120), (180, 220, 255), (255, 190, 210)])
            tx = _txt(word, font, (20, 20, 20))
            t = Image.new("RGBA", (tx.width + 8, tx.height + 6), face + (255,))
            bd = ImageDraw.Draw(t)
            bd.line([(0, t.height - 1), (0, 0), (t.width - 1, 0)], fill=(255, 255, 255, 255))
            bd.line([(t.width - 1, 0), (t.width - 1, t.height - 1), (0, t.height - 1)], fill=(60, 60, 60, 255))
            bd.line([(t.width - 2, 1), (t.width - 2, t.height - 2), (1, t.height - 2)], fill=(140, 140, 140, 255))
            t.paste(tx, (4, 3), tx)
        elif deco == "badge":
            tx = _txt(word, font, (255, 255, 255) if col != (200, 170, 0) else (0, 0, 0))
            bs = max(h, tx.width + 6)
            t = starburst(bs, col, (0, 0, 0)) if rnd.random() < 0.5 else Image.new("RGBA", (bs, bs), (0, 0, 0, 0))
            if t.getbbox() is None:
                ImageDraw.Draw(t).ellipse([0, 0, bs - 1, bs - 1], fill=col + (255,), outline=(0, 0, 0, 255))
            t.paste(tx, ((bs - tx.width) // 2, (bs - tx.height) // 2), tx)
        else:   # 2行（漢字と英語のペアっぽく）
            other = rnd.choice(PT_WORDS)
            a = _txt(word, font, col)
            b = _txt(other, load_font(rnd.choice(PT_FONTS), size), col2)
            t = Image.new("RGBA", (max(a.width, b.width), a.height + b.height + 1), (0, 0, 0, 0))
            t.paste(a, ((t.width - a.width) // 2, 0), a)
            t.paste(b, ((t.width - b.width) // 2, a.height + 1), b)
        if rnd.random() < 0.18:   # ちょっと傾ける
            t = t.rotate(rnd.choice([-9, -6, 6, 9]), expand=True, resample=Image.NEAREST)
        if t.width <= max_w and t.height <= h + 2:
            return t
    return None


def pack_tiles(rnd, region, blink_pick):
    """region（x, y, 幅, 高さ）を、ロゴでぎっしり埋める。[(絵, x, y, 点滅するか), ...]"""
    x0, y0, w, h = region
    out = []
    y = y0
    while y < y0 + h - 8:
        rh = min(rnd.choice([12, 14, 16, 18, 20]), y0 + h - y)
        x = x0 + rnd.randint(0, 2)
        tallest = 0
        misses = 0
        while x < x0 + w - 8 and misses < 4:
            t = make_tile(rnd, x0 + w - x, rh)
            if t is None:
                misses += 1
                continue
            ty = y + max(0, (rh - t.height) // 2)
            out.append((t, x, ty, rnd.random() < blink_pick))
            x += t.width + rnd.randint(2, 6)
            tallest = max(tallest, t.height)
        y += max(rh, tallest) + rnd.randint(1, 3)
    return out


# ---------- おまかせ ----------

def list_ads():
    """neon_ads フォルダの絵のファイル名（名前順）。"""
    try:
        return sorted(f for f in os.listdir(ADS_DIR)
                      if f.lower().endswith(IMG_EXTS) and os.path.isfile(os.path.join(ADS_DIR, f)))
    except OSError:
        return []


_AD_CACHE = {}


def load_ad(name):
    """絵を読み込む（読めないときは None）。同じ絵は2回読まない。"""
    p = os.path.join(ADS_DIR, name)
    try:
        key = (p, os.path.getmtime(p))
    except OSError:
        return None
    if key not in _AD_CACHE:
        try:
            with Image.open(p) as im:
                _AD_CACHE[key] = im.convert("RGB")
        except Exception:
            return None
    return _AD_CACHE[key]


def ad_label(name):
    """メニューに出す名前（01_ラッキー占い.png → ラッキー占い）。"""
    stem = os.path.splitext(name)[0]
    head, _, rest = stem.partition("_")
    return rest if head.isdigit() and rest else stem


def random_image_sign(rnd=random, avoid=()):
    """画像の広告を1枚、ばらばらに決める（絵がないときは None）。"""
    ads = list_ads()
    if not ads:
        return None
    pool = [a for a in ads if a not in avoid] or ads
    return dict(SIGN_DEFAULT, kind="image", bg="image", image=rnd.choice(pool),
                img_fx=rnd.choices(["flash", "glitch", "both", "none"], [4, 3, 2, 1])[0],
                size=rnd.choices(["S", "M", "L"], [3, 5, 1])[0])


def random_ad(rnd=random):
    """ポップアップ広告風の、ばらばらな見た目。"""
    return dict(ad_skin=rnd.choice(list(AD_SKINS)), ad_bg=rnd.choice([k for _, k in AD_BG_NAMES]),
                ad_pal=rnd.randrange(len(AD_PALETTES)), ad_title=rnd.randrange(len(AD_TITLES)),
                ad_cta=rnd.randrange(len(AD_CTAS)), ad_badge=rnd.randrange(len(AD_BADGES)))


def random_sign(rnd=random):
    """看板を1枚、ばらばらに決める。"""
    kind = rnd.choices(["neon", "board", "led"], [5, 3, 2])[0]
    colors = list(NEON)
    c1 = rnd.choice(colors)
    c2 = rnd.choice([c for c in colors if c != c1])
    d = dict(SIGN_DEFAULT, kind=kind, color=c1, flicker=rnd.random() < 0.8, **random_ad(rnd))
    if kind == "led":
        d.update(vertical=rnd.random() < 0.3, size=rnd.choice(["S", "M", "M", "L"]),
                 color=rnd.choice(["amber", "amber", "red", "green", "orange", "white"]),
                 led_style=rnd.choices(["single", "rainbow", "blink"], [5, 2, 1])[0], speed=rnd.choice([2, 4, 4, 6]))
        d["text"] = rnd.choice(WORDS_SHORT) if d["vertical"] and rnd.random() < 0.5 else rnd.choice(WORDS_LED)
        return d
    vertical = rnd.random() < 0.45
    short = vertical or rnd.random() < 0.4
    text = rnd.choice(WORDS_SHORT if short else WORDS_LONG)
    if vertical and len(text) > 5:
        text = text[:5]
    d.update(text=text, vertical=vertical, font=rnd.choice(list(FONTS)),
             size=rnd.choice(["M", "L", "L"]) if len(text) <= 4 else rnd.choice(["S", "M", "M"]))
    if kind == "neon":
        d.update(color2=rnd.choice([c2, c2, "none"]), style=rnd.choices(["outline", "solid", "double"], [4, 3, 2])[0],
                 border=rnd.choices(["round", "double", "dash"], [4, 2, 2])[0],
                 anim=rnd.choices(["steady", "chase", "blink"], [6, 2, 1])[0],
                 mark=rnd.choice(["none"] * 4 + [k for _, k in MARK_NAMES[1:]]))
    else:
        panel = rnd.choice(list(PANEL))
        ink = rnd.choice(["red", "blue", "green", "white", "yellow", "pink"])
        if panel in ("cream", "white", "yellow", "sky", "pink") and ink in ("white", "yellow"):
            ink = rnd.choice(["red", "blue"])
        if panel in ("navy", "black", "green", "red") and ink not in ("white", "yellow"):
            ink = rnd.choice(["white", "yellow"])
        d.update(color=ink, color2=panel, bulbs=rnd.random() < 0.55,
                 light="box" if panel in ("cream", "white", "yellow", "sky", "pink") and rnd.random() < 0.5 else "lamp")
    return d


class Sign:
    """看板1枚（ウィンドウ1つ）。"""

    def __init__(self, app, data):
        self.app = app
        self.d = dict(SIGN_DEFAULT, **data)
        self.t = tk.Toplevel(app.root)
        self.t.overrideredirect(True)
        self.t.attributes("-topmost", app.cfg["topmost"])
        self.label = tk.Label(self.t, bd=0, highlightthickness=0, bg="black")
        self.label.pack()
        for w in (self.t, self.label):
            w.bind("<ButtonPress-1>", self.on_press)
            w.bind("<B1-Motion>", self.on_drag)
            w.bind("<ButtonRelease-1>", self.on_release)
            w.bind("<Double-Button-1>", lambda e: self.edit_text())
            w.bind("<Button-3>", lambda e: app.popup(self, e))
        self.job = None
        self.render_pending = False
        self.build()
        self.place()
        self.loop()

    # --- 中身の文字 ---
    def current_text(self):
        src = self.d["source"]
        if src == "clock":
            return time.strftime("%H:%M")
        if src == "music":
            now = load_now_playing()
            return ("♪ " + now.get("title", "")) if now else "♪ ーーー"
        return self.d["text"] or " "

    def lit(self):
        return not self.app.cfg["night_only"] or is_night_time()

    # --- 組み立て（文字や設定が変わったときだけ） ---
    def build(self):
        self.shown_text = self.current_text()
        kind = self.d["kind"]
        self.start = time.time() - random.random() * 0.2
        if kind == "image":
            self.build_image()
            return
        if kind == "led":
            self.build_led()
        elif kind == "board":
            self.build_board()
        else:
            self.build_neon()
        self.cw, self.ch = self.dw * P, self.dh * P
        self.ad = self.d["bg"] == "ad"
        self.portal = self.d["bg"] == "portal"
        if self.ad:   # ポップアップ広告のウィンドウで囲む
            self.ad_off = (AD_B * P, (AD_B + AD_TB) * P)
            self.W, self.H = self.cw + 2 * AD_B * P, self.ch + (2 * AD_B + AD_TB + AD_CTA) * P
            self.build_ad()
        elif self.portal:   # ごちゃまぜポータルで囲む
            self.ad_off = ((PT_B + PT_SIDE) * P, (PT_B + PT_HEAD + PT_TOP) * P)
            self.W = self.cw + 2 * (PT_B + PT_SIDE) * P
            self.H = self.ch + (2 * PT_B + PT_HEAD + PT_TOP + PT_BOTTOM) * P
            self.build_portal()
        else:
            self.ad_off = (0, 0)
            self.W, self.H = self.cw, self.ch

    def build_image(self):
        """画像の広告：絵をそのままウィンドウにする。"""
        self.ad = self.portal = False
        self.ad_off = (0, 0)
        ads = list_ads()
        if self.d["image"] not in ads and ads:   # 絵が消えていたら、ほかの絵にする
            self.d["image"] = ads[0]
        src = load_ad(self.d["image"]) if ads else None
        if src is None:   # 絵がひとつもないとき
            src = Image.new("RGB", (120, 40), (20, 20, 30))
            d = ImageDraw.Draw(src)
            d.rectangle([0, 0, 119, 39], outline=(255, 70, 170))
            px_text(d, 10, 12, "NO IMAGE", (255, 255, 255), 2)
            px_text(d, 10, 26, "NEON_ADS", (255, 70, 170))
        k = IMG_SCALE.get(self.d["size"], 1.0)
        w, h = max(8, round(src.width * k)), max(8, round(src.height * k))
        self.img = src if (w, h) == src.size else src.resize((w, h), Image.LANCZOS)
        self.W, self.H = self.cw, self.ch = w, h
        self.img_k = k
        r = random.Random(self.d["image"])
        self.flash_every = 3.5 + r.random() * 3   # ピカッと光る間かく（絵ごとに少しちがう）
        self.flash_img = Image.blend(self.img, Image.new("RGB", self.img.size, (255, 255, 255)), 0.45)
        self.dark_img = Image.eval(self.img, lambda v: v * 2 // 5)
        self.glitch = 0          # 乱れている残りコマ数
        self.glitch_seed = 0
        self.state = None

    def img_state(self):
        fx = self.d["img_fx"]
        if not self.lit():
            return ("off",)
        if fx in ("glitch", "both"):
            if self.glitch:
                self.glitch -= 1
            elif random.random() < 0.006:
                self.glitch = random.randint(2, 5)
                self.glitch_seed = random.randint(1, 10 ** 6)
        if self.glitch:
            return ("glitch", self.glitch, self.glitch_seed)
        if fx in ("flash", "both"):
            c = (time.time() - self.start) % self.flash_every
            if c < 0.1 or 0.22 < c < 0.32:
                return ("flash",)
        return ("on",)

    def render_image(self):
        st = self.state or ("on",)
        if st[0] == "off":
            img = self.dark_img
        elif st[0] == "flash":
            img = self.flash_img
        elif st[0] == "glitch":   # 横の帯をずらして、色を少しにじませる
            r = random.Random(st[1] * 7919 + st[2])
            img = self.img.copy()
            w, h = img.size
            for _ in range(r.randint(2, 5)):
                y0 = r.randrange(h)
                bh = r.randint(2, max(3, h // 8))
                dx = r.randint(-w // 10, w // 10)
                band = self.img.crop((0, y0, w, min(h, y0 + bh)))
                rr, gg, bb = band.split()
                band = Image.merge("RGB", (ImageChops.offset(rr, 3, 0), gg, ImageChops.offset(bb, -3, 0)))
                img.paste(ImageChops.offset(band, dx, 0), (0, y0))
            if r.random() < 0.5:   # ときどき、白い走査線
                y = r.randrange(h)
                ImageDraw.Draw(img).line([(0, y), (w, y)], fill=(255, 255, 255))
        else:
            img = self.img
        self.photo = ImageTk.PhotoImage(img)
        self.label.config(image=self.photo)

    def next_image(self, step=1):
        ads = list_ads()
        if not ads:
            return
        i = ads.index(self.d["image"]) if self.d["image"] in ads else -1
        self.set(image=ads[(i + step) % len(ads)])

    def build_ad(self):
        d0 = self.d
        k = AD_SKINS.get(d0["ad_skin"], AD_SKINS["classic"])
        wd, hd = self.W // P, self.H // P
        fr = Image.new("RGB", (wd, hd), k["face"])
        d = ImageDraw.Draw(fr)
        d.rectangle([0, 0, wd - 1, hd - 1], outline=k["dark"])
        d.line([(1, 1), (wd - 2, 1)], fill=k["light"])
        d.line([(1, 1), (1, hd - 2)], fill=k["light"])
        d.line([(wd - 2, 1), (wd - 2, hd - 2)], fill=k["shade"])
        d.line([(1, hd - 2), (wd - 2, hd - 2)], fill=k["shade"])
        x0, x1 = AD_B, wd - AD_B - 1
        for x in range(x0, x1 + 1):   # タイトルバー（左から右へ色が変わる）
            d.line([(x, AD_B), (x, AD_B + AD_TB - 2)], fill=mix(k["t1"], k["t2"], (x - x0) / max(1, x1 - x0)))
        title = AD_TITLES[d0["ad_title"] % len(AD_TITLES)]
        bx = x1 - 3 * 9 + 1
        px_text(d, x0 + 3, AD_B + 3, title, k["ttext"], max_w=bx - x0 - 6)
        self.ad_close = None
        for i, g in enumerate(("min", "max", "close")):
            bxx = bx + i * 9
            box = [bxx, AD_B + 1, bxx + 7, AD_B + 8]
            d.rectangle(box, fill=k["close"] if g == "close" else k["face"] if d0["ad_skin"] == "classic" else k["light"],
                        outline=k["dark"])
            c = k["xcol"] if g == "close" else (0, 0, 0)
            if g == "min":
                d.line([(bxx + 2, AD_B + 6), (bxx + 5, AD_B + 6)], fill=c)
            elif g == "max":
                d.rectangle([bxx + 2, AD_B + 3, bxx + 5, AD_B + 6], outline=c)
            else:
                for t in range(4):
                    d.point([(bxx + 2 + t, AD_B + 3 + t), (bxx + 5 - t, AD_B + 3 + t)], fill=c)
                self.ad_close = tuple(v * P for v in box)
        self.ad_frame = fr
        self.ad_bgimg = ad_pattern(d0["ad_bg"], self.dw, self.dh, AD_PALETTES[d0["ad_pal"] % len(AD_PALETTES)])
        self.ad_font = load_font(_GOTHIC, 11)
        self.ad_state = None

    def build_portal(self):
        rnd = random.Random(self.d["portal_seed"] or hash(self.d["text"]) & 0xFFFF)
        wd, hd = self.W // P, self.H // P
        bgc = rnd.choice(PT_BGS)
        fr = Image.new("RGB", (wd, hd), bgc)
        d = ImageDraw.Draw(fr)
        if rnd.random() < 0.4:   # うすい方眼
            for x in range(0, wd, 8):
                d.line([(x, 0), (x, hd)], fill=mix(bgc, (120, 140, 200), 0.12))
            for y in range(0, hd, 8):
                d.line([(0, y), (wd, y)], fill=mix(bgc, (120, 140, 200), 0.12))
        d.rectangle([0, 0, wd - 1, hd - 1], outline=(0, 0, 0))
        d.line([(1, 1), (wd - 2, 1)], fill=(255, 255, 255))
        d.line([(1, 1), (1, hd - 2)], fill=(255, 255, 255))
        d.line([(wd - 2, 1), (wd - 2, hd - 2)], fill=(128, 128, 128))
        d.line([(1, hd - 2), (wd - 2, hd - 2)], fill=(128, 128, 128))
        # 見出し：MAIN MENU と、サイトのロゴ
        h1, h2 = rnd.choice(PT_HEADS)
        x0, x1 = PT_B, wd - PT_B - 1
        for x in range(x0, x1 + 1):
            d.line([(x, PT_B), (x, PT_B + PT_HEAD - 2)], fill=mix(h1, h2, (x - x0) / max(1, x1 - x0)))
        px_text(d, x0 + 4, PT_B + 4, "MAIN MENU", (0, 0, 0), 2)
        px_text(d, x0 + 3, PT_B + 3, "MAIN MENU", (255, 255, 255), 2)
        site = rnd.choice(PT_SITES)
        logo = _txt(site, load_font(rnd.choice(PT_FONTS), 11), (255, 255, 255), 1, h1)
        mark = Image.new("RGBA", (12, 11), rnd.choice(PT_COLORS) + (255,))
        md = ImageDraw.Draw(mark)
        md.rectangle([0, 0, 11, 10], outline=(255, 255, 255, 255))
        px_text(md, 2, 3, site[:2] if site[:2].isascii() else "SN", (255, 255, 255))
        lx = x1 - logo.width - mark.width - 4
        if lx > x0 + px_text_w("MAIN MENU", 2) + 6:
            fr.paste(mark, (lx, PT_B + 2), mark)
            fr.paste(logo, (lx + mark.width + 2, PT_B + max(0, (PT_HEAD - 1 - logo.height) // 2)), logo)
        # 看板のまわりの、ロゴをぎっしり
        cx0, cy0 = PT_B + PT_SIDE, PT_B + PT_HEAD + PT_TOP
        regions = [(PT_B + 2, PT_B + PT_HEAD + 2, wd - 2 * PT_B - 4, PT_TOP - 4),           # 上
                   (PT_B + 2, cy0, PT_SIDE - 5, self.dh),                                  # 左
                   (cx0 + self.dw + 3, cy0, PT_SIDE - 5, self.dh),                         # 右
                   (PT_B + 2, cy0 + self.dh + 3, wd - 2 * PT_B - 4, PT_BOTTOM - 5)]        # 下
        tiles = []
        for r in regions:
            tiles += pack_tiles(rnd, r, 0.08)
        self.pt_frames = []
        for blink in (0, 1):
            f = fr.copy()
            for t, x, y, bl in tiles:
                if bl and blink:   # 点滅するロゴ：色を反転して見せる
                    rgb = Image.eval(t.convert("RGB"), lambda v: 255 - v)
                    f.paste(rgb, (x, y), t)
                else:
                    f.paste(t, (x, y), t)
            # 看板のまわりの、へこんだ枠
            fd = ImageDraw.Draw(f)
            fd.rectangle([cx0 - 2, cy0 - 2, cx0 + self.dw + 1, cy0 + self.dh + 1], outline=(128, 128, 128))
            fd.line([(cx0 - 2, cy0 + self.dh + 1), (cx0 + self.dw + 1, cy0 + self.dh + 1), (cx0 + self.dw + 1, cy0 - 2)],
                    fill=(255, 255, 255))
            fd.rectangle([cx0 - 1, cy0 - 1, cx0 + self.dw, cy0 + self.dh], outline=(0, 0, 0))
            self.pt_frames.append(f.resize((self.W, self.H), Image.NEAREST))
        self.pt_bg = (12, 10, 22)
        self.ad_state = None

    def portal_overlay(self, img):
        blink = int((time.time() - self.start) / 0.5) % 2
        full = self.pt_frames[blink].copy()
        full.paste(img, self.ad_off)
        return full

    def overlay(self, img):
        """広告やポータルのまわりをつけた、ウィンドウ全体の絵。"""
        if self.ad:
            return self.ad_overlay(img)
        if self.portal:
            return self.portal_overlay(img)
        return img

    def ad_overlay(self, img):
        """広告のふち・タイトル・点滅する NEW! と「クリック！」の帯を、看板の絵のまわりにつける。"""
        d0 = self.d
        blink = int((time.time() - self.start) / 0.5) % 2
        full = self.ad_frame.resize((self.W, self.H), Image.NEAREST)
        full.paste(img, self.ad_off)
        wd, hd = self.W // P, self.H // P
        cta = Image.new("RGB", (wd - 2 * AD_B, AD_CTA), (0, 0, 0))
        cd = ImageDraw.Draw(cta)
        cd.fontmode = "1"
        bgc = [(255, 230, 0), (255, 40, 90)][blink]
        fgc = [(220, 0, 40), (255, 255, 255)][blink]
        cd.rectangle([0, 0, cta.width - 1, cta.height - 1], fill=bgc, outline=(0, 0, 0))
        text = "▶ " + AD_CTAS[d0["ad_cta"] % len(AD_CTAS)]
        tw = self.ad_font.getlength(text)
        if tw > cta.width - 4:   # 細い広告では、▶ をはぶく
            text = text[2:]
            tw = self.ad_font.getlength(text)
        cd.text(((cta.width - tw) / 2, 1), text, font=self.ad_font, fill=fgc)
        full.paste(cta.resize((cta.width * P, cta.height * P), Image.NEAREST), (AD_B * P, (hd - AD_B - AD_CTA) * P))
        # NEW! のバッジ（中身の右上）
        bs = 22
        bcol = [(255, 230, 0), (255, 120, 0)][blink]
        badge = starburst(bs, bcol, (120, 0, 0))
        word = AD_BADGES[d0["ad_badge"] % len(AD_BADGES)]
        bd = ImageDraw.Draw(badge)
        px_text(bd, (bs - px_text_w(word)) // 2, bs // 2 - 2, word, (200, 0, 30))
        bx = wd - AD_B - bs - 1
        by = AD_B + AD_TB + 1
        big = badge.resize((bs * P, bs * P), Image.NEAREST)
        full.paste(big, (bx * P, by * P), big)
        return full

    def build_neon(self):
        d0 = self.d
        size = FONT_PX[d0["size"]]
        font = load_font(FONTS.get(d0["font"], FONTS["gothic"])[1], size)
        chars, tw, th = layout_chars(self.shown_text, font, size, d0["vertical"])
        mark = d0["mark"] if d0["mark"] in MARKS else None
        if mark:   # マークは、文字の前（横長なら左、縦長なら上）に置く
            ms = size if d0["vertical"] else round(size * 1.1)
            gap = max(3, size // 5)
            mm = mark_mask(mark, ms)
            if d0["vertical"]:
                chars = [(m, x, y + ms + gap) for m, x, y in chars]
                chars.insert(0, (mm, (tw - ms) // 2, 0))
                th += ms + gap
            else:
                chars = [(m, x + ms + gap, y) for m, x, y in chars]
                chars.insert(0, (mm, 0, (th - ms) // 2))
                tw += ms + gap
        pad = 6
        self.dw, self.dh = tw + 2 * (pad + GLOW), th + 2 * (pad + GLOW)
        ox, oy = GLOW + pad, GLOW + pad
        self.inner = (GLOW, GLOW, self.dw - GLOW - 1, self.dh - GLOW - 1)
        col = NEON[d0["color"]][1]
        c2 = NEON[d0["color2"]][1] if d0["color2"] in NEON else (255, 255, 255)
        hot = mix(col, (255, 255, 255), 0.55)
        n = 1 if size < 22 else 2
        # 1文字ずつ：[(マスク, 芯の色, 光の色), ...]
        self.parts = []
        for i, (m, x, y) in enumerate(chars):
            full = Image.new("L", (self.dw, self.dh), 0)
            full.paste(m, (ox + x, oy + y))
            if mark and i == 0:   # マークは、ふちのネオンと同じ色（なければ同じ色）
                mc = c2 if d0["color2"] in NEON else col
                self.parts.append([(full, mix(mc, (255, 255, 255), 0.5), mc)])
                continue
            style = d0["style"]
            if style == "solid":
                core = erode(full, 1)
                self.parts.append([(ImageChops.subtract(full, core), col, col),
                                   (core, mix(col, (255, 255, 255), 0.28), col)])   # 白くとばしすぎない
            elif style == "double":
                e1, e2, e3 = erode(full, 1), erode(full, 2), erode(full, 3)
                inner = ImageChops.subtract(e2, e3)
                self.parts.append([(ImageChops.subtract(full, e1), mix(col, (255, 255, 255), 0.3), col),
                                   (inner, mix(c2, (255, 255, 255), 0.5), c2)])
            else:
                self.parts.append([(ImageChops.subtract(full, erode(full, n)), hot, col)])
        # 金具（看板をとめる細い棒）と、消えているときのガラス管
        base = Image.new("RGBA", (self.dw, self.dh), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        rod = (52, 50, 62, 255)
        x0, y0, x1, y1 = self.inner
        if d0["vertical"]:
            for x in (x0 + 2, x1 - 2):
                d.line([(x, y0 - 4), (x, y1 + 2)], fill=rod)
            for y in range(y0 + 4, y1, 18):
                d.line([(x0 + 2, y), (x1 - 2, y)], fill=rod)
        else:
            for y in (y0 + 2, y1 - 2):
                d.line([(x0 - 2, y), (x1 + 2, y)], fill=rod)
            for x in range(x0 + 4, x1, 22):
                d.line([(x, y0 + 2), (x, y1 - 2)], fill=rod)
        # ふちのネオン管（流れる点線は、コマごとのマスクを用意）
        self.borders = []
        if d0["color2"] in NEON:
            bs = d0["border"]
            if bs == "dash":
                path = rounded_path(x0 + 1, y0 + 1, x1 - 1, y1 - 1, 5)
                for ph in range(4):
                    b = Image.new("L", (self.dw, self.dh), 0)
                    b.putdata([0] * (self.dw * self.dh))
                    bd = ImageDraw.Draw(b)
                    bd.point([p for k, p in enumerate(path) if (k + ph * 2) % 8 < 4], fill=255)
                    self.borders.append(b)
            else:
                b = Image.new("L", (self.dw, self.dh), 0)
                bd = ImageDraw.Draw(b)
                bd.rounded_rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], radius=5, outline=255, width=1)
                if bs == "double":
                    bd.rounded_rectangle([x0 + 4, y0 + 4, x1 - 4, y1 - 4], radius=3, outline=255, width=1)
                self.borders.append(b)
        glass = mix(col, (0, 0, 0), 0.72)
        for parts in self.parts:
            for m, _, gc in parts:
                base.paste(mix(gc, (0, 0, 0), 0.72) + (255,), (0, 0), m)
        if self.borders:
            allb = self.borders[0] if len(self.borders) == 1 else Image.new("L", (self.dw, self.dh), 0)
            if len(self.borders) > 1:
                ImageDraw.Draw(allb).point(rounded_path(x0 + 1, y0 + 1, x1 - 1, y1 - 1, 5), fill=255)
            base.paste(mix(c2, (0, 0, 0), 0.72) + (255,), (0, 0), allb)
        del glass
        self.base = base
        self.flick = [0] * len(self.parts)   # ちらつき中のコマ（0 = ふつう）
        self.on_at = [0.15 + i * 0.12 + random.random() * 0.1 for i in range(len(self.parts))]   # つきはじめ
        self.state = None
        self.lit_chars = self.neon_state()[0]

    def neon_state(self):
        """いま点いている文字（と、ふち・点線のコマ）。"""
        now = time.time() - self.start
        lit = self.lit()
        n = len(self.parts)
        anim = self.d["anim"]
        on = []
        border_on = lit and now >= 0.1
        for i in range(n):
            ok = lit and now >= self.on_at[i]
            if ok and anim == "chase":   # 1文字ずつ点いて、ぜんぶ点いたら少しして消える、のくり返し
                cycle = n * 0.25 + 2.2
                t = (now - self.on_at[-1] - 0.3) % cycle if now > self.on_at[-1] + 0.3 else None
                if t is not None:
                    ok = i * 0.25 <= t < n * 0.25 + 1.6
            elif ok and anim == "blink":   # ときどき、ぜんぶがチカチカ
                t = now % 6
                ok = not (t > 4.4 and int(t * 5) % 2)
                border_on = border_on and ok
            if self.flick[i] and FLICK[self.flick[i]] == 0:
                ok = False
            on.append(ok)
        phase = int(now / 0.12) % 4 if len(self.borders) > 1 else 0
        return tuple(on), border_on, phase

    def build_led(self):
        n = LED_LEN[self.d["size"]]
        vertical = self.d["vertical"]
        self.cols, self.rows = (16, n) if vertical else (n, 16)
        case = 3
        bw, bh = self.cols * 2, self.rows * 2
        self.dw, self.dh = bw + 2 * (case + GLOW), bh + 2 * (case + GLOW)
        self.board_at = (GLOW + case, GLOW + case)
        self.inner = (GLOW, GLOW, self.dw - GLOW - 1, self.dh - GLOW - 1)
        base = Image.new("RGBA", (self.dw, self.dh), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        x0, y0, x1, y1 = self.inner
        d.rectangle([x0, y0, x1, y1], fill=(64, 66, 80, 255), outline=(14, 14, 20, 255))
        d.line([(x0 + 1, y0 + 1), (x1 - 1, y0 + 1)], fill=(118, 120, 136, 255))
        d.line([(x0 + 1, y1 - 1), (x1 - 1, y1 - 1)], fill=(40, 40, 52, 255))
        for sx, sy in ((x0 + 1, y0 + 1), (x1 - 1, y0 + 1), (x0 + 1, y1 - 1), (x1 - 1, y1 - 1)):
            d.point((sx, sy), fill=(170, 172, 186, 255))
        bx, by = self.board_at
        d.rectangle([bx - 1, by - 1, bx + bw, by + bh], fill=(12, 9, 11, 255))
        self.base = base
        # 文字の帯（1ドット = LED 1個）
        font = load_font(LED_FONT, 16)
        text = one_line(self.shown_text)
        if vertical:
            chars = [ch for ch in text if ch.strip()]
            strip = Image.new("L", (16, max(1, len(chars)) * 16), 0)
            for i, ch in enumerate(chars):
                g = Image.new("L", (16, 16), 0)
                gd = ImageDraw.Draw(g)
                gd.fontmode = "1"
                b = font.getbbox(ch)
                gd.text(((16 - (b[2] - b[0])) // 2 - b[0], (16 - (b[3] - b[1])) // 2 - b[1]), ch, font=font, fill=255)
                if ch in ROTATE_V:
                    g = g.rotate(-90)
                strip.paste(g, (0, i * 16))
            length = strip.height
        else:
            b = font.getbbox("国")
            w = max(1, round(font.getlength(text)))
            strip = Image.new("L", (w, 16), 0)
            sd = ImageDraw.Draw(strip)
            sd.fontmode = "1"
            sd.text((0, (16 - (b[3] - b[1])) // 2 - b[1]), text, font=font, fill=255)
            length = w
        view = self.rows if vertical else self.cols
        self.scroll = length > view
        if self.scroll:   # 入りきらない：前に1画面ぶんの空白をつけて、ぐるぐる流す
            gap = view
            if vertical:
                s2 = Image.new("L", (16, length + gap), 0)
                s2.paste(strip, (0, gap))
            else:
                s2 = Image.new("L", (length + gap, 16), 0)
                s2.paste(strip, (gap, 0))
            self.strip, self.period = s2, length + gap
            first = gap
        else:             # 入る：まん中にとめる
            s2 = Image.new("L", (self.cols, self.rows), 0)
            first = ((self.cols - strip.width) // 2) if not vertical else ((self.rows - strip.height) // 2)
            s2.paste(strip, ((self.cols - strip.width) // 2, (self.rows - strip.height) // 2))
            self.strip, self.period = s2, 1
        # 色の帯（虹色なら、1文字ぶん＝16個ごとに色を変える）
        col = NEON[self.d["color"]][1]
        colors = Image.new("RGB", self.strip.size, col)
        if self.d["led_style"] == "rainbow":
            cd = ImageDraw.Draw(colors)
            length_px = self.strip.height if vertical else self.strip.width
            for k in range(0, length_px, 16):
                c = RAINBOW[((k - first) // 16) % len(RAINBOW)]
                if vertical:
                    cd.rectangle([0, k, 15, k + 15], fill=c)
                else:
                    cd.rectangle([k, 0, k + 15, 15], fill=c)
        self.colors = colors
        self.led_col = col
        self.offset = 0.0
        s = 2 * P
        cell = Image.new("L", (s, s), 0)
        ImageDraw.Draw(cell).rectangle([0, 0, s - 2, s - 2], fill=255)   # 小さいので、丸より四角のほうが LED らしく見える
        mask = Image.new("L", (self.cols * s, self.rows * s), 0)
        for yy in range(self.rows):
            for xx in range(self.cols):
                mask.paste(cell, (xx * s, yy * s))
        self.led_mask = mask
        self.state = None

    def build_board(self):
        size = FONT_PX[self.d["size"]]
        font = load_font(FONTS.get(self.d["font"], FONTS["gothic"])[1], size)
        chars, tw, th = layout_chars(self.shown_text, font, size, self.d["vertical"])
        box = self.d["light"] == "box"
        pad = 7
        top = 2 if box else 9   # 上のランプのぶん
        self.dw, self.dh = tw + 2 * (pad + GLOW), th + 2 * pad + top + 2 * GLOW
        px0, py0 = GLOW, GLOW + top
        px1, py1 = self.dw - GLOW - 1, self.dh - GLOW - 1
        self.inner = (px0, GLOW, px1, py1)
        self.panel_box = (px0, py0, px1, py1)
        panel = PANEL.get(self.d["color2"], PANEL["cream"])[1]
        self.panel_col = panel
        ink = NEON[self.d["color"]][1]
        base = Image.new("RGBA", (self.dw, self.dh), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        if box:   # 行灯：金属のふちに、光る板
            d.rectangle([px0, py0, px1, py1], fill=(60, 60, 72, 255), outline=(20, 16, 20, 255))
            d.rectangle([px0 + 2, py0 + 2, px1 - 2, py1 - 2], fill=panel + (255,))
        else:
            d.rectangle([px0, py0, px1, py1], fill=panel + (255,), outline=(20, 16, 20, 255))
            d.rectangle([px0 + 2, py0 + 2, px1 - 2, py1 - 2], outline=mix(panel, (255, 255, 255), 0.4) + (255,))
        textm = Image.new("L", (self.dw, self.dh), 0)
        for m, x, y in chars:
            textm.paste(m, (px0 + pad + x, py0 + pad + y), m)
        if not box:
            base.paste(mix(panel, (0, 0, 0), 0.45) + (255,), (1, 1), textm)
        base.paste(ink + (255,), (0, 0), textm)
        self.lamps = []
        light = Image.new("L", (self.dw, self.dh), 0)
        ld = ImageDraw.Draw(light)
        if box:
            ld.rectangle([px0 + 2, py0 + 2, px1 - 2, py1 - 2], fill=255)
        else:   # ランプ（腕と、かさ）
            n = max(2, (px1 - px0) // 40 + 1)
            for i in range(n):
                lx = px0 + round((px1 - px0) * (i + 0.5) / n)
                d.line([(lx, py0), (lx, py0 - 5), (lx + 3, py0 - 7)], fill=(40, 40, 50, 255))
                d.polygon([(lx + 1, py0 - 8), (lx + 6, py0 - 8), (lx + 7, py0 - 5), (lx, py0 - 5)], fill=(60, 60, 72, 255))
                self.lamps.append((lx + 3, py0 - 4))
            for lx, ly in self.lamps:
                ld.ellipse([lx - 16, ly - 4, lx + 16, ly + 22], fill=255)
            light = light.filter(ImageFilter.GaussianBlur(10))
        self.base = base
        self.lamp_light = light
        self.box = box
        # まわりの電球
        self.bulbs = []
        if self.d["bulbs"]:
            per = list(range(px0 + 3, px1 - 1, 5))
            side = list(range(py0 + 3, py1 - 1, 5))
            self.bulbs = ([(x, py0) for x in per] + [(px1, y) for y in side] +
                          [(x, py1) for x in reversed(per)] + [(px0, y) for y in reversed(side)])
        self.state = None

    # --- 描く ---
    def background(self):
        x, y = self.t.winfo_x(), self.t.winfo_y()
        bg = self.d["bg"]
        if bg == "wall" and self.app.wall is not None:
            return self.app.wall.crop((x, y, x + self.cw, y + self.ch))
        if bg == "ad":
            return self.ad_bgimg.resize((self.cw, self.ch), Image.NEAREST)
        if bg == "portal":
            return Image.new("RGB", (self.cw, self.ch), self.pt_bg)
        if bg == "brick":
            return brick_wall(self.dw, self.dh).resize((self.cw, self.ch), Image.NEAREST)
        return Image.new("RGB", (self.cw, self.ch), (10, 8, 14))

    def frame_layers(self):
        """いまの瞬間の (光の芯, 光の色)。どちらもドットの大きさ。"""
        kind, lit = self.d["kind"], self.lit()
        core = Image.new("RGB", (self.dw, self.dh), (0, 0, 0))
        glow = Image.new("RGB", (self.dw, self.dh), (0, 0, 0))
        if kind == "neon":
            on, border_on, phase = self.neon_state()
            for ok, parts in zip(on, self.parts):
                if ok:
                    for m, cc, gc in parts:
                        core.paste(cc, (0, 0), m)
                        glow.paste(gc, (0, 0), m)
            if self.borders and border_on:
                c2 = NEON[self.d["color2"]][1]
                b = self.borders[phase % len(self.borders)]
                core.paste(mix(c2, (255, 255, 255), 0.5), (0, 0), b)
                glow.paste(c2, (0, 0), b)
        elif kind == "board":
            if lit:
                warm = (255, 220, 150)
                phase = int((time.time() - self.start) / 0.35)
                for i, (bx, by) in enumerate(self.bulbs):
                    if (i + phase) % 3:
                        core.paste((255, 246, 210), (bx - 1, by - 1, bx + 1, by + 1))
                        glow.paste(warm, (bx - 1, by - 1, bx + 1, by + 1))
                for lx, ly in self.lamps:
                    glow.paste(warm, (lx - 2, ly - 1, lx + 3, ly + 1))
                if self.box:   # 行灯は、板そのものがまわりを照らす
                    x0, y0, x1, y1 = self.panel_box
                    glow.paste(mix(self.panel_col, (0, 0, 0), 0.35), (x0, y0, x1 + 1, y1 + 1))
        return core, glow

    def led_cells(self):
        """いま光っている LED（1ドット = LED 1個）と、その色。"""
        if not self.scroll:
            return self.strip, self.colors
        off = int(self.offset) % self.period
        if self.d["vertical"]:
            box = (0, off, 16, off + self.rows)
            size = (16, self.period * 2)
            at2 = (0, self.period)
        else:
            box = (off, 0, off + self.cols, 16)
            size = (self.period * 2, 16)
            at2 = (self.period, 0)
        out = []
        for src, mode in ((self.strip, "L"), (self.colors, "RGB")):
            big = Image.new(mode, size)
            big.paste(src, (0, 0))
            big.paste(src, at2)
            out.append(big.crop(box))
        return out[0], out[1]

    def led_blink_off(self):
        return self.d["led_style"] == "blink" and int((time.time() - self.start) / 0.6) % 2 == 1

    def render(self):
        self.render_pending = False
        if self.d["kind"] == "image":
            return self.render_image()
        W, H = self.cw, self.ch
        img = self.background()
        if img.size != (W, H):
            img = img.resize((W, H))
        x0, y0, x1, y1 = self.inner
        lit = self.lit()
        if self.d["bg"] == "wall":   # 看板のまわりを少し暗くして、光を見やすく（ふちでは 0 なので、壁紙とつながる）
            dark = soft_dark(self.dw, self.dh, (x0 - 2, y0 - 2, x1 + 2, y1 + 2), 0.42 if lit else 0.2)
            img = Image.composite(Image.new("RGB", (W, H), (8, 6, 12)), img, dark.resize((W, H), Image.BILINEAR))
        kind = self.d["kind"]
        if kind == "led":
            cells, colors = self.led_cells()
            on = lit and not self.led_blink_off()
            if on:
                glow = Image.new("RGB", (self.dw, self.dh), (0, 0, 0))
                big_cells = cells.resize((self.cols * 2, self.rows * 2), Image.NEAREST)
                glow.paste(colors.resize(big_cells.size, Image.NEAREST), self.board_at, big_cells)
                img = ImageChops.screen(img, glow_of(glow, 0.8).resize((W, H), Image.BILINEAR))
            base = self.base.resize((W, H), Image.NEAREST)
            img.paste(base, (0, 0), base)
            s = 2 * P
            onm = cells.resize((self.cols * s, self.rows * s), Image.NEAREST)
            led = Image.new("RGB", onm.size, mix(self.led_col, (0, 0, 0), 0.84))
            cbig = colors.resize(onm.size, Image.NEAREST)
            if on:
                led.paste(cbig, (0, 0), onm)
            else:
                led.paste(Image.eval(cbig, lambda v: v // 6), (0, 0), onm)
            bx, by = self.board_at
            img.paste(led, (bx * P, by * P), self.led_mask)
            return self.show(img)
        core, glow = self.frame_layers()
        if kind == "board":
            base = self.base.resize((W, H), Image.NEAREST)
            alpha = base.getchannel("A")
            if self.box:   # 行灯：点いていると明るく、消えていると少しくすむ
                lightmap = self.lamp_light.point(lambda v: 255 - int((255 - v) * 0.0) if lit else 175)
            else:          # ランプで照らす（明かりの届かないところは暗め）
                lightmap = self.lamp_light.point(lambda v: (150 if lit else 120) + int(v * (105 if lit else 40) / 255))
            shaded = ImageChops.multiply(base.convert("RGB"), Image.merge("RGB", [lightmap.resize((W, H), Image.BILINEAR)] * 3))
            img = ImageChops.screen(img, glow_of(glow, 1.1).resize((W, H), Image.BILINEAR))
            img.paste(shaded, (0, 0), alpha)
            if lit and not self.box:   # ランプの近くに、あたたかい光をのせる
                warm = Image.new("RGB", (self.dw, self.dh), (0, 0, 0))
                warm.paste((90, 60, 20), (0, 0), self.lamp_light)
                img = ImageChops.add(img, warm.resize((W, H), Image.BILINEAR))
        else:
            img = ImageChops.screen(img, glow_of(glow, 1.25).resize((W, H), Image.BILINEAR))
            base = self.base.resize((W, H), Image.NEAREST)
            img.paste(base, (0, 0), base)
        onmask = core.convert("L").point(lambda v: 255 if v else 0)
        img.paste(core.resize((W, H), Image.NEAREST), (0, 0), onmask.resize((W, H), Image.NEAREST))
        return self.show(img)

    def show(self, img):
        if self.ad or self.portal:
            img = self.overlay(img)
        elif self.d["bg"] == "wall" and self.app.wall is not None:
            x, y = self.t.winfo_x(), self.t.winfo_y()
            img = Image.composite(img, self.app.wall.crop((x, y, x + self.W, y + self.H)), edge_feather(self.W, self.H))
        self.photo = ImageTk.PhotoImage(img)
        self.label.config(image=self.photo)

    def request_render(self):
        if not self.render_pending:
            self.render_pending = True
            self.t.after_idle(self.render)

    # --- 動き ---
    def loop(self):
        """アニメ：ネオンのちらつき・電球・LED を流す・時計や曲名の更新。"""
        self.job = None
        kind = self.d["kind"]
        changed = False
        if self.d["source"] != "text" and self.current_text() != self.shown_text:
            self.rebuild()
            return
        lit = self.lit()
        if kind == "image":
            st = self.img_state()
            if st != self.state:
                self.state = st
                self.render()
            self.job = self.t.after(70, self.loop)
            return
        if kind == "neon":
            now = time.time() - self.start
            for i in range(len(self.parts)):
                if self.flick[i]:
                    self.flick[i] = (self.flick[i] + 1) % len(FLICK)
                elif lit and self.d["flicker"] and now > 3 and random.random() < 0.0025:
                    self.flick[i] = 1
            st = self.neon_state()
            changed = st != self.state
            self.state = st
            delay = 60
        elif kind == "board":
            st = (int((time.time() - self.start) / 0.35) % 3 if self.bulbs else 0, lit)
            changed = st != self.state
            self.state = st
            delay = 100
        else:
            st = (lit, self.led_blink_off())
            if self.scroll and lit:
                old = int(self.offset)
                self.offset += (10 + self.d["speed"] * 6) * 0.03
                changed = int(self.offset) != old
            changed = changed or st != self.state
            self.state = st
            delay = 30
        if self.ad or self.portal:
            ab = int((time.time() - self.start) / 0.5) % 2
            changed = changed or ab != self.ad_state
            self.ad_state = ab
        if changed:
            self.render()
        self.job = self.t.after(delay, self.loop)

    def rebuild(self):
        if self.job:
            self.t.after_cancel(self.job)
            self.job = None
        x, y = self.t.winfo_x(), self.t.winfo_y()
        self.build()
        self.t.geometry(f"{self.W}x{self.H}+{x}+{y}")
        self.t.update_idletasks()
        self.render()
        self.loop()

    def place(self):
        self.t.geometry(f"{self.W}x{self.H}+{self.d['x']}+{self.d['y']}")
        self.t.update_idletasks()
        self.render()

    def move_to(self, x, y):
        self.d["x"], self.d["y"] = x, y
        self.place()

    # --- 操作 ---
    def on_press(self, e):
        self._press = (e.x_root, e.y_root, self.t.winfo_x(), self.t.winfo_y())

    def on_drag(self, e):
        px, py, wx, wy = self._press
        self.t.geometry(f"+{wx + e.x_root - px}+{wy + e.y_root - py}")
        if self.d["bg"] == "wall":
            self.request_render()

    def on_release(self, e):
        px, py, wx, wy = self._press
        if self.ad and self.ad_close and abs(e.x_root - px) < 4 and abs(e.y_root - py) < 4:
            lx, ly = e.x_root - self.t.winfo_rootx(), e.y_root - self.t.winfo_rooty()
            x0, y0, x1, y1 = self.ad_close
            if x0 <= lx <= x1 + P and y0 <= ly <= y1 + P:
                self.app.remove_sign(self)
                return
        if self.d["kind"] == "image" and abs(e.x_root - px) < 4 and abs(e.y_root - py) < 4:
            lx, ly = e.x_root - self.t.winfo_rootx(), e.y_root - self.t.winfo_rooty()
            k = self.img_k
            if lx >= self.W - 24 * k and ly <= 22 * k:   # 絵の右上（× ボタンのあたり）
                self.app.remove_sign(self)
                return
        self.d["x"], self.d["y"] = self.t.winfo_x(), self.t.winfo_y()
        self.app.save()
        self.render()

    def edit_text(self):
        if self.d["kind"] == "image":
            return self.next_image()
        s = ask_text(self.app.root, NEON_THEME, "看板の文字", "看板に出す言葉を入れてね", initial=self.d["text"], near=self.t)
        if s is not None and s.strip():
            self.d["text"] = s.strip()
            self.d["source"] = "text"
            self.set(text=self.d["text"])

    def set(self, **kw):
        self.d.update(kw)
        self.app.save()
        self.rebuild()

    def close(self):
        if self.job:
            self.t.after_cancel(self.job)
        self.t.destroy()


class App:
    def __init__(self):
        self.cfg = dict(DEFAULT_CONFIG)
        self.cfg.update(load_json(CONFIG_PATH, {}))
        if not SHOW_WALL:
            for key in ("signs", "prev_signs"):
                self.cfg[key] = [dict(d, bg=PLAIN_BG) if d.get("bg", "wall") == "wall" else d for d in self.cfg[key]]
            if self.cfg["random_bg"] == "wall":
                self.cfg["random_bg"] = "mix"
        self.root = tk.Tk()
        self.root.withdraw()
        log_errors(self.root, "neon_sign_error.txt")
        self.root.title(f"ドットネオン街 ver.{APP_VERSION}")
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "neon_sign.ico"))
        except tk.TclError:
            pass
        self.menu = PixelMenu(self.root, lambda: NEON_THEME, title="NEON.EXE")
        self.wall_sig = None
        self.wall = None
        self.load_wall()
        self.signs = []
        if self.cfg["open_random"] and self.cfg["signs"]:
            self.arrange_random(keep_prev=True)
        else:
            if not self.cfg["signs"]:
                sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                spots = [(0.52, 0.10), (0.50, 0.42), (0.86, 0.12), (0.76, 0.12)]
                self.cfg["signs"] = [dict(s, x=int(sw * fx), y=int(sh * fy)) for s, (fx, fy) in zip(STARTER, spots)]
            for data in self.cfg["signs"]:
                self.signs.append(Sign(self, data))
        self.save()
        self.root.after(4000, self.watch)

    # --- 壁紙 ---
    def wall_signature(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if self.cfg["wall"] != "auto":
            path, style, tile, bg = self.cfg["wall"], "10", "0", (0, 0, 0)
        else:
            path, style, tile, bg = wallpaper_info()
        try:
            mt = os.path.getmtime(path)
        except OSError:
            mt = 0
        return (path, mt, style, tile, bg, sw, sh)

    def load_wall(self):
        sig = self.wall_signature()
        if sig == self.wall_sig:
            return False
        self.wall_sig = sig
        path, _, style, tile, bg, sw, sh = sig
        self.wall = screen_wallpaper(path, sw, sh, style, tile, bg) if path else None
        return True

    def watch(self):
        """壁紙が変わったら（ランチャーの昼夜の切り替えなど）、追いかけて描きなおす。"""
        if self.load_wall():
            for s in self.signs:
                s.render()
        self.root.after(4000, self.watch)

    # --- 保存 ---
    def save(self):
        self.cfg["signs"] = [s.d for s in self.signs] if self.signs else self.cfg["signs"]
        save_json(CONFIG_PATH, self.cfg)

    # --- おまかせ ---
    def work_area(self):
        try:
            from ctypes import wintypes
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0):
                return r.left, r.top, r.right, r.bottom
        except Exception:
            pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def find_spot(self, w, h, taken, rnd=random, m=GLOW * P):
        """ほかの看板となるべく重ならない場所（光の余白 m は重なってもいい）。"""
        left, top, right, bottom = self.work_area()
        best, best_cost = None, None
        for _ in range(160):
            x = rnd.randint(left - m, max(left - m, right - w + m))
            y = rnd.randint(top - m, max(top - m, int(top + (bottom - top) * 0.8) - h + m))
            box = (x + m, y + m, x + w - m, y + h - m)
            cost = 0
            for b in taken:
                ix = max(0, min(box[2], b[2]) - max(box[0], b[0]))
                iy = max(0, min(box[3], b[3]) - max(box[1], b[1]))
                cost += ix * iy
            if best_cost is None or cost < best_cost:
                best, best_cost = (x, y), cost
                if cost == 0:
                    break
        return best

    def place_new(self, data, taken):
        sign = Sign(self, dict(data, x=-3000, y=-3000))
        m = GLOW * P if data.get("bg") == "wall" else 0   # 透けない看板は、余白も見えるので重ならないように
        x, y = self.find_spot(sign.W, sign.H, taken, m=m)
        sign.move_to(x, y)
        taken.append((x + m, y + m, x + sign.W - m, y + sign.H - m))
        return sign

    def arrange_random(self, keep_prev=True):
        if keep_prev and self.signs:
            self.cfg["prev_signs"] = [dict(s.d) for s in self.signs]
        elif keep_prev and self.cfg["signs"]:
            self.cfg["prev_signs"] = [dict(s) for s in self.cfg["signs"]]
        for s in self.signs:
            s.close()
        self.signs = []
        taken = []
        used = set()
        n_portal = n_image = 0
        used_img = set()
        for _ in range(random.randint(3, 4) if self.cfg["random_bg"] in ("portal", "image") else random.randint(5, 6)):
            data = random_sign()
            for _ in range(5):   # 同じ言葉がかぶらないように
                if data["text"] not in used:
                    break
                data = random_sign()
            used.add(data["text"])
            data["bg"] = self.pick_bg()
            if data["bg"] == "portal" and self.cfg["random_bg"] == "mix" and n_portal >= 2:
                data["bg"] = self.plain_bg()   # ポータルは大きいので、まぜるときは2枚まで
            if data["bg"] == "portal":
                n_portal += 1
                data["size"] = "S" if data["size"] == "M" or data["kind"] == "led" else "M" if data["size"] == "L" else data["size"]
            data["portal_seed"] = random.randint(1, 10 ** 9)
            if data["bg"] == "image":
                img = None
                if not (self.cfg["random_bg"] == "mix" and n_image >= 3):   # まぜるときは3枚まで
                    img = random_image_sign(avoid=used_img)
                if img:
                    data = img
                    used_img.add(img["image"])
                    n_image += 1
                else:
                    data["bg"] = self.plain_bg()
            self.signs.append(self.place_new(data, taken))
        self.save()

    def add_random(self):
        taken = []
        for s in self.signs:
            m = GLOW * P if s.d["bg"] == "wall" else 0
            taken.append((s.d["x"] + m, s.d["y"] + m, s.d["x"] + s.W - m, s.d["y"] + s.H - m))
        data = dict(random_sign(), bg=self.pick_bg(), portal_seed=random.randint(1, 10 ** 9))
        if data["bg"] == "image":
            data = random_image_sign(avoid={s.d["image"] for s in self.signs}) or dict(data, bg=self.plain_bg())
        self.signs.append(self.place_new(data, taken))
        self.save()

    def undo_arrange(self):
        prev = self.cfg.get("prev_signs") or []
        if not prev:
            return
        now = [dict(s.d) for s in self.signs]
        for s in self.signs:
            s.close()
        self.signs = [Sign(self, d) for d in prev]
        self.cfg["prev_signs"] = now   # もう一度押すと、おまかせの並びに戻る
        self.save()

    # --- メニュー ---
    def popup(self, sign, e):
        self.menu.title = "NEON.EXE"
        self.menu.popup(lambda: self.menu_items(sign), e.x_root, e.y_root)

    def menu_items(self, sign):
        d = sign.d
        kind = d["kind"]

        def radio(key, pairs):
            return [{"type": "radio", "label": n, "checked": d[key] == v, "cmd": lambda v=v: sign.set(**{key: v})}
                    for n, v in pairs]

        def now(pairs, key):
            return next((n for n, k in pairs if k == d[key]), "")
        colors = [(n, k) for k, (n, _) in NEON.items()]
        head = [
            {"type": "cmd", "label": "おまかせで並べる", "cmd": self.arrange_random, "right": "5〜6枚"},
            {"type": "cmd", "label": "もとに戻す", "cmd": self.undo_arrange, "enabled": bool(self.cfg.get("prev_signs"))},
            {"type": "sub", "label": "看板を増やす", "items": [
                {"type": "cmd", "label": "おまかせで1枚", "cmd": self.add_random}, {"type": "sep"}] + [
                {"type": "cmd", "label": n, "cmd": lambda k=k: self.add_sign(sign, k)} for n, k in KINDS] + [
                {"type": "cmd", "label": "画像の広告", "cmd": lambda: self.add_sign(sign, "image"), "enabled": bool(list_ads())}]},
            {"type": "sep"},
            {"type": "head", "label": "この看板"},
        ]
        if kind == "image":
            ads = list_ads()
            return head + [
                {"type": "cmd", "label": "次の絵にする", "cmd": sign.next_image, "right": "ダブルクリック"},
                {"type": "sub", "label": "絵をえらぶ", "right": ad_label(d["image"]) if d["image"] else "",
                 "items": [{"type": "radio", "label": ad_label(a), "checked": d["image"] == a,
                            "cmd": lambda a=a: sign.set(image=a)} for a in ads] or [{"type": "head", "label": "絵がありません"}]},
                {"type": "cmd", "label": "画像のフォルダを開く", "cmd": self.open_ads_dir},
                {"type": "sub", "label": "動き", "items": radio("img_fx", IMG_FX), "right": now(IMG_FX, "img_fx")},
                {"type": "sub", "label": "大きさ", "items": radio("size", SIZES), "right": now(SIZES, "size")},
                {"type": "cmd", "label": "この看板を消す", "cmd": lambda: self.remove_sign(sign),
                 "enabled": len(self.signs) > 1, "right": "×"},
            ] + self.common_items()
        items = head + [
            {"type": "cmd", "label": "文字を変える…", "cmd": sign.edit_text, "right": "ダブルクリック"},
            {"type": "cmd", "label": "この看板をおまかせで変える", "cmd": lambda: sign.set(**dict(random_sign(), x=d["x"], y=d["y"], bg=d["bg"]))},
            {"type": "sub", "label": "出すもの", "items": radio("source", SOURCES), "right": now(SOURCES, "source")},
            {"type": "sub", "label": "種類", "items": radio("kind", KINDS), "right": now(KINDS, "kind")},
            {"type": "sub", "label": "向き", "items": radio("vertical", [("横長", False), ("縦長（縦書き）", True)]),
             "right": "縦長" if d["vertical"] else "横長"},
            {"type": "sub", "label": "文字の色" if kind == "board" else "光の色", "items": radio("color", colors),
             "right": NEON[d["color"]][0]},
        ]
        if kind == "neon":
            items += [
                {"type": "sub", "label": "管のかたち", "items": radio("style", TUBE_STYLES), "right": now(TUBE_STYLES, "style")},
                {"type": "sub", "label": "ふちのネオン管", "items": radio("color2", [("なし", "none")] + colors),
                 "right": NEON[d["color2"]][0] if d["color2"] in NEON else "なし"},
                {"type": "sub", "label": "ふちの形", "items": radio("border", BORDER_STYLES), "right": now(BORDER_STYLES, "border"),
                 "enabled": d["color2"] in NEON},
                {"type": "sub", "label": "マーク", "items": radio("mark", MARK_NAMES), "right": now(MARK_NAMES, "mark")},
                {"type": "sub", "label": "動き", "items": radio("anim", ANIMS), "right": now(ANIMS, "anim")},
                {"type": "check", "label": "ときどきちらつく", "checked": d["flicker"],
                 "cmd": lambda: sign.set(flicker=not d["flicker"])},
            ]
        if kind == "board":
            items += [
                {"type": "sub", "label": "板の色", "items": radio("color2", [(n, k) for k, (n, _) in PANEL.items()]),
                 "right": PANEL.get(d["color2"], PANEL["cream"])[0]},
                {"type": "sub", "label": "照らし方", "items": radio("light", LIGHTS), "right": now(LIGHTS, "light")},
                {"type": "check", "label": "まわりの電球", "checked": d["bulbs"], "cmd": lambda: sign.set(bulbs=not d["bulbs"])},
            ]
        if kind == "led":
            items += [
                {"type": "sub", "label": "光り方", "items": radio("led_style", LED_STYLES), "right": now(LED_STYLES, "led_style")},
                {"type": "sub", "label": "流れる速さ", "right": str(d["speed"]),
                 "items": radio("speed", [("ゆっくり", 1), ("ふつう", 4), ("はやめ", 7), ("かなりはやめ", 10)])},
            ]
        else:
            items.append({"type": "sub", "label": "書体", "items": radio("font", [(n, k) for k, (n, _) in FONTS.items()]),
                          "right": FONTS.get(d["font"], FONTS["gothic"])[0]})
        if d["bg"] == "portal":
            items.append({"type": "cmd", "label": "ポータルをおまかせで組みなおす",
                          "cmd": lambda: sign.set(portal_seed=random.randint(1, 10 ** 9))})
        if d["bg"] == "ad":
            items += [
                {"type": "sub", "label": "広告のまど", "items": radio("ad_skin", AD_SKIN_NAMES), "right": now(AD_SKIN_NAMES, "ad_skin")},
                {"type": "sub", "label": "広告の模様", "items": radio("ad_bg", AD_BG_NAMES), "right": now(AD_BG_NAMES, "ad_bg")},
                {"type": "cmd", "label": "広告の中身をおまかせで変える", "cmd": lambda: sign.set(**random_ad())},
            ]
        items += [
            {"type": "sub", "label": "大きさ", "items": radio("size", SIZES), "right": now(SIZES, "size")},
            {"type": "sub", "label": "背景", "items": radio("bg", BGS),
             "right": {"wall": "壁紙", "ad": "広告", "portal": "ポータル", "brick": "レンガ", "dark": "まっくら"}[d["bg"]]},
            {"type": "cmd", "label": "この看板を消す", "cmd": lambda: self.remove_sign(sign),
             "enabled": len(self.signs) > 1},
        ]
        return items + self.common_items()

    def common_items(self):
        """ぜんぶの看板に関わるメニュー（どの看板でも同じ）。"""
        items = [
            {"type": "sep"},
            {"type": "head", "label": "ぜんぶの看板"},
            {"type": "sub", "label": "壁紙の画像", "items": [
                {"type": "radio", "label": "Windows の壁紙を使う", "checked": self.cfg["wall"] == "auto",
                 "cmd": lambda: self.set_wall("auto")},
                {"type": "cmd", "label": "画像をえらぶ…", "cmd": self.choose_wall},
                {"type": "head", "label": "壁紙と同じ画像にすると、看板が透けて見えるよ"}],
             "right": "Windows" if self.cfg["wall"] == "auto" else "えらんだ画像"},
            {"type": "sub", "label": "おまかせの背景", "right": next(n for n, k in RANDOM_BGS if k == self.cfg["random_bg"]),
             "items": [{"type": "radio", "label": n, "checked": self.cfg["random_bg"] == k,
                        "cmd": lambda k=k: self.set_random_bg(k)} for n, k in RANDOM_BGS]},
            {"type": "check", "label": "開くたびにおまかせで並べる", "checked": self.cfg["open_random"],
             "cmd": self.toggle_open_random},
            {"type": "check", "label": "夜だけ点ける（昼は消灯）", "checked": self.cfg["night_only"],
             "cmd": self.toggle_night_only},
            {"type": "check", "label": "最前面に表示", "checked": self.cfg["topmost"], "cmd": self.toggle_topmost},
            {"type": "sep"},
            {"type": "cmd", "label": "終了", "cmd": self.quit},
            {"type": "head", "label": f"ドットネオン街 ver.{APP_VERSION}"},
        ]
        return [i for i in items if SHOW_WALL or i.get("label") != "壁紙の画像"]

    def open_ads_dir(self):
        os.makedirs(ADS_DIR, exist_ok=True)
        os.startfile(ADS_DIR)

    def add_sign(self, near, kind):
        if kind == "image":
            data = random_image_sign(avoid={s.d["image"] for s in self.signs})
            if data:
                self.signs.append(Sign(self, dict(data, x=near.d["x"] + 40, y=near.d["y"] + 40)))
                self.save()
            return
        data = dict(SIGN_DEFAULT, kind=kind, x=near.d["x"] + 40, y=near.d["y"] + 40,
                    text={"neon": "NEON", "led": "いらっしゃいませ　SugarOS 24", "board": "営業中"}[kind],
                    color={"neon": "cyan", "led": "amber", "board": "red"}[kind],
                    color2={"neon": "pink", "led": "none", "board": "cream"}[kind])
        self.signs.append(Sign(self, data))
        self.save()

    def remove_sign(self, sign):
        self.cfg["prev_signs"] = [dict(s.d) for s in self.signs]   # 「もとに戻す」で戻せるように
        sign.close()
        self.signs.remove(sign)
        self.save()

    def set_wall(self, value):
        self.cfg["wall"] = value
        self.save()
        if self.load_wall():
            for s in self.signs:
                s.render()

    def choose_wall(self):
        path = filedialog.askopenfilename(title="壁紙と同じ画像をえらぶ",
                                          filetypes=[("画像", "*.png *.jpg *.jpeg *.bmp *.webp"), ("すべて", "*.*")])
        if path:
            self.set_wall(path)

    def set_random_bg(self, k):
        self.cfg["random_bg"] = k
        self.save()

    def pick_bg(self):
        rb = self.cfg["random_bg"]
        if rb == "mix":
            if SHOW_WALL:
                return random.choice(["wall", "wall", "wall", "ad", "portal", "image", "image"])
            return random.choice(["dark", "dark", "brick", "ad", "ad", "portal", "image", "image"])
        return rb

    def plain_bg(self):
        """広告やポータルが入りきらないときの、ふつうの背景。"""
        return "wall" if SHOW_WALL else random.choice(["dark", "dark", "brick"])

    def toggle_open_random(self):
        self.cfg["open_random"] = not self.cfg["open_random"]
        self.save()

    def toggle_night_only(self):
        self.cfg["night_only"] = not self.cfg["night_only"]
        self.save()
        for s in self.signs:
            s.render()

    def toggle_topmost(self):
        self.cfg["topmost"] = not self.cfg["topmost"]
        self.save()
        for s in self.signs:
            s.t.attributes("-topmost", self.cfg["topmost"])

    def quit(self):
        self.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        App().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "neon_sign_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
