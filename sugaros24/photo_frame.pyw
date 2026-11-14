# -*- coding: utf-8 -*-
"""
資料フォトフレーム ver.2
Eagle ライブラリから選んだタグ（「参考資料」「自力絵」など）の画像をランダム表示する常駐ウィンドウ。
見た目は「ドットSNS（タイムライン風）」と「ドット窓（デスクトップ風）」の2種類。

操作:
  STOP / PLAY     … 再生と停止
  NEXT            … 次の画像へ
  ドラッグ        … ウィンドウを移動
  ダブルクリック  … その画像を Eagle で開く
  右クリック      … メニュー（表示するタグ / 並べる枚数 / 色縛り / 見た目 / 間隔 / サイズ など）

必要なもの: pip install pillow
"""
import colorsys
import json
import os
import queue
import random
import threading
import webbrowser
from collections import Counter, deque
import tkinter as tk
from tkinter import colorchooser, filedialog

from mushiboshi_ui import (COLORWAY_NAMES, dither_bar, log_errors, is_night_time, THEMES, PixelMenu, ask_text, colorway_menu,
                           colorway_theme, load_colorway, make_colormap, pick_items, recolor, save_colorway,
                           ui_font, PX_FONT, px_pattern, px_text, px_text_w, save_json)

from PIL import Image, ImageDraw, ImageOps, ImageTk

APP_VERSION = "2.5"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "frame_config.json")
INDEX_PATH = os.path.join(APP_DIR, "frame_index.json")
INDEX_VERSION = 3

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "bmp"}
BG = "#16161a"
BG_RGB = (0x16, 0x16, 0x1A)
GAP = 3  # 複数枚表示のときのすき間（px）
# 「細長い画像は全体を表示」で、細長いとみなす縦横比（長い辺 ÷ 短い辺）
ASPECT_FIT_RATIO = 1.3

# 色縛りの判定：その色が画像全体の何％以上を占めていたら「その色の画像」とみなすか
COLOR_MIN_SHARE = 15
# 「色を指定…」で選んだ色に、どれくらい近ければ同じ色とみなすか（大きいほどゆるい）
CUSTOM_COLOR_RANGE = 70

DEFAULT_CONFIG = {
    "library": "",          # 〇〇.library フォルダのパス
    "tags": ["参考資料"],                 # 表示するタグ（複数選ぶと「どれか付いていればOK」）
    "tag_choices": ["参考資料", "自力絵"],  # メニューに並べるタグ
    "interval_sec": 30,     # 切り替え間隔（秒）
    "size": 360,            # ウィンドウの一辺（px）
    "topmost": True,        # 最前面に表示
    "grid": 1,              # 1 / 2 / 3 → 1枚 / 2×2 / 3×3
    "switch": "one",        # 複数枚のときの切り替え方 "one"=1枚ずつ / "all"=まとめて
    "color": "",            # 色縛り（"" / 色名 / "#rrggbb"）
    "frame": "pixelsns",    # 見た目 "pixelsns" / "pixelwin" / "freeware"
    "fit_odd": True,        # 複数枚のとき、細長い画像は切り抜かずに全体を表示する
    "x": 100,
    "y": 100,
}

INTERVALS = [("5秒", 5), ("10秒", 10), ("30秒", 30), ("1分", 60), ("3分", 180),
             ("10分", 600), ("30分", 1800)]
SIZES = [("ミニ", 180), ("小", 240), ("中", 360), ("大", 520), ("特大", 720)]
GRIDS = [("1枚", 1), ("2×2（4枚）", 2), ("3×3（9枚）", 3)]
NO_COLOR = "__none__"  # 色縛りなし（メニュー用の目印）
COLOR_NAMES = ["赤", "オレンジ", "黄", "緑", "水色", "青", "紫", "ピンク", "茶", "白", "グレー", "黒"]


FRAMES = [("ドットSNS（タイムライン風）", "pixelsns"), ("ドット窓（デスクトップ風）", "pixelwin"),
          ("フリーソフト風（2000年代）", "freeware")]

SNS_CAPTIONS = ["TODAY'S PICK!", "LOOK AT THIS!!", "SO GOOD...", "SAVED IT AGAIN",
                "I LOVE THIS", "REFERENCE OF THE DAY", "NEED TO DRAW THIS", "MY FAVORITE"]
SNS_TIMES = ["JUST NOW", "1M", "5M", "12M", "1H", "3H"]
FREEWARE_BANNERS = ["!! NEW VERSION 1.03 OUT !!", "BEST VIEWED IN 800X600",
                    "PLEASE SIGN MY GUESTBOOK", "*** LINK FREE! ***", "VISITOR #{n:06d}",
                    "THANK YOU FOR DOWNLOADING!!", "SUPPORT: SEND ME AN E-MAIL"]


# ---------- ドット絵のフチ ----------

def _mix(c, target, t):
    return tuple(round(a + (b - a) * t) for a, b in zip(c, target))


_ICONS = {
    "heart": ".##.##.|#######|#######|.#####.|..###..|...#...",
    "bubble": ".#####.|#.....#|#.....#|.#####.|.#.....|#......",
    "repost": "..#....|.#####.|..#..#.|.#..#..|.#####.|....#..",
    "bookmark": "#####|#...#|#...#|#.#.#|##.##|#...#",
    "fwd": "..#..|...#.|#####|...#.|..#..",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
    "folder": "##....|######|#....#|#....#|######",
    "sparkle": "..#..|..#..|##.##|..#..|..#..",
    "play": "#...|##..|###.|##..|#...",
    "next": "#..#..|##.##.|######|##.##.|#..#..",
    "back": "..#..#|.##.##|######|.##.##|..#..#",
    "pause": "#.#|#.#|#.#|#.#|#.#",
    "disk": "#######|#.###.#|#.###.#|#######|#.....#|#.....#|#######",
    "help": ".###.|#...#|...#.|..#..|.....|..#..",
}


def short_count(n):
    return str(n) if n < 1000 else f"{n / 1000:.1f}K"


INFO_H = 12        # 画像の下の情報欄の高さ（ドット）
CHIPS_W = 5 * 7    # 色見本チップの幅
PIXEL_LAYOUT = {"pixelwin": (3, 27, 3, 11 + INFO_H), "pixelsns": (5, 31, 5, 19 + INFO_H),
                "freeware": (4, 36, 4, 27 + INFO_H)}
INFO_COLORS = {"pixelwin": ((255, 255, 255), (64, 48, 92)), "pixelsns": ((255, 255, 255), (58, 50, 78)),
               "freeware": ((255, 255, 255), (0, 0, 0))}


def draw_info_strip(d, style, x0, y0, hw, palette):
    """画像の下の情報欄（文字はあとから上に重ねる）と色見本チップ。"""
    fill, _ = INFO_COLORS[style]
    out = {"pixelwin": (64, 48, 92), "pixelsns": (70, 60, 90), "freeware": (0, 0, 0)}[style]
    if style == "freeware":
        d.rectangle([x0, y0, x0 + hw - 1, y0 + 9], fill=fill)
        win_bevel(d, x0, y0, x0 + hw - 1, y0 + 9, raised=False, single=True)
    else:
        d.rectangle([x0, y0, x0 + hw - 1, y0 + 9], fill=fill, outline=out)
    chips = sorted(palette or [], key=lambda c: -c[3])[:5]
    for i, c in enumerate(chips):
        x = x0 + hw - 1 - CHIPS_W + i * 7
        d.rectangle([x, y0 + 2, x + 5, y0 + 7], fill=(c[0], c[1], c[2]), outline=out)


