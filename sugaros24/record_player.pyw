# -*- coding: utf-8 -*-
"""
資料レコード ver.1.4
Eagle ライブラリの音声ファイルを、ランダムに1曲ずつ流すレコードプレーヤー。
Eagle がなくても、ふつうのフォルダの曲を流せる（右クリック →「読み込み先」→「ふつうのフォルダ」）。
  フォルダのときは、タグの代わりに「フォルダの名前」で選ぶ（登録したフォルダ・その中のフォルダ）。
曲が流れていると、エレクトロガールがときどきノッてくれる。
たまに、模様の入ったスペシャルカラーレコード（6種類）が回る。見つけた盤はコレクションに残る。
曲ごとにレコードのラベルの色が変わって、再生中はくるくる回る。

操作:
  PREV / STOP / NEXT … 前の曲 / 停止と再生 / 次の曲
  再生位置バー       … クリック・ドラッグでその位置へ
  音量バー           … クリック・ドラッグで音量
  ダブルクリック     … 再生中のファイルを Eagle で開く（フォルダのときは、ふつうのアプリで開く）
  ドラッグ           … ウィンドウを移動
  右クリック         … メニュー（タグ / 流すファイル / カラー / サイズ など）

必要なもの:
  VLC 本体（https://www.videolan.org/）
  pip install python-vlc pillow
"""
import json
import math
import os
import queue
import random
import sys
import threading
import time
import webbrowser
from collections import Counter, deque
import tkinter as tk
from tkinter import filedialog

from PIL import Image, ImageDraw, ImageTk

from mushiboshi_ui import (COLORWAY_NAMES, log_errors, is_night_time, PixelMenu, colorway_cmap, colorway_menu,
                           colorway_theme, load_colorway, pick_items, recolor, save_colorway, save_now_playing,
                           ui_font, Scale, PX_FONT, hexc, mix, px_pattern, px_text, px_text_w, save_json,
                           folder_label, scan_media_folders, load_folder_index, save_folder_index)


def _add_vlc_dll_dirs():
    """Windows では Python 3.8 以降、VLC の DLL の場所を明示しないと読み込めないことがある。"""
    if not sys.platform.startswith("win") or not hasattr(os, "add_dll_directory"):
        return
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        d = os.path.join(base, "VideoLAN", "VLC")
        if os.path.isfile(os.path.join(d, "libvlc.dll")):
            try:
                os.add_dll_directory(d)
                os.environ.setdefault("PYTHON_VLC_MODULE_PATH", os.path.join(d, "plugins"))
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            except OSError:
                pass


_add_vlc_dll_dirs()
try:
    import vlc
    VLC_ERROR = None
except Exception as ex:
    vlc = None
    VLC_ERROR = str(ex)

APP_VERSION = "1.4"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "record_config.json")
INDEX_PATH = os.path.join(APP_DIR, "record_index.json")
THEATER_INDEX = os.path.join(APP_DIR, "theater_index.json")   # シアターの一覧があれば借りる
BORROW_CONFIGS = ("theater_config.json", "frame_config.json")
INDEX_VERSION = 1
FOLDER_INDEX_PATH = os.path.join(APP_DIR, "record_folder_index.json")   # フォルダの曲の一覧
RESCAN_HOURS = 12           # フォルダの一覧が、これより古ければ裏で探し直す

VIDEO_EXTS = {"mp4", "webm", "mov", "mkv", "avi", "m4v", "flv", "wmv", "mpg", "mpeg", "ts"}
AUDIO_EXTS = {"mp3", "wav", "m4a", "ogg", "flac", "aac", "opus", "wma"}


def folder_kind(ext):
    return "video" if ext in VIDEO_EXTS else "audio" if ext in AUDIO_EXTS else None

DEFAULT_CONFIG = {
    "source": "eagle",      # 読み込み先 "eagle"=Eagle のライブラリ / "folder"=ふつうのフォルダ
    "library": "",
    "folders": [],          # ふつうのフォルダのパス（いくつでも）
    "other_tags": None,     # 読み込み先を切り替えたときの、もう片方のタグ選び
    "tags": ["参考資料"],
    "tag_choices": ["参考資料", "自力絵"],
    "kinds": "audio",      # "audio"=音声ファイルだけ / "both"=動画の音も
    "volume": 70,
    "muted": False,
    "scale": 3,            # 1ドットの大きさ
    "topmost": True,
    "x": 160,
    "y": 160,
    "rare_found": [],      # 見つけたスペシャルカラーレコード
}
KINDS = [("音声ファイルだけ", "audio"), ("動画の音も流す", "both")]
SCALES = [("ミニ", 1.5), ("小", 2), ("中", 3), ("大", 4)]

# ---------- ドット絵 ----------

_ICONS = {
    "record": "..###..|.#...#.|#..#..#|#.###.#|#..#..#|.#...#.|..###..",
    "play": "#...|##..|###.|##..|#...",
    "pause": "#.#|#.#|#.#|#.#|#.#",
    "next": "#..#..|##.##.|######|##.##.|#..#..",
    "prev": "..#..#|.##.##|######|.##.##|..#..#",
    "sound": "..#..#.|.##...#|###.#.#|.##...#|..#..#.",
    "mute": "..#....|.##.#.#|###..#.|.##.#.#|..#....",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
    "note": "..##|..#.|..#.|###.|###.",
}

# 元の色（カラーで塗り替えられる）
PAL = dict(face=(244, 240, 252), out=(54, 46, 84), light=(255, 255, 255), shade=(200, 192, 228),
           title=(176, 160, 232), title2=(206, 196, 244), accent=(236, 84, 140), hover=(255, 214, 232),
           second=(132, 116, 190))
COLOR_BASE = {v: k for k, v in PAL.items() if k != "light"}

# レイアウト（ドット単位）
W, H = 106, 166                          # 縦長
DX, DY, DW, DH = 3, 14, 100, 104          # ターンテーブルの台
NAME_Y, BAR_Y = 120, 131
ROW1, ROW2 = 139, 152
BUTTONS = {"prev": (3, ROW1, 17), "play": (21, ROW1, 41), "next": (63, ROW1, 40), "mute": (3, ROW2, 13)}
VOL_X, VOL_W = 17, 86
TRACK_W = 60                              # 再生位置バーの長さ
CX, CY, R = 45, 48, 40                    # レコードの中心と半径（台の中で）
ARM_PIVOT = (92, 12)

LABEL_COLORS = [(240, 96, 140), (110, 200, 170), (250, 200, 90), (120, 150, 230), (250, 150, 90),
                (190, 140, 230), (255, 255, 255), (70, 70, 80), (240, 70, 70), (150, 210, 120)]
