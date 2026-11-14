# -*- coding: utf-8 -*-
"""
のぞき窓 ver.1.6（NOZOKI.EXE）  —  SugarOS 24 のデスクトップアート担当
開くたびに、窓5〜6枚をおまかせで並べる（見た目・大きさ・位置・背景・エフェクトがランダム。キャラが写る場所に集まる）。
右クリック →「おまかせで並べなおす」でいつでも振り直し。
右クリック →「セット」で、いまの並び（窓の種類・位置・大きさ・背景・エフェクト）を名前をつけて記憶・呼び出し。設定で「開くたびにおまかせで並べる」を切ると、前の配置で開く。
1枚の絵を「画面そのもの」に貼りつけて、小窓をのぞき窓にする。
窓を動かすと、その場所にある絵の部分が見える。窓をいくつも並べると、複数の窓で1枚の絵ができあがる。

絵は2層:
  キャラ絵 … 背景が透明な PNG。全部の窓で共通で、窓をまたいでつながる（大きさ・位置・ドラッグで動かす）
  背景     … 窓ごとに選べる。共通の絵 / 透明（デスクトップが透ける）/ 単色・模様 / その窓だけの画像

エフェクト（窓ごとに選べる。右クリック →「エフェクト」）:
  窓ぜんぶに … 減色＋網点 / ゲーム機の4色 / モノクロ / セピア / 走査線 / VHS / グリッチ / 暗視カメラ / サーモグラフィ
  キャラだけに … 色ずれ / デュオトーン / 色相まわし / ネガ反転 / 漫画の網点 / 線画だけ / グロー

窓の見た目（窓ごとに選べる）:
  ふつう         … シンプルな窓
  ゲーム         … RPG風の窓。セリフの枠がつく。窓の中をクリックすると次のセリフ
  音楽プレーヤー … 絵がジャケットになる。▶ で再生、スペクトラムが踊る（資料レコードが鳴っていると、その曲名に）
  ドット絵ツール … 道具パレットと色パレットつき。中の絵がドット絵になる（ほかのドット窓とドットがそろう）
  動画           … シークバーと LIVE。クリックで一時停止 / 再生
  ブラウザ       … タブ・戻る/進む/更新/ホーム・アドレスバー。更新すると上から少しずつ読み込む
  ピンボード     … ブラウザの中に画像カードが並ぶ。カードの穴からキャラが見える。ホイールでスクロール
  SNS            … タイムライン。丸いアイコンと投稿画像が窓。♡ はクリックで押せる。ホイールでスクロール
  お絵かきソフト … 道具・色・ブラシ・スライダー・レイヤー・定規つき（かざり）。透明は市松模様になる
  付箋           … 黄色いメモ（絵はのぞかず、文字だけ）

操作:
  ドラッグ           … 窓を動かす（窓のどこをつかんでもOK）
  右下の ◢ をドラッグ … 窓の大きさを変える
  _ ボタン           … タイトルバーだけにたたむ / もどす
  □ ボタン・タイトルをダブルクリック … 画面いっぱいにする / もどす
  × ボタン           … その窓を閉じる（最後の窓を閉じると終了）
  右クリック         … メニュー（窓を増やす / 見た目 / 名前 / セリフ / 絵をえらぶ / カラー / サイズ など）
  Esc                … ぜんぶ閉じる

配置（絵・窓の位置と大きさ・見た目・名前・セリフ）は nozokimado_config.json に自動で保存される。これが「作品データ」。

必要なもの: pip install pillow
"""
import math
import os
import random
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageTk

# Windows の画面拡大率（125% など）で、絵と窓の位置がずれないようにする。Tk を作る前に呼ぶ
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

from mushiboshi_ui import (BAYER4, COLORWAY_NAMES, PixelMenu, Scale, ask_text, colorway_cmap, colorway_menu, colorway_theme,
                           dither_bar, dither_gradient, hexc, is_night_time, load_colorway, load_json, load_now_playing,
                           log_errors, mix, px_pattern, px_text, px_text_w, recolor, save_colorway, save_json, ui_font)

APP_VERSION = "1.6"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "nozokimado_config.json")

DEFAULT_CONFIG = {"image": "", "scale": 2, "topmost": True, "screen": None, "windows": [],
                  "chara": "", "chara_size": 0.75, "chara_cx": None, "chara_bottom": None, "random_open": True,
                  "presets": [], "open_preset": None}
BG_COLORS = [("クリーム", (255, 246, 226)), ("ピンク", (255, 222, 234)), ("ミント", (214, 244, 232)),
             ("みずいろ", (210, 232, 250)), ("ラベンダー", (230, 222, 250)), ("よる", (44, 40, 76))]
BG_PATTERNS = [("無地", "plain"), ("チェック", "check"), ("ドット", "dots"), ("しましま", "stripe"), ("グリッド", "grid")]
CHARA_SIZES = [("小", 0.5), ("中", 0.75), ("大", 1.0), ("特大", 1.3)]
CHARA_SPOTS = [("左", 0.2), ("まんなか", 0.5), ("右", 0.8)]
KEY = (255, 0, 254)          # 透明にする色（この色のところはデスクトップが透けて、クリックも下に抜ける）
SCALES = [("ミニ", 1.5), ("小", 2), ("中", 3), ("大", 4)]
ZOOMS = [("こまかい", 4), ("ふつう", 8), ("おおきい", 16)]

STYLES = [("normal", "ふつう"), ("game", "ゲーム"), ("music", "音楽プレーヤー"),
          ("dot", "ドット絵ツール"), ("video", "動画"), ("browser", "ブラウザ"), ("pin", "ピンボード"),
          ("sns", "SNS"), ("paint", "お絵かきソフト"), ("memo", "付箋")]
STYLE_NAMES = dict(STYLES)
TEXT_STYLES = ("normal", "game", "memo")   # （SNS も「|」区切りで投稿の文を入れられる）   # セリフ（メモ）を出せる見た目

# 絵の見えるところ = 窓のフチからの距離（ドット）: 左, 上, 右, 下
INSETS = {"normal": (2, 13, 2, 2), "game": (4, 15, 4, 4), "music": (2, 21, 2, 31),
          "dot": (15, 21, 2, 12), "video": (2, 13, 2, 15), "browser": (2, 35, 10, 11),
          "pin": (2, 35, 10, 11), "sns": (2, 23, 2, 13), "paint": (43, 27, 40, 11)}
MIN_SIZE = {"normal": (46, 26), "game": (50, 36), "music": (60, 72), "dot": (60, 50), "video": (60, 42),
            "browser": (80, 64), "pin": (90, 80), "sns": (80, 90), "paint": (112, 96), "memo": (34, 24)}
DEFAULT_SIZE = {"normal": (300, 220), "game": (400, 290), "music": (250, 350), "dot": (360, 270),
                "video": (400, 260), "browser": (440, 340), "pin": (460, 420),
                "sns": (300, 440), "paint": (600, 400), "memo": (210, 160)}   # 「小」サイズのときのピクセル
DEFAULT_TITLES = {
    "normal": ["へや_01.bmp", "けしき.png", "まど.exe", "noname000", "SugarOS"],
    "game": ["おやつ.exe", "ひなたクエスト", "room24.exe", "シュガーRPG"],
    "music": ["SugarPlayer", "おやつラジオ", "ひなたプレーヤー", "ROOM24 FM"],
    "dot": ["ドット.exe", "らくがき.png", "noname000", "PIXEL24"],
    "video": ["ひなた日常ライブ 24h", "おやつ配信", "ROOM24 LIVE", "まどの外.mp4"],
    "browser": ["SugarRoom24 - ホーム", "ひなたのへや", "～ようこそ～", "キャラ絵ギャラリー"],
    "pin": ["ピンボード - おすすめ", "あつめた絵", "ボード：すき", "ピンボード - 検索"],
    "sns": ["タイムライン", "ホーム", "@room24", "おすすめ"],
    "paint": ["*chara.png-1.0 (RGB カラー 8 ビット)", "らくがき.xcf-2.0", "[無題]-1.0 (RGB)", "*room24.xcf-3.0"],
    "memo": ["メモ"],
}
SONGS = ["ひなたぼっこ.mp3", "シュガーボックス.wav", "おやつ棚のうた.mid", "room24_loop.ogg", "ドロップ缶.mp3"]
HINT_TEXT = "右クリックの「絵をえらぶ」で\nすきな絵をのぞけるよ"
FIRST_TEXT = "マスター!\nきょうもヒマです!"
MEMO_TEXT = "メモ\n・おやつ\n・おひるね"

_ICONS = {
    "normal": "#####|#####|#...#|#.#.#|#####",
    "game": ".#.#.|#####|#####|.###.|..#..",
    "music": "..##.|..#.#|..#..|###..|##...",
    "dot": "...##|..###|.###.|###..|#....",
    "video": "#....|###..|#####|###..|#....",
    "browser": ".###.|#.#.#|#####|#.#.#|.###.",
    "pin": ".###.|#####|.###.|..#..|..#..",
    "sns": "#####|#...#|#...#|#####|.#...",
    "paint": "...##|..###|.###.|###..|#....",
    "back": "..#..|.##..|#####|.##..|..#..",
    "fwd": "..#..|..##.|#####|..##.|..#..",
    "reload": ".###.|#...#|#..##|#....|.###.",
    "home": "..#..|.###.|#####|.#.#.|.#.#.",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
    "play": "#....|###..|#####|###..|#....",
    "pause": "##.##|##.##|##.##|##.##|##.##",
    "prev": "#...#|#..##|#.###|#..##|#...#",
    "next": "#...#|##..#|###.#|##..#|#...#",
    "stop": "####|####|####|####",
}
TOOL_ICONS = ["...##|..###|.###.|###..|#....",      # えんぴつ
              ".#...|###..|#####|.####|..#.#",      # バケツ
              "..###|.#..#|#..#.|#.#..|.#...",      # けしゴム
              "....#|...#.|..#..|.#...|#....",      # 直線
              "#####|#...#|#...#|#...#|#####",      # 四角
              ".###.|#...#|#...#|#...#|.###.",      # まる
              "#####|..#..|..#..|..#..|..#..",      # 文字
              "#.#.#|.....|#...#|.....|#.#.#",      # 選択
              ".##..|#..#.|#..#.|.##..|....#"]      # ルーペ
GRIP_OUT = "....#|...##|..#.#|.#..#|#####"
GRIP_FACE = ".....|.....|...#.|..##.|....."
BIG_PLAY = "#......|###....|#####..|#######|#####..|###....|#......"
BIG_PAUSE = "##.##|##.##|##.##|##.##|##.##|##.##|##.##"

PAL = dict(face=(250, 244, 246), out=(72, 50, 84), light=(255, 255, 255), shade=(226, 204, 216),
           title=(246, 178, 196), title2=(252, 210, 222), accent=(236, 96, 128), hover=(255, 224, 232))
COLOR_BASE = {v: k for k, v in PAL.items() if k != "light"}
# カラーで塗り替えない色（液晶・LIVE・付箋）
LCD_BG, LCD_ON, LCD_PEAK = (26, 38, 44), (120, 232, 170), (250, 220, 110)
LIVE_RED = (232, 60, 84)
MEMO_PAPER, MEMO_STRIP, MEMO_EDGE, MEMO_INK = (255, 246, 190), (250, 230, 150), (226, 200, 116), (96, 80, 56)

BAR_Y0, BAR_Y1 = 2, 11      # タイトルバー（ドット）
SHADED_H = 13               # たたんだときの高さ
BTN_W = 9
MOVABLE = (None, "video")   # ここをつかんだら窓が動く
BROWSER_BTNS = ("back", "fwd", "reload", "home")
BROWSER_URLS = ["http://www.sugarroom24.net/", "http://hinata.oyatsu.jp/~room24/",
                "http://www.geocities.sugar/chara/index.html", "http://room24.dreamcore.net/gallery/",
                "http://sugar.os24/~desktop/peek.html"]
LOAD_TIME = 1.1             # ブラウザの「読み込み」にかかる秒数
PIN_URLS = ["http://www.pinboard24.net/", "http://www.pinboard24.net/search/?q=chara",
            "http://www.pinboard24.net/board/suki/", "http://www.pinboard24.net/ideas/dreamcore/"]
SNS_USERS = [("ひなた", "hinata_24"), ("シュガー", "sugar_room"), ("まどべ", "madobe"), ("ねむねむ", "nemu2"),
             ("おやつ係", "oyatsu24"), ("ルーム24", "room24_official")]
SNS_TEXTS = ["きょうのおやつ、なににしよう", "まどの外がきれい。\nしばらく見てた", "新しい絵を描いたよ!", "ねむい……\nおやすみなさい",
             "SugarRoom24 きょうも開店中です", "このへや、すきだなあ", "だれか見てる?", "レコード聴きながら作業中",
             "#今日の一枚", "雨の日は、のんびり"]
FONT_FILES = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts", "DotGothic16-Regular.ttf"),
              r"C:\Windows\Fonts\DotGothic16-Regular.ttf", r"C:\Windows\Fonts\BIZ-UDGothicR.ttc",
              r"C:\Windows\Fonts\meiryo.ttc", r"C:\Windows\Fonts\msgothic.ttc"]
HEART_PAT = ".#.#.|#####|#####|.###.|..#.."
REPOST_PAT = "..#..|.###.|..#.#|#.#..|.###."
REPLY_PAT = "#####|#...#|#...#|#####|.#..."
GAME_LINES = ["マスター!\nきょうもヒマです!", "おやつの時間、まだ?", "ここ、どこの窓?", "のぞかないでよ～",
              "SugarRoom24へ\nようこそ!", "……zzz", "セーブしますか?\n▶はい　いいえ", "レベルが上がった!\nかわいさ +1",
              "ねえ、そっちの窓\nなにが見える?", "きょうは何の日?", "まどの外、\nあめかなあ", "もうちょっとだけ\nここにいるね"]


# ---------- 絵 ----------

def fit_cover(img, sw, sh):
    """画面いっぱいを覆うように拡大して、はみ出しを中央で切る。"""
    iw, ih = img.size
    s = max(sw / iw, sh / ih)
    nw, nh = max(sw, int(iw * s + 0.5)), max(sh, int(ih * s + 0.5))
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - sw) // 2, (nh - sh) // 2
    return img.crop((left, top, left + sw, top + sh))