def info_label_rect(style, size):
    """情報欄の文字を置く場所（ドット単位）: x, y, 幅, 高さ"""
    p = pixel_scale(size)
    L, T, R, B = PIXEL_LAYOUT[style]
    hw = -(-size // p)
    return (L + 2, T + hw + 3, hw - CHIPS_W - 5, 8)


def win_bevel(d, x0, y0, x1, y1, raised=True, single=False):
    """2000年代のウィンドウっぽい立体の線。raised=出っぱり / False=へこみ"""
    light, shadow, dark, soft = (255, 255, 255), (128, 128, 128), (0, 0, 0), (223, 223, 223)
    tl, br = (light, dark) if raised else (shadow, light)
    d.line([(x0, y1), (x0, y0), (x1, y0)], fill=tl)
    d.line([(x1, y0), (x1, y1), (x0, y1)], fill=br)
    if not single:
        tl2, br2 = (soft, shadow) if raised else (dark, soft)
        d.line([(x0 + 1, y1 - 1), (x0 + 1, y0 + 1), (x1 - 1, y0 + 1)], fill=tl2)
        d.line([(x1 - 1, y0 + 1), (x1 - 1, y1 - 1), (x0 + 1, y1 - 1)], fill=br2)


def resize_grip(d, x1, y1, dark, light):
    """右下の、ななめのつまみ。"""
    for k in (0, 3, 6):
        for i in range(k + 1):
            d.point((x1 - k + i, y1 - i), fill=dark)
            if i < k:
                d.point((x1 - k + i + 1, y1 - i), fill=light)


def pixel_scale(size):
    return max(2, round(size / 120))


# カラー（全ツール共通の配色）で塗り替える元の色
COLOR_BASE = {
    "pixelwin": {(64, 48, 92): "out", (244, 238, 255): "face", (196, 184, 224): "shade",
                 (255, 176, 206): "title", (255, 210, 228): "title2", (232, 72, 128): "accent",
                 (255, 214, 228): "hover", (255, 220, 232): "hover"},
    "pixelsns": {(70, 60, 90): "out", (255, 252, 246): "face", (140, 186, 206): "shade",
                 (186, 226, 240): "title", (206, 238, 248): "title2", (240, 96, 140): "accent",
                 (255, 222, 232): "hover", (150, 140, 168): "meta", (58, 50, 78): "text"},
}


def render_pixel(style, size, info, cmap=None):
    p = pixel_scale(size)
    L, T, R, B = PIXEL_LAYOUT[style]
    hw = -(-size // p)
    W, H = L + hw + R, T + hw + B
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    count = info.get("count", 0)

    if style == "pixelwin":
        OUT, BGW, HL, SH = (64, 48, 92), (244, 238, 255), (255, 255, 255), (196, 184, 224)
        TITLE, TITLE2, PINK = (255, 176, 206), (255, 210, 228), (232, 72, 128)
        d.rectangle([0, 0, W - 1, H - 1], fill=BGW, outline=OUT)
        d.line([(1, 1), (W - 2, 1)], fill=HL)
        d.line([(1, 1), (1, H - 2)], fill=HL)
        d.line([(W - 2, 2), (W - 2, H - 2)], fill=SH)
        d.line([(2, H - 2), (W - 2, H - 2)], fill=SH)
        # タイトルバー（左の明るい色から、右へ網点でなめらかに）
        dither_bar(d, 2, 2, W - 3, 11, TITLE2, TITLE)
        d.line([(2, 11), (W - 3, 11)], fill=TITLE)
        px_pattern(d, 5, 5, _ICONS["heart"], HL)       # ハートに白いふちどり（影）
        px_pattern(d, 4, 4, _ICONS["heart"], PINK)
        bw = 8
        bx0 = W - 3 - 3 * (bw + 1)
        px_text(d, 14, 6, "PIXELVIEW.EXE", HL, max_w=bx0 - 15)
        px_text(d, 13, 5, "PIXELVIEW.EXE", OUT, max_w=bx0 - 15)
        for i, icon in enumerate(("min", "max", "close")):
            x0 = bx0 + i * (bw + 1)
            d.rectangle([x0, 3, x0 + bw - 1, 10], fill=(255, 220, 232) if icon == "close" else BGW,
                        outline=OUT)
            px_pattern(d, x0 + 2, 4 if icon != "min" else 4, _ICONS[icon], OUT)
        d.line([(1, 12), (W - 2, 12)], fill=OUT)
        # ツールバー（左の STOP / NEXT はボタンとして上に重なる）とアドレス欄
        ax = 79
        d.line([(76, 14), (76, 24)], fill=SH)          # ボタンとアドレス欄のしきり
        d.line([(77, 14), (77, 24)], fill=HL)
        d.rectangle([ax, 16, W - 4, 22], fill=HL, outline=OUT)
        d.line([(ax + 1, 17), (ax + 1, 21)], fill=SH)  # へこみ
        px_pattern(d, ax + 3, 17, _ICONS["folder"], (240, 176, 60))
        px_text(d, ax + 11, 17, "RANDOM", OUT, max_w=W - 4 - ax - 22)
        if W - 4 - ax > 40:   # 右はしの「移動」ボタン
            d.rectangle([W - 12, 17, W - 5, 21], fill=TITLE2)
            px_pattern(d, W - 11, 17, _ICONS["fwd"], PINK)
        d.line([(2, 25), (W - 3, 25)], fill=SH)
        # 画像まわりと情報欄
        d.rectangle([L - 1, T - 1, L + hw, T + hw], outline=OUT)
        draw_info_strip(d, style, L, T + hw + 2, hw, info.get("palette"))
        # ステータスバー
        y = T + hw + 4 + INFO_H
        d.line([(2, y - 2), (W - 3, y - 2)], fill=SH)  # ステータスバーのしきり
        px_pattern(d, 4, y, _ICONS["sparkle"], PINK)
        px_text(d, 11, y, f"{count:,} ITEMS".replace(",", ","), OUT, max_w=W // 2)
        state = "PAUSED" if info.get("paused") else "PLAYING"
        sx = W - 13 - px_text_w(state)
        resize_grip(d, W - 4, H - 4, SH, HL)
        px_text(d, sx, y, state, OUT)
        px_pattern(d, sx - 6, y, _ICONS["pause" if info.get("paused") else "play"], PINK)

    elif style == "freeware":
        FACE, LIGHT, SHADOW, DARK = (192, 192, 192), (255, 255, 255), (128, 128, 128), (0, 0, 0)
        NAVY = (0, 0, 128)
        d.rectangle([0, 0, W - 1, H - 1], fill=FACE)
        win_bevel(d, 0, 0, W - 1, H - 1, raised=True)
        # タイトルバー（段々のグラデーション）
        for x in range(3, W - 3):
            t = round((x - 3) / (W - 7) * 7) / 7
            d.line([(x, 3), (x, 12)], fill=_mix(NAVY, (16, 132, 208), t))
        px_pattern(d, 5, 5, _ICONS["sparkle"], (255, 255, 0))
        bx0 = W - 4 - 3 * 9 - 2
        px_text(d, 12, 6, "PHOTOVIEW 2000 FREE", LIGHT, max_w=bx0 - 14)
        for i, icon in enumerate(("min", "max", "close")):
            x0 = bx0 + i * 9 + (2 if icon == "close" else 0)
            d.rectangle([x0, 4, x0 + 8, 11], fill=FACE)
            win_bevel(d, x0, 4, x0 + 8, 11, raised=True)
            px_pattern(d, x0 + 2, 5, _ICONS[icon], DARK)
        # メニューバー
        for x, word in ((6, "FILE"), (24, "EDIT"), (42, "VIEW"), (60, "HELP")):
            px_text(d, x, 15, word, DARK)
            d.line([(x, 21), (x + 2, 21)], fill=DARK)
        d.line([(3, 23), (W - 4, 23)], fill=SHADOW)
        d.line([(3, 24), (W - 4, 24)], fill=LIGHT)
        # ツールバー（STOP / NEXT はボタンとして上に重なる）
        d.line([(78, 26), (78, 34)], fill=SHADOW)
        d.line([(79, 26), (79, 34)], fill=LIGHT)
        px_pattern(d, 83, 28, _ICONS["disk"], NAVY)
        px_pattern(d, 93, 28, _ICONS["help"], NAVY)
        ver = "V1.02"
        px_text(d, W - 6 - px_text_w(ver), 29, ver, NAVY)
        # 画像まわり（へこんだ枠）
        win_bevel(d, L - 1, T - 1, L + hw, T + hw, raised=False, single=True)
        draw_info_strip(d, style, L, T + hw + 2, hw, info.get("palette"))
        # ステータスバー
        y0 = T + hw + 3 + INFO_H
        mid = W // 2
        for x0, x1 in ((4, mid - 2), (mid, W - 5)):
            win_bevel(d, x0, y0, x1, y0 + 8, raised=False, single=True)
        px_text(d, 7, y0 + 2, "PAUSED" if info.get("paused") else "READY", DARK, max_w=mid - 10)
        px_text(d, mid + 3, y0 + 2, f"{count} FILES", DARK, max_w=W - mid - 16)
        resize_grip(d, W - 7, y0 + 7, SHADOW, LIGHT)
        # いかにもな広告バナー
        y1 = y0 + 11
        d.rectangle([4, y1, W - 5, y1 + 10], fill=(255, 255, 0), outline=DARK)
        banner = info.get("banner", "BEST VIEWED IN 800X600")[:(W - 12) // 4]
        bx = (W - px_text_w(banner)) // 2
        for i, ch in enumerate(banner):
            px_pattern(d, bx + i * 4, y1 + 3, PX_FONT.get(ch.upper(), PX_FONT["?"]),
                       (224, 0, 0) if i % 2 == 0 else (0, 0, 200))

    else:  # pixelsns
        SKY, CARD, OUT, GRAY, PINK = (186, 226, 240), (255, 252, 246), (70, 60, 90), (150, 140, 168), (240, 96, 140)
        d.rectangle([0, 0, W - 1, H - 1], fill=SKY)
        for y in range(0, H, 4):            # 背景にうっすら水玉
            for x in range((y // 4) % 2 * 4, W, 8):
                d.point((x, y), fill=(206, 238, 248))
        d.rectangle([1, 1, W - 3, H - 3], fill=CARD, outline=OUT)
        d.line([(W - 2, 3), (W - 2, H - 2)], fill=(140, 186, 206))
        d.line([(3, H - 2), (W - 2, H - 2)], fill=(140, 186, 206))
        # アイコン（空色の丸に、前髪の女の子）
        SKIN, HAIR = (255, 214, 184), (74, 56, 82)   # 髪はカラーや夜で塗り替えない色
        d.ellipse([4, 4, 18, 18], fill=SKY, outline=OUT)
        d.pieslice([6, 6, 16, 19], 180, 360, fill=HAIR)         # 髪
        d.ellipse([7, 9, 15, 17], fill=SKIN)                     # 顔
        d.line([(7, 9), (15, 9)], fill=HAIR)                     # 前髪
        d.point((9, 10), fill=OUT)
        d.point((12, 10), fill=OUT)
        d.point((9, 12), fill=OUT)
        d.point((13, 12), fill=OUT)
        d.point((8, 14), fill=PINK)
        d.point((14, 14), fill=PINK)
        d.point((11, 15), fill=OUT)
        name = "MY ARCHIVE"
        px_text(d, 22, 6, name, OUT, max_w=W - 34)
        bx = 22 + px_text_w(name) + 2
        if bx + 5 < W - 12:   # 認証バッジ
            px_pattern(d, bx, 5, ".#.#.|#####|.###.|#####|.#.#.", PINK)
            d.point((bx + 2, 7), fill=CARD)
        px_text(d, 22, 13, f"@REF_FRAME - {info.get('time', '1M')}", GRAY, max_w=W - 34)
        for i in range(3):
            d.point((W - 10 + i * 2, 8), fill=GRAY)
        for x in range(L, W - 6, 2):   # 名前と本文のあいだの点線
            d.point((x, 20), fill=SKY)
        px_text(d, L, 22, info.get("caption", "TODAY'S PICK!"), OUT, max_w=hw)
        d.rectangle([L - 1, T - 1, L + hw, T + hw], outline=OUT)
        draw_info_strip(d, style, L, T + hw + 2, hw, info.get("palette"))
        # リアクション欄（右端の BACK / PLAY / NEXT はボタンとして上に重なる）
        y = T + hw + 6 + INFO_H
        for x in range(L, L + hw, 2):   # リアクション欄の上の点線
            d.point((x, y - 3), fill=SKY)
        slot = (hw - 45) // 3
        rows = [("bubble", GRAY, info.get("replies", 0)), ("repost", GRAY, info.get("reposts", 0)),
                ("heart", PINK, info.get("likes", 0))]
        for i, (icon, col, n) in enumerate(rows):
            x = L + 1 + i * slot
            px_pattern(d, x, y, _ICONS[icon], col)
            px_text(d, x + 9, y + 1, short_count(n), PINK if icon == "heart" else GRAY,
                    max_w=slot - 11)

    im = recolor(im, cmap)
    return im.resize((W * p, H * p), Image.NEAREST)


# ドット系フチのボタンの色 (地, 線, アクセント, マウスを乗せたとき)
PIXEL_THEMES = {
    "pixelwin": ((244, 238, 255), (64, 48, 92), (232, 72, 128), (255, 214, 228)),
    "pixelsns": ((255, 252, 246), (70, 60, 90), (240, 96, 140), (255, 222, 232)),
    "freeware": ((192, 192, 192), (0, 0, 0), (0, 0, 128), (192, 192, 192)),
}


def render_button(style, size, icon, text, width, hover=False, cmap=None):
    bg, out, acc, hov = PIXEL_THEMES[style]
    p = pixel_scale(size)
    iw = len(_ICONS[icon].split("|")[0])
    w, h = width, 11
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im)
    if style == "freeware":   # グレーの立体ボタン。マウスを乗せるとへこむ
        win_bevel(d, 0, 0, w - 1, h - 1, raised=not hover)
        o = 1 if hover else 0
        if text:
            px_pattern(d, 3 + o, 3 + o, _ICONS[icon], acc)
            px_text(d, 3 + iw + 2 + o, 3 + o, text, out)
        else:
            px_pattern(d, (w - iw) // 2 + o, 3 + o, _ICONS[icon], acc)
        return im.resize((w * p, h * p), Image.NEAREST)
    d.rectangle([0, 0, w - 1, h - 1], fill=hov if hover else bg, outline=out)
    d.line([(1, 1), (w - 2, 1)], fill=(255, 255, 255))
    d.line([(1, h - 2), (w - 2, h - 2)], fill=_mix(hov if hover else bg, (0, 0, 0), 0.12))
    if text:
        px_pattern(d, 3, 3, _ICONS[icon], out if hover else acc)
        px_text(d, 3 + iw + 2, 3, text, out)
    else:
        px_pattern(d, (w - iw) // 2, 3, _ICONS[icon], out if hover else acc)
    im = recolor(im, cmap)
    return im.resize((w * p, h * p), Image.NEAREST)


def frame_border(style, size):
    """フチの太さ (左, 上, 右, 下)。ウィンドウはこの分だけ外側に広がる。"""
    p = pixel_scale(size)
    L, T, R, B = PIXEL_LAYOUT[style]
    extra = -(-size // p) * p - size
    return (L * p, T * p, R * p + extra, B * p + extra)


def button_slots(style, size):
    """常設ボタンの位置（ドット単位）: key → (x, y, 幅, 文字あり?)"""
    p = pixel_scale(size)
    L, T, R, B = PIXEL_LAYOUT[style]
    hw = -(-size // p)
    if style == "pixelwin":
        return {"back": (4, 14, 13, False), "play": (18, 14, 27, True), "next": (46, 14, 29, True)}
    if style == "freeware":
        return {"back": (5, 25, 13, False), "play": (19, 25, 27, True), "next": (47, 25, 29, True)}
    y = T + hw + 3 + INFO_H
    return {"back": (L + hw - 43, y, 13, False), "play": (L + hw - 28, y, 13, False),
            "next": (L + hw - 13, y, 13, False)}


def render_frame(style, size, info=None, cmap=None):
    """フチの画像を描く。中央の size×size の部分に画像が乗る。"""
    return render_pixel(style, size, info or {}, cmap)


# ---------- 色の判定 ----------

def classify_color(r, g, b):
    """RGB をざっくりした色名に分類する。"""
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    h *= 360
    if v < 0.18:
        return "黒"
    if s < 0.15:
        if v > 0.85:
            return "白"
        return "グレー" if v > 0.3 else "黒"
    if s < 0.25 and v > 0.88:
        return "白"
    if h < 15 or h >= 345:
        if v < 0.45:
            return "茶"
        return "ピンク" if (s < 0.5 and v > 0.8) else "赤"
    if h < 40:
        return "茶" if v < 0.65 else "オレンジ"
    if h < 70:
        return "茶" if v < 0.45 else "黄"
    if h < 165:
        return "緑"
    if h < 200:
        return "水色"
    if h < 255:
        return "青"
    if h < 290:
        return "紫"
    return "ピンク"


def hex_to_rgb(hx):
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))


def matches_color(palettes, color):
    """palettes: [[r, g, b, ratio], ...]。color の占める割合が基準以上なら True。"""
    if not palettes:
        return False
    total_all = sum(p[3] for p in palettes) or 1
    if color.startswith("#"):
        tr, tg, tb = hex_to_rgb(color)
        hit = sum(p[3] for p in palettes
                  if ((p[0] - tr) ** 2 + (p[1] - tg) ** 2 + (p[2] - tb) ** 2) ** 0.5 <= CUSTOM_COLOR_RANGE)
    else:
        hit = sum(p[3] for p in palettes if classify_color(p[0], p[1], p[2]) == color)
    return hit / total_all * 100 >= COLOR_MIN_SHARE


def format_interval(sec):
    if sec % 3600 == 0:
        return f"{sec // 3600}時間"
    if sec % 60 == 0:
        return f"{sec // 60}分"
    if sec > 60:
        return f"{sec // 60}分{sec % 60}秒"
    return f"{sec}秒"


def parse_interval(text):
    """「45」「45秒」「2分」「1分30秒」「1時間」などを秒に変換。読めなければ None。"""
    t = text.strip().replace(" ", "").replace("　", "")
    t = t.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if not t:
        return None
    if t.isdigit():
        return int(t)
    total, num = 0, ""
    for ch in t:
        if ch.isdigit():
            num += ch
        elif ch in "時分秒" and num:
            total += int(num) * {"時": 3600, "分": 60, "秒": 1}[ch]
            num = ""
        elif ch == "間":
            continue
        else:
            return None
    if num:
        return None
    return total or None


def color_label(color):
    if not color:
        return "なし"
    return f"指定色 {color}" if color.startswith("#") else color


# ---------- 設定とインデックス ----------

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        cfg.update(saved)
        if "tags" not in saved and saved.get("tag"):   # 旧バージョンの設定を引き継ぐ
            cfg["tags"] = [saved["tag"]]
    except (OSError, ValueError):
        pass
    if cfg["frame"] not in PIXEL_LAYOUT:     # ver.1 の額縁を選んでいた場合
        cfg["frame"] = "pixelsns"
    cfg.pop("frame_color", None)
    if cfg["color"] in ("なし", NO_COLOR):   # 旧バージョンのバグで保存された値を直す
        cfg["color"] = ""
    for t in cfg["tags"]:
        if t not in cfg["tag_choices"]:
            cfg["tag_choices"].append(t)
    return cfg


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


def load_index(library):
    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") == INDEX_VERSION and data.get("library") == library:
            return data.get("items", [])
    except (OSError, ValueError):
        pass
    return None


def save_index(library, items):
    save_json(INDEX_PATH, {"version": INDEX_VERSION, "library": library, "items": items}, pretty=False)


def is_library(path):
    return bool(path) and os.path.isdir(os.path.join(path, "images"))


def find_image_file(info_dir, name, ext):
    path = os.path.join(info_dir, f"{name}.{ext}")
    if os.path.exists(path):
        return path
    # 名前が一致しない場合の保険：サムネイル以外の画像ファイルを探す
    try:
        for fn in os.listdir(info_dir):
            low = fn.lower()
            if low == "metadata.json" or low.endswith("_thumbnail.png"):
                continue
            if low.rsplit(".", 1)[-1] in IMAGE_EXTS:
                return os.path.join(info_dir, fn)
    except OSError:
        pass
    return None


def read_palettes(meta):
    pal = []
    for p in meta.get("palettes") or []:
        try:
            c = p.get("color")
            if isinstance(c, list) and len(c) >= 3:
                pal.append([int(c[0]), int(c[1]), int(c[2]), float(p.get("ratio") or 0)])
        except (TypeError, ValueError, AttributeError):
            continue
    return pal


def scan_library(library, progress=None):
    """Eagle ライブラリを走査して、タグ付きの画像を [id, path, palettes, tags] のリストで返す。
    タグごとに読み直さなくて済むよう、タグが1つでも付いた画像はすべて記録しておく。"""
    items = []
    images_dir = os.path.join(library, "images")
    count = 0
    with os.scandir(images_dir) as it:
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
            tags = [t for t in (meta.get("tags") or []) if isinstance(t, str)]
            if not tags:
                continue
            ext = str(meta.get("ext", "")).lower()
            if ext not in IMAGE_EXTS:
                continue
            path = find_image_file(entry.path, meta.get("name", ""), ext)
            if path:
                items.append([meta.get("id", ""), path, read_palettes(meta), tags])
    return items


def read_meta_text(path):
    """Eagle の metadata.json から、情報欄に出す文字（名前・サイズ・日付）を作る。"""
    try:
        with open(os.path.join(os.path.dirname(path), "metadata.json"), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return os.path.basename(path)
    name = f"{meta.get('name', '')}.{meta.get('ext', '')}".strip(".")
    parts = []
    if meta.get("width") and meta.get("height"):
        parts.append(f"{meta['width']}×{meta['height']}")
    ts = meta.get("btime") or meta.get("modificationTime") or meta.get("mtime")
    if ts:
        try:
            from datetime import datetime
            parts.append(datetime.fromtimestamp(float(ts) / 1000).strftime("%Y/%m/%d"))
        except (ValueError, OSError, OverflowError):
            pass
    parts.append(name or os.path.basename(path))   # 名前は最後（長くても、切れるのは名前の末尾だけ）
    return "　".join(parts)


def load_picture(path, size, cover=False, fit_odd=False):
    """cover=True なら正方形に切り抜き、False なら全体が収まるように縮小。
    fit_odd=True のときは、細長い画像だけ切り抜かずに全体を表示する。"""
    with Image.open(path) as im:
        im.draft("RGB", (size * 2, size * 2))  # JPEG を軽く読む
        try:
            im.seek(0)
        except EOFError:
            pass
        im = im.convert("RGBA")
        base = Image.new("RGBA", im.size, BG_RGB + (255,))
        base.alpha_composite(im)
        im = base.convert("RGB")
        if cover and fit_odd:
            w, h = im.size
            if max(w, h) / max(1, min(w, h)) > ASPECT_FIT_RATIO:
                cover = False
        if cover:
            return ImageOps.fit(im, (size, size), Image.LANCZOS)
        im.thumbnail((size, size), Image.LANCZOS)
        return im.copy()


# ---------- 本体 ----------

class PhotoFrame:
    def __init__(self):
        self.cfg = load_config()
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.items = []      # タグ付き画像すべて
        self.pool = []       # 色縛り後の候補
        self.tiles = []      # 表示枠
        self.recent = deque(maxlen=80)
        self.timer = None
        self.flash_id = None
        self.rr = 0
        self.gen = 0
        self.cell = self.cfg["size"]
        self.menu_tile = None
        self.scanning = False
        self.q = queue.Queue()

        self.root = tk.Tk()
        log_errors(self.root, "photo_frame_error.txt")
        self.root.title(f"資料フォトフレーム ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:   # タグ選びなどの小窓に付くアイコン
            self.root.iconbitmap(default=os.path.join(APP_DIR, "photo_frame.ico"))
        except tk.TclError:
            pass
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", self.cfg["topmost"])

        self.var_paused = tk.BooleanVar(value=False)
        self.frame_label = tk.Label(self.root, bd=0, highlightthickness=0, bg=BG)
        self.frame_photo = None
        self.body = tk.Frame(self.root, bg=BG)
        self.msg = tk.Label(self.root, bg=BG, fg="#9a9aa6",
                            font=("Yu Gothic UI", 10), justify="center")
        for w in (self.root, self.frame_label, self.body, self.msg):
            self.bind_events(w)
        # フチに描いてある ×・＿・… ボタンを押せるように
        self.frame_label.bind("<Motion>", self.frame_hover, add="+")
        self.frame_label.bind("<ButtonRelease-1>", self.frame_click, add="+")
        # 情報欄（ファイル名・サイズ・日付）
        self.meta = {}            # id → 情報欄の文字
        self.info_item = None
        self.hover_tile = None
        self.info_label = tk.Label(self.root, anchor="w", bd=0, highlightthickness=0, padx=2)
        self.info_label.bind("<Double-Button-1>", lambda e: self.open_item_in_eagle(self.info_item))
        self.info_label.bind("<Button-3>", self.popup_menu)
        # 戻る用の履歴（画面の状態を順に記録）
        self.want = []
        self.history, self.hpos = [], -1
        self.rand_info = {}
        self.new_rand()
        self.build_buttons()
        self.apply_geometry()

        self.var_topmost = tk.BooleanVar(value=self.cfg["topmost"])
        self.var_interval = tk.IntVar(value=self.cfg["interval_sec"])
        self.var_size = tk.IntVar(value=self.cfg["size"])
        self.var_grid = tk.IntVar(value=self.cfg["grid"])
        self.var_switch = tk.StringVar(value=self.cfg["switch"])
        self.var_color = tk.StringVar(value=self.cfg["color"] or NO_COLOR)
        self.var_frame = tk.StringVar(value=self.cfg["frame"])
        self.var_fit_odd = tk.BooleanVar(value=self.cfg["fit_odd"])
        self.pmenu = PixelMenu(self.root, self.menu_theme, title="PHOTO FRAME")
        self.root.after(2000, self.watch_colorway)
        self.build_tiles()

        self.root.after(150, self.poll)
        self.root.after(200, self.start)

    # --- 表示まわり ---
    def bind_events(self, w):
        w.bind("<ButtonPress-1>", self.drag_start)
        w.bind("<B1-Motion>", self.drag_move)
        w.bind("<ButtonRelease-1>", self.drag_end)
        w.bind("<Double-Button-1>", lambda e: self.open_in_eagle(self.tile_of(e.widget)))
        w.bind("<Button-3>", self.popup_menu)

    def apply_geometry(self):
        s = self.cfg["size"]
        l, t, r, b = frame_border(self.cfg["frame"], s)
        w, h = s + l + r, s + t + b
        self.root.geometry(f"{w}x{h}+{self.cfg['x']}+{self.cfg['y']}")
        self.frame_photo = ImageTk.PhotoImage(render_frame(self.cfg["frame"], s, self.frame_info(), self.cmap()))
        self.frame_label.config(image=self.frame_photo)
        self.frame_label.place(x=0, y=0, width=w, height=h)
        self.body.place(x=l, y=t, width=s, height=s)
        p = pixel_scale(s)
        ix, iy, iw, ih = info_label_rect(self.cfg["frame"], s)
        bg, fg = INFO_COLORS[self.cfg["frame"]]
        cm = self.cmap() or {}
        bg, fg = cm.get(bg, bg), cm.get(fg, fg)
        self.info_label.config(bg="#%02x%02x%02x" % bg, fg="#%02x%02x%02x" % fg,
                               font=ui_font(self.root, max(10, int(ih * p * 0.6))))
        self.info_label.place(x=ix * p, y=iy * p, width=iw * p, height=ih * p)
        self.place_buttons()

    def new_rand(self):
        """SNSのいいね数や広告バナーなど、画像が変わるたびに入れ替える部分。"""
        self.rand_info = {
            "caption": random.choice(SNS_CAPTIONS), "time": random.choice(SNS_TIMES),
            "likes": int(random.paretovariate(1.2) * 8), "reposts": int(random.paretovariate(1.4) * 3),
            "replies": random.randint(0, 24),
            "banner": random.choice(FREEWARE_BANNERS).format(n=random.randint(1, 99999)),
        }

    def frame_info(self):
        info = dict(self.rand_info)
        info.update(count=len(self.pool), paused=self.var_paused.get(),
                    palette=self.info_item[2] if self.info_item and len(self.info_item) > 2 else [])
        return info

    # --- 情報欄 ---
    def set_info(self, item):
        self.info_item = item
        self.info_label.config(text=self.meta.get(item[0], "") if item else "")
        self.refresh_frame()

    def tile_enter(self, t):
        self.hover_tile = t
        if t["item"]:
            self.set_info(t["item"])

    def tile_leave(self, t):
        if self.hover_tile is t:
            self.hover_tile = None

    def open_item_in_eagle(self, item):
        if item:
            self.open_in_eagle({"item": item})

    def refresh_frame(self):
        """フチの文字（枚数・再生状態・いいね数など）を描き直す。"""
        img = render_frame(self.cfg["frame"], self.cfg["size"], self.frame_info(), self.cmap())
        self.frame_photo = ImageTk.PhotoImage(img)
        self.frame_label.config(image=self.frame_photo)

    def build_tiles(self):
        self.gen += 1
        for t in self.tiles:
            t["label"].destroy()
        n = self.cfg["grid"]
        self.cell = (self.cfg["size"] - GAP * (n - 1)) // n
        self.tiles = []
        for i in range(n * n):
            lb = tk.Label(self.body, bg=BG, bd=0, highlightthickness=0)
            lb.place(x=(i % n) * (self.cell + GAP), y=(i // n) * (self.cell + GAP),
                     width=self.cell, height=self.cell)
            self.bind_events(lb)
            tile = {"label": lb, "item": None, "photo": None}
            lb.bind("<Enter>", lambda e, t=tile: self.tile_enter(t), add="+")
            lb.bind("<Leave>", lambda e, t=tile: self.tile_leave(t), add="+")
            self.tiles.append(tile)
        self.rr = 0
        self.want = [None] * len(self.tiles)
        self.history, self.hpos = [], -1

    def clear_tiles(self):
        for t in self.tiles:
            t["label"].config(image="")
            t["item"] = t["photo"] = None

    def tile_of(self, widget):
        for t in self.tiles:
            if t["label"] is widget:
                return t
        return self.tiles[0] if len(self.tiles) == 1 else None

    def message(self, text):
        self.msg.config(text=text, wraplength=self.cfg["size"] - 24)
        self.msg.place(in_=self.body, x=0, y=0, relwidth=1, relheight=1)
        self.msg.lift()

    def hide_message(self):
        self.msg.place_forget()

    def flash(self, text, ms=1500):
        self.message(text)
        if self.flash_id:
            self.root.after_cancel(self.flash_id)

        def done():
            self.flash_id = None
            self.hide_message()

        self.flash_id = self.root.after(ms, done)

    # --- 常設ボタン ---
    def build_buttons(self):
        self.pimgs = {}
        self.buttons = {}
        for key, action in (("back", self.go_back), ("play", self.toggle_play), ("next", self.show_next)):
            lb = tk.Label(self.root, bd=0, highlightthickness=0, cursor="hand2", bg=BG)
            lb.bind("<Button-1>", lambda e, a=action: a())
            lb.bind("<Enter>", lambda e, k=key: self.draw_button(k, True))
            lb.bind("<Leave>", lambda e, k=key: self.draw_button(k, False))
            lb.bind("<Button-3>", self.popup_menu)
            self.buttons[key] = lb

    def draw_button(self, key, hover=False):
        style, size = self.cfg["frame"], self.cfg["size"]
        x, y, width, with_text = button_slots(style, size)[key]
        if key == "play":
            icon, text = ("play", "PLAY") if self.var_paused.get() else ("pause", "STOP")
        elif key == "back":
            icon, text = "back", "BACK"
        else:
            icon, text = "next", "NEXT"
        img = ImageTk.PhotoImage(render_button(style, size, icon, text if with_text else "", width, hover,
                                                  self.cmap()))
        self.pimgs[key] = img
        self.buttons[key].config(image=img)

    def place_buttons(self):
        p = pixel_scale(self.cfg["size"])
        for key, (x, y, width, _) in button_slots(self.cfg["frame"], self.cfg["size"]).items():
            self.draw_button(key)
            self.buttons[key].place(x=x * p, y=y * p)
            self.buttons[key].lift()

    def toggle_play(self):
        self.var_paused.set(not self.var_paused.get())
        self.on_pause_changed()

    def on_pause_changed(self):
        self.schedule()
        self.draw_button("play")
        self.refresh_frame()

    # --- メニュー ---
    def menu_items(self):
        c = self.cfg

        def pick(var, value, fn):
            return lambda: (var.set(value), fn())

        def short(text, n=10):
            return text if len(text) <= n else text[:n - 1] + "…"

        tag_items = [{"type": "check", "label": t, "checked": t in c["tags"],
                      "cmd": lambda t=t: self.toggle_tag(t)} for t in c["tag_choices"]]
        tag_items += [{"type": "sep"}, {"type": "cmd", "label": "タグを追加…", "cmd": self.add_tag}]
        if len(c["tag_choices"]) > 1:
            tag_items.append({"type": "sub", "label": "メニューから外す",
                              "items": [{"type": "cmd", "label": t, "cmd": lambda t=t: self.remove_tag_choice(t)}
                                        for t in c["tag_choices"]]})

        color_items = [{"type": "radio", "label": "なし", "checked": not c["color"],
                        "cmd": pick(self.var_color, NO_COLOR, self.set_color)}, {"type": "sep"}]
        color_items += [{"type": "radio", "label": n, "checked": c["color"] == n,
                         "cmd": pick(self.var_color, n, self.set_color)} for n in COLOR_NAMES]
        color_items += [{"type": "sep"},
                        {"type": "radio", "label": "色を指定…", "checked": c["color"].startswith("#"),
                         "right": c["color"] if c["color"].startswith("#") else "", "cmd": self.pick_custom_color}]

        grid_items = [{"type": "radio", "label": n, "checked": c["grid"] == v,
                       "cmd": pick(self.var_grid, v, self.set_grid)} for n, v in GRIDS]
        grid_items += [{"type": "sep"}, {"type": "head", "label": "切り替え方"},
                       {"type": "radio", "label": "1枚ずつ", "checked": c["switch"] == "one",
                        "cmd": pick(self.var_switch, "one", self.set_switch)},
                       {"type": "radio", "label": "まとめて", "checked": c["switch"] == "all",
                        "cmd": pick(self.var_switch, "all", self.set_switch)},
                       {"type": "sep"},
                       {"type": "check", "label": "細長い画像は全体を表示", "checked": c["fit_odd"],
                        "cmd": pick(self.var_fit_odd, not c["fit_odd"], self.set_fit_odd)}]

        look_items = [{"type": "radio", "label": n, "checked": c["frame"] == k,
                       "cmd": pick(self.var_frame, k, self.set_frame)} for n, k in FRAMES]
        interval_items = [{"type": "radio", "label": n, "checked": c["interval_sec"] == v,
                           "cmd": pick(self.var_interval, v, self.set_interval)} for n, v in INTERVALS]
        interval_items += [{"type": "sep"}, {"type": "cmd", "label": "自由に設定…", "cmd": self.ask_interval}]
        size_items = [{"type": "radio", "label": f"{n}（{v}px）", "checked": c["size"] == v,
                       "cmd": pick(self.var_size, v, self.set_size)} for n, v in SIZES]
        settings = [
            {"type": "sub", "label": "カラー", "items": lambda: colorway_menu(
                self.colorway, self.set_colorway, self.cfg["frame"] in COLOR_BASE),
             "right": next(n for n, k in COLORWAY_NAMES if k == self.colorway)},
            {"type": "sub", "label": "見た目", "items": look_items,
             "right": next((n.split("（")[0] for n, k in FRAMES if k == c["frame"]), "")},
            {"type": "sub", "label": "切り替え間隔", "items": interval_items,
             "right": format_interval(c["interval_sec"])},
            {"type": "sub", "label": "サイズ", "items": size_items,
             "right": next((n for n, v in SIZES if v == c["size"]), f"{c['size']}px")},
            {"type": "check", "label": "最前面に表示", "checked": c["topmost"],
             "cmd": pick(self.var_topmost, not c["topmost"], self.set_topmost)},
        ]
        library = [{"type": "cmd", "label": "画像リストを再読み込み", "cmd": lambda: self.load_items(force=True)},
                   {"type": "cmd", "label": "ライブラリを選び直す", "cmd": self.rechoose_library}]
        paused = self.var_paused.get()
        tile = self.menu_tile
        return [
            {"type": "cmd", "label": "次の画像", "cmd": self.show_next},
            {"type": "cmd", "label": "前の画面に戻る", "cmd": self.go_back, "enabled": self.hpos > 0},
            {"type": "cmd", "label": "再生する" if paused else "一時停止", "cmd": self.toggle_play},
            {"type": "cmd", "label": "この画像を Eagle で開く", "cmd": lambda: self.open_in_eagle(tile),
             "enabled": bool(tile and tile["item"])},
            {"type": "sep"},
            {"type": "head", "label": "流す画像"},
            {"type": "sub", "label": "タグ", "items": tag_items,
             "right": short("＋".join(c["tags"])) if c["tags"] else "なし"},
            {"type": "sub", "label": "色縛り", "items": color_items,
             "right": short(color_label(c["color"]))},
            {"type": "sub", "label": "並べる枚数", "items": grid_items,
             "right": next((n.split("（")[0] for n, v in GRIDS if v == c["grid"]), "")},
            {"type": "sep"},
            {"type": "sub", "label": "設定", "items": settings},
            {"type": "sub", "label": "ライブラリ", "items": library},
            {"type": "sep"},
            {"type": "cmd", "label": "終了", "cmd": self.quit},
            {"type": "head", "label": f"資料フォトフレーム ver.{APP_VERSION}"},
        ]

    def popup_menu(self, e):
        self.menu_tile = self.tile_of(e.widget)
        self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

    # --- ドラッグ移動 ---
    def frame_hotspots(self):
        """フチの上の押せる場所（ドット単位の四角）。"""
        st, size = self.cfg["frame"], self.cfg["size"]
        p = pixel_scale(size)
        l, t, r, b = frame_border(st, size)
        W = (size + l + r) // p
        if st == "pixelwin":
            bx0 = W - 3 - 3 * 9
            return {"min": (bx0, 3, bx0 + 7, 10), "close": (bx0 + 18, 3, bx0 + 25, 10)}
        if st == "freeware":
            bx0 = W - 4 - 3 * 9 - 2
            return {"min": (bx0, 4, bx0 + 8, 11), "close": (bx0 + 20, 4, bx0 + 28, 11)}
        return {"menu": (W - 13, 3, W - 3, 13)}

    def hotspot_at(self, e):
        p = pixel_scale(self.cfg["size"])
        x = (e.x_root - self.root.winfo_rootx()) / p
        y = (e.y_root - self.root.winfo_rooty()) / p
        for name, (x0, y0, x1, y1) in self.frame_hotspots().items():
            if x0 <= x <= x1 + 1 and y0 <= y <= y1 + 1:
                return name
        return None

    def frame_hover(self, e):
        self.frame_label.config(cursor="hand2" if self.hotspot_at(e) else "")

    def frame_click(self, e):
        px, py = getattr(self, "_press", (e.x_root, e.y_root))
        if abs(e.x_root - px) > 4 or abs(e.y_root - py) > 4:
            return   # ドラッグだった
        spot = self.hotspot_at(e)
        if spot == "close":
            self.quit()
        elif spot == "min":
            self.minimize()
        elif spot == "menu":
            self.menu_tile = None
            self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

    def minimize(self):
        """枠なしウィンドウは普通には最小化できないので、一時的に枠ありに戻してしまう。"""
        self.root.overrideredirect(False)
        self.root.iconify()

        def restore(ev):
            if ev.widget is self.root and self.root.state() == "normal":
                self.root.overrideredirect(True)
                self.root.unbind("<Map>")
        self.root.bind("<Map>", restore)

    def drag_start(self, e):
        self._press = (e.x_root, e.y_root)
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def drag_end(self, e):
        self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        save_config(self.cfg)

    # --- 起動とライブラリ ---
    def start(self):
        if not self.cfg["library"]:
            self.choose_library()
        self.load_items()

    def choose_library(self):
        self.message("Eagle のライブラリ（〇〇.library）を選んでね")
        self.root.attributes("-topmost", False)
        path = filedialog.askdirectory(parent=self.root, title="Eagle のライブラリフォルダを選択")
        self.root.attributes("-topmost", self.cfg["topmost"])
        if path:
            path = os.path.normpath(path)
            if is_library(path):
                self.cfg["library"] = path
                save_config(self.cfg)
            else:
                self.message("そのフォルダは Eagle のライブラリじゃないみたい。\n右クリック →「ライブラリを選び直す」")

    def rechoose_library(self):
        self.choose_library()
        self.load_items()

    def load_items(self, force=False):
        lib = self.cfg["library"]
        if not lib:
            self.message("ライブラリが未設定だよ。\n右クリック →「ライブラリを選び直す」")
            return
        if not is_library(lib):
            self.message("ライブラリが見つからないよ。\n外付けHDDはつながってる？\n（1分ごとに再確認するね）")
            self.root.after(60_000, self.load_items)
            return
        if not force:
            cached = load_index(lib)
            if cached:
                self.items = cached
                self.apply_filter()
                return
        if self.scanning:
            return
        self.scanning = True
        self.message("ライブラリを読み込んでいます…\n（初回は数分かかるかも）")

        def work():
            try:
                items = scan_library(lib, progress=lambda n, h: self.q.put(("progress", n, h)))
                save_index(lib, items)
                self.q.put(("scanned", items))
            except OSError as ex:
                self.q.put(("scan_error", str(ex)))

        threading.Thread(target=work, daemon=True).start()

    # --- 色縛り ---
    def apply_filter(self, announce=False):
        color = self.cfg["color"]
        tags = set(self.cfg["tags"])
        pool = [it for it in self.items if tags.intersection(it[3])]
        if color:
            pool = [it for it in pool if matches_color(it[2], color)]
        self.pool = pool
        tag_text = "＋".join(self.cfg["tags"])
        if not tags:
            self.clear_tiles()
            self.cancel_timer()
            self.message("表示するタグが選ばれていないよ。\n右クリック →「表示するタグ」")
            return
        if not self.pool:
            self.clear_tiles()
            self.cancel_timer()
            if color:
                self.message(f"「{tag_text}」×「{color_label(color)}」の画像は見つからなかったよ。\n"
                             "右クリック →「色縛り」で変えてね")
            else:
                self.message(f"「{tag_text}」タグの画像が見つからなかったよ")
            return
        self.hide_message()
        self.refresh_all()
        self.schedule()
        self.refresh_frame()
        if announce:
            text = tag_text if not color else f"{tag_text} × {color_label(color)}"
            self.flash(f"{text}：{len(self.pool):,} 枚")

    def toggle_tag(self, t):
        on = set(self.cfg["tags"]) ^ {t}
        self.cfg["tags"] = [x for x in self.cfg["tag_choices"] if x in on]
        save_config(self.cfg)
        self.apply_filter(announce=True)

    def add_tag(self):
        """画像に付いているタグを件数つきで一覧にして、そこから選ぶ。"""
        counts = Counter(t for it in self.items for t in it[3])
        if not counts:
            self.flash("タグの付いた画像がまだ見つかっていないよ", 2500)
            return
        entries = [(t, f"{t}（{n:,}件）", t in self.cfg["tags"]) for t, n in counts.most_common()]
        picked = pick_items(self.root, self.menu_theme(), "表示するタグを選ぶ",
                            "表示したいタグを選んでね", entries, near=self.root)
        if not picked:
            return
        for t in picked:
            if t not in self.cfg["tag_choices"]:
                self.cfg["tag_choices"].append(t)
            if t not in self.cfg["tags"]:
                self.cfg["tags"].append(t)
        save_config(self.cfg)
        self.apply_filter(announce=True)

    def remove_tag_choice(self, t):
        if len(self.cfg["tag_choices"]) <= 1:
            return
        self.cfg["tag_choices"].remove(t)
        if t in self.cfg["tags"]:
            self.cfg["tags"].remove(t)
        save_config(self.cfg)
        self.apply_filter(announce=True)

    def set_color(self):
        v = self.var_color.get()
        self.cfg["color"] = "" if v == NO_COLOR else v
        save_config(self.cfg)
        self.apply_filter(announce=True)

    def pick_custom_color(self):
        self.root.attributes("-topmost", False)
        init = self.cfg["color"] if self.cfg["color"].startswith("#") else "#e07a5f"
        _, hx = colorchooser.askcolor(color=init, parent=self.root, title="縛る色を選んでね")
        self.root.attributes("-topmost", self.cfg["topmost"])
        if hx:
            self.var_color.set(hx.lower())
            self.set_color()

    # --- 画像の切り替え ---
    def pick_item(self):
        if not self.pool:
            return None
        showing = {t["item"][0] for t in self.tiles if t["item"]}
        item = random.choice(self.pool)
        for _ in range(20):
            if item[0] not in showing and item[0] not in self.recent:
                break
            item = random.choice(self.pool)
        self.recent.append(item[0])
        return item

    def load_tile(self, i, item=None):
        item = item or self.pick_item()
        if not item:
            return
        if i < len(self.want):
            self.want[i] = item
        gen, cell, cover, fit_odd = self.gen, self.cell, self.cfg["grid"] > 1, self.cfg["fit_odd"]
        need_meta = item[0] not in self.meta

        def work():
            try:
                img = load_picture(item[1], cell, cover, fit_odd)
            except Exception:
                self.q.put(("image_error", gen, i, item))
                return
            meta = read_meta_text(item[1]) if need_meta else None
            self.q.put(("image", gen, i, item, img, meta))

        threading.Thread(target=work, daemon=True).start()

    def refresh_all(self):
        for i in range(len(self.tiles)):
            self.load_tile(i)
        self.record()

    # --- 履歴（戻る・進む）---
    def record(self):
        snap = list(self.want)
        if self.history and self.hpos == len(self.history) - 1 and \
                [x and x[0] for x in self.history[-1]] == [x and x[0] for x in snap]:
            return
        del self.history[self.hpos + 1:]
        self.history.append(snap)
        if len(self.history) > 100:
            del self.history[0]
        self.hpos = len(self.history) - 1

    def apply_snapshot(self, snap):
        for i, item in enumerate(snap):
            if i < len(self.tiles) and item and (not self.want[i] or self.want[i][0] != item[0]):
                self.load_tile(i, item)

    def go_back(self):
        if self.hpos <= 0:
            self.flash("これより前はないよ", 1200)
            return
        self.hpos -= 1
        self.apply_snapshot(self.history[self.hpos])
        if not self.var_paused.get():       # 戻ったときは自動送りを止める
            self.var_paused.set(True)
            self.on_pause_changed()

    def tick(self):
        self.new_rand()
        self.refresh_frame()
        if self.hpos < len(self.history) - 1:     # 戻っていた分は、先に履歴をたどる
            self.hpos += 1
            self.apply_snapshot(self.history[self.hpos])
        elif self.cfg["switch"] == "one" and len(self.tiles) > 1:
            self.load_tile(self.rr % len(self.tiles))
            self.rr += 1
            self.record()
        else:
            self.refresh_all()
        self.schedule()

    def show_next(self):
        self.new_rand()
        self.refresh_frame()
        if self.hpos < len(self.history) - 1:
            self.hpos += 1
            self.apply_snapshot(self.history[self.hpos])
        else:
            self.refresh_all()
        self.schedule()

    def cancel_timer(self):
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None

    def schedule(self):
        self.cancel_timer()
        if not self.var_paused.get() and self.pool:
            self.timer = self.root.after(self.cfg["interval_sec"] * 1000, self.tick)

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    self.message("ライブラリを読み込んでいます…\n"
                                 f"{msg[1]:,} 件確認済み")
                elif kind == "scanned":
                    self.scanning = False
                    self.items = msg[1]
                    self.apply_filter()
                elif kind == "scan_error":
                    self.scanning = False
                    self.message(f"読み込みに失敗したよ\n{msg[1]}")
                elif kind == "image":
                    _, gen, i, item, img, meta = msg
                    if meta is not None:
                        self.meta[item[0]] = meta
                    if gen != self.gen or i >= len(self.tiles):
                        continue
                    t = self.tiles[i]
                    t["photo"] = ImageTk.PhotoImage(img)
                    t["label"].config(image=t["photo"])
                    t["item"] = item
                    if self.hover_tile is None or self.hover_tile is t:
                        self.set_info(item)
                    if not self.flash_id:
                        self.hide_message()
                elif kind == "image_error":
                    _, gen, i, item = msg
                    if item in self.pool:
                        self.pool.remove(item)
                    if gen == self.gen:
                        self.root.after(300, lambda i=i: self.load_tile(i))
        except queue.Empty:
            pass
        self.root.after(150, self.poll)

    # --- メニュー操作 ---
    def relayout(self):
        """枚数やサイズを変えたとき。表示中の画像はできるだけ引き継ぐ。"""
        keep = [t["item"] for t in self.tiles]
        self.build_tiles()
        for i in range(len(self.tiles)):
            self.load_tile(i, keep[i] if i < len(keep) else None)
        self.record()
        self.schedule()

    def set_grid(self):
        self.cfg["grid"] = self.var_grid.get()
        save_config(self.cfg)
        self.relayout()

    def set_fit_odd(self):
        self.cfg["fit_odd"] = self.var_fit_odd.get()
        save_config(self.cfg)
        self.relayout()

    def set_switch(self):
        self.cfg["switch"] = self.var_switch.get()
        save_config(self.cfg)

    def set_interval(self):
        self.cfg["interval_sec"] = self.var_interval.get()
        save_config(self.cfg)
        self.schedule()

    def ask_interval(self):
        text = ask_text(self.root, self.menu_theme(), "切り替え間隔",
                        "何秒ごとに切り替える？\n例：45 / 45秒 / 2分 / 1分30秒 / 1時間",
                        initial=format_interval(self.cfg["interval_sec"]), near=self.root)
        if text is None:
            return
        sec = parse_interval(text)
        if not sec or sec < 3:
            self.flash("うまく読めなかったよ（3秒以上で入れてね）", 2500)
            return
        self.var_interval.set(sec)
        self.set_interval()
        self.flash(f"{format_interval(sec)}ごとに切り替えるね")

    def set_size(self):
        self.cfg["size"] = self.var_size.get()
        save_config(self.cfg)
        self.apply_geometry()
        self.relayout()

    # --- カラー ---
    def cmap(self):
        return make_colormap(COLOR_BASE.get(self.cfg["frame"]), self.colorway)

    def menu_theme(self):
        if (self.colorway != "original" or is_night_time()) and self.cfg["frame"] in COLOR_BASE:
            return colorway_theme(self.colorway, COLOR_BASE[self.cfg["frame"]])
        return THEMES[self.cfg["frame"]]

    def set_colorway(self, name):
        save_colorway(name)
        self.apply_colorway(name)

    def apply_colorway(self, name):
        self.colorway = name
        self.apply_geometry()

    def watch_colorway(self):
        """ほかのツールで色が変わったら、こっちも着替える。"""
        look = (load_colorway(), is_night_time())   # 色を変えたとき・昼夜が切り替わったときに着替える
        if look != self.look:
            self.look = look
            self.apply_colorway(look[0])
        self.root.after(2000, self.watch_colorway)

    def set_frame(self):
        self.cfg["frame"] = self.var_frame.get()
        save_config(self.cfg)
        self.apply_geometry()

    def set_topmost(self):
        self.cfg["topmost"] = self.var_topmost.get()
        save_config(self.cfg)
        self.root.attributes("-topmost", self.cfg["topmost"])

    def open_in_eagle(self, tile):
        if not tile or not tile["item"] or not tile["item"][0]:
            return
        url = f"eagle://item/{tile['item'][0]}"
        try:
            os.startfile(url)
        except (AttributeError, OSError):
            webbrowser.open(url)

    def quit(self):
        save_config(self.cfg)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    PhotoFrame().run()