VINYL_COLORS = [(250, 140, 180), (120, 210, 190), (150, 170, 240), (250, 190, 110), (200, 160, 240)]


def fmt_time(ms):
    s = max(0, int(ms // 1000))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def render_window(p):
    k = PAL
    im = Image.new("RGB", (W, H), k["face"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W - 1, H - 1], outline=k["out"])
    d.line([(1, 1), (W - 2, 1)], fill=k["light"])
    d.line([(1, 1), (1, H - 2)], fill=k["light"])
    d.rectangle([2, 2, W - 3, 11], fill=k["title"])
    for y in range(2, 6):
        for x in range(2 + (y % 2), W - 2, 2):
            d.point((x, y), fill=k["title2"])
    px_pattern(d, 4, 3, _ICONS["record"], k["out"])
    px_text(d, 14, 5, "RECORD.EXE", k["out"])
    bx0 = W - 3 - 3 * 9
    for i, icon in enumerate(("min", "max", "close")):
        x0 = bx0 + i * 9
        d.rectangle([x0, 3, x0 + 7, 10], fill=k["hover"] if icon == "close" else k["face"], outline=k["out"])
        px_pattern(d, x0 + 1, 4, _ICONS[icon], k["out"])
    d.line([(1, 12), (W - 2, 12)], fill=k["out"])
    d.rectangle([DX - 1, DY - 1, DX + DW, DY + DH], outline=k["out"])
    d.rectangle([DX, NAME_Y - 1, DX + DW - 1, NAME_Y + 9], fill=k["light"], outline=k["out"])
    return im


def render_button(icon, text, width, hover=False):
    k = PAL
    iw = len(_ICONS[icon].split("|")[0])
    w, h = width, 11
    fill = k["hover"] if hover else k["face"]
    im = Image.new("RGB", (w, h), fill)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], fill=fill, outline=k["out"])
    d.line([(1, 1), (w - 2, 1)], fill=k["light"])
    d.line([(1, h - 2), (w - 2, h - 2)], fill=tuple(round(v * 0.88) for v in fill))
    iy = (h - len(_ICONS[icon].split("|"))) // 2
    if text:
        px_pattern(d, 3, iy, _ICONS[icon], k["out"] if hover else k["accent"])
        px_text(d, 3 + iw + 2, 3, text, k["out"])
    else:
        px_pattern(d, (w - iw) // 2, iy, _ICONS[icon], k["out"] if hover else k["accent"])
    return im


PLATTER = (36, 34, 46)
GOLD = (236, 196, 96)

# スペシャルカラーレコード：(種類, 名前, 出やすさ)
SPECIALS = [("marble", "MARBLE", 3), ("splatter", "SPLATTER", 3), ("split", "HALF & HALF", 3),
            ("picture", "PICTURE DISC", 2), ("clear", "CLEAR", 2), ("rainbow", "RAINBOW", 1)]
SPECIAL_NAMES = {k: n for k, n, _ in SPECIALS}
SPECIAL_JA = {"marble": "マーブル", "splatter": "スプラッター", "split": "ハーフ＆ハーフ",
              "picture": "ピクチャー盤", "clear": "クリア", "rainbow": "レインボー"}
SPECIAL_CHANCE = 0.07
PICTURE_MOTIFS = {   # ピクチャー盤に印刷する小さな絵
    "heart": (".#.#.|#####|.###.|..#..", (240, 96, 140)),
    "star": ("..#..|#####|.###.|.#.#.", (250, 200, 90)),
    "berry": ("..#..|.###.|#####|.###.|..#..", (230, 70, 90)),
}


def new_record():
    if random.random() < SPECIAL_CHANCE:
        kind = random.choices([k for k, _, _ in SPECIALS], [w for _, _, w in SPECIALS])[0]
        c1, c2 = random.sample(VINYL_COLORS, 2)
        return {"label": random.choice(LABEL_COLORS), "colored": True, "vinyl": c1, "special": kind,
                "colors": [c1, c2, random.choice(LABEL_COLORS)], "seed": random.randrange(10 ** 6)}
    colored = random.random() < 0.3
    return {"label": random.choice(LABEL_COLORS), "colored": colored, "special": None,
            "vinyl": random.choice(VINYL_COLORS) if colored else (30, 30, 38), "seed": random.randrange(10 ** 6)}


def _rainbow(t):
    """0〜1 → パステルの虹色。"""
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(t % 1.0, 0.42, 0.98)
    return round(r * 255), round(g * 255), round(b * 255)


def make_disc(rec):
    """レコード1枚の絵（ラベルまで）。回転させて使う。溝・模様・ラベルを、点ごとに描く。"""
    size = 2 * R + 1
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = im.load()
    kind = rec.get("special")
    c1, c2, c3 = (rec.get("colors") or [rec["vinyl"]] * 3)[:3]
    rnd = random.Random(rec.get("seed", 0))
    base = rec["vinyl"] if rec["colored"] else (30, 30, 38)
    blobs = [(rnd.uniform(-R, R), rnd.uniform(-R, R), rnd.uniform(1.5, 4.5), rnd.choice([c2, c3, (255, 255, 255)]))
             for _ in range(46)] if kind == "splatter" else []
    for y in range(size):
        for x in range(size):
            dx, dy = x - R, y - R
            r = math.hypot(dx, dy)
            if r > R + 0.4:
                continue
            th = math.atan2(dy, dx)
            if kind == "marble":     # 2色がぐるぐる混ざる
                v = math.sin(th * 2 + r * 0.22 + math.sin(r * 0.37 + th * 3) * 1.8)
                c = c1 if v < -0.25 else c2 if v > 0.35 else mix(c1, c2, 0.5)
            elif kind == "splatter":  # 絵の具を飛ばしたような
                c = c1
                for bx, by, br, bc in blobs:
                    if (dx - bx) ** 2 + (dy - by) ** 2 <= br * br:
                        c = bc
                        break
            elif kind == "split":     # 半分ずつ
                c = c1 if dx < 0 else c2
                if abs(dx) < 0.6:
                    c = mix(c1, c2, 0.5)
            elif kind == "picture":   # 淡い地に、小さな絵がぐるりと並ぶ（あとで描く）
                c = mix(c1, (255, 255, 255), 0.45)
            elif kind == "clear":     # すけて、下のターンテーブルが見える
                c = mix(PLATTER, c1, 0.4)
            elif kind == "rainbow":   # 外へ向かって虹色
                c = _rainbow(r / R * 0.9 + th / (math.pi * 2) * 0.15)
            else:
                c = base
            if r >= R - 1:   # ふちは濃く（溝は回さずに、あとから上に重ねる）
                c = mix(c, (0, 0, 0), 0.4)
            alpha = 200 if kind == "clear" and r < R - 1 else 255
            px[x, y] = c + (alpha,)
    d = ImageDraw.Draw(im)
    if kind == "picture":
        motifs = list(PICTURE_MOTIFS.values())
        for ring, count in ((22, 8), (32, 12)):
            for i in range(count):
                a = i / count * math.pi * 2 + ring
                pat, col = motifs[(i + ring) % len(motifs)]
                px_pattern(d, R + ring * math.cos(a) - 2, R + ring * math.sin(a) - 2, pat, col)
    if kind == "clear":   # きらきらのつぶ
        for _ in range(30):
            a, rr = rnd.uniform(0, math.pi * 2), rnd.uniform(16, R - 3)
            d.point((R + rr * math.cos(a), R + rr * math.sin(a)), fill=mix(c1, (255, 255, 255), 0.6) + (255,))
    if not kind:   # 回っているのがわかるように、外周にしるし
        d.rectangle([R + R - 5, R - 1, R + R - 3, R + 1], fill=mix(base, (255, 255, 255), 0.5) + (255,))
    # ラベル（スペシャル盤は金のふちと星）
    lc = rec["label"] if not kind else c3
    d.ellipse([R - 14, R - 14, R + 14, R + 14], fill=lc, outline=GOLD if kind else mix(lc, (0, 0, 0), 0.35))
    dark = mix(lc, (0, 0, 0), 0.22)
    d.pieslice([R - 13, R - 13, R + 13, R + 13], 0, 70, fill=dark)
    d.pieslice([R - 13, R - 13, R + 13, R + 13], 180, 250, fill=dark)
    a = math.radians(35)
    d.ellipse([R + 9 * math.cos(a) - 1, R + 9 * math.sin(a) - 1, R + 9 * math.cos(a) + 1, R + 9 * math.sin(a) + 1],
              fill=(255, 255, 255))
    if kind:
        px_pattern(d, R - 9, R - 3, "..#..|#####|.###.|.#.#.", GOLD)
    return im


def _groove_mask():
    """レコードの溝（回っても形が変わらないので、回転させずに重ねる）。3本に1本を少し暗く。"""
    size = 2 * R + 1
    m = Image.new("L", (size, size), 0)
    px = m.load()
    for y in range(size):
        for x in range(size):
            r = math.hypot(x - R, y - R)
            if 15 < r < R - 1 and int(r) % 3 == 0:
                px[x, y] = 58
    return m


GROOVES = _groove_mask()


def render_deck(angle, record, playing, arm_t, level, k=PAL, now=0.0):
    """ターンテーブル。angle=回転角、record=今のレコードの見た目、arm_t=0（上がってる）〜1（盤の上）"""
    plinth = mix(k["second"], k["title"], 0.45)
    im = Image.new("RGB", (DW, DH), plinth)
    d = ImageDraw.Draw(im)
    # 台：上が少し明るく、木目のすじ
    for y in range(DH):
        d.line([(0, y), (DW - 1, y)], fill=mix(mix(plinth, k["light"], 0.12), plinth, y / DH))
    rnd = random.Random(3)
    for y in range(4, DH - 10, 5):
        x0 = rnd.randint(-10, 30)
        d.line([(x0, y), (x0 + rnd.randint(30, 70), y + rnd.choice((0, 1)))], fill=mix(plinth, k["out"], 0.1))
    d.rectangle([0, 0, DW - 1, DH - 1], outline=mix(plinth, k["light"], 0.35))
    d.line([(0, DH - 1), (DW - 1, DH - 1)], fill=mix(plinth, k["out"], 0.3))
    # プラッター（外周のストロボの点は、回る）
    d.ellipse([CX - R - 4, CY - R - 4, CX + R + 4, CY + R + 4], fill=mix(PLATTER, (255, 255, 255), 0.18),
              outline=k["out"])
    d.ellipse([CX - R - 2, CY - R - 2, CX + R + 2, CY + R + 2], fill=PLATTER)
    for i in range(36):
        a = math.radians(angle + i * 10)
        d.point((CX + (R + 3) * math.cos(a), CY + (R + 3) * math.sin(a)),
                fill=(200, 200, 214) if i % 2 else (120, 120, 136))
    if record:
        if "disc" not in record:
            record["disc"] = make_disc(record)
        disc = record["disc"].rotate(-angle, resample=Image.NEAREST)
        im.paste(disc, (CX - R, CY - R), disc)
        im.paste((0, 0, 0), (CX - R, CY - R, CX + R + 1, CY + R + 1), GROOVES)
        base = record["vinyl"] if record["colored"] else (30, 30, 38)
        # 光の反射（回らない）
        shine = mix(base, (255, 255, 255), 0.35)
        for rr in range(19, R - 2, 4):
            d.arc([CX - rr, CY - rr, CX + rr, CY + rr], 205, 235, fill=shine)
            d.arc([CX - rr, CY - rr, CX + rr, CY + rr], 25, 55, fill=shine)
        if record.get("special"):
            if playing:   # スペシャル盤は、ふちがきらきら
                for i in range(3):
                    a = math.radians((now * 40 + i * 130) % 360)
                    sx, sy = CX + (R - 2) * math.cos(a), CY + (R - 2) * math.sin(a)
                    if int(now * 4 + i) % 3:
                        px_pattern(d, sx - 2, sy - 2, "..#..|..#..|#####|..#..|..#..", (255, 250, 220))
            tag = SPECIAL_NAMES[record["special"]]
            d.rectangle([2, 2, 4 + px_text_w(tag) + 9, 9], fill=(40, 32, 56))   # 昼も夜も濃い地に金の文字
            px_pattern(d, 4, 3, ".#.|###|.#.", GOLD)
            px_text(d, 9, 3, tag, GOLD)
    d.ellipse([CX - 2, CY - 2, CX + 2, CY + 2], fill=(210, 210, 220), outline=(90, 90, 100))
    d.point((CX - 1, CY - 1), fill=(250, 250, 255))
    # トーンアーム（うしろにおもり、先にヘッドシェル）
    px, py = ARM_PIVOT
    d.ellipse([px - 7, py - 7, px + 7, py + 7], fill=mix(k["second"], k["out"], 0.5), outline=k["out"])
    d.arc([px - 6, py - 6, px + 6, py + 6], 200, 290, fill=mix(k["second"], k["light"], 0.3))
    rest = (px + 2, py + 52)
    on = (CX + 26, CY - 22)
    tx = rest[0] + (on[0] - rest[0]) * arm_t
    ty = rest[1] + (on[1] - rest[1]) * arm_t
    ang = math.atan2(ty - py, tx - px)
    wx, wy = px - 9 * math.cos(ang), py - 9 * math.sin(ang)   # おもり
    d.line([(px, py), (wx, wy)], fill=(150, 150, 160), width=3)
    d.ellipse([wx - 3, wy - 3, wx + 3, wy + 3], fill=(90, 90, 104), outline=k["out"])
    d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(210, 210, 220), outline=k["out"])
    d.line([(px, py), (tx, ty)], fill=(220, 220, 228), width=3)
    d.line([(px, py), (tx, ty)], fill=(150, 150, 160), width=1)
    d.line([(px + 1, py - 1), (tx + 1, ty - 1)], fill=(246, 246, 252))
    d.rectangle([tx - 3, ty - 2, tx + 3, ty + 3], fill=k["out"])
    d.rectangle([tx - 2, ty - 1, tx + 2, ty + 2], fill=k["accent"])
    d.line([(tx + 3, ty), (tx + 5, ty - 2)], fill=k["out"])   # 指かけ
    # 右のピッチのつまみ
    d.rectangle([92, 64, 95, 86], fill=mix(plinth, k["out"], 0.25))
    d.rectangle([90, 74, 97, 76], fill=(210, 210, 220), outline=k["out"])
    # 下の表示
    rx = 4
    px_text(d, rx, 95, "33 RPM", mix(plinth, k["light"], 0.75))
    lamp = k["accent"] if playing else mix(plinth, k["out"], 0.4)
    d.ellipse([rx + 27, 95, rx + 31, 99], fill=lamp)
    if playing:
        d.point((rx + 28, 96), fill=mix(lamp, (255, 255, 255), 0.5))
    rx = 64
    # 小さなレベルメーター
    for i in range(8):
        h = max(1, int(level[i] * 6)) if playing else 1
        for j in range(h):
            c = k["accent"] if j >= 5 else mix(k["title"], k["light"], 0.45)
            d.rectangle([rx + i * 4, 99 - j * 2, rx + 2 + i * 4, 99 - j * 2], fill=c)
    return im