def placeholder(sw, sh):
    """絵がまだ選ばれていないときの、仮のドット絵（空・雲・ハート・チェックの床）。"""
    u = 4
    w, h = sw // u + 1, sh // u + 1
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    floor = int(h * 0.68)
    dither_gradient(d, 0, 0, w - 1, floor - 1, (170, 214, 246), (255, 214, 232), steps=10)
    for y in range(floor, h):   # チェックの床
        for x in range(w):
            d.point((x, y), fill=(255, 246, 250) if (x // 8 + (y - floor) // 6) % 2 == 0 else (248, 196, 218))
    d.line([(0, floor), (w, floor)], fill=(200, 140, 180))
    rnd = random.Random(24)
    for _ in range(9):   # 雲
        cx, cy, r = rnd.randrange(w), rnd.randrange(int(floor * 0.7)), rnd.randint(5, 10)
        for k in range(3):
            d.ellipse([cx + k * r - r, cy - r // 2, cx + k * r + r, cy + r // 2 + 2], fill=(255, 255, 255))
    for _ in range(40):   # きらきら
        d.point((rnd.randrange(w), rnd.randrange(floor)), fill=(255, 255, 255))
    hx, hy, r = w // 2, int(h * 0.42), max(10, h // 9)   # 大きなハート
    for col, grow in (((82, 44, 86), 1), ((240, 96, 140), 0)):
        rr = r + grow
        d.ellipse([hx - 2 * rr, hy - rr, hx, hy + rr], fill=col)
        d.ellipse([hx, hy - rr, hx + 2 * rr, hy + rr], fill=col)
        d.polygon([(hx - 2 * rr + 1, hy + 2), (hx + 2 * rr - 1, hy + 2), (hx, hy + 2 * rr + 2)], fill=col)
    d.ellipse([hx - int(r * 1.5), hy - r // 2, hx - r, hy], fill=(255, 210, 226))
    text = "NOZOKIMADO"
    px_text(d, (w - px_text_w(text, 2)) // 2 + 1, floor + 9, text, (200, 140, 180), 2)
    px_text(d, (w - px_text_w(text, 2)) // 2, floor + 8, text, (82, 44, 86), 2)
    return im.resize((w * u, h * u), Image.NEAREST).crop((0, 0, sw, sh))


def pattern_tile(color, pattern, u):
    """背景の模様の1マス（8×8 ドットを u 倍）。"""
    dark = mix(color, (255, 255, 255), 0.14) if sum(color) < 300 else mix(color, (90, 60, 110), 0.10)
    tile = Image.new("RGB", (8, 8), color)
    d = ImageDraw.Draw(tile)
    if pattern == "check":
        d.rectangle([0, 0, 3, 3], fill=dark)
        d.rectangle([4, 4, 7, 7], fill=dark)
    elif pattern == "dots":
        d.rectangle([1, 1, 2, 2], fill=dark)
        d.rectangle([5, 5, 6, 6], fill=dark)
    elif pattern == "stripe":
        d.rectangle([0, 0, 1, 7], fill=dark)
        d.rectangle([4, 0, 5, 7], fill=dark)
    elif pattern == "grid":
        d.line([(0, 0), (7, 0)], fill=dark)
        d.line([(0, 0), (0, 7)], fill=dark)
    return tile.resize((8 * u, 8 * u), Image.NEAREST)


def flatten(im):
    """RGBA を窓に出せる RGB にする。透けているところ（アルファが半分より下）は KEY の色にして、本当に透けさせる。"""
    a = im.getchannel("A")
    if a.getextrema()[0] >= 255:
        return im.convert("RGB")
    out = Image.new("RGB", im.size, KEY)
    out.paste(im.convert("RGB"), mask=a.point(lambda v: 255 if v >= 128 else 0))
    return out


# ---------- エフェクト ----------

# (キー, 名前, かける場所, 動くか)。かける場所: "all"=窓の中ぜんぶ / "chara"=キャラ絵だけ
EFFECTS = [
    ("none", "なし", "all", False),
    ("gif", "減色＋網点", "all", False), ("gb", "ゲーム機の4色", "all", False),
    ("mono", "モノクロ", "all", False), ("sepia", "セピア", "all", False),
    ("scan", "走査線", "all", False), ("rgb", "色ずれ", "chara", False),
    ("vhs", "VHS", "all", True), ("glitch", "グリッチ", "all", True),
    ("duo", "デュオトーン", "chara", False), ("hue", "色相まわし", "chara", True),
    ("nega", "ネガ反転", "chara", False), ("night", "暗視カメラ", "all", False), ("thermal", "サーモグラフィ", "all", False),
    ("halftone", "漫画の網点", "chara", False), ("line", "線画だけ", "chara", False), ("glow", "グロー", "chara", False),
]
EFFECT_GROUPS = [("レトロPC・古いネット", ["gif", "gb", "mono", "sepia"]),
                 ("ブラウン管・ビデオ", ["scan", "rgb", "vhs", "glitch"]),
                 ("色あそび", ["duo", "hue", "nega", "night", "thermal"]),
                 ("描きかた", ["halftone", "line", "glow"])]
EFFECT_NAMES = {k: n for k, n, _, _ in EFFECTS}
ALL_FX = {k for k, _, where, _ in EFFECTS if where == "all" and k != "none"}
CHARA_FX = {k for k, _, where, _ in EFFECTS if where == "chara"}
MOVING_FX = {k for k, _, _, moving in EFFECTS if moving}
GB_COLORS = [(30, 46, 44), (72, 112, 84), (146, 182, 116), (218, 234, 184)]
THERMAL_STOPS = [(0.0, (10, 0, 40)), (0.25, (76, 0, 140)), (0.5, (222, 32, 86)), (0.75, (255, 162, 24)),
                 (1.0, (255, 252, 214))]
_fx_cache = {}


def _bayer_screen(w, h, sx, sy, u):
    """画面にくっついた 4×4 の網点のしきい値（0〜63）。窓をまたいでも模様がそろう。"""
    key = ("bayer", u)
    if key not in _fx_cache:
        t = Image.new("L", (4, 4))
        t.putdata([v * 4 for row in BAYER4 for v in row])
        _fx_cache[key] = t.resize((4 * u, 4 * u), Image.NEAREST)
    tile = _fx_cache[key]
    tw = tile.width
    big = Image.new("L", (w + tw, h + tw))
    for y in range(0, h + tw, tw):
        for x in range(0, w + tw, tw):
            big.paste(tile, (x, y))
    ox, oy = sx % tw, sy % tw
    return big.crop((ox, oy, ox + w, oy + h))


def _dither(ch, bay, levels):
    """1つのチャンネルを levels 段に減らす。段のあいだは網点でつなぐ。"""
    step = 255 / (levels - 1)
    bias = bay.point(lambda v: int(round((v / 64 - 0.5) * step)) + 128)
    mixed = ImageChops.add(ch, bias, 1.0, -128)
    return mixed.point(lambda v: int(round(round(v / step) * step)))


def _lut(stops):
    """色の段（0〜1 の位置と色）から、256段のグラデーション表（R, G, B）を作る。"""
    out = ([], [], [])
    for i in range(256):
        t = i / 255
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                c = mix(c0, c1, (t - t0) / max(1e-6, t1 - t0))
                break
        for k in range(3):
            out[k].append(c[k])
    return out


def _vignette(w, h):
    key = ("vig", w, h)
    if key not in _fx_cache:
        small = Image.new("L", (64, 64), 0)
        d = ImageDraw.Draw(small)
        for i in range(32):
            d.ellipse([i - 8, i - 8, 71 - i, 71 - i], fill=min(255, 90 + i * 9))
        _fx_cache[key] = small.filter(ImageFilter.GaussianBlur(4)).resize((w, h), Image.BILINEAR)
        if len(_fx_cache) > 40:
            _fx_cache.clear()
            _fx_cache[key] = small.resize((w, h), Image.BILINEAR)
    return _fx_cache[key]


def fx_all(eff, im, sx, sy, now, p, seed):
    """窓の中ぜんぶにかけるエフェクト。im は RGBA（透明はそのまま残す）。sx, sy は画面での左上。"""
    rgb, a = im.convert("RGB"), im.getchannel("A")
    w, h = rgb.size
    u = max(1, round(p))
    if eff == "mono":
        rgb = ImageOps.grayscale(rgb).convert("RGB")
    elif eff == "sepia":
        rgb = ImageOps.colorize(ImageOps.grayscale(rgb), (40, 24, 16), (255, 242, 210), (160, 116, 82))
    elif eff == "gif":   # 1色6段（216色）＋網点
        bay = _bayer_screen(w, h, sx, sy, u)
        rgb = Image.merge("RGB", [_dither(c, bay, 6) for c in rgb.split()])
    elif eff == "gb":    # 4色＋網点
        g = _dither(ImageOps.autocontrast(ImageOps.grayscale(rgb), cutoff=1), _bayer_screen(w, h, sx, sy, u), 4)
        idx = [min(3, round(v / 85)) for v in range(256)]
        rgb = Image.merge("RGB", [g.point([GB_COLORS[idx[v]][k] for v in range(256)]) for k in range(3)])
    elif eff == "scan":  # ブラウン管の横じま（画面の行にそろえる）
        period = 3 * u
        col = Image.new("L", (1, h + period))
        col.putdata([150 if (y % period) >= 2 * u else 255 for y in range(h + period)])
        mask = col.crop((0, sy % period, 1, sy % period + h)).resize((w, h), Image.NEAREST)
        rgb = ImageChops.multiply(ImageEnhance.Brightness(rgb).enhance(1.12), mask.convert("RGB"))
    elif eff == "night":
        g = ImageOps.autocontrast(ImageOps.grayscale(rgb), cutoff=2)
        rgb = ImageOps.colorize(g, (0, 16, 6), (190, 255, 170), (40, 150, 60))
        rnd = random.Random(seed)
        d = ImageDraw.Draw(rgb)
        for _ in range(w * h // 300):   # ざらざら
            d.point((rnd.randrange(w), rnd.randrange(h)), fill=(150, 230, 140))
        rgb = ImageChops.multiply(rgb, _vignette(w, h).convert("RGB"))
    elif eff == "thermal":
        key = ("thermal_lut",)
        if key not in _fx_cache:
            _fx_cache[key] = _lut(THERMAL_STOPS)
        lr, lg, lb = _fx_cache[key]
        g = ImageOps.autocontrast(ImageOps.grayscale(rgb).filter(ImageFilter.GaussianBlur(2 * u)), cutoff=1)
        rgb = Image.merge("RGB", [g.point(lr), g.point(lg), g.point(lb)])
    elif eff == "vhs":
        rnd = random.Random(int(now * 8) * 7919 + seed)
        soft = rgb.resize((max(1, w // 2), h), Image.BILINEAR).resize((w, h), Image.BILINEAR)
        r, g, b = soft.split()
        rgb = Image.merge("RGB", [ImageChops.offset(r, 2 * u, 0), g, ImageChops.offset(b, -u, 0)])
        rgb = ImageEnhance.Color(rgb).enhance(0.8)
        band_y = int((now * 70) % (h + 60)) - 30   # ゆっくり下りてくる、トラッキングのみだれ
        bh = 5 * u
        if 0 <= band_y < h:
            band = rgb.crop((0, band_y, w, min(h, band_y + bh)))
            band = ImageEnhance.Brightness(ImageChops.offset(band, rnd.randint(4, 12) * u, 0)).enhance(1.3)
            rgb.paste(band, (0, band_y))
        d = ImageDraw.Draw(rgb)
        for _ in range(max(2, w * h // 9000)):   # 白いノイズ
            x, y = rnd.randrange(w), rnd.randrange(h)
            d.line([(x, y), (x + rnd.randint(2, 10) * u, y)], fill=(235, 235, 240))
        stamp = time.strftime("%b.%d %Y").upper()
        su = u
        for dx, col in ((su, (40, 30, 50)), (0, (250, 248, 255))):
            px_text(d, 6 * su + dx, 6 * su + dx, "PLAY", col, su)
            px_pattern(d, 6 * su + 18 * su + dx, 6 * su + dx, "#..|##.|###|##.|#..", col, su)
            px_text(d, 6 * su + dx, h - 12 * su + dx, stamp, col, su)
    elif eff == "glitch":
        rnd = random.Random(int(now * 10) * 104729 + seed)
        burst = rnd.random() < 0.35
        for _ in range(rnd.randint(5, 12) if burst else rnd.randint(0, 2)):
            y, bh = rnd.randrange(h), rnd.randint(2, max(3, h // 7))
            band = ImageChops.offset(rgb.crop((0, y, w, min(h, y + bh))), rnd.randint(-w // 5, w // 5), 0)
            rgb.paste(band, (0, y))
        if burst:
            r, g, b = rgb.split()
            rgb = Image.merge("RGB", [ImageChops.offset(r, rnd.randint(3, 9) * u, 0), g,
                                      ImageChops.offset(b, -rnd.randint(2, 6) * u, 0)])
            d = ImageDraw.Draw(rgb)
            for _ in range(rnd.randint(2, 6)):
                bx, by = rnd.randrange(w), rnd.randrange(h)
                bw, bh = rnd.randint(4, 30) * u, rnd.randint(2, 8) * u
                d.rectangle([bx, by, bx + bw, by + bh], fill=rnd.choice([(255, 80, 180), (80, 240, 255), (255, 255, 255),
                                                                         (20, 10, 30)]))
    out = rgb.convert("RGBA")
    out.putalpha(a)
    return out


def fx_chara(eff, im, ox, oy, now, p):
    """キャラ絵だけにかけるエフェクト。im はまわりに余白をつけて切り出した RGBA。ox, oy は画面での左上。"""
    rgb, a = im.convert("RGB"), im.getchannel("A")
    w, h = im.size
    if eff == "nega":
        rgb = ImageOps.invert(rgb)
    elif eff == "duo":   # ヴェイパーウェイブ色の2色（＋中間色）
        rgb = ImageOps.colorize(ImageOps.grayscale(rgb), (52, 28, 104), (255, 214, 238), (96, 196, 232))
    elif eff == "hue":
        shift = int(now * 40) % 256
        hh, ss, vv = rgb.convert("HSV").split()
        rgb = Image.merge("HSV", [hh.point(lambda v: (v + shift) % 256), ss, vv]).convert("RGB")
    elif eff == "rgb":   # 赤を左、水色を右にずらす
        d = max(2, round(2 * p))
        r, g, b = rgb.split()
        ar, ac = ImageChops.offset(a, -d, 0), ImageChops.offset(a, d, 0)
        on = lambda m: m.point(lambda v: 255 if v >= 128 else 0)
        rgb = Image.merge("RGB", [ImageChops.multiply(ImageChops.offset(r, -d, 0), on(ar)),
                                  ImageChops.multiply(ImageChops.offset(g, d, 0), on(ac)),
                                  ImageChops.multiply(ImageChops.offset(b, d, 0), on(ac))])
        a = ImageChops.lighter(ar, ac)
    elif eff in ("halftone", "line"):
        base = Image.new("RGB", (w, h), (255, 255, 255))
        base.paste(rgb, mask=a)
        gray = ImageOps.grayscale(base)
        if eff == "halftone":   # 画面にそろった格子に、濃さに合わせた大きさの点
            c = max(4, round(3 * p))
            ax, ay = ox % c, oy % c
            W2, H2 = ((w + ax) // c + 1) * c, ((h + ay) // c + 1) * c
            pad = Image.new("L", (W2, H2), 255)
            pad.paste(gray, (ax, ay))
            small = pad.reduce(c)
            dots = Image.new("L", (W2, H2), 255)
            dd = ImageDraw.Draw(dots)
            px = small.load()
            for j in range(small.height):
                for i in range(small.width):
                    r_ = (c / 2) * 1.3 * math.sqrt(max(0.0, 1 - px[i, j] / 255))
                    if r_ > 0.5:
                        cx, cy = i * c + c / 2, j * c + c / 2
                        dd.ellipse([cx - r_, cy - r_, cx + r_, cy + r_], fill=0)
            rgb = ImageOps.colorize(dots.crop((ax, ay, ax + w, ay + h)), (54, 36, 84), (255, 250, 244))
        else:   # 線画だけ：輪郭と、中の線を取り出す
            e = ImageChops.lighter(gray.filter(ImageFilter.FIND_EDGES), a.filter(ImageFilter.FIND_EDGES))
            mask = e.point(lambda v: 255 if v > 48 else 0)
            if p >= 2:
                mask = mask.filter(ImageFilter.MaxFilter(3))
            rgb = Image.new("RGB", (w, h), (58, 38, 96))
            a = mask
    elif eff == "glow":
        rad = 5 * p
        blur = im.filter(ImageFilter.GaussianBlur(rad))
        br, bg_, bb, ba = blur.split()
        soft = Image.merge("RGB", [br, bg_, bb])
        soft = Image.blend(soft, Image.new("RGB", (w, h), (255, 236, 250)), 0.45)
        glow = soft.convert("RGBA")
        glow.putalpha(ba.point(lambda v: min(255, int(v * 2.4))))
        glow.alpha_composite(im)
        lit = ImageChops.screen(glow.convert("RGB"), soft.point(lambda v: v // 3))
        out = lit.convert("RGBA")
        out.putalpha(glow.getchannel("A"))
        return out
    out = rgb.convert("RGBA")
    out.putalpha(a)
    return out


# ---------- ページの中身（ピンボード・SNS・お絵かきソフト） ----------

_pil_fonts = {}


def pil_font(size):
    """絵の中に日本語を書くためのフォント（DotGothic16 があればそれ）。"""
    if size not in _pil_fonts:
        font = None
        for path in FONT_FILES:
            try:
                font = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        _pil_fonts[size] = font or ImageFont.load_default()
    return _pil_fonts[size]


def render_pin(comp, cw, ch, scroll, p, seed, page, shadow, sub):
    """ピンボード：画像カードの形の穴からキャラが見える。scroll でカードが流れる。"""
    gap = max(3, round(4 * p))
    ncol = max(2, min(6, cw // max(1, round(56 * p))))
    colw = max(8, (cw - gap * (ncol + 1)) // ncol)
    cap = max(6, round(9 * p))
    rad = max(2, round(3 * p))
    page_im = Image.new("RGBA", (cw, ch), tuple(page) + (255,))
    pd = ImageDraw.Draw(page_im)
    mask = Image.new("L", (cw, ch), 0)
    md = ImageDraw.Draw(mask)
    for c in range(ncol):
        x0 = gap + c * (colw + gap)
        hs = [int(colw * (0.7 + ((seed * 31 + c * 17 + i * 53) % 9) / 8 * 0.95)) for i in range(10)]
        period = sum(h + cap + gap for h in hs)
        y = gap + (c % 2) * round(14 * p) - int(scroll) % period - period
        while y < ch:
            for h in hs:
                if y + h + cap >= 0 and y < ch:
                    pd.rounded_rectangle([x0 + 1, y + 2, x0 + colw + 1, y + h + 2], rad, fill=tuple(shadow) + (255,))
                    md.rounded_rectangle([x0, y, x0 + colw, y + h], rad, fill=255)
                    cy = y + h + cap // 2 + 1
                    r = max(2, round(2.5 * p))
                    pd.ellipse([x0 + 1, cy - r, x0 + 1 + 2 * r, cy + r], fill=tuple(sub) + (255,))
                    pd.rectangle([x0 + 2 * r + 4, cy - max(1, round(p)), x0 + int(colw * 0.75), cy + max(1, round(p))],
                                 fill=tuple(sub) + (255,))
                y += h + cap + gap
                if y >= ch:
                    break
    return Image.composite(comp, page_im, mask)


def render_sns(comp, cw, ch, scroll, p, seed, cols, liked, own_texts):
    """SNS：投稿のアイコン（丸）と投稿画像が窓。♡ を押したところは hits で返す。"""
    page, line_c, text_c, sub_c, accent = [tuple(c) for c in cols]
    im = Image.new("RGBA", (cw, ch), page + (255,))
    d = ImageDraw.Draw(im)
    mask = Image.new("L", (cw, ch), 0)
    md = ImageDraw.Draw(mask)
    pad, av = max(4, round(5 * p)), max(10, round(16 * p))
    fs = max(10, round(5.5 * p))
    font = pil_font(fs)
    lh = fs + max(2, round(2 * p))
    left = pad + av + max(3, round(4 * p))
    u = max(1, round(p))
    rad = max(2, round(3 * p))
    texts = [t for t in own_texts if t.strip()] or [t.replace("\\n", "\n") for t in SNS_TEXTS]
    posts = []
    for i in range(8):
        user = SNS_USERS[(seed + i * 5) % len(SNS_USERS)]
        text = texts[(seed // 7 + i * 3) % len(texts)]
        ratio = [None, 0.62, 0.9, 0.55, 1.1][(seed + i * 7) % 5]
        nlines = text.count("\n") + 1
        img_h = int((cw - left - pad) * ratio) if ratio else 0
        hgt = pad + lh + nlines * lh + (img_h + rad if img_h else 0) + lh + pad
        posts.append((user, text, img_h, hgt))
    period = sum(pp[3] for pp in posts)
    hits, rings = [], []
    y = -(int(scroll) % period)
    while y < ch:
        for i, (user, text, img_h, hgt) in enumerate(posts):
            if y + hgt >= 0 and y < ch:
                md.ellipse([pad, y + pad, pad + av, y + pad + av], fill=255)
                rings.append(("o", [pad, y + pad, pad + av, y + pad + av]))
                name, handle = user
                d.text((left, y + pad), name, font=font, fill=text_c + (255,))
                nw = d.textlength(name, font=font)
                d.text((left + nw + 4 * u, y + pad), f"@{handle} · {(seed + i * 11) % 59 + 1}分", font=font,
                       fill=sub_c + (255,))
                ty = y + pad + lh
                for ln in text.split("\n"):
                    d.text((left, ty), ln, font=font, fill=text_c + (255,))
                    ty += lh
                if img_h:
                    box = [left, ty + rad // 2, cw - pad, ty + rad // 2 + img_h]
                    md.rounded_rectangle(box, rad, fill=255)
                    rings.append(("r", box))
                    ty += img_h + rad
                on = i in liked
                ay = ty + (lh - 5 * u) // 2
                likes = 3 + (seed + i * 7) % 40 + (1 if on else 0)
                px_pattern(d, left, ay, HEART_PAT, (accent if on else sub_c) + (255,), u)
                d.text((left + 7 * u, ty), str(likes), font=font, fill=(accent if on else sub_c) + (255,))
                hits.append(((left - 2 * u, ty, left + 7 * u + int(d.textlength(str(likes), font=font)) + 2 * u,
                              ty + lh), i))
                x2 = left + 40 * u
                px_pattern(d, x2, ay, REPOST_PAT, sub_c + (255,), u)
                d.text((x2 + 7 * u, ty), str((seed + i * 3) % 12), font=font, fill=sub_c + (255,))
                x3 = x2 + 34 * u
                px_pattern(d, x3, ay, REPLY_PAT, sub_c + (255,), u)
                d.text((x3 + 7 * u, ty), str((seed + i * 5) % 9), font=font, fill=sub_c + (255,))
                d.line([(0, y + hgt - 1), (cw, y + hgt - 1)], fill=line_c + (255,))
            y += hgt
            if y >= ch:
                break
    out = Image.composite(comp, im, mask)
    od = ImageDraw.Draw(out)
    for kind, box in rings:   # アイコンと画像のふち
        if kind == "o":
            od.ellipse(box, outline=line_c + (255,), width=u)
        else:
            od.rounded_rectangle(box, rad, outline=line_c + (255,), width=u)
    return out, hits


def checker_under(comp, p):
    """お絵かきソフトの「透明」は、灰色の市松模様。"""
    c = max(4, round(4 * p))
    w, h = comp.size
    bg = Image.new("RGBA", (w, h), (214, 214, 214, 255))
    d = ImageDraw.Draw(bg)
    for y in range(0, h, c):
        for x in range((y // c) % 2 * c, w, 2 * c):
            d.rectangle([x, y, x + c - 1, y + c - 1], fill=(168, 168, 168, 255))
    bg.alpha_composite(comp)
    return bg


# ---------- 窓の絵（ドット単位で描いて、あとで拡大） ----------

def draw_button(d, x0, y0, x1, y1, icon, fill, ink, k):
    d.rectangle([x0, y0, x1, y1], fill=fill, outline=k["out"])
    d.line([(x0 + 1, y0 + 1), (x1 - 1, y0 + 1)], fill=k["light"])
    pat = _ICONS[icon]
    pw, ph = len(pat.split("|")[0]), len(pat.split("|"))
    px_pattern(d, x0 + (x1 - x0 + 2 - pw) // 2, y0 + (y1 - y0 + 2 - ph) // 2, pat, ink)


def render_chrome(style, wd, hd, hover, shaded, game_cols=None, url="", status="", thumb=0.0, palette=None):
    """窓のフチ・タイトルバー・メニュー行・道具パレット。絵の入るところは out で塗っておく。
    game_cols: ゲームの窓の (濃い色, 明るい色, ステッチの色)。昼も夜も、帯はいつも濃い色にする。"""
    k = PAL
    if style == "memo":
        return render_memo(wd, hd, hover)
    h = SHADED_H if shaded else hd
    im = Image.new("RGB", (wd, h), k["face"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, wd - 1, h - 1], outline=k["out"])
    d.line([(1, 1), (wd - 2, 1)], fill=k["light"])
    d.line([(1, 1), (1, h - 2)], fill=k["light"])
    if style == "game":   # RPG風：濃い帯に、ステッチの点線
        dark, _light, stitch = game_cols or (k["out"], k["light"], k["accent"])
        d.rectangle([2, BAR_Y0, wd - 3, BAR_Y1], fill=dark)
        for x in range(3, wd - 3, 2):
            d.point((x, BAR_Y0 + 1), fill=stitch)
            d.point((x, BAR_Y1 - 1), fill=stitch)
        px_pattern(d, 4, 4, _ICONS["game"], stitch)
    else:
        dither_bar(d, 2, BAR_Y0, wd - 3, BAR_Y1, k["title2"], k["title"])
        px_pattern(d, 5, 5, _ICONS[style], k["light"])
        px_pattern(d, 4, 4, _ICONS[style], k["out"])
    bx0 = wd - 3 - 3 * BTN_W
    for i, icon in enumerate(("min", "max", "close")):
        x0 = bx0 + i * BTN_W
        if icon == "close":
            fill = k["accent"] if hover == icon else k["hover"]
        else:
            fill = k["hover"] if hover == icon else k["face"]
        d.rectangle([x0, 3, x0 + 7, 10], fill=fill, outline=k["out"])
        px_pattern(d, x0 + 1, 4, _ICONS[icon], k["out"])
    if shaded:
        return im
    d.line([(1, 12), (wd - 2, 12)], fill=k["out"])
    d.line([(wd - 2, 2), (wd - 2, h - 2)], fill=k["shade"])
    d.line([(2, h - 2), (wd - 2, h - 2)], fill=k["shade"])
    l, t, r, b = INSETS[style]
    if style in ("music", "dot"):   # メニュー行
        menu = "FILE  PLAY  LIST  HELP" if style == "music" else "FILE  EDIT  IMAGE  TOOL"
        px_text(d, 5, 14, menu, k["out"], max_w=wd - 10)
        d.line([(1, 20), (wd - 2, 20)], fill=k["out"])
    if style == "game":   # 絵のまわりに、もう1本フチ
        d.rectangle([l - 1, t - 1, wd - r, hd - b], outline=k["out"])
        d.rectangle([l - 2, t - 2, wd - r + 1, hd - b + 1], outline=k["light"])
    if style == "dot":   # 左の道具パレット
        d.line([(14, 21), (14, hd - 13)], fill=k["out"])
        y = 23
        for i, pat in enumerate(TOOL_ICONS):
            if y + 7 > hd - 13:
                break
            if i == 0:   # えんぴつを選んでいるところ
                d.rectangle([3, y - 1, 12, y + 5], fill=k["hover"], outline=k["accent"])
            px_pattern(d, 6, y, pat, k["out"])
            y += 8
    if style in ("browser", "pin"):
        d.rectangle([2, 13, wd - 3, 21], fill=k["shade"])   # タブの列
        tw = max(20, min(78, wd - 26))
        d.rectangle([3, 14, 3 + tw, 22], fill=k["face"], outline=k["out"])
        d.line([(4, 15), (2 + tw, 15)], fill=k["light"])
        px_pattern(d, 5, 16, _ICONS["browser"], k["accent"])
        px_pattern(d, 7 + tw, 16, "..#..|..#..|#####|..#..|..#..", k["out"])   # ＋（新しいタブ）
        d.line([(1, 22), (wd - 2, 22)], fill=k["out"])
        d.line([(4, 22), (2 + tw, 22)], fill=k["face"])
        for i, icon in enumerate(BROWSER_BTNS):   # 戻る・進む・更新・ホーム
            x0 = 3 + i * 10
            draw_button(d, x0, 24, x0 + 8, 32, icon, k["hover"] if hover == icon else k["face"], k["out"], k)
        ax0, ax1 = 44, wd - 15
        d.rectangle([ax0, 24, ax1, 32], fill=k["light"], outline=k["out"])   # アドレスバー
        px_text(d, ax0 + 3, 26, url, k["out"], max_w=ax1 - ax0 - 5)
        gx0 = wd - 13
        d.rectangle([gx0, 24, wd - 4, 32], fill=k["hover"] if hover == "go" else k["face"], outline=k["out"])
        px_text(d, gx0 + 2, 26, "GO", k["accent"])
        d.line([(1, 34), (wd - 2, 34)], fill=k["out"])
        sx0, sy1 = wd - 10, hd - 12   # スクロールバー
        d.rectangle([sx0, 35, wd - 4, sy1], fill=k["shade"], outline=k["out"])
        d.rectangle([sx0, 35, wd - 4, 41], fill=k["face"], outline=k["out"])
        px_pattern(d, sx0 + 1, 37, _ICONS["up"] if "up" in _ICONS else "..#..|.###.|#####", k["out"])
        d.rectangle([sx0, sy1 - 6, wd - 4, sy1], fill=k["face"], outline=k["out"])
        px_pattern(d, sx0 + 1, sy1 - 4, "#####|.###.|..#..", k["out"])
        th = max(6, (sy1 - 50) // 3)
        ty0 = 43 + int(max(0, sy1 - 51 - th) * (thumb % 1))
        d.rectangle([sx0, ty0, wd - 4, min(sy1 - 8, ty0 + th)], fill=k["face"], outline=k["out"])
        d.line([(1, hd - b), (wd - 2, hd - b)], fill=k["out"])   # ステータスバー
        px_text(d, 5, hd - 8, status, k["out"], max_w=wd - 12)
    if style == "sns":
        d.rectangle([2, 13, wd - 3, 21], fill=k["face"])
        px_text(d, 5, 15, "HOME", k["out"])
        tx = 5 + px_text_w("HOME") + 8
        px_text(d, tx, 15, "FOR YOU", k["accent"])
        d.line([(tx, 20), (tx + px_text_w("FOR YOU"), 20)], fill=k["accent"])
        px_text(d, tx + px_text_w("FOR YOU") + 8, 15, "FOLLOW", k["title"], max_w=wd - tx - px_text_w("FOR YOU") - 14)
        d.line([(1, 22), (wd - 2, 22)], fill=k["out"])
        d.rectangle([4, hd - 11, wd - 23, hd - 4], fill=k["light"], outline=k["out"])   # 投稿する欄
        d.rectangle([wd - 21, hd - 11, wd - 5, hd - 4], fill=k["accent"], outline=k["out"])
        px_text(d, wd - 20, hd - 9, "POST", k["light"])
    if style == "paint":
        px_text(d, 5, 14, "FILE  EDIT  SELECT  VIEW  IMAGE  LAYER  COLORS  TOOLS  FILTERS", k["out"], max_w=wd - 10)
        d.line([(1, 20), (wd - 2, 20)], fill=k["out"])
        pal = list(palette or []) or [k["accent"], k["out"], k["title"], k["title2"], k["shade"], k["hover"],
                                      (120, 200, 230), (250, 220, 110), (130, 200, 150), (200, 160, 230),
                                      (60, 60, 70), (255, 255, 255)]
        bot = hd - 13
        d.line([(36, 21), (36, hd - 12)], fill=k["out"])   # 左のドック：道具
        icons = TOOL_ICONS + ["#...#|.#.#.|..#..|.#.#.|#...#", "..#..|..#..|#####|..#..|..#..",
                              ".#.#.|#.#.#|.#.#.|#.#.#|.#.#."]
        for i, pat in enumerate(icons[:12]):
            x0, y0 = 4 + (i % 3) * 10, 23 + (i // 3) * 10
            if y0 + 9 > bot:
                break
            d.rectangle([x0, y0, x0 + 8, y0 + 8], fill=k["hover"] if i == 0 else k["face"],
                        outline=k["accent"] if i == 0 else k["shade"])
            px_pattern(d, x0 + 2, y0 + 2, pat, k["out"])
        if 65 + 15 < bot:   # 前景色・背景色
            d.rectangle([12, 69, 22, 79], fill=pal[1 % len(pal)], outline=k["out"])
            d.rectangle([5, 65, 15, 75], fill=pal[0], outline=k["out"])
            px_pattern(d, 26, 66, "..#|.##|###|.##|..#", k["out"])
        if 82 + 17 < bot:   # ブラシ
            px_text(d, 4, 82, "BRUSH", k["out"])
            d.rectangle([4, 89, 33, 98], fill=k["light"], outline=k["out"])
            for x in range(6, 32):
                yy = 93 + round(math.sin((x - 6) / 4) * 2.4)
                d.rectangle([x, yy, x, yy + 1], fill=pal[0])
        y = 102
        for name, val, f in [("SIZE", "51", 0.5), ("OPAC", "100", 1.0), ("HARD", "75", 0.75),
                             ("SPACE", "10", 0.1), ("FORCE", "50", 0.5), ("ANGLE", "0", 0.02)]:
            if y + 10 > bot:
                break
            px_text(d, 4, y, name, k["out"])
            px_text(d, 34 - px_text_w(val), y, val, k["accent"])
            d.rectangle([4, y + 6, 33, y + 9], fill=k["light"], outline=k["out"])
            fw = int(28 * f)
            if fw > 0:
                d.rectangle([5, y + 7, 4 + fw, y + 8], fill=k["accent"])
            y += 13
        rx0 = wd - 38   # 右のドック：レイヤーと色
        d.line([(wd - 40, 21), (wd - 40, hd - 12)], fill=k["out"])
        px_text(d, rx0, 23, "LAYERS", k["out"])
        for i, name in enumerate(("CHARA", "LINE", "BG")):
            y0 = 30 + i * 11
            if y0 + 9 > bot:
                break
            d.rectangle([rx0 - 1, y0, wd - 4, y0 + 9], fill=k["hover"] if i == 0 else k["face"], outline=k["shade"])
            px_pattern(d, rx0 + 1, y0 + 3, ".###.|#.#.#|.###.", k["out"])
            d.rectangle([rx0 + 7, y0 + 1, rx0 + 14, y0 + 8], fill=pal[(i * 3) % len(pal)], outline=k["out"])
            px_text(d, rx0 + 17, y0 + 3, name, k["out"], max_w=wd - rx0 - 21)
        if 66 + 8 < bot:
            px_text(d, rx0, 66, "COLORS", k["out"])
            for i, col in enumerate(pal[:12]):
                x0, y0 = rx0 + (i % 4) * 7, 73 + (i // 4) * 7
                if y0 + 6 > bot:
                    break
                d.rectangle([x0, y0, x0 + 5, y0 + 5], fill=col, outline=k["out"])
        d.rectangle([37, 21, wd - 41, 26], fill=k["light"])   # 定規
        d.line([(37, 26), (wd - 41, 26)], fill=k["out"])
        for x in range(43, wd - 40, 4):
            d.line([(x, 26 - (4 if (x - 43) % 16 == 0 else 1)), (x, 26)], fill=k["out"])
        d.rectangle([37, 27, 42, hd - 12], fill=k["light"])
        d.line([(42, 27), (42, hd - 12)], fill=k["out"])
        for yy in range(27, hd - 11, 4):
            d.line([(42 - (4 if (yy - 27) % 16 == 0 else 1), yy), (42, yy)], fill=k["out"])
        px_text(d, 5, hd - 8, status, k["out"], max_w=wd - 12)
    if style in ("music", "dot", "video", "sns", "paint"):   # 下のパネルとの境目
        d.line([(1, hd - b), (wd - 2, hd - b)], fill=k["out"])
    d.rectangle([l, t, wd - r - 1, hd - b - 1], fill=k["out"])
    return im


def render_memo(wd, hd, hover):
    """付箋。上に少し濃い帯、右上に ×、右下に折り返し（ここをつかむと大きさが変わる）。"""
    im = Image.new("RGB", (wd, hd), MEMO_PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, wd - 1, 6], fill=MEMO_STRIP)
    d.line([(wd - 1, 0), (wd - 1, hd - 1)], fill=MEMO_EDGE)
    d.line([(0, hd - 1), (wd - 1, hd - 1)], fill=MEMO_EDGE)
    px_pattern(d, wd - 8, 1, _ICONS["close"], LIVE_RED if hover == "close" else MEMO_INK)
    for i in range(6):   # 右下の折り返し
        d.line([(wd - 6 + i, hd - 1 - i), (wd - 1, hd - 1 - i)], fill=MEMO_STRIP)
        d.point((wd - 6 + i, hd - 1 - i), fill=MEMO_EDGE)
    return im


def render_grip():
    k = PAL
    im = Image.new("RGBA", (5, 5), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    px_pattern(d, 0, 0, GRIP_FACE, k["face"] + (255,))
    px_pattern(d, 0, 0, GRIP_OUT, k["out"] + (255,))
    return im


def render_msg_box(bw, bh, game_cols=None):
    """セリフの枠。ふつうは白地に二重のフチ、ゲーム（game_cols あり）は濃い地に明るいフチ。"""
    k = PAL
    if game_cols:
        dark, light, stitch = game_cols
        im = Image.new("RGB", (bw, bh), dark)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, bw - 1, bh - 1], outline=light)
        d.rectangle([2, 2, bw - 3, bh - 3], outline=stitch)
        return im
    im = Image.new("RGB", (bw, bh), k["light"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, bw - 1, bh - 1], outline=k["out"])
    d.rectangle([2, 2, bw - 3, bh - 3], outline=k["accent"])
    d.line([(3, bh - 4), (bw - 4, bh - 4)], fill=k["hover"])
    return im


MUSIC_H, VIDEO_H, DOT_H = 28, 12, 9


def music_buttons():
    """音楽プレーヤーのボタン（パネルの中のドット座標）。"""
    return {"prev": (1, 18, 9, 26), "play": (11, 17, 23, 27), "next": (25, 18, 33, 26), "stop": (35, 18, 43, 26)}


def render_music_panel(w, active, playing, t, pos, length, hover):
    k = PAL
    im = Image.new("RGB", (w, MUSIC_H), k["face"])
    d = ImageDraw.Draw(im)
    lx0, ly0, lx1, ly1 = 1, 1, w - 2, 15   # 液晶
    d.rectangle([lx0, ly0, lx1, ly1], fill=LCD_BG, outline=k["out"])
    n = (lx1 - lx0 - 3) // 3
    for i in range(n):   # スペクトラム
        x = lx0 + 2 + i * 3
        if active:
            v = abs(math.sin(t * (2.3 + (i % 5) * 0.41) + i * 1.7)) * (0.55 + 0.45 * math.sin(t * 0.8 + i * 0.6))
            hgt = max(1, min(6, round(v * 6)))
        else:
            hgt = 1
        for j in range(hgt):
            d.line([(x, 14 - j), (x + 1, 14 - j)], fill=LCD_PEAK if j >= 4 else LCD_ON)
    s = "%02d:%02d" % divmod(int(pos), 60)
    px_text(d, lx1 - 1 - px_text_w(s), 3, s, LCD_ON)
    for name, (x0, y0, x1, y1) in music_buttons().items():
        if name == "play":   # 大きなスタートボタン
            draw_button(d, x0, y0, x1, y1, "pause" if playing else "play",
                        k["accent"] if hover != name else k["title"], k["light"], k)
        else:
            draw_button(d, x0, y0, x1, y1, name, k["hover"] if hover == name else k["face"], k["out"], k)
    px0, px1 = 47, w - 4
    if px1 - px0 > 6:   # 再生バー
        d.rectangle([px0, 21, px1, 23], fill=k["light"], outline=k["out"])
        fw = int((px1 - px0 - 2) * min(1, pos / max(1, length)))
        if fw > 0:
            d.line([(px0 + 1, 22), (px0 + fw, 22)], fill=k["accent"])
        kx = px0 + 1 + fw
        d.rectangle([kx - 1, 20, kx, 24], fill=k["out"])
    return im


def render_video_bar(w, playing, t):
    k = PAL
    im = Image.new("RGB", (w, VIDEO_H), k["face"])
    d = ImageDraw.Draw(im)
    d.rectangle([1, 1, w - 2, 3], fill=k["shade"], outline=k["out"])   # シークバー（ライブなので、いつも右はし）
    d.line([(2, 2), (w - 3, 2)], fill=LIVE_RED)
    if playing and int(t * 2) % 2 == 0:
        d.rectangle([w - 4, 0, w - 2, 4], fill=LIVE_RED)
    px_pattern(d, 3, 6, _ICONS["play" if not playing else "pause"], k["out"])
    if not playing or int(t * 1.5) % 2 == 0:
        d.rectangle([11, 7, 13, 9], fill=LIVE_RED if playing else k["shade"])
    px_text(d, 16, 6, "LIVE", LIVE_RED if playing else k["out"])
    return im


def render_dot_palette(w, colors, zoom):
    k = PAL
    im = Image.new("RGB", (w, DOT_H), k["face"])
    d = ImageDraw.Draw(im)
    label = "X%d" % zoom
    lw = px_text_w(label)
    for i, c in enumerate(colors):
        x = 1 + i * 8
        if x + 7 > w - lw - 4:
            break
        d.rectangle([x, 1, x + 6, 7], fill=c, outline=k["out"])
        if i == 0:
            d.rectangle([x - 1, 0, x + 7, 8], outline=k["accent"])
    px_text(d, w - 2 - lw, 2, label, k["out"])
    return im


def video_overlay(part, playing, flash):
    """動画の絵の上に、大きな ▶（止まっているとき）や ⏸（再生した直後）と、LIVE のしるしを重ねる。"""
    cw, ch = part.size
    s = max(2, min(cw, ch) // 44)
    if playing:   # 左上の LIVE
        badge = Image.new("RGBA", (21, 9), LIVE_RED + (230,))
        bd = ImageDraw.Draw(badge)
        bd.rectangle([2, 2, 4, 6], fill=(255, 255, 255, 255))
        px_text(bd, 6, 2, "LIVE", (255, 255, 255, 255))
        bs = max(2, min(cw, ch) // 100)
        badge = badge.resize((21 * bs, 9 * bs), Image.NEAREST)
        part = part.convert("RGBA")
        part.alpha_composite(badge, (3 * bs, 3 * bs))
    if not playing or flash:
        icon = Image.new("RGBA", (15, 15), (0, 0, 0, 0))
        idr = ImageDraw.Draw(icon)
        idr.ellipse([0, 0, 14, 14], fill=(30, 24, 40, 150))
        if playing:
            px_pattern(idr, 5, 4, BIG_PAUSE, (255, 255, 255, 235))
        else:
            px_pattern(idr, 5, 4, BIG_PLAY, (255, 255, 255, 235))
        big = max(2, min(cw, ch) // 45)
        icon = icon.resize((15 * big, 15 * big), Image.NEAREST)
        part = part.convert("RGBA")
        part.alpha_composite(icon, ((cw - icon.width) // 2, (ch - icon.height) // 2))
    return part.convert("RGB")


def recolor_rgba(im, cmap):
    if not cmap:
        return im
    a = im.getchannel("A")
    out = recolor(im.convert("RGB"), cmap).convert("RGBA")
    out.putalpha(a)
    return out


# ---------- 窓 ----------

class PeekWindow:
    def __init__(self, app, title, x, y, w, h, text="", shaded=False, style="normal", zoom=8, playing=None,
                 bg="shared", bg_color="ピンク", bg_pattern="plain", bg_image="", effect="none", url=""):
        self.app = app
        self.effect = effect if effect in EFFECT_NAMES else "none"
        self.url = url or random.choice(PIN_URLS if style == "pin" else BROWSER_URLS)
        self.scroll = random.uniform(0, 600)
        self.liked = set()
        self.hits = []
        self.load_until = 0
        self.cur = ""               # いま出しているセリフ
        self.line_i = random.randrange(len(GAME_LINES))
        self.seed = random.randrange(1 << 30)
        self.bg = bg if bg in ("shared", "clear", "color", "image") else "shared"
        self.bg_color = bg_color if bg_color in dict(BG_COLORS) else "ピンク"
        self.bg_pattern = bg_pattern if bg_pattern in [v for _, v in BG_PATTERNS] else "plain"
        self.bg_image = bg_image
        self._bg_cache = None
        self.small = None
        self.title = title
        self.text = text
        self.shown_text = ""
        self.style = style if style in STYLE_NAMES else "normal"
        self.shaded = bool(shaded) and self.style != "memo"
        self.zoom = zoom if zoom in [v for _, v in ZOOMS] else 8
        self.playing = (self.style == "video") if playing is None else bool(playing)
        self.max_back = None        # 画面いっぱいにする前の (x, y, wd, hd)
        self.hover = None
        self.x, self.y = int(x), int(y)
        p = app.p
        mw, mh = MIN_SIZE[self.style]
        self.wd, self.hd = max(mw, round(w / p)), max(mh, round(h / p))
        self._type_job = self._blink_job = None
        self.t = random.random() * 10       # アニメの時計
        self.pos, self.song_i = random.uniform(0, 60), random.randrange(len(SONGS))
        self.flash_until = 0
        self._was_active = None
        self.photo = self.chrome_photo = self.grip_photo = self.box_photo = self.panel_photo = None

        t = self.top = tk.Toplevel(app.root)
        t.overrideredirect(True)
        t.attributes("-topmost", app.cfg["topmost"])
        try:
            t.attributes("-transparentcolor", hexc(KEY))   # 背景「透明」のところを、本当に透けさせる
        except tk.TclError:
            pass
        t.title(title)
        c = self.canvas = tk.Canvas(t, highlightthickness=0, bd=0, bg=hexc(PAL["out"]), cursor="")
        c.pack(fill="both", expand=True)
        self.chrome_id = c.create_image(0, 0, anchor="nw")
        self.img_id = c.create_image(0, 0, anchor="nw")
        self.title_id = c.create_text(0, 0, anchor="w")
        self.panel_id = c.create_image(0, 0, anchor="nw", state="hidden")
        self.ptext_id = c.create_text(0, 0, anchor="nw", state="hidden")
        self.box_id = c.create_image(0, 0, anchor="nw", state="hidden")
        self.msg_id = c.create_text(0, 0, anchor="nw", state="hidden")
        self.next_id = c.create_text(0, 0, anchor="se", text="▼", state="hidden")
        self.grip_id = c.create_image(0, 0, anchor="nw")

        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Double-Button-1>", self.on_double)
        c.bind("<Motion>", self.on_motion)
        c.bind("<Leave>", lambda e: self.set_hover(None))
        c.bind("<Button-3>", self.popup_menu)
        c.bind("<MouseWheel>", self.on_wheel)
        t.bind("<Escape>", lambda e: app.on_escape())   # 小窓（名前を変える など）の Esc とまざらないよう、窓ごとに

        self.layout()
        if self.style in ("normal", "game"):
            self.start_typing()

    # --- 大きさと位置（ピクセル） ---
    def height_dots(self):
        return SHADED_H if self.shaded else self.hd

    def content_box(self):
        """絵が見えるところ（窓の中でのピクセル）: x, y, 幅, 高さ。付箋は None。"""
        if self.style == "memo":
            return None
        p = self.app.p
        l, t, r, b = INSETS[self.style]
        x0, y0 = l * p, t * p
        return x0, y0, (self.wd - r) * p - x0, (self.hd - b) * p - y0

    def font(self, k):
        return ui_font(self.app.root, max(10, round(self.app.p * k)))

    def fit_text(self, text, font, max_px):
        """長すぎたら、うしろを … にする。"""
        f = tkfont.Font(root=self.app.root, font=font)
        if f.measure(text) <= max_px:
            return text
        while text and f.measure(text + "…") > max_px:
            text = text[:-1]
        return text + "…"

    def layout(self):
        """大きさ・見た目・カラー・サイズが変わったときに、ぜんぶ描き直す。"""
        p, c = self.app.p, self.canvas
        W, H = self.wd * p, self.height_dots() * p
        self.top.geometry(f"{W}x{H}+{self.x}+{self.y}")
        c.config(width=W, height=H)
        self.draw_chrome()
        if self.style == "memo":
            c.itemconfigure(self.title_id, state="hidden")
        else:
            c.coords(self.title_id, 12 * p, (BAR_Y0 + BAR_Y1 + 1) / 2 * p)
            font = self.font(5.5)
            c.itemconfigure(self.title_id, state="normal", font=font,
                            text=self.fit_text(self.title, font, max(10, (self.wd - 3 - 3 * BTN_W - 14) * p)),
                            fill=hexc(self.app.game_colors()[1] if self.style == "game" else self.app.col("out")))
        hide = [self.img_id, self.grip_id, self.panel_id, self.ptext_id, self.box_id, self.msg_id, self.next_id]
        if self.shaded:
            for item in hide:
                c.itemconfigure(item, state="hidden")
            return
        if self.style == "memo":
            for item in hide:
                c.itemconfigure(item, state="hidden")
            self.layout_message()
            return
        c.itemconfigure(self.img_id, state="normal")
        c.itemconfigure(self.grip_id, state="normal")
        g = recolor_rgba(render_grip(), self.app.cmap()).resize((5 * p, 5 * p), Image.NEAREST)
        self.grip_photo = ImageTk.PhotoImage(g)
        c.itemconfigure(self.grip_id, image=self.grip_photo)
        c.coords(self.grip_id, (self.wd - 2) * p - 5 * p, (self.hd - 2) * p - 5 * p)
        self.refresh_picture()
        self.draw_panel()
        self.layout_message()
        c.tag_raise(self.grip_id)

    def draw_chrome(self):
        p = self.app.p
        status = "LOADING..." if time.time() < self.load_until else "DONE"
        if self.style == "paint":
            status = f"{self.app.sw}X{self.app.sh}  RGB 8BIT  33%"
        im = render_chrome(self.style, self.wd, self.hd, self.hover, self.shaded, self.app.game_colors(),
                           self.url, status, self.scroll / (700 * self.app.p), self.app.chara_palette)
        im = recolor(im, self.app.cmap()).resize((self.wd * p, self.height_dots() * p), Image.NEAREST)
        self.chrome_photo = ImageTk.PhotoImage(im)
        self.canvas.itemconfigure(self.chrome_id, image=self.chrome_photo)

    def refresh_picture(self):
        """窓が今いる場所の、絵の部分を見せる（これがのぞき窓の正体）。"""
        box = self.content_box()
        if self.shaded or box is None:
            return
        cx, cy, cw, ch = box
        if cw < 1 or ch < 1:
            return
        sx, sy = self.x + cx, self.y + cy
        if self.style == "dot":   # ドットの格子を画面の左上からそろえて、どの窓でもつながるように
            b = self.zoom
            ax, ay = (sx // b) * b, (sy // b) * b
            aw, ah = -(-(sx + cw - ax) // b) * b, -(-(sy + ch - ay) // b) * b
            self.small = self.with_fx(self.compose(ax, ay, aw, ah), ax, ay).reduce(b)
            comp = self.small.resize((aw, ah), Image.NEAREST).crop((sx - ax, sy - ay, sx - ax + cw, sy - ay + ch))
        else:
            comp = self.with_fx(self.compose(sx, sy, cw, ch), sx, sy)
        if self.style in ("pin", "sns"):
            comp = self.render_page(comp, cw, ch)
        elif self.style == "paint":
            comp = checker_under(comp, self.app.p)
        part = flatten(comp)
        if self.style == "video":
            part = video_overlay(part, self.playing, time.time() < self.flash_until)
        if self.style == "browser" and time.time() < self.load_until:   # 上から少しずつ読み込まれる
            frac = 1 - (self.load_until - time.time()) / LOAD_TIME
            cut = int(ch * max(0.0, min(1.0, frac)) // (4 * self.app.p) * (4 * self.app.p))
            if cut < ch:
                part.paste(Image.new("RGB", (cw, ch - cut), (255, 255, 255)), (0, cut))
        self.photo = ImageTk.PhotoImage(part)
        self.canvas.itemconfigure(self.img_id, image=self.photo)
        self.canvas.coords(self.img_id, cx, cy)
        if self.style == "dot":
            self.draw_panel()   # 色パレットは、見えている絵の色

    def render_page(self, comp, cw, ch):
        """ピンボード・SNS：ページの上に、カードやアイコンの形の穴をあけてキャラを見せる。"""
        app = self.app
        if self.style == "pin":
            return render_pin(comp, cw, ch, self.scroll, app.p, self.seed % 997, app.col("light"),
                              app.col("shade"), mix(app.col("shade"), app.col("out"), 0.25))
        own = [t for t in self.text.split("|")] if self.text else []
        out, hits = render_sns(comp, cw, ch, self.scroll, app.p, self.seed % 997,
                               (app.col("light"), app.col("shade"), app.col("out"),
                                mix(app.col("out"), app.col("light"), 0.45), app.col("accent")), self.liked, own)
        self.hits = hits
        return out

    def on_wheel(self, e):
        if self.style in ("pin", "sns") and not self.shaded:
            self.scroll += (-1 if e.delta > 0 else 1) * 30 * self.app.p
            if self.style == "pin":
                self.draw_chrome()
            self.refresh_picture()

    def compose(self, sx, sy, w, h):
        """画面の (sx, sy) から w×h の、背景＋キャラ絵（RGBA）。"""
        app = self.app
        pic = self.bg_picture() if self.bg == "image" else None
        if self.bg == "clear":
            im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        elif self.bg == "color":
            im = app.pattern_screen(self.bg_color, self.bg_pattern).crop((sx, sy, sx + w, sy + h)).convert("RGBA")
        elif pic is not None:
            img, ox, oy = pic
            im = img.crop((sx - ox, sy - oy, sx - ox + w, sy - oy + h)).convert("RGBA")
        else:
            im = app.screen_img.crop((sx, sy, sx + w, sy + h)).convert("RGBA")
        if app.chara_img is not None:
            x0, y0 = sx - app.chara_x, sy - app.chara_y
            if self.effect in CHARA_FX:   # まわりに余白をつけて切り出してからかけると、窓のふちで線や光が切れない
                m = int(14 * app.p)
                part = app.chara_img.crop((x0 - m, y0 - m, x0 + w + m, y0 + h + m))
                if part.getchannel("A").getbbox():
                    part = fx_chara(self.effect, part, sx - m, sy - m, time.time(), app.p)
                part = part.crop((m, m, m + w, m + h))
            else:
                part = app.chara_img.crop((x0, y0, x0 + w, y0 + h))
            im.alpha_composite(part)
        return im

    def with_fx(self, im, sx, sy):
        if self.effect in ALL_FX:
            return fx_all(self.effect, im, sx, sy, time.time(), self.app.p, self.seed)
        return im

    def set_effect(self, key):
        self.effect = key
        self.refresh_picture()
        self.app.save()

    def bg_picture(self):
        """その窓だけの背景画像（絵が見えるところいっぱいに合わせる）と、画面での位置。"""
        box = self.content_box()
        if not self.bg_image or box is None:
            return None
        cx, cy, cw, ch = box
        key = (self.bg_image, cw, ch)
        if self._bg_cache is None or self._bg_cache[0] != key:
            try:
                img = fit_cover(Image.open(self.bg_image).convert("RGB"), cw, ch)
            except (OSError, ValueError):
                img = None
            self._bg_cache = (key, img)
        img = self._bg_cache[1]
        return None if img is None else (img, self.x + cx, self.y + cy)

    def set_bg(self, kind, **kw):
        self.bg = kind
        for k, v in kw.items():
            setattr(self, k, v)
        self.refresh_picture()
        self.app.save()

    def in_content(self, e):
        box = self.content_box()
        return box is not None and box[0] <= e.x < box[0] + box[2] and box[1] <= e.y < box[1] + box[3]

    # --- 下のパネル（音楽・動画・ドット） ---
    def music_title(self):
        now = load_now_playing()
        return (now.get("title") or "RECORD") if now else SONGS[self.song_i]

    def song_length(self):
        return 150 + (self.song_i * 53) % 140

    def draw_panel(self):
        c, p = self.canvas, self.app.p
        if self.style == "sns" and not self.shaded:   # 投稿欄の「いまどうしてる？」
            c.itemconfigure(self.panel_id, state="hidden")
            c.itemconfigure(self.ptext_id, state="normal", font=self.font(4.5), anchor="w",
                            fill=hexc(mix(self.app.col("out"), self.app.col("light"), 0.5)), text="いまどうしてる？")
            c.coords(self.ptext_id, 7 * p, (self.hd - 7.5) * p)
            c.tag_raise(self.ptext_id)
            return
        if self.style in ("browser", "pin") and not self.shaded:   # タブの名前
            c.itemconfigure(self.panel_id, state="hidden")
            font = self.font(4.5)
            tw = max(20, min(78, self.wd - 26))
            c.itemconfigure(self.ptext_id, state="normal", font=font, fill=hexc(self.app.col("out")),
                            text=self.fit_text(self.title, font, max(10, (tw - 10) * p)), anchor="w")
            c.coords(self.ptext_id, 12 * p, 18.5 * p)
            c.tag_raise(self.ptext_id)
            return
        c.itemconfigure(self.ptext_id, anchor="nw")
        if self.shaded or self.style not in ("music", "video", "dot"):
            c.itemconfigure(self.panel_id, state="hidden")
            c.itemconfigure(self.ptext_id, state="hidden")
            return
        w = self.wd - 4
        if self.style == "music":
            active = self.playing or load_now_playing() is not None
            im = render_music_panel(w, active, self.playing, self.t, self.pos, self.song_length(),
                                    self.hover if self.hover in music_buttons() else None)
            y0 = self.hd - 2 - MUSIC_H
        elif self.style == "video":
            im = render_video_bar(w, self.playing, self.t)
            y0 = self.hd - 2 - VIDEO_H
        else:
            im = render_dot_palette(w, self.region_colors(w // 8), self.zoom)
            y0 = self.hd - 2 - DOT_H
        im = recolor(im, self.app.cmap()).resize((w * p, im.height * p), Image.NEAREST)
        self.panel_photo = ImageTk.PhotoImage(im)
        c.itemconfigure(self.panel_id, image=self.panel_photo, state="normal")
        c.coords(self.panel_id, 2 * p, y0 * p)
        if self.style == "music":   # 液晶の曲名
            font = self.font(4.5)
            c.itemconfigure(self.ptext_id, state="normal", font=font, fill=hexc(LCD_ON),
                            text=self.fit_text(self.music_title(), font, max(10, (w - 26) * p)))
            c.coords(self.ptext_id, 5 * p, (y0 + 2) * p)
        elif self.style == "video":
            font = self.font(4.5)
            c.itemconfigure(self.ptext_id, state="normal", font=font, fill=hexc(self.app.col("out")),
                            text=self.fit_text(self.title, font, max(10, (w - 36) * p)))
            c.coords(self.ptext_id, 36 * p, (y0 + 4) * p)
        else:
            c.itemconfigure(self.ptext_id, state="hidden")
        c.tag_raise(self.panel_id)
        c.tag_raise(self.ptext_id)
        c.tag_raise(self.grip_id)

    def region_colors(self, n):
        """ドット窓に見えている絵の、多い色から順に n 色（透けているところは数えない）。"""
        if self.small is None:
            return []
        q = flatten(self.small).quantize(colors=max(2, min(24, n + 1))).convert("RGB")
        cols = [c for _, c in sorted(q.getcolors(4096) or [], reverse=True) if c != KEY]
        return cols[:max(1, n)]

    def animate(self, dt):
        """アプリ全体の時計から、0.12秒ごとに呼ばれる。"""
        if self.shaded:
            return
        if self.style == "music":
            now = load_now_playing()
            active = self.playing or now is not None
            if self.playing:
                self.pos += dt
                if self.pos >= self.song_length():
                    self.pos, self.song_i = 0, (self.song_i + 1) % len(SONGS)
            if active or self._was_active:
                self.t += dt
                self.draw_panel()
            self._was_active = active
        elif self.style == "video":
            if self.playing:
                self.t += dt
                self.draw_panel()
            if self.flash_until and time.time() >= self.flash_until:
                self.flash_until = 0
                self.refresh_picture()
        if self.style == "browser" and self.load_until:
            if time.time() >= self.load_until:
                self.load_until = 0
            self.draw_chrome()
            self.refresh_picture()
        elif self.effect in MOVING_FX:
            self.refresh_picture()

    # --- セリフ・メモ ---
    def layout_message(self):
        c, p = self.canvas, self.app.p
        items = (self.box_id, self.msg_id, self.next_id)
        if self.style == "memo":
            c.itemconfigure(self.box_id, state="hidden")
            c.itemconfigure(self.next_id, state="hidden")
            c.coords(self.msg_id, 4 * p, 9 * p)
            c.itemconfigure(self.msg_id, state="normal", text=self.text, fill=hexc(MEMO_INK),
                            width=max(10, (self.wd - 9) * p), font=self.font(6))
            return
        l, t, r, b = INSETS.get(self.style, INSETS["normal"])
        cw_d, ch_d = self.wd - l - r, self.hd - t - b
        if not self.cur or self.shaded or self.style not in ("normal", "game") or ch_d < 24 or cw_d < 30:
            for item in items:
                c.itemconfigure(item, state="hidden")
            return
        game = self.style == "game"
        m = 3
        bw, bh = cw_d - 2 * m, max(18, int(ch_d * 0.38))
        bx, by = l + m, self.hd - b - m - bh
        gc = self.app.game_colors() if game else None
        box = recolor(render_msg_box(bw, bh, gc), self.app.cmap()).resize((bw * p, bh * p), Image.NEAREST)
        self.box_photo = ImageTk.PhotoImage(box)
        c.itemconfigure(self.box_id, image=self.box_photo, state="normal")
        c.coords(self.box_id, bx * p, by * p)
        c.coords(self.msg_id, (bx + 6) * p, (by + 5) * p)
        c.itemconfigure(self.msg_id, text=self.shown_text, state="normal", width=max(10, (bw - 12) * p),
                        fill=hexc(gc[1] if game else self.app.col("out")), font=self.font(7))
        c.coords(self.next_id, (bx + bw - 5) * p, (by + bh - 4) * p)
        c.itemconfigure(self.next_id, fill=hexc(gc[2] if game else self.app.col("accent")), font=self.font(4))
        if self.shown_text != self.cur:
            c.itemconfigure(self.next_id, state="hidden")
        for item in items:
            c.tag_raise(item)

    def stop_typing(self):
        for job in (self._type_job, self._blink_job):
            if job:
                self.top.after_cancel(job)
        self._type_job = self._blink_job = None

    def lines(self):
        """出せるセリフ。ゲームは「|」で区切った自分のセリフ、なければおまかせのセリフ集。"""
        if self.style == "game":
            own = [t for t in self.text.split("|") if t.strip()]
            return own or [t.replace("\\n", "\n") for t in GAME_LINES]
        if self.style == "normal" and self.text:
            return [self.text]
        return []

    def start_typing(self):
        self.stop_typing()
        self.shown_text = ""
        ls = self.lines()
        self.cur = ls[self.line_i % len(ls)] if ls else ""
        self.layout_message()
        if self.cur:
            self._type(0)

    def next_line(self):
        """ゲームの窓をクリックしたとき：次のセリフへ（打ち込み中なら、まず全部出す）。"""
        if self._type_job:
            self.stop_typing()
            self.shown_text = self.cur
            self.layout_message()
            self._blink(True)
            return
        ls = self.lines()
        if len(ls) < 2:
            self.start_typing()
            return
        if self.text.strip():   # 自分のセリフは順番に
            self.line_i = (self.line_i + 1) % len(ls)
        else:                   # おまかせは、今とちがうものをランダムに
            self.line_i = random.choice([i for i in range(len(ls)) if i != self.line_i % len(ls)])
        self.start_typing()

    def _type(self, i):
        self.shown_text = self.cur[:i]
        self.canvas.itemconfigure(self.msg_id, text=self.shown_text)
        if i < len(self.cur):
            self._type_job = self.top.after(60, self._type, i + 1)
        else:
            self._type_job = None
            self.layout_message()
            self._blink(True)

    def _blink(self, on):
        """打ち終わったら、右下の ▼ がぴこぴこする。"""
        if not self.cur or self.shaded or self.style not in ("normal", "game"):
            self._blink_job = None
            return
        self.canvas.itemconfigure(self.next_id, state="normal" if on else "hidden")
        self._blink_job = self.top.after(500, self._blink, not on)

    # --- マウス ---
    def spot_at(self, e):
        p = self.app.p
        x, y = e.x / p, e.y / p
        if self.style == "memo":
            if self.wd - 9 <= x <= self.wd - 2 and y <= 7:
                return "close"
            if x >= self.wd - 8 and y >= self.hd - 8:
                return "grip"
            return None
        bx0 = self.wd - 3 - 3 * BTN_W
        if 3 <= y <= 11:
            for i, name in enumerate(("min", "max", "close")):
                x0 = bx0 + i * BTN_W
                if x0 <= x <= x0 + 8:
                    return name
        if self.shaded:
            return None
        if x >= self.wd - 9 and y >= self.hd - 9:
            return "grip"
        if self.style in ("browser", "pin") and 24 <= y <= 33:
            if 3 <= x < 43 and (x - 3) % 10 <= 8:
                return BROWSER_BTNS[int((x - 3) // 10)]
            if 44 <= x <= self.wd - 15:
                return "addr"
            if x >= self.wd - 13:
                return "go"
        if self.style == "music":
            py0 = self.hd - 2 - MUSIC_H
            for name, (x0, y0, x1, y1) in music_buttons().items():
                if x0 <= x - 2 <= x1 + 1 and y0 <= y - py0 <= y1 + 1:
                    return name
        if self.style == "video":
            l, t, r, b = INSETS["video"]
            if l <= x < self.wd - r and t <= y < self.hd - 2:
                return "video"
        return None

    def set_hover(self, name):
        if name in ("grip", "video"):
            name = None
        if name != self.hover:
            old, self.hover = self.hover, name
            if {old, name} & {"min", "max", "close", "go", *BROWSER_BTNS}:
                self.draw_chrome()
            if self.style == "music" and {old, name} & set(music_buttons()):
                self.draw_panel()

    def on_motion(self, e):
        spot = self.spot_at(e)
        self.set_hover(spot)
        cursor = "size_nw_se" if spot == "grip" else ("" if spot in MOVABLE else ("xterm" if spot == "addr" else "hand2"))
        if self.app.chara_mode and spot in MOVABLE and self.in_content(e):
            cursor = "fleur"
        try:
            self.canvas.config(cursor=cursor)
        except tk.TclError:
            self.canvas.config(cursor="bottom_right_corner" if spot == "grip" else "")

    def on_press(self, e):
        self.app.lift_all(self)
        self._spot = self.spot_at(e)
        if self.app.chara_mode and self.app.chara_img is not None and self._spot in MOVABLE and self.in_content(e):
            self._spot = "chara"   # キャラを動かすモード：窓ではなくキャラが動く
            self._chara_start = (self.app.cfg["chara_cx"], self.app.cfg["chara_bottom"])
        self._press = (e.x_root, e.y_root)
        self._start = (self.x, self.y, self.wd, self.hd)
        self._moved = False

    def on_drag(self, e):
        if not hasattr(self, "_press"):
            return
        dx, dy = e.x_root - self._press[0], e.y_root - self._press[1]
        if abs(dx) + abs(dy) > 2:
            self._moved = True
        x0, y0, wd0, hd0 = self._start
        if self._spot == "chara":
            cx0, by0 = self._chara_start
            self.app.move_chara(cx0 + dx, by0 + dy)
        elif self._spot == "grip":
            p = self.app.p
            mw, mh = MIN_SIZE[self.style]
            self.wd = max(mw, wd0 + round(dx / p))
            self.hd = max(mh, hd0 + round(dy / p))
            self.layout()
        elif self._spot in MOVABLE and self._moved:
            self.x, self.y = x0 + dx, y0 + dy
            self.top.geometry(f"+{self.x}+{self.y}")
            self.refresh_picture()

    def on_release(self, e):
        if not hasattr(self, "_press"):
            return   # 押していないのに「離した」だけ届いたとき
        spot, moved = self._spot, self._moved
        del self._press
        if moved:
            if spot in MOVABLE:
                self.max_back = None
            self.app.save()
            return
        if spot != self.spot_at(e):
            return
        if spot == "close":
            self.app.remove_window(self)
        elif spot == "min":
            self.toggle_shade()
        elif spot == "max":
            self.toggle_max()
        elif spot == "play":
            self.playing = not self.playing
            self.draw_panel()
        elif spot in ("prev", "next"):
            if self.pos > 3 and spot == "prev":
                self.pos = 0
            else:
                self.song_i = (self.song_i + (1 if spot == "next" else -1)) % len(SONGS)
                self.pos = 0
            self.draw_panel()
        elif spot == "stop":
            self.playing, self.pos = False, 0
            self.draw_panel()
        elif spot == "video":
            self.playing = not self.playing
            self.flash_until = time.time() + 0.8 if self.playing else 0
            self.refresh_picture()
            self.draw_panel()
            self.app.save()
        elif spot in ("back", "fwd"):
            urls = PIN_URLS if self.style == "pin" else BROWSER_URLS
            i = urls.index(self.url) if self.url in urls else 0
            self.go_url(urls[(i + (1 if spot == "fwd" else -1)) % len(urls)])
        elif spot == "home":
            self.go_url((PIN_URLS if self.style == "pin" else BROWSER_URLS)[0])
        elif spot in ("reload", "go"):
            self.go_url(self.url)
        elif spot == "addr":
            s = ask_text(self.app.root, self.app.menu_theme(), "アドレス", "どこをひらく？（ハリボテだよ）",
                         initial=self.url, near=self.top)
            if s:
                self.go_url(s.strip())
        elif spot is None and self.style == "game" and self.in_content(e):
            self.next_line()
        elif spot is None and self.style == "sns" and self.in_content(e):   # ♡ を押す
            cx, cy = self.content_box()[:2]
            x, y = e.x - cx, e.y - cy
            for (x0, y0, x1, y1), i in self.hits:
                if x0 <= x <= x1 and y0 <= y <= y1:
                    self.liked ^= {i}
                    self.refresh_picture()
                    break

    def go_url(self, url):
        """ブラウザの「読み込み」。アドレスを変えて、上から少しずつ絵を出す。"""
        self.url = url
        self.load_until = time.time() + LOAD_TIME
        self.draw_chrome()
        self.refresh_picture()
        self.app.save()

    def on_double(self, e):
        if self.style != "memo" and e.y / self.app.p <= BAR_Y1 + 1 and self.spot_at(e) is None:
            self.toggle_max()

    def toggle_shade(self):
        if self.style == "memo":
            return
        self.shaded = not self.shaded
        self.layout()
        if not self.shaded and self.cur and self.shown_text == self.cur:
            self._blink(True)
        self.app.save()

    def toggle_max(self):
        p = self.app.p
        if self.max_back:
            self.x, self.y, self.wd, self.hd = self.max_back
            self.max_back = None
        else:
            self.max_back = (self.x, self.y, self.wd, self.hd)
            self.x, self.y = 0, 0
            self.wd, self.hd = int(self.app.sw / p), int(self.app.sh / p)
            self.shaded = False
        self.layout()
        self.app.save()

    def set_style(self, style):
        self.style = style
        if style == "memo":
            self.shaded = False
        if style == "video":
            self.playing = True
        mw, mh = MIN_SIZE[style]
        self.wd, self.hd = max(mw, self.wd), max(mh, self.hd)
        self.stop_typing()
        self.layout()
        if style in ("normal", "game"):
            self.start_typing()
        self.app.save()

    def set_zoom(self, z):
        self.zoom = z
        self.layout()
        self.app.save()

    # --- メニュー ---
    def popup_menu(self, e):
        self.app.pmenu.popup(lambda: self.app.menu_items(self), e.x_root, e.y_root)

    def rename(self):
        s = ask_text(self.app.root, self.app.menu_theme(), "名前を変える", "窓の名前", initial=self.title, near=self.top)
        if s is not None:
            self.title = s
            self.top.title(s)
            self.layout()
            self.app.save()

    def edit_text(self):
        memo = self.style == "memo"
        s = ask_text(self.app.root, self.app.menu_theme(), "メモを書く" if memo else "セリフを入れる",
                     "メモ（\\n で改行）" if memo else
                     ("セリフ（\\n で改行。| で区切ると、クリックで次のセリフ。からっぽにすると、おまかせのセリフ）"
                      if self.style == "game" else "セリフ（\\n で改行。からっぽにすると消えるよ）"),
                     initial=self.text.replace("\n", "\\n"), near=self.top)
        if s is not None:
            self.text = s.replace("\\n", "\n")
            if memo:
                self.layout_message()
            else:
                self.line_i = 0
                self.start_typing()
            self.app.save()

    def to_dict(self):
        x, y, wd, hd = self.max_back or (self.x, self.y, self.wd, self.hd)
        p = self.app.p
        return {"title": self.title, "style": self.style, "x": x, "y": y, "w": wd * p, "h": hd * p,
                "text": self.text, "shaded": self.shaded, "zoom": self.zoom, "playing": self.playing,
                "bg": self.bg, "bg_color": self.bg_color, "bg_pattern": self.bg_pattern, "bg_image": self.bg_image,
                "effect": self.effect, "url": self.url}

    def destroy(self):
        self.stop_typing()
        try:
            self.top.destroy()
        except tk.TclError:
            pass


# ---------- 全体 ----------

class App:
    def __init__(self):
        self.cfg = dict(DEFAULT_CONFIG)
        self.cfg.update(load_json(CONFIG_PATH, {}))
        self.p = Scale(self.cfg["scale"])
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())

        self.root = tk.Tk()
        self.root.withdraw()
        log_errors(self.root, "nozokimado_error.txt")
        self.root.title(f"のぞき窓 ver.{APP_VERSION}")
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "nozokimado.ico"))
        except tk.TclError:
            pass
        self.sw, self.sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.pmenu = PixelMenu(self.root, self.menu_theme, title="NOZOKI - MENU")

        self.screen_img = None
        self._patterns = {}
        self.chara_mode = False
        self.chara_src = self.chara_img = None
        self.chara_palette = None
        self.chara_x = self.chara_y = 0
        self.set_image(self.cfg.get("image", ""), redraw=False)
        self.load_chara()
        self.windows = []
        preset = self.find_preset(self.cfg.get("open_preset"))
        if preset:
            wins = preset["windows"]        # 開いたときの並びに、記憶したセットを選んでいるとき
        elif self.cfg.get("random_open", True) and (self.chara_img is not None or self.cfg.get("image")):
            wins = self.random_windows()   # キャラ鑑賞用：開くたびに、おまかせで並べる
        else:
            wins = self.cfg.get("windows") or self.default_windows()
        for w in wins:
            self.add_window(**w)
        if not self.windows:
            for w in self.default_windows():
                self.add_window(**w)
        self._last_tick = time.time()
        self.root.after(120, self.tick)
        self.root.after(2000, self.watch_colorway)

    # --- 色 ---
    def cmap(self):
        return colorway_cmap(COLOR_BASE, self.colorway)

    def col(self, role):
        c = PAL[role]
        return (self.cmap() or {}).get(c, c)

    def game_colors(self):
        """ゲームの窓の色：濃い色・明るい色・ステッチの色。夜は地とフチの明るさが入れかわるので、暗いほうを選ぶ。"""
        a, b = self.col("out"), self.col("face")
        dark, light = (a, b) if sum(a) < sum(b) else (b, a)
        return dark, light, self.col("accent")

    def menu_theme(self):
        if self.colorway != "original" or is_night_time():
            return colorway_theme(self.colorway, COLOR_BASE)
        return dict(face=PAL["face"], out=PAL["out"], light=PAL["light"], title=PAL["title"], title2=PAL["title2"],
                    title_text=PAL["out"], accent=PAL["accent"], sub=mix(PAL["out"], PAL["face"], 0.45),
                    text=PAL["out"], field=PAL["light"], select=PAL["accent"], select_text=PAL["light"])

    def set_colorway(self, name):
        save_colorway(name)
        self.colorway = name
        self.look = (name, is_night_time())
        self.relayout()

    def watch_colorway(self):
        look = (load_colorway(), is_night_time())   # ほかのツールで色を変えたとき・昼夜が切り替わったときに着替える
        if look != self.look:
            self.look = look
            self.colorway = look[0]
            self.relayout()
        self.root.after(2000, self.watch_colorway)

    def relayout(self):
        for w in self.windows:
            w.layout()

    def tick(self):
        now = time.time()
        dt, self._last_tick = min(0.5, now - self._last_tick), now
        for w in list(self.windows):
            w.animate(dt)
        self.root.after(120, self.tick)

    # --- 絵 ---
    def set_image(self, path, redraw=True):
        img = None
        if path and os.path.exists(path):
            try:
                img = Image.open(path).convert("RGB")
            except (OSError, ValueError):
                img = None
        if img is None:
            path = ""
            self.screen_img = placeholder(self.sw, self.sh)
        else:
            self.screen_img = fit_cover(img, self.sw, self.sh)
        self.cfg["image"] = path
        if redraw:
            for w in self.windows:
                w.refresh_picture()

    def pattern_screen(self, color_name, pattern):
        """単色・模様の背景を、画面ぜんぶの大きさで（模様は画面にくっついていて、窓を動かすとのぞく場所が変わる）。"""
        key = (color_name, pattern, float(self.p))
        if key not in self._patterns:
            if len(self._patterns) > 6:
                self._patterns.clear()
            tile = pattern_tile(dict(BG_COLORS).get(color_name, BG_COLORS[1][1]), pattern, max(1, round(self.p)))
            full = Image.new("RGB", (self.sw, self.sh))
            for y in range(0, self.sh, tile.height):
                for x in range(0, self.sw, tile.width):
                    full.paste(tile, (x, y))
            self._patterns[key] = full
        return self._patterns[key]

    def refresh_all(self):
        for w in self.windows:
            w.refresh_picture()

    # --- キャラ絵 ---
    def load_chara(self):
        path = self.cfg.get("chara") or ""
        self.chara_src = None
        if path and os.path.exists(path):
            try:
                src = Image.open(path).convert("RGBA")
                bbox = src.getchannel("A").getbbox()   # まわりの透明な余白は切る
                self.chara_src = src.crop(bbox) if bbox else None
            except (OSError, ValueError):
                self.chara_src = None
        if self.chara_src is None:
            self.cfg["chara"] = ""
        self.chara_palette = self.make_palette()
        self.scale_chara()

    def make_palette(self):
        """キャラ絵の多い色 12色（お絵かきソフトの色パレットに使う）。"""
        if self.chara_src is None:
            return None
        sm = self.chara_src.copy()
        sm.thumbnail((48, 48))
        px = [c[:3] for c in sm.getdata() if c[3] >= 128]
        if not px:
            return None
        im = Image.new("RGB", (len(px), 1))
        im.putdata(px)
        q = im.quantize(colors=12).convert("RGB")
        return [c for _, c in sorted(q.getcolors(64) or [], reverse=True)]

    def scale_chara(self):
        """キャラ絵を今の大きさにする。位置は「足もとのまんなか」で覚えているので、大きさを変えても立つ場所は同じ。"""
        src = self.chara_src
        if src is None:
            self.chara_img = None
            return
        th = max(8, int(self.sh * self.cfg["chara_size"]))
        s = th / src.height
        tw = max(1, int(src.width * s))
        self.chara_img = src.resize((tw, th), Image.NEAREST if s >= 2 else Image.LANCZOS)   # 小さなドット絵はくっきり拡大
        if self.cfg.get("chara_cx") is None:
            self.cfg["chara_cx"], self.cfg["chara_bottom"] = self.sw // 2, self.sh
        self.place_chara()

    def place_chara(self):
        if self.chara_img is not None:
            self.chara_x = int(self.cfg["chara_cx"] - self.chara_img.width // 2)
            self.chara_y = int(self.cfg["chara_bottom"] - self.chara_img.height)

    def move_chara(self, cx, bottom):
        self.cfg["chara_cx"], self.cfg["chara_bottom"] = int(cx), int(bottom)
        self.place_chara()
        self.refresh_all()

    def pick_chara(self, near=None):
        start = os.path.dirname(self.cfg.get("chara") or "") or None
        p = filedialog.askopenfilename(parent=near or self.root, title="キャラ絵をえらぶ（背景が透明な PNG）",
                                       initialdir=start,
                                       filetypes=[("画像", "*.png *.webp *.gif"), ("すべて", "*.*")])
        if p:
            self.cfg["chara"] = p
            self.load_chara()
            self.refresh_all()
            self.save()

    def clear_chara(self):
        self.cfg["chara"] = ""
        self.chara_mode = False
        self.load_chara()
        self.refresh_all()
        self.save()

    def set_chara_size(self, v):
        self.cfg["chara_size"] = v
        self.scale_chara()
        self.refresh_all()
        self.save()

    def set_chara_spot(self, f):
        self.move_chara(int(self.sw * f), self.sh)
        self.save()

    def toggle_chara_mode(self):
        self.chara_mode = not self.chara_mode

    def on_escape(self):
        if self.chara_mode:   # キャラを動かしているときの Esc は、モードを終わるだけ
            self.chara_mode = False
        else:
            self.quit()

    def pick_window_image(self, win):
        start = os.path.dirname(win.bg_image or self.cfg.get("image") or "") or None
        p = filedialog.askopenfilename(parent=win.top, title="この窓の背景にする画像をえらぶ", initialdir=start,
                                       filetypes=[("画像", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("すべて", "*.*")])
        if p:
            win.set_bg("image", bg_image=p)

    def pick_image(self, near=None):
        start = os.path.dirname(self.cfg.get("image") or "") or None
        p = filedialog.askopenfilename(parent=near or self.root, title="のぞき窓で見る絵をえらぶ", initialdir=start,
                                       filetypes=[("画像", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("すべて", "*.*")])
        if p:
            self.set_image(p)
            for w in self.windows:   # 絵を選んだら、仮のヒントは消す
                if w.text == HINT_TEXT:
                    w.text = ""
                    w.start_typing()
            self.save()

    # --- 窓 ---
    def window_size(self, style):
        w, h = DEFAULT_SIZE[style]
        return round(w * self.p / 2), round(h * self.p / 2)

    def default_windows(self):
        """はじめて開いたときの6枚（見た目ぜんぶ）。"""
        styles = ["game", "music", "dot", "video", "normal", "memo"]
        spots = [(0.08, 0.10), (0.62, 0.06), (0.36, 0.40), (0.05, 0.55), (0.66, 0.52), (0.40, 0.08)]
        wins = []
        for style, (fx, fy) in zip(styles, spots):
            w, h = self.window_size(style)
            x = min(int(self.sw * fx) + random.randint(-20, 20), self.sw - w - 20)
            y = min(int(self.sh * fy) + random.randint(-20, 20), self.sh - h - 80)
            wins.append({"title": DEFAULT_TITLES[style][0], "style": style, "x": max(0, x), "y": max(0, y),
                         "w": w, "h": h, "text": ""})
        wins[0]["text"] = FIRST_TEXT if self.cfg.get("image") else HINT_TEXT
        wins[5]["text"] = MEMO_TEXT
        return wins

    def random_windows(self, n=None):
        """おまかせの窓 5〜6枚。見た目・大きさ・背景・エフェクトはばらばら。キャラ絵があれば、キャラの上に集める。"""
        rnd = random.Random()
        n = n or rnd.choice([5, 6])
        styles = ["normal", "game", "music", "dot", "video", "browser", "pin", "sns", "paint"]
        picks = rnd.sample(styles, len(styles)) + [rnd.choice(styles) for _ in range(max(0, n - len(styles)))]
        effects = [k for k, *_ in EFFECTS if k != "none"]
        if self.chara_img is not None:   # キャラが見えている範囲（画面の中だけ）
            x0, y0 = max(0, self.chara_x), max(0, self.chara_y)
            x1 = min(self.sw, self.chara_x + self.chara_img.width)
            y1 = min(self.sh - 40, self.chara_y + self.chara_img.height)
            if x1 - x0 < 50 or y1 - y0 < 50:
                x0, y0, x1, y1 = 0, 0, self.sw, self.sh - 40
        else:
            x0, y0, x1, y1 = 0, 0, self.sw, self.sh - 40
        wins = []
        for style in picks[:n]:
            bw, bh = self.window_size(style)
            k = rnd.uniform(0.7, 1.35)
            w, h = int(bw * k * rnd.uniform(0.85, 1.15)), int(bh * k * rnd.uniform(0.85, 1.15))
            cx, cy = rnd.uniform(x0, x1), rnd.uniform(y0, y1)   # 窓のまんなかを、キャラの上のどこかに
            x = int(max(0, min(self.sw - w, cx - w / 2)))
            y = int(max(0, min(self.sh - 40 - h, cy - h / 2)))
            roll = rnd.random()
            if roll < 0.3:
                bg = "clear"
            elif roll < 0.6 and self.cfg.get("image"):
                bg = "shared"
            else:
                bg = "color"
            wins.append({"title": rnd.choice(DEFAULT_TITLES[style]), "style": style, "x": x, "y": y, "w": w, "h": h,
                         "text": "", "bg": bg, "bg_color": rnd.choice(BG_COLORS)[0],
                         "bg_pattern": rnd.choice(BG_PATTERNS)[1], "zoom": rnd.choice([4, 8, 8, 16]),
                         "effect": "none" if rnd.random() < 0.2 else rnd.choice(effects)})
        return wins

    def reroll(self):
        """いまの窓をぜんぶ閉じて、おまかせで並べなおす。"""
        self.pmenu.close_all()
        for w in list(self.windows):
            w.destroy()
        self.windows = []
        for w in self.random_windows():
            self.add_window(**w)
        self.save()

    def toggle_random_open(self):
        self.cfg["random_open"] = not self.cfg.get("random_open", True)
        self.save()

    # --- セット（並びの記憶） ---
    def find_preset(self, name):
        return next((pr for pr in self.cfg.get("presets", []) if pr.get("name") == name), None) if name else None

    def save_preset(self, near=None):
        presets = self.cfg.setdefault("presets", [])
        name = ask_text(self.root, self.menu_theme(), "セットを記憶する",
                        "セットの名前（同じ名前なら上書き）", initial=f"セット{len(presets) + 1}", near=near)
        if not name or not name.strip():
            return
        data = {"name": name.strip(), "windows": [w.to_dict() for w in self.windows]}
        old = self.find_preset(data["name"])
        if old:
            old.update(data)
        else:
            presets.append(data)
        self.save()

    def load_preset(self, name):
        pr = self.find_preset(name)
        if not pr:
            return
        self.pmenu.close_all()
        for w in list(self.windows):
            w.destroy()
        self.windows = []
        for w in pr["windows"]:
            self.add_window(**w)
        self.save()

    def delete_preset(self, name):
        self.cfg["presets"] = [pr for pr in self.cfg.get("presets", []) if pr.get("name") != name]
        if self.cfg.get("open_preset") == name:
            self.cfg["open_preset"] = None
        self.save()

    def set_open(self, mode):
        """開いたときの並び：random=おまかせ / last=前回のまま / それ以外=セットの名前"""
        self.cfg["open_preset"] = mode if mode not in ("random", "last") else None
        if mode in ("random", "last"):
            self.cfg["random_open"] = mode == "random"
        self.save()

    def preset_menu(self, win):
        presets = self.cfg.get("presets", [])
        op = self.cfg.get("open_preset")
        items = [{"type": "cmd", "label": "いまの並びを記憶する…", "cmd": lambda: self.save_preset(win.top)}]
        if presets:
            items += [{"type": "sep"}, {"type": "head", "label": "よびだす"}]
            items += [{"type": "cmd", "label": pr["name"], "right": f"{len(pr['windows'])} 枚",
                       "cmd": lambda n=pr["name"]: self.load_preset(n)} for pr in presets]
            items.append({"type": "sub", "label": "消す", "items": [
                {"type": "cmd", "label": pr["name"], "cmd": lambda n=pr["name"]: self.delete_preset(n)}
                for pr in presets]})
        items += [{"type": "sep"}, {"type": "head", "label": "開いたときの並び"},
                  {"type": "radio", "label": "おまかせ", "checked": not op and self.cfg.get("random_open", True),
                   "cmd": lambda: self.set_open("random")},
                  {"type": "radio", "label": "前回のまま", "checked": not op and not self.cfg.get("random_open", True),
                   "cmd": lambda: self.set_open("last")}]
        items += [{"type": "radio", "label": f"セット：{pr['name']}", "checked": op == pr["name"],
                   "cmd": lambda n=pr["name"]: self.set_open(n)} for pr in presets]
        return items

    def add_window(self, title="まど.exe", x=100, y=100, w=300, h=220, text="", shaded=False, style="normal",
                   zoom=8, playing=None, bg="shared", bg_color="ピンク", bg_pattern="plain", bg_image="",
                   effect="none", url="", **_):
        win = PeekWindow(self, title, x, y, w, h, text, shaded, style, zoom, playing, bg, bg_color, bg_pattern,
                         bg_image, effect, url)
        self.windows.append(win)
        return win

    def new_window(self, style, near=None):
        w, h = self.window_size(style)
        if near is not None:
            x, y = near.x + 40, near.y + 40
        else:
            x, y = (self.sw - w) // 2, (self.sh - h) // 2
        text = MEMO_TEXT if style == "memo" else ""
        self.add_window(title=random.choice(DEFAULT_TITLES[style]), x=x, y=y, w=w, h=h, style=style, text=text)
        self.save()

    def remove_window(self, win):
        if win in self.windows:
            self.windows.remove(win)
        win.destroy()
        if not self.windows:
            self.quit()
        else:
            self.save()

    def lift_all(self, front=None):
        if front is not None:
            front.top.lift()
            try:
                front.top.focus_force()   # Esc が届くように
            except tk.TclError:
                pass

    def set_scale(self, v):
        old = [w.to_dict() for w in self.windows]
        self.cfg["scale"] = v
        self.p = Scale(v)
        for w, d in zip(self.windows, old):
            mw, mh = MIN_SIZE[w.style]
            w.wd, w.hd = max(mw, round(d["w"] / self.p)), max(mh, round(d["h"] / self.p))
            w.max_back = None
        self.relayout()
        self.save()

    def toggle_topmost(self):
        self.cfg["topmost"] = not self.cfg["topmost"]
        for w in self.windows:
            w.top.attributes("-topmost", self.cfg["topmost"])
        self.save()

    # --- メニュー ---
    def menu_items(self, win):
        c = self.cfg
        name = os.path.basename(c.get("image") or "") or "（仮の絵）"
        items = [
            {"type": "cmd", "label": "おまかせで並べなおす", "cmd": self.reroll},
            {"type": "sub", "label": "セット", "items": lambda: self.preset_menu(win),
             "right": self.cfg.get("open_preset") or ""},
            {"type": "sub", "label": "窓を増やす", "items": [
                {"type": "cmd", "label": n, "cmd": lambda s=s: self.new_window(s, win)} for s, n in STYLES]},
            {"type": "sub", "label": "見た目", "right": STYLE_NAMES[win.style], "items": [
                {"type": "radio", "label": n, "checked": win.style == s, "cmd": lambda s=s: win.set_style(s)}
                for s, n in STYLES]},
            {"type": "cmd", "label": "名前を変える…", "cmd": win.rename},
        ]
        if win.style in TEXT_STYLES or win.style == "sns":
            items.append({"type": "cmd", "label": "メモを書く…" if win.style == "memo" else "セリフを入れる…",
                          "cmd": win.edit_text})
        if win.style == "dot":
            items.append({"type": "sub", "label": "ドットの大きさ", "right": next(n for n, v in ZOOMS if v == win.zoom),
                          "items": [{"type": "radio", "label": n, "checked": win.zoom == v,
                                     "cmd": lambda v=v: win.set_zoom(v)} for n, v in ZOOMS]})
        if win.style != "memo":
            items.append({"type": "check", "label": "たたむ", "checked": win.shaded, "cmd": win.toggle_shade})
            items.append({"type": "sub", "label": "この窓の背景", "items": lambda: self.bg_menu(win),
                          "right": self.bg_label(win)})
            items.append({"type": "sub", "label": "エフェクト", "items": lambda: self.effect_menu(win),
                          "right": EFFECT_NAMES[win.effect] if win.effect != "none" else ""})
        chara = os.path.basename(c.get("chara") or "")
        has = self.chara_img is not None
        items += [
            {"type": "sep"},
            {"type": "sub", "label": "キャラ絵", "right": "あり" if has else "なし", "items": [
                {"type": "cmd", "label": "読み込む…（透明な PNG）", "cmd": lambda: self.pick_chara(win.top)},
                {"type": "sub", "label": "大きさ", "right": next((n for n, v in CHARA_SIZES if v == c["chara_size"]), ""),
                 "enabled": has, "items": [{"type": "radio", "label": n, "checked": c["chara_size"] == v,
                                            "cmd": lambda v=v: self.set_chara_size(v)} for n, v in CHARA_SIZES]},
                {"type": "sub", "label": "位置", "enabled": has, "items": [
                    {"type": "cmd", "label": n, "cmd": lambda f=f: self.set_chara_spot(f)} for n, f in CHARA_SPOTS]},
                {"type": "check", "label": "ドラッグで動かす", "checked": self.chara_mode, "enabled": has,
                 "cmd": self.toggle_chara_mode},
                {"type": "cmd", "label": "外す", "enabled": has, "cmd": self.clear_chara},
                {"type": "sep"},
                {"type": "head", "label": (chara if len(chara) <= 24 else chara[:23] + "…") if has
                 else "背景が透明な PNG を使ってね"},
                {"type": "head", "label": "動かすモード中は、窓の中をドラッグ。Esc で終わり"},
            ]},
            {"type": "cmd", "label": "共通の絵を読み込む…", "cmd": lambda: self.pick_image(win.top)},
            {"type": "head", "label": name if len(name) <= 24 else name[:23] + "…"},
            {"type": "sep"},
            {"type": "sub", "label": "設定", "items": [
                {"type": "sub", "label": "カラー", "items": lambda: colorway_menu(self.colorway, self.set_colorway),
                 "right": next(n for n, k in COLORWAY_NAMES if k == self.colorway)},
                {"type": "sub", "label": "サイズ", "right": next((n for n, v in SCALES if v == c["scale"]), ""),
                 "items": [{"type": "radio", "label": n, "checked": c["scale"] == v,
                            "cmd": lambda v=v: self.set_scale(v)} for n, v in SCALES]},
                {"type": "check", "label": "最前面に表示", "checked": c["topmost"], "cmd": self.toggle_topmost},

            ]},
            {"type": "sep"},
            {"type": "cmd", "label": "この窓を閉じる", "cmd": lambda: self.remove_window(win)},
            {"type": "cmd", "label": "ぜんぶ閉じる（終了）", "cmd": self.quit},
            {"type": "head", "label": f"のぞき窓 ver.{APP_VERSION}　窓 {len(self.windows)} 枚"},
        ]
        return items

    def effect_menu(self, win):
        items = [{"type": "radio", "label": "なし", "checked": win.effect == "none", "cmd": lambda: win.set_effect("none")}]
        for group, keys in EFFECT_GROUPS:
            items.append({"type": "head", "label": group})
            for k in keys:
                where = "キャラ" if k in CHARA_FX else "窓"
                items.append({"type": "radio", "label": EFFECT_NAMES[k], "checked": win.effect == k,
                              "right": where, "cmd": lambda k=k: win.set_effect(k)})
        items += [{"type": "sep"},
                  {"type": "cmd", "label": "全部の窓に、ばらばらにかける", "cmd": self.shuffle_effects},
                  {"type": "cmd", "label": "全部の窓から外す", "cmd": lambda: self.effect_all("none")}]
        return items

    def shuffle_effects(self):
        """見くらべ用：窓ごとに、ちがうエフェクトをおまかせで。"""
        keys = [k for k, *_ in EFFECTS if k != "none"]
        random.shuffle(keys)
        targets = [w for w in self.windows if w.style != "memo"]
        for i, w in enumerate(targets):
            w.effect = keys[i % len(keys)]
            w.refresh_picture()
        self.save()

    def effect_all(self, key):
        for w in self.windows:
            if w.style != "memo":
                w.effect = key
                w.refresh_picture()
        self.save()

    def bg_label(self, win):
        if win.bg == "color":
            return win.bg_color
        return {"shared": "共通の絵", "clear": "透明", "image": "画像"}[win.bg]

    def bg_menu(self, win):
        color_items = [{"type": "head", "label": "色"}]
        color_items += [{"type": "radio", "label": n, "checked": win.bg == "color" and win.bg_color == n,
                         "cmd": lambda n=n: win.set_bg("color", bg_color=n)} for n, _ in BG_COLORS]
        color_items += [{"type": "sep"}, {"type": "head", "label": "模様"}]
        color_items += [{"type": "radio", "label": n, "checked": win.bg == "color" and win.bg_pattern == v,
                         "cmd": lambda v=v: win.set_bg("color", bg_pattern=v)} for n, v in BG_PATTERNS]
        items = [
            {"type": "radio", "label": "共通の絵", "checked": win.bg == "shared", "cmd": lambda: win.set_bg("shared")},
            {"type": "radio", "label": "透明", "checked": win.bg == "clear", "cmd": lambda: win.set_bg("clear")},
            {"type": "sub", "label": "単色・模様", "items": color_items,
             "right": win.bg_color if win.bg == "color" else ""},
            {"type": "radio", "label": "画像を読み込む…", "checked": win.bg == "image",
             "cmd": lambda: self.pick_window_image(win)},
        ]
        if win.bg_image and win.bg != "image":
            items.append({"type": "cmd", "label": "前の画像にもどす", "cmd": lambda: win.set_bg("image")})
        items += [{"type": "sep"}, {"type": "head", "label": "透明のところは、クリックが下に抜けるよ"}]
        return items

    # --- 保存 ---
    def save(self):
        self.cfg["screen"] = [self.sw, self.sh]
        self.cfg["windows"] = [w.to_dict() for w in self.windows]
        save_json(CONFIG_PATH, self.cfg)

    def quit(self):
        self.pmenu.close_all()
        if self.windows:
            self.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        App().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "nozokimado_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