# ---------- 設定と一覧 ----------

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        for name in BORROW_CONFIGS:   # 初回は、ほかのツールの設定からライブラリとタグを借りる
            try:
                with open(os.path.join(APP_DIR, name), encoding="utf-8") as f:
                    other = json.load(f)
            except (OSError, ValueError):
                continue
            for key in ("library", "tag_choices", "tags"):
                if other.get(key):
                    cfg[key] = other[key]
            break
    for t in cfg["tags"]:
        if t not in cfg["tag_choices"]:
            cfg["tag_choices"].append(t)
    cfg["rare_found"] = list(cfg.get("rare_found") or [])
    return cfg


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


def load_index(library):
    for path in (INDEX_PATH, THEATER_INDEX):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version") == INDEX_VERSION and data.get("library") == library:
                return data.get("items", [])
        except (OSError, ValueError):
            continue
    return None


def save_index(library, items):
    save_json(INDEX_PATH, {"version": INDEX_VERSION, "library": library, "items": items}, pretty=False)


def is_library(path):
    return bool(path) and os.path.isdir(os.path.join(path, "images"))


def find_media_file(info_dir, name, ext):
    path = os.path.join(info_dir, f"{name}.{ext}")
    if os.path.exists(path):
        return path
    try:
        for fn in os.listdir(info_dir):
            if fn.lower().rsplit(".", 1)[-1] == ext:
                return os.path.join(info_dir, fn)
    except OSError:
        pass
    return None


def scan_library(library, progress=None):
    """タグ付きの動画・音声を [id, path, name, tags, kind] のリストで返す（シアターと同じ形）。"""
    items = []
    count = 0
    with os.scandir(os.path.join(library, "images")) as it:
        for entry in it:
            if not entry.name.endswith(".info") or not entry.is_dir():
                continue
            count += 1
            if progress and count % 500 == 0:
                progress(count, len(items))
            try:
                with open(os.path.join(entry.path, "metadata.json"), encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                continue
            if meta.get("isDeleted"):
                continue
            ext = str(meta.get("ext", "")).lower()
            kind = "video" if ext in VIDEO_EXTS else "audio" if ext in AUDIO_EXTS else None
            if not kind:
                continue
            tags = [t for t in (meta.get("tags") or []) if isinstance(t, str)]
            if not tags:
                continue
            path = find_media_file(entry.path, meta.get("name", ""), ext)
            if path:
                items.append([meta.get("id", ""), path, meta.get("name", ""), tags, kind])
    return items


# ---------- 本体 ----------

class RecordPlayer:
    def __init__(self):
        self.cfg = load_config()
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.p = Scale(self.cfg["scale"])
        self.items, self.pool = [], []
        self.recent = deque(maxlen=40)
        self.history = deque(maxlen=50)
        self.current = None
        self.record = None
        self.angle = 0.0
        self.arm = 0.0
        self.level = [0.0] * 8
        self.paused = False
        self.scanning = False
        self.wait_ticks = 0
        self.told = (None, 0.0)   # ほかのツールに最後に知らせた（再生中かどうか, 曲）と時刻
        self.q = queue.Queue()
        self.pimgs = {}

        self.root = tk.Tk()
        log_errors(self.root, "record_error.txt")
        self.root.title(f"資料レコード ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "record_player.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])

        self.frame_label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.deck = tk.Label(self.root, bd=0, highlightthickness=0)
        self.name = tk.Label(self.root, anchor="w", bd=0)
        self.bar = tk.Canvas(self.root, bd=0, highlightthickness=0, cursor="hand2")
        self.vol = tk.Canvas(self.root, bd=0, highlightthickness=0, cursor="hand2")
        for w in (self.root, self.frame_label, self.deck, self.name):
            self.bind_events(w)
        self.frame_label.bind("<Motion>", self.frame_hover, add="+")
        self.frame_label.bind("<ButtonRelease-1>", self.frame_click, add="+")
        for w, fn in ((self.bar, self.seek_at), (self.vol, self.volume_at)):
            w.bind("<Button-1>", fn)
            w.bind("<B1-Motion>", fn)
            w.bind("<Button-3>", self.popup_menu)
        self.buttons = {}
        for key, action in (("prev", self.prev_item), ("play", self.toggle_play),
                            ("next", self.next_item), ("mute", self.toggle_mute)):
            lb = tk.Label(self.root, bd=0, highlightthickness=0, cursor="hand2")
            lb.bind("<Button-1>", lambda e, a=action: a())
            lb.bind("<Enter>", lambda e, k=key: self.draw_button(k, True))
            lb.bind("<Leave>", lambda e, k=key: self.draw_button(k, False))
            lb.bind("<Button-3>", self.popup_menu)
            self.buttons[key] = lb

        self.pmenu = PixelMenu(self.root, self.menu_theme, title="RECORD.EXE - MENU")
        self.layout()

        self.player = None
        self.vlc_problem = VLC_ERROR
        if vlc:
            try:
                self.vlc = vlc.Instance("--quiet", "--no-video")
                self.player = self.vlc.media_player_new()
                self.player.audio_set_volume(self.cfg["volume"])
            except Exception as ex:
                self.player, self.vlc_problem = None, str(ex)

        self.root.after(100, self.animate)
        self.root.after(250, self.poll)
        self.root.after(200, self.start)
        self.root.after(2000, self.watch_colorway)

    # --- 色 ---
    def cmap(self):
        return colorway_cmap(COLOR_BASE, self.colorway)

    def col(self, role):
        c = PAL[role]
        return (self.cmap() or {}).get(c, c)

    def menu_theme(self):
        if self.colorway != "original" or is_night_time():
            return colorway_theme(self.colorway, COLOR_BASE)
        return dict(face=PAL["face"], out=PAL["out"], light=PAL["light"], title=PAL["title"],
                    title2=PAL["title2"], title_text=PAL["out"], accent=PAL["accent"],
                    sub=mix(PAL["out"], PAL["face"], 0.45), text=PAL["out"], field=PAL["light"],
                    select=PAL["accent"], select_text=PAL["light"])

    def set_colorway(self, name):
        save_colorway(name)
        self.colorway = name
        self.layout()

    def watch_colorway(self):
        look = (load_colorway(), is_night_time())   # 色を変えたとき・昼夜が切り替わったときに着替える
        if look != self.look:
            self.look = look
            self.colorway = look[0]
            self.layout()
        self.root.after(2000, self.watch_colorway)

    # --- 見た目 ---
    def layout(self):
        p = self.p
        self.root.geometry(f"{W * p}x{H * p}+{self.cfg['x']}+{self.cfg['y']}")
        img = recolor(render_window(p), self.cmap()).resize((W * p, H * p), Image.NEAREST)
        self.frame_photo = ImageTk.PhotoImage(img)
        self.frame_label.config(image=self.frame_photo)
        self.frame_label.place(x=0, y=0, width=W * p, height=H * p)
        self.deck.place(x=DX * p, y=DY * p, width=DW * p, height=DH * p)
        self.name.config(bg=hexc(self.col("light")), fg=hexc(self.col("out")),
                         font=ui_font(self.root, max(11, int(p * 3.4))))
        self.name.place(x=(DX + 2) * p, y=NAME_Y * p, width=(DW - 4) * p, height=8 * p)
        self.bar.config(bg=hexc(self.col("face")))
        self.bar.place(x=DX * p, y=BAR_Y * p, width=DW * p, height=6 * p)
        self.vol.config(bg=hexc(self.col("face")))
        self.vol.place(x=VOL_X * p, y=ROW2 * p, width=VOL_W * p, height=11 * p)
        for key, (x, y, w) in BUTTONS.items():
            self.draw_button(key)
            self.buttons[key].place(x=x * p, y=y * p)
        self.draw_deck()
        self.draw_bar(0, 0)
        self.draw_volume()

    def draw_deck(self):
        pal = {role: self.col(role) for role in PAL}
        img = render_deck(self.angle, self.record, self.is_playing(), self.arm, self.level, pal, time.time())
        img = img.resize((DW * self.p, DH * self.p), Image.NEAREST)
        self.deck_photo = ImageTk.PhotoImage(img)
        self.deck.config(image=self.deck_photo)

    def draw_button(self, key, hover=False):
        x, y, w = BUTTONS[key]
        icon, text = {"prev": ("prev", ""), "next": ("next", "NEXT"),
                      "play": ("play", "PLAY") if self.paused or not self.current else ("pause", "STOP"),
                      "mute": ("mute" if self.cfg["muted"] else "sound", "")}[key]
        img = recolor(render_button(icon, text, w, hover), self.cmap())
        img = ImageTk.PhotoImage(img.resize((w * self.p, 11 * self.p), Image.NEAREST))
        self.pimgs[key] = img
        self.buttons[key].config(image=img)

    def canvas_text(self, cv, x, y, text, color):
        p = self.p
        for i, ch in enumerate(text.upper()):
            for ry, row in enumerate(PX_FONT.get(ch, PX_FONT["?"]).split("|")):
                for rx, c in enumerate(row):
                    if c == "#":
                        X, Y = (x + i * 4 + rx) * p, (y + ry) * p
                        cv.create_rectangle(X, Y, X + p, Y + p, fill=color, width=0)

    def draw_bar(self, pos, total):
        cv, p = self.bar, self.p
        cv.delete("all")
        cv.create_rectangle(0, p, TRACK_W * p, 5 * p, fill=hexc(self.col("light")), outline=hexc(self.col("out")),
                            width=max(1, p // 2))
        if total > 0:
            fw = int((TRACK_W - 2) * min(1, pos / total))
            if fw > 0:
                cv.create_rectangle(p, 2 * p, (1 + fw) * p, 4 * p, fill=hexc(self.col("accent")), width=0)
        label = f"{fmt_time(pos)}/{fmt_time(total)}" if total > 0 else "--:--"
        self.canvas_text(cv, DW - px_text_w(label), 1, label, hexc(self.col("out")))

    def draw_volume(self):
        cv, p = self.vol, self.p
        cv.delete("all")
        v = 0 if self.cfg["muted"] else self.cfg["volume"]
        cv.create_rectangle(p, 4 * p, (VOL_W - 2) * p, 7 * p, fill=hexc(self.col("light")),
                            outline=hexc(self.col("out")), width=max(1, p // 2))
        fw = int((VOL_W - 4) * v / 100)
        if fw > 0:
            cv.create_rectangle(2 * p, 5 * p, (2 + fw) * p, 6 * p, fill=hexc(self.col("accent")), width=0)
        kx = 1 + int((VOL_W - 5) * v / 100)
        cv.create_rectangle(kx * p, p, (kx + 3) * p, 10 * p, fill=hexc(self.col("face")),
                            outline=hexc(self.col("out")), width=max(1, p // 2))

    def show_message(self, text):
        self.name.config(text=text)

    # --- アニメーション ---
    def is_playing(self):
        return bool(self.current) and not self.paused

    def animate(self):
        playing = self.is_playing()
        if playing:
            self.angle = (self.angle + 360 * 0.55 * 0.1) % 360   # 33回転/分くらい
            for i in range(8):
                self.level[i] += (random.uniform(0.2, 1.0) - self.level[i]) * 0.6
        target = 1.0 if playing else 0.0
        if abs(self.arm - target) > 0.01:
            self.arm += (target - self.arm) * 0.35
        self.draw_deck()
        self.tell_others()
        self.root.after(100, self.animate)

    def tell_others(self):
        """曲が聞こえているかを、ほかのツール（エレクトロガールなど）に知らせる。
        変わったときと、再生中は5秒おきに書く（閉じ忘れても、書かれなくなれば止まった扱いになる）。"""
        audible = self.is_playing() and not self.cfg["muted"] and self.cfg["volume"] > 0
        key = (audible, self.current and self.current[0])
        if key != self.told[0] or (audible and time.time() - self.told[1] > 5):
            save_now_playing(audible, self.current[2] if audible else "", self.record and self.record["label"])
            self.told = (key, time.time())

    # --- 読み込み ---
    def start(self):
        if not self.player:
            hint = ""
            if self.vlc_problem and ("193" in self.vlc_problem or "%1" in self.vlc_problem):
                hint = "（Python と VLC の 64bit / 32bit が合っていないかも）"
            self.show_message("VLC が見つからないよ。VLC と python-vlc を入れてね" + hint)
            return
        if not self.folder_mode() and not self.cfg["library"] and not self.cfg["folders"]:
            self.first_choose()
        self.load_items()

    # --- 読み込み先（Eagle / ふつうのフォルダ） ---
    def folder_mode(self):
        return self.cfg.get("source") == "folder"

    def tag_word(self):
        return "フォルダ" if self.folder_mode() else "タグ"

    def first_choose(self):
        """はじめて起動したとき：曲のフォルダ（Eagle のライブラリでもOK）を選んでもらう。"""
        self.show_message("曲のフォルダを選んでね（Eagle のライブラリでもOK）")
        path = self.ask_folder("曲のフォルダ（または Eagle のライブラリ）を選択")
        if not path:
            return
        if is_library(path):
            self.cfg["library"] = path
            save_config(self.cfg)
        else:
            self.set_source("folder", load=False)
            self.register_folder(path)

    def ask_folder(self, title):
        self.root.attributes("-topmost", False)
        path = filedialog.askdirectory(parent=self.root, title=title)
        self.root.attributes("-topmost", self.cfg["topmost"])
        return os.path.normpath(path) if path else ""

    def set_source(self, source, load=True):
        """読み込み先を Eagle ⇔ フォルダで切り替える。タグ選びは、それぞれ覚えておく。"""
        c = self.cfg
        if c.get("source", "eagle") != source:
            other = c.get("other_tags") or [[], []]
            c["other_tags"] = [c["tags"], c["tag_choices"]]
            c["tags"], c["tag_choices"] = list(other[0]), list(other[1])
            c["source"] = source
            save_config(c)
            self.items, self.pool = [], []
            self.stop_player()
            self.current = None
            self.draw_button("play")
        if not load:
            return
        if source == "folder" and not c["folders"]:
            self.add_folder()
        elif source == "eagle" and not c["library"]:
            self.choose_library()
        self.load_items()

    def register_folder(self, path):
        c = self.cfg
        if path not in c["folders"]:
            c["folders"].append(path)
        label = folder_label(path)
        if label not in c["tag_choices"]:
            c["tag_choices"].append(label)
        if label not in c["tags"]:
            c["tags"].append(label)
        save_config(c)

    def add_folder(self):
        path = self.ask_folder("曲のフォルダを選択（中のフォルダも全部読むよ）")
        if not path:
            return
        if is_library(path):
            self.show_message("そこは Eagle のライブラリだよ。「読み込み先」→「Eagle のライブラリ」で選んでね")
            return
        self.register_folder(path)
        self.load_items(force=True)

    def remove_folder(self, path):
        c = self.cfg
        if path in c["folders"]:
            c["folders"].remove(path)
        label = folder_label(path)
        if not any(folder_label(f) == label for f in c["folders"]):
            c["tags"] = [t for t in c["tags"] if t != label]
            c["tag_choices"] = [t for t in c["tag_choices"] if t != label]
        save_config(c)
        self.load_items(force=True)

    def load_folder_items(self, force=False):
        folders = self.cfg["folders"]
        if not folders:
            self.stop_player()
            self.current = None
            self.draw_button("play")
            self.show_message("曲のフォルダが未設定だよ。右クリック →「読み込み先」→「フォルダを追加…」")
            return
        present = [f for f in folders if os.path.isdir(f)]
        if not present:
            self.show_message("フォルダが見つからないよ。外付けHDDはつながってる？（1分ごとに再確認するね）")
            self.root.after(60_000, self.load_items)
            return
        quiet = False
        if not force:
            cached = load_folder_index(FOLDER_INDEX_PATH, folders)
            if cached is not None and cached[0]:
                self.items = cached[0]
                self.apply_filter()
                if time.time() - cached[1] < RESCAN_HOURS * 3600:
                    return
                quiet = True   # 一覧が古いので、流しているものはそのままで、裏で探し直す
        if self.scanning:
            return
        self.scanning = True
        if not quiet:
            self.show_message("フォルダを読み込んでいます…")

        def work():
            try:
                items = scan_media_folders(present, folder_kind,
                                           progress=None if quiet else lambda n, h: self.q.put(("progress", n, h)))
                save_folder_index(FOLDER_INDEX_PATH, folders, items)
                self.q.put(("scanned", items, quiet))
            except OSError as ex:
                self.q.put(("scan_error", str(ex)))

        threading.Thread(target=work, daemon=True).start()

    def choose_library(self):
        self.root.attributes("-topmost", False)
        path = filedialog.askdirectory(parent=self.root, title="Eagle のライブラリフォルダを選択")
        self.root.attributes("-topmost", self.cfg["topmost"])
        if path and is_library(os.path.normpath(path)):
            self.cfg["library"] = os.path.normpath(path)
            save_config(self.cfg)

    def rechoose_library(self):
        self.choose_library()
        self.load_items(force=True)

    def load_items(self, force=False):
        if self.folder_mode():
            self.load_folder_items(force)
            return
        lib = self.cfg["library"]
        if not lib:
            self.show_message("ライブラリが未設定だよ。右クリック →「ライブラリ」")
            return
        if not is_library(lib):
            self.show_message("ライブラリが見つからないよ。外付けHDDはつながってる？")
            self.root.after(60_000, self.load_items)
            return
        if not force:
            cached = load_index(lib)
            if cached is not None:
                self.items = cached
                self.apply_filter()
                return
        if self.scanning:
            return
        self.scanning = True
        self.show_message("ライブラリを読み込んでいます…（初回は数分かかるかも）")

        def work():
            try:
                items = scan_library(lib, progress=lambda n, h: self.q.put(("progress", n, h)))
                save_index(lib, items)
                self.q.put(("scanned", items))
            except OSError as ex:
                self.q.put(("scan_error", str(ex)))

        threading.Thread(target=work, daemon=True).start()

    def apply_filter(self, restart=False):
        tags = set(self.cfg["tags"])
        kinds = self.cfg["kinds"]
        self.pool = [it for it in self.items
                     if tags.intersection(it[3]) and (kinds == "both" or it[4] == "audio")]
        if not self.pool:
            self.stop_player()
            self.current = None
            self.show_message(f"「{'＋'.join(self.cfg['tags']) or 'なし'}」の音声が見つからなかったよ")
            self.draw_button("play")
            return
        if restart or not self.current:
            self.next_item(record_history=False)

    # --- 再生 ---
    def pick_item(self):
        item = random.choice(self.pool)
        for _ in range(20):
            if item[0] not in self.recent and (not self.current or item[0] != self.current[0]):
                break
            item = random.choice(self.pool)
        self.recent.append(item[0])
        return item

    def play_item(self, item):
        if not self.player:
            return
        self.current = item
        self.record = new_record()
        special = self.record["special"]
        if special and special not in self.cfg["rare_found"]:   # はじめて見つけたスペシャル盤
            self.cfg["rare_found"].append(special)
            save_config(self.cfg)
        self.angle = random.uniform(0, 360)
        media = self.vlc.media_new(item[1])
        media.add_option(":no-video")
        self.player.set_media(media)
        self.player.audio_set_mute(self.cfg["muted"])
        self.player.play()
        self.wait_ticks = 0
        self.paused = False
        self.name.config(text=("★ " if special else "♪ ") + item[2])
        self.draw_button("play")

    def next_item(self, record_history=True):
        if not self.pool:
            return
        if record_history and self.current:
            self.history.append(self.current)
        self.play_item(self.pick_item())

    def prev_item(self):
        if self.history:
            self.play_item(self.history.pop())

    def stop_player(self):
        if self.player:
            self.player.stop()
        self.draw_bar(0, 0)

    def toggle_play(self):
        if not self.player or not self.current:
            return
        self.paused = not self.paused
        self.player.set_pause(1 if self.paused else 0)
        self.draw_button("play", True)

    def toggle_mute(self):
        self.cfg["muted"] = not self.cfg["muted"]
        save_config(self.cfg)
        if self.player:
            self.player.audio_set_mute(self.cfg["muted"])
        self.draw_button("mute", True)
        self.draw_volume()

    def seek_at(self, e):
        if not (self.player and self.current):
            return
        x = e.x / self.p
        length = self.player.get_length()
        if x > TRACK_W or length <= 0:
            return
        t = int(min(1, max(0, (x - 1) / (TRACK_W - 2))) * length)
        self.player.set_time(t)
        self.draw_bar(t, length)

    def volume_at(self, e):
        v = round(min(1, max(0, (e.x / self.p - 2) / (VOL_W - 4))) * 100)
        self.cfg["volume"] = v
        if self.cfg["muted"]:
            self.cfg["muted"] = False
            self.draw_button("mute")
        if self.player:
            self.player.audio_set_mute(False)
            self.player.audio_set_volume(v)
        self.draw_volume()
        save_config(self.cfg)

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "progress":
                    where = "フォルダ" if self.folder_mode() else "ライブラリ"
                    self.show_message(f"{where}を読み込んでいます…（{msg[1]:,} 件確認済み）")
                elif msg[0] == "scanned":
                    self.scanning = False
                    self.items = msg[1]
                    self.apply_filter(restart=not (len(msg) > 2 and msg[2]))   # 裏で探し直しただけなら、曲はそのまま
                elif msg[0] == "scan_error":
                    self.scanning = False
                    self.show_message(f"読み込みに失敗したよ：{msg[1]}")
        except queue.Empty:
            pass
        if self.player and self.current and not self.paused:
            state = self.player.get_state()
            if state in (vlc.State.Ended, vlc.State.Error):
                self.next_item()
            elif state == vlc.State.Playing:
                self.wait_ticks = 0
                length = self.player.get_length()
                if length > 0:
                    self.draw_bar(self.player.get_time(), length)
            else:
                self.wait_ticks += 1
                if self.wait_ticks > 40:   # 10秒たっても始まらない曲は飛ばす
                    self.next_item()
        self.root.after(250, self.poll)

    # --- メニュー ---
    def menu_items(self):
        c = self.cfg

        def short(text, n=10):
            return text if len(text) <= n else text[:n - 1] + "…"

        tag_items = [{"type": "check", "label": t, "checked": t in c["tags"],
                      "cmd": lambda t=t: self.toggle_tag(t)} for t in c["tag_choices"]]
        tag_items += [{"type": "sep"}, {"type": "cmd", "label": "タグを追加…" if not self.folder_mode() else "中のフォルダから選ぶ…",
                                        "cmd": self.add_tag}]
        kind_items = [{"type": "radio", "label": n, "checked": c["kinds"] == k,
                       "cmd": lambda k=k: self.set_kinds(k)} for n, k in KINDS]
        size_items = [{"type": "radio", "label": n, "checked": c["scale"] == v,
                       "cmd": lambda v=v: self.set_scale(v)} for n, v in SCALES]
        settings = [
            {"type": "sub", "label": "カラー", "items": lambda: colorway_menu(self.colorway, self.set_colorway),
             "right": next(n for n, k in COLORWAY_NAMES if k == self.colorway)},
            {"type": "sub", "label": "サイズ", "items": size_items,
             "right": next(n for n, v in SCALES if v == c["scale"])},
            {"type": "check", "label": "最前面に表示", "checked": c["topmost"], "cmd": self.toggle_topmost},
        ]
        folder = self.folder_mode()
        library = [{"type": "radio", "label": "Eagle のライブラリ", "checked": not folder,
                    "cmd": lambda: self.set_source("eagle")},
                   {"type": "radio", "label": "ふつうのフォルダ", "checked": folder,
                    "cmd": lambda: self.set_source("folder")},
                   {"type": "sep"},
                   {"type": "cmd", "label": "リストを再読み込み", "cmd": lambda: self.load_items(force=True)}]
        if folder:
            library += [{"type": "cmd", "label": "フォルダを追加…", "cmd": self.add_folder},
                        {"type": "sub", "label": "フォルダを外す", "enabled": bool(c["folders"]),
                         "items": [{"type": "cmd", "label": short(folder_label(f), 16),
                                    "right": "" if os.path.isdir(f) else "見つからない",
                                    "cmd": lambda f=f: self.remove_folder(f)} for f in c["folders"]]}]
        else:
            library.append({"type": "cmd", "label": "ライブラリを選び直す", "cmd": self.rechoose_library})
        word = self.tag_word()
        return [
            {"type": "cmd", "label": "次の曲", "cmd": self.next_item, "enabled": bool(self.pool)},
            {"type": "cmd", "label": "前の曲", "cmd": self.prev_item, "enabled": bool(self.history)},
            {"type": "cmd", "label": "再生する" if self.paused else "一時停止", "cmd": self.toggle_play,
             "enabled": bool(self.current)},
            {"type": "cmd", "label": "この曲のファイルを開く" if folder else "この曲を Eagle で開く", "cmd": self.open_in_eagle,
             "enabled": bool(self.current)},
            {"type": "sep"},
            {"type": "head", "label": "流す曲"},
            {"type": "sub", "label": word, "items": tag_items,
             "right": short("＋".join(c["tags"])) if c["tags"] else "なし"},
            {"type": "sub", "label": "流すファイル", "items": kind_items,
             "right": next(n for n, k in KINDS if k == c["kinds"])},
            {"type": "sep"},
            {"type": "sub", "label": "設定", "items": settings},
            {"type": "sub", "label": "読み込み先", "items": library, "right": "フォルダ" if folder else "Eagle"},
            {"type": "sub", "label": "スペシャルレコード", "right": f"{len(c['rare_found'])}/{len(SPECIALS)}",
             "items": [{"type": "head", "label": f"{len(c['rare_found'])}/{len(SPECIALS)} 枚みつけた"}]
             + [{"type": "head", "label": ("★ " + SPECIAL_JA[k2]) if k2 in c["rare_found"] else "？？？"}
                for k2, _, _ in SPECIALS]
             + [{"type": "head", "label": "曲ごとに、たまに出てくるよ"}]},
            {"type": "sep"},
            {"type": "cmd", "label": "終了", "cmd": self.quit},
            {"type": "head", "label": f"資料レコード ver.{APP_VERSION}"},
        ]

    def popup_menu(self, e):
        self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

    def toggle_tag(self, t):
        on = set(self.cfg["tags"]) ^ {t}
        self.cfg["tags"] = [x for x in self.cfg["tag_choices"] if x in on]
        save_config(self.cfg)
        self.apply_filter(restart=True)

    def add_tag(self):
        counts = Counter(t for it in self.items
                         if self.cfg["kinds"] == "both" or it[4] == "audio" for t in it[3])
        word = self.tag_word()
        if not counts:
            self.show_message("曲がまだ見つかっていないよ")
            return
        entries = [(t, f"{t}（{n:,}件）", t in self.cfg["tags"]) for t, n in counts.most_common()]
        picked = pick_items(self.root, self.menu_theme(), f"流す{word}を選ぶ", f"流したい{word}を選んでね",
                            entries, near=self.root)
        if not picked:
            return
        for t in picked:
            if t not in self.cfg["tag_choices"]:
                self.cfg["tag_choices"].append(t)
            if t not in self.cfg["tags"]:
                self.cfg["tags"].append(t)
        save_config(self.cfg)
        self.apply_filter(restart=True)

    def set_kinds(self, k):
        self.cfg["kinds"] = k
        save_config(self.cfg)
        self.apply_filter(restart=True)

    def set_scale(self, v):
        self.cfg["scale"] = v
        self.p = Scale(v)
        save_config(self.cfg)
        self.layout()

    def toggle_topmost(self):
        self.cfg["topmost"] = not self.cfg["topmost"]
        save_config(self.cfg)
        self.root.attributes("-topmost", self.cfg["topmost"])

    def open_in_eagle(self):
        if not self.current or not self.current[0]:
            return
        if self.folder_mode():   # フォルダのファイルは、ふつうのアプリで開く
            try:
                os.startfile(self.current[1])
            except (AttributeError, OSError):
                pass
            return
        url = f"eagle://item/{self.current[0]}"
        try:
            os.startfile(url)
        except (AttributeError, OSError):
            webbrowser.open(url)

    # --- ウィンドウ ---
    def bind_events(self, w):
        w.bind("<ButtonPress-1>", self.drag_start)
        w.bind("<B1-Motion>", self.drag_move)
        w.bind("<ButtonRelease-1>", self.drag_end)
        w.bind("<Double-Button-1>", lambda e: self.open_in_eagle())
        w.bind("<Button-3>", self.popup_menu)

    def drag_start(self, e):
        self._press = (e.x_root, e.y_root)
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def drag_end(self, e):
        self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        save_config(self.cfg)

    def hotspot_at(self, e):
        x = (e.x_root - self.root.winfo_rootx()) / self.p
        y = (e.y_root - self.root.winfo_rooty()) / self.p
        bx0 = W - 3 - 3 * 9
        for name, (x0, y0, x1, y1) in {"min": (bx0, 3, bx0 + 7, 10), "close": (bx0 + 18, 3, bx0 + 25, 10)}.items():
            if x0 <= x <= x1 + 1 and y0 <= y <= y1 + 1:
                return name
        return None

    def frame_hover(self, e):
        self.frame_label.config(cursor="hand2" if self.hotspot_at(e) else "")

    def frame_click(self, e):
        px, py = getattr(self, "_press", (e.x_root, e.y_root))
        if abs(e.x_root - px) > 4 or abs(e.y_root - py) > 4:
            return
        spot = self.hotspot_at(e)
        if spot == "close":
            self.quit()
        elif spot == "min":
            self.root.overrideredirect(False)
            self.root.iconify()

            def restore(ev):
                if ev.widget is self.root and self.root.state() == "normal":
                    self.root.overrideredirect(True)
                    self.root.unbind("<Map>")
            self.root.bind("<Map>", restore)

    def quit(self):
        save_config(self.cfg)
        save_now_playing(False)
        if self.player:
            self.player.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        RecordPlayer().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "record_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
