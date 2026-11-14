# -*- coding: utf-8 -*-
"""
ドット温室 ver.1.2
デスクトップに置いておく、ドット絵の小さな温室。鉢に種をまいて、水をあげて育てる。

操作:
  空の鉢をクリック   … 種をまく
  植えてある鉢をクリック … 水をあげる
  鉢を右クリック     … その鉢のメニュー（植え替える / 種類を選ぶ / 抜く）
  WATER              … ぜんぶの鉢に水をあげる
  SEED               … 空いている鉢に種をまく
  LIGHT              … 照明（自動 / 昼 / 夜）
  ドラッグ           … ウィンドウを移動（フチの部分）

必要なもの: pip install pillow
"""
import math
import os
import random
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from mushiboshi_ui import (COLORWAY_NAMES, dither_gradient, log_errors, is_night_time, draw_weather, load_weather, PixelMenu,
                           colorway_cmap, colorway_menu, colorway_theme, load_colorway, recolor, save_colorway,
                           Scale, mix, px_pattern, px_text, px_text_w, load_json, save_json)

APP_VERSION = "1.2"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "greenhouse_config.json")
FPS = 10

DEFAULT_CONFIG = {"pots": [None] * 5, "saved_at": 0, "speed": 1.0, "light": "auto",
                  "scale": 3, "topmost": True, "x": 240, "y": 240}
SCALES = [("ミニ", 1.5), ("小", 2), ("中", 3), ("大", 4)]
LIGHTS = [("自動（SugarOS の昼と夜）", "auto"), ("昼", "day"), ("夜", "night")]
SPEEDS = [("のんびり", 0.25), ("ふつう", 1.0), ("はやい", 6.0)]

# 成長：水が残っているあいだだけ進む。各段階にかかる秒数（ふつうの速さ）
STAGE_SECONDS = [600, 1800, 3600, 7200]          # 種→芽→若葉→成長→花
DRY_SECONDS = 4 * 3600                           # 水やりから乾ききるまで
WILT_AFTER = 6 * 3600                            # 乾いてからしおれるまで
STAGE_NAMES = ["たね", "め", "わかば", "そだった", "りっぱ"]

# ---------- ドット絵の部品 ----------

_ICONS = {
    "leaf": "...##|..###|.###.|###..|#....",
    "drop": "..#..|.###.|#####|#####|.###.",
    "seed": ".#.#.|..#..|.###.|#####|.###.",
    "sun": "#.#.#|.###.|#####|.###.|#.#.#",
    "moon": ".###.|##...|##...|##...|.###.",
    "auto": "###..|#.#..|###.#|#.#.#|#.#.#",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
}

PAL = dict(face=(240, 248, 238), out=(44, 72, 52), light=(255, 255, 255), shade=(196, 222, 188),
           title=(150, 214, 140), title2=(194, 236, 180), accent=(236, 104, 120), hover=(255, 220, 224),
           second=(100, 160, 96))
COLOR_BASE = {v: k for k, v in PAL.items() if k != "light"}

W, H = 106, 176                    # 縦長
TX, TY, TW, TH = 3, 14, 100, 132
IW, IH = 100, 132                  # 中身（ver.1.2 から等倍で、細かく描く）
TZ = TW // IW
ROW, ROW2 = 149, 162
BUTTONS = {"water": (3, 34), "seed": (38, 30), "light": (69, 34)}
# 2段のプランタースタンド：(鉢の中心x, 土の表面y, 棚板y)
UPPER_SHELF, LOWER_SHELF, FLOOR_Y = 72, 114, 120
STAND_L, STAND_R = 20, 80
POTS = [(36, UPPER_SHELF - 12, UPPER_SHELF), (64, UPPER_SHELF - 12, UPPER_SHELF),
        (20, LOWER_SHELF - 12, LOWER_SHELF), (50, LOWER_SHELF - 12, LOWER_SHELF), (80, LOWER_SHELF - 12, LOWER_SHELF)]
DRAW_ORDER = [0, 1, 2, 3, 4]


# ---------- 植物（観葉植物） ----------

SPECIES = {
    "monstera": "モンステラ", "pothos": "ポトス", "sansevieria": "サンセベリア", "rubber": "ゴムの木",
    "pachira": "パキラ", "fern": "シダ", "cactus": "サボテン",
}
ROMAJI = {"monstera": "MONSTERA", "pothos": "POTHOS", "sansevieria": "SANSEVIERIA", "rubber": "RUBBER",
          "pachira": "PACHIRA", "fern": "FERN", "cactus": "CACTUS"}
# 前のバージョンの植物は、近い観葉植物に植え替える
OLD_SPECIES = {"sunflower": "rubber", "tulip": "sansevieria", "tomato": "pothos"}


def new_plant(species=None, now=None):
    sp = species or random.choice(list(SPECIES))
    return {"species": sp, "stage": 0, "progress": 0.0, "water": 1.0, "dry_for": 0.0,
            "variant": random.randrange(5), "planted": now or time.time()}


def grow(plant, seconds, speed):
    """seconds 秒ぶん時間を進める（閉じていたあいだのぶんもまとめて計算できる）。"""
    if not plant:
        return
    wet = min(seconds, plant["water"] * DRY_SECONDS)
    plant["water"] = max(0.0, plant["water"] - seconds / DRY_SECONDS)
    if plant["water"] <= 0:
        plant["dry_for"] += seconds - wet
    remaining = wet * speed
    while remaining > 0 and plant["stage"] < 4:
        need = STAGE_SECONDS[plant["stage"]] * (1 - plant["progress"])
        if remaining >= need:
            remaining -= need
            plant["stage"] += 1
            plant["progress"] = 0.0
        else:
            plant["progress"] += remaining / STAGE_SECONDS[plant["stage"]]
            remaining = 0


def is_wilted(plant):
    return plant and plant["water"] <= 0 and plant["dry_for"] > WILT_AFTER


INK = (30, 50, 40)   # フチ取りに混ぜる色

# ポトスのハートの葉（5×4）。# = 葉、h = 光、v = 斑（ふいり）
HEART = ["#h.##", "#####", ".#v#.", "..#.."]


def heart(d, x, y, col, hi, var=None):
    for ry, row in enumerate(HEART):
        for rx, ch in enumerate(row):
            if ch == ".":
                continue
            c = hi if ch == "h" else (var or col) if ch == "v" else col
            d.point((x - 2 + rx, y + ry), fill=c)
    d.point((x + 2, y + 1), fill=mix(col, INK, 0.4))   # 右下の影


def leaf(d, cx, cy, rx, ry, col, dark, light, vein=True):
    """だ円の葉。フチ・ハイライト・葉脈つき。"""
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=col, outline=dark)
    d.arc([cx - rx + 1, cy - ry + 1, cx + rx - 1, cy + ry - 1], 190, 290, fill=light)
    if vein and rx >= 3:
        d.line([(cx - rx + 2, cy), (cx + rx - 2, cy)], fill=dark)


def draw_plant(d, plant, cx, soil, shelf, t):
    sp, st = plant["species"], plant["stage"]
    wilt = is_wilted(plant)
    g1 = (78, 160, 84) if not wilt else (150, 150, 84)
    g2 = (46, 112, 64) if not wilt else (118, 116, 66)
    g3 = (150, 214, 128) if not wilt else (172, 170, 112)
    sway = math.sin(t * 1.2 + cx * 0.15) * 1.2 * (0 if wilt else 1)
    top = soil - 1
    if st == 0:   # たね
        d.ellipse([cx - 2, top, cx + 1, top + 2], fill=(120, 84, 56))
        d.point((cx - 1, top), fill=(160, 120, 84))
        return
    if st == 1:   # め：ふた葉
        d.line([(cx, top), (cx, top - 5)], fill=g2)
        d.ellipse([cx - 5, top - 8, cx - 1, top - 5], fill=g1, outline=g2)
        d.ellipse([cx + 1, top - 8, cx + 5, top - 5], fill=g1, outline=g2)
        d.point((cx - 3, top - 7), fill=g3)
        d.point((cx + 3, top - 7), fill=g3)
        return
    droop = 6 if wilt else 0

    if sp == "monstera":
        n = {2: 2, 3: 4, 4: 5}[st]
        for i in range(n):
            ang = -90 + (i - (n - 1) / 2) * 34 + sway * 2
            length = 10 + (i % 3) * 4 + (4 if st == 4 else 0)
            ex = cx + math.cos(math.radians(ang)) * length
            ey = top + math.sin(math.radians(ang)) * length + droop
            d.line([(cx, top), (ex, ey)], fill=g2, width=1)
            r = 6 if st >= 3 else 4
            leaf(d, ex, ey, r, r - 1, g1, g2, g3, vein=False)
            # 葉脈は、茎の向きにそって葉のまんなかを通す
            ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            d.line([(ex - ca * (r - 1), ey - sa * (r - 1)), (ex + ca * (r - 2), ey + sa * (r - 2))], fill=g2)
            if st == 4:   # 葉の切れ込み：葉脈から左右のふちへ
                for k in (-2, 1):
                    bx, by = ex + ca * k, ey + sa * k
                    for side in (-1, 1):
                        nx, ny = -sa * side, ca * side
                        d.line([(bx + nx * (r - 3), by + ny * (r - 3)), (bx + nx * r, by + ny * r)], fill=(214, 232, 206))
    elif sp == "pothos":
        # 上に少し茂って、育つとつるが鉢のふちから垂れる
        spots = ((-4, 4), (2, 6), (0, 10), (4, 2), (-2, 12))[: {2: 2, 3: 4, 4: 5}[st]]
        for ox, oy in spots:
            heart(d, cx + ox, top - oy + droop // 2, g1, g3, (232, 220, 120) if st == 4 and ox > 0 else None)
        if st >= 3:
            length = 14 if st == 3 else 26
            for side in (-1, 1):
                x0 = cx + side * 8
                pts = []
                for s in range(length):
                    x = x0 + side * (2 if s < 4 else 0) + math.sin(t * 1.0 + s * 0.25 + side) * 1.0 * (s / length)
                    pts.append((x, soil + s))
                d.line(pts, fill=g2)
                for s in range(2, length, 5):
                    x, y = pts[s]
                    heart(d, int(x) + side * 2, int(y), g1, g3, (232, 220, 120) if st == 4 and s % 2 else None)
    elif sp == "sansevieria":
        n = {2: 2, 3: 3, 4: 5}[st]
        hs = {2: 12, 3: 22, 4: 30}[st]
        for i in range(n):
            x = cx - (n - 1) * 2 + i * 4
            h = hs - abs(i - (n - 1) / 2) * 6
            tip = top - int(h) + (droop if wilt else 0)
            d.polygon([(x - 1, top), (x + 2, top), (x + 1, tip + 2), (x + 0.5, tip)], fill=g1)   # 先のとがった葉
            d.line([(x - 1, top), (x, tip + 1)], fill=g2)
            for yy in range(tip + 4, top, 4):   # トラのような、ぎざぎざの濃い帯
                d.point((x, yy), fill=g2)
                d.point((x + 1, yy + 1), fill=g2)
            d.line([(x + 1, tip + 3), (x + 1, top - 1)], fill=g3) if st >= 3 else None
            if st == 4 and i in (0, n - 1):   # 外側の葉に黄色いふち
                ex = x - 2 if i == 0 else x + 3
                d.line([(ex, tip + 6), (ex, top)], fill=(214, 206, 110))
    elif sp == "rubber":
        h = {2: 12, 3: 24, 4: 32}[st]
        pts = [(cx + sway * (i / h) + (droop * (i / h) ** 2), top - i) for i in range(h)]
        d.line(pts, fill=(110, 90, 60))
        d.line([(x + 1, y) for x, y in pts], fill=(140, 116, 80))
        for k, i in enumerate(range(5, h, 7)):
            x, y = pts[i]
            side = -1 if k % 2 else 1
            lx, ly = x + side * 6, y - 1 + droop // 2
            dark = (40, 96, 64) if not wilt else g2
            leaf(d, lx, ly, 5, 3, dark, mix(dark, INK, 0.4), (120, 184, 140) if not wilt else g3)
            d.point((lx - side * 2, ly - 2), fill=(200, 230, 210))   # つやの光
        x, y = pts[-1]
        if st == 4:   # 赤い新芽
            d.polygon([(x, y - 1), (x + 2, y - 1), (x + 1, y - 7)], fill=(200, 60, 70))
        else:
            d.line([(x, y - 1), (x, y - 3)], fill=g3)
    elif sp == "pachira":
        h = {2: 10, 3: 20, 4: 26}[st]
        trunk, trunk_d = (150, 120, 84), (112, 86, 58)
        d.rectangle([cx - 1, top - h, cx + 1, top], fill=trunk)
        d.line([(cx + 1, top - h), (cx + 1, top)], fill=trunk_d)
        if st >= 3:   # 編み込みの幹
            for yy in range(top - h + 1, top, 3):
                d.line([(cx - 1, yy), (cx + 1, yy + 2)], fill=trunk_d)
        heads = [(cx, top - h)] if st == 2 else [(cx - 6, top - h + 2), (cx + 6, top - h - 2), (cx, top - h - 6)][: 2 if st == 3 else 3]
        for hx, hy in heads:
            hy += droop
            d.line([(cx, top - h + 4), (hx, hy)], fill=trunk)
            for a in range(5):   # 手のひら形の葉（5枚）
                ang = math.radians(-90 + (a - 2) * 38 + sway * 3)
                ex, ey = hx + math.cos(ang) * 6, hy + math.sin(ang) * 6
                mx_, my_ = (hx + ex) / 2, (hy + ey) / 2
                d.line([(hx, hy), (ex, ey)], fill=g2)
                d.point((mx_ + 1, my_), fill=g1)
                d.point((mx_ - 1, my_), fill=g1)
                d.point((ex, ey), fill=g3)
    elif sp == "cactus":
        h = {2: 8, 3: 18, 4: 22}[st]
        body, rib, rib_d = g1, g3, g2
        d.rounded_rectangle([cx - 3, top - h + 1, cx + 3, top], radius=3, fill=body, outline=rib_d)
        d.line([(cx - 1, top - h + 3), (cx - 1, top - 1)], fill=rib)
        d.line([(cx + 1, top - h + 3), (cx + 1, top - 1)], fill=rib_d)
        if st >= 3:   # 腕
            for side, y0, y1 in ((-1, top - 13, top - 6), (1, top - 15, top - 8)):
                ax = cx + side * 6
                d.rounded_rectangle([min(ax, ax + side * 3) - 1, y0, max(ax, ax + side * 3) - 1, y1], radius=2,
                                    fill=body, outline=rib_d)
                d.line([(cx + side * 3, y1 - 1), (ax, y1 - 1)], fill=body)
        for yy in range(top - h + 3, top, 4):   # トゲ
            d.point((cx - 4, yy), fill=(244, 244, 226))
            d.point((cx + 4, yy + 2), fill=(244, 244, 226))
        if st == 4:   # ピンクの花
            fy = top - h - 1
            for ox, oy in ((0, 0), (-2, -1), (2, -1), (-1, -2), (1, -2), (0, -3)):
                d.point((cx + ox, fy + oy), fill=(250, 110, 170))
            d.point((cx, fy - 1), fill=(255, 220, 120))
    else:   # fern
        n = {2: 3, 3: 5, 4: 7}[st]
        for i in range(n):
            ang = -90 + (i - (n - 1) / 2) * 19 + sway * 2.5
            length = 10 + (4 if i % 2 else 7) + (4 if st >= 3 else 0)
            pts = []
            for s in range(length):
                a = math.radians(ang + s * (2.2 if ang > -90 else -2.2) + (s * 4.5 if wilt else 0))
                pts.append((cx + math.cos(a) * s, top + math.sin(a) * s))
            d.line(pts, fill=g2)
            for s in range(2, len(pts), 2):   # 小さな葉が左右に
                x, y = pts[s]
                size = 2 if s < len(pts) - 4 else 1
                d.line([(x - size, y - 1), (x, y)], fill=g1)
                d.line([(x + size, y - 1), (x, y)], fill=g1)
                if s % 4 == 0:
                    d.point((x - size, y - 1), fill=g3)


# ---------- 背景 ----------

WINDOW_BOTTOM = 72
def build_background(night):
    im = Image.new("RGB", (IW, IH))
    d = ImageDraw.Draw(im)
    top, bottom = ((16, 24, 64), (40, 52, 110)) if night else ((96, 160, 236), (196, 226, 250))
    dither_gradient(d, 0, 0, IW - 1, WINDOW_BOTTOM - 1, top, bottom, steps=6)
    if night:
        rnd = random.Random(7)
        for _ in range(40):
            d.point((rnd.randrange(IW), rnd.randrange(44)), fill=rnd.choice([(255, 255, 220), (200, 210, 255)]))
        d.ellipse([68, 6, 78, 16], fill=(250, 246, 210))
        d.ellipse([72, 4, 80, 13], fill=mix(top, bottom, 0.1))
    # 丘（2000年代の壁紙みたいな。植物が目立つよう淡く）
    far = (150, 200, 168) if not night else (30, 50, 70)
    near = (174, 220, 150) if not night else (40, 64, 70)
    for x in range(IW):
        y1 = int(48 + 6 * math.sin(x / 16 + 1) + 3 * math.sin(x / 8))
        y2 = int(58 + 6 * math.sin(x / 22 + 3))
        d.line([(x, y1), (x, WINDOW_BOTTOM - 1)], fill=far)
        d.point((x, y1), fill=mix(far, (255, 255, 255), 0.25))
        d.line([(x, y2), (x, WINDOW_BOTTOM - 1)], fill=near)
        d.point((x, y2), fill=mix(near, (255, 255, 255), 0.3))
    if not night:   # 遠くの木
        for tx in (14, 86):
            ty = int(58 + 6 * math.sin(tx / 22 + 3))
            d.line([(tx, ty), (tx, ty - 4)], fill=(120, 100, 80))
            d.ellipse([tx - 3, ty - 9, tx + 3, ty - 3], fill=(120, 180, 120))
    return im


def draw_room(d, night):
    """温室のガラス枠・壁・プランタースタンド・床。"""
    frame = (236, 244, 238) if not night else (120, 130, 140)
    frame_d = mix(frame, INK, 0.3)
    for x in (0, 32, 66, IW - 2):
        d.rectangle([x, 0, x + 1, WINDOW_BOTTOM], fill=frame)
        d.line([(x + 1, 0), (x + 1, WINDOW_BOTTOM)], fill=frame_d)
    for y in (0, 24, 48):
        d.rectangle([0, y, IW - 1, y + 1], fill=frame)
        d.line([(0, y + 1), (IW - 1, y + 1)], fill=frame_d)
    glare = (230, 240, 250) if not night else (90, 100, 140)
    for x0 in (6, 40, 74):   # ガラスの映り込み（ななめ2本）
        for i in range(8):
            d.point((x0 + i, 12 - i), fill=glare)
            if i < 5:
                d.point((x0 + i + 4, 12 - i), fill=glare)
    wall = (236, 240, 230) if not night else (104, 110, 120)
    d.rectangle([0, WINDOW_BOTTOM, IW - 1, IH - 1], fill=wall)
    d.line([(0, WINDOW_BOTTOM + 2), (IW - 1, WINDOW_BOTTOM + 2)], fill=mix(wall, (0, 0, 0), 0.15))
    d.line([(0, WINDOW_BOTTOM + 3), (IW - 1, WINDOW_BOTTOM + 3)], fill=mix(wall, (255, 255, 255), 0.4))
    for x in range(6, IW, 12):   # 壁の板張り
        d.line([(x, WINDOW_BOTTOM + 5), (x, FLOOR_Y - 1)], fill=mix(wall, (0, 0, 0), 0.06))
    tile_a, tile_b = ((214, 210, 196), (196, 192, 178)) if not night else ((80, 80, 90), (70, 70, 80))
    grout = mix(tile_b, INK, 0.2)
    for y in range(FLOOR_Y, IH):
        for x in range(IW):
            c = tile_a if ((x // 8) + (y - FLOOR_Y) // 6) % 2 else tile_b
            if x % 8 == 0 or (y - FLOOR_Y) % 6 == 0:
                c = grout
            d.point((x, y), fill=c)
    wood, wood_d = ((176, 124, 80), (140, 96, 60)) if not night else ((96, 70, 56), (74, 54, 44))
    for x in (STAND_L, STAND_R):   # スタンドの脚
        d.rectangle([x, UPPER_SHELF, x + 1, IH - 1], fill=wood_d)
    for y0, x0, x1 in ((UPPER_SHELF, STAND_L - 4, STAND_R + 5), (LOWER_SHELF, 2, IW - 3)):
        d.rectangle([x0, y0, x1, y0 + 3], fill=wood)
        d.line([(x0, y0), (x1, y0)], fill=mix(wood, (255, 255, 255), 0.3))
        d.line([(x0, y0 + 4), (x1, y0 + 4)], fill=wood_d)
        for gx in range(x0 + 3, x1, 9):   # 木目
            d.line([(gx, y0 + 2), (gx + 3, y0 + 2)], fill=mix(wood, wood_d, 0.6))
    # じょうろ
    can, can_d = ((150, 196, 220), (110, 150, 180)) if not night else ((80, 100, 120), (60, 76, 96))
    d.rounded_rectangle([84, IH - 9, 94, IH - 2], radius=2, fill=can, outline=can_d)
    d.line([(84, IH - 7), (78, IH - 11)], fill=can_d)
    d.arc([86, IH - 13, 92, IH - 7], 180, 360, fill=can_d)


POT_COLORS = [((206, 110, 70), (168, 84, 52)), ((244, 244, 238), (204, 204, 196)), ((150, 214, 196), (110, 180, 162)),
              ((246, 176, 196), (214, 136, 160)), ((70, 84, 130), (50, 60, 100))]


def draw_pot(d, i, plant, night):
    cx, soil, shelf = POTS[i]
    terra, terra_d = POT_COLORS[i % len(POT_COLORS)]
    if night:
        terra, terra_d = mix(terra, (20, 24, 50), 0.45), mix(terra_d, (20, 24, 50), 0.45)
    hi = mix(terra, (255, 255, 255), 0.35)
    d.polygon([(cx - 6, soil + 4), (cx + 6, soil + 4), (cx + 4, shelf - 1), (cx - 4, shelf - 1)], fill=terra)
    d.line([(cx + 5, soil + 4), (cx + 3, shelf - 1)], fill=terra_d)          # 右の影
    d.line([(cx - 4, soil + 5), (cx - 3, shelf - 2)], fill=hi)               # 左の光
    d.rectangle([cx - 8, soil, cx + 8, soil + 3], fill=terra)               # ふち
    d.line([(cx - 8, soil), (cx + 8, soil)], fill=hi)
    d.line([(cx - 8, soil + 3), (cx + 8, soil + 3)], fill=terra_d)
    d.line([(cx - 5, shelf - 1), (cx + 5, shelf - 1)], fill=terra_d)
    if plant:
        wet = plant["water"] > 0
        soil_c = (84, 58, 40) if wet else (150, 116, 84)
        d.line([(cx - 6, soil), (cx + 6, soil)], fill=soil_c)
        d.point((cx - 3, soil), fill=mix(soil_c, (255, 255, 255), 0.2))
        n = math.ceil(plant["water"] * 5)   # 水のゲージ
        for k in range(5):
            d.rectangle([cx - 5 + k * 2, shelf + 2, cx - 5 + k * 2, shelf + 3],
                        fill=(80, 170, 240) if k < n else (120, 90, 64))
    else:
        d.line([(cx - 6, soil), (cx + 6, soil)], fill=(110, 80, 56))


BUTTERFLY = [".#.#.", "##.##", ".#.#.", "#...#"]
BUTTERFLY2 = [".....", "#####", ".###.", "....."]


def render_house(t, pots, night, drops, butterflies, clouds, hover, weather=None):
    im = build_background(night)
    d = ImageDraw.Draw(im)
    if not night:
        for c in clouds:
            x = c["x"]
            for dx, dy, r in ((0, 0, 4), (4, -2, 5), (9, 0, 4), (5, 1, 4)):
                d.ellipse([x + dx - r, c["y"] + dy - r + 1, x + dx + r, c["y"] + dy + r - 1], fill=(250, 252, 255))
            d.line([(x - 2, c["y"] + 3), (x + 11, c["y"] + 3)], fill=(226, 236, 248))   # 雲のかげ
    draw_weather(im, (0, 0, IW - 1, WINDOW_BOTTOM - 1), weather, t, night)   # 窓の外の雨や雪
    draw_room(d, night)
    for i in DRAW_ORDER:   # 上の段から描いて、下の段を手前に
        cx, soil, shelf = POTS[i]
        if pots[i]:
            draw_plant(d, pots[i], cx, soil, shelf, t)
        draw_pot(d, i, pots[i], night)
    if hover is not None:
        cx, soil, shelf = POTS[hover]
        d.rectangle([cx - 12, soil - 36, cx + 12, shelf + 3], outline=(255, 255, 255) if not night else (180, 190, 220))
    for dr in drops:
        d.line([(int(dr["x"]), int(dr["y"])), (int(dr["x"]), int(dr["y"]) + 1)], fill=(110, 190, 250))
    for b in butterflies:
        pat = BUTTERFLY if int(t * 8 + b["p"]) % 2 else BUTTERFLY2
        for y, row in enumerate(pat):
            for x, ch in enumerate(row):
                if ch == "#":
                    d.point((int(b["x"]) + x - 2, int(b["y"]) + y - 2), fill=b["c"])
        d.point((int(b["x"]), int(b["y"])), fill=(60, 50, 60))   # 胴
    if night:   # ランプのあかり
        over = Image.new("RGBA", (IW, IH), (0, 0, 0, 0))
        ImageDraw.Draw(over).ellipse([4, 60, 96, 148], fill=(255, 220, 140, 22))
        im = Image.alpha_composite(im.convert("RGBA"), over).convert("RGB")
    return im


def render_window():
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
    px_pattern(d, 4, 4, _ICONS["leaf"], k["out"])
    px_text(d, 12, 5, "GREEN.EXE", k["out"])
    bx0 = W - 3 - 3 * 9
    for i, icon in enumerate(("min", "max", "close")):
        x0 = bx0 + i * 9
        d.rectangle([x0, 3, x0 + 7, 10], fill=k["hover"] if icon == "close" else k["face"], outline=k["out"])
        px_pattern(d, x0 + 1, 4, _ICONS[icon], k["out"])
    d.line([(1, 12), (W - 2, 12)], fill=k["out"])
    d.rectangle([TX - 1, TY - 1, TX + TW, TY + TH], outline=k["out"])
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
    px_pattern(d, 3, iy, _ICONS[icon], k["out"] if hover else k["accent"])
    px_text(d, 3 + iw + 2, 3, text, k["out"])
    return im


# ---------- 設定 ----------

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_PATH, {}))
    pots = list(cfg.get("pots") or [])[:5]
    cfg["pots"] = pots + [None] * (5 - len(pots))
    return cfg


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


# ---------- 本体 ----------

class Greenhouse:
    def __init__(self):
        self.cfg = load_config()
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.p = Scale(self.cfg["scale"])
        now = time.time()
        for pl in self.cfg["pots"]:   # 前のバージョンの植物を、観葉植物に植え替える
            if pl and pl.get("species") not in SPECIES:
                pl["species"] = OLD_SPECIES.get(pl.get("species"), "monstera")
        if not any(self.cfg["pots"]) and not self.cfg["saved_at"]:   # はじめての温室
            self.cfg["pots"] = [new_plant("pothos", now), new_plant("sansevieria", now), None,
                                new_plant("monstera", now), new_plant("pachira", now)]
        elif self.cfg["saved_at"]:   # 閉じていたあいだのぶん、育てる
            away = max(0.0, now - self.cfg["saved_at"])
            for pl in self.cfg["pots"]:
                grow(pl, away, self.cfg["speed"])
        self.last = now
        self.save()
        self.drops, self.butterflies = [], []
        self.clouds = [{"x": random.uniform(0, IW), "y": random.uniform(6, 24), "v": random.uniform(0.04, 0.1)}
                       for _ in range(3)]
        self.hover = None
        self.t0 = now
        self.pimgs = {}

        self.root = tk.Tk()
        log_errors(self.root, "greenhouse_error.txt")
        self.root.title(f"ドット温室 ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "greenhouse.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])
        self.frame_label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.house = tk.Label(self.root, bd=0, highlightthickness=0)
        self.status = tk.Label(self.root, bd=0, highlightthickness=0)
        for w in (self.root, self.frame_label, self.status):
            w.bind("<ButtonPress-1>", self.drag_start)
            w.bind("<B1-Motion>", self.drag_move)
            w.bind("<ButtonRelease-1>", self.drag_end)
            w.bind("<Button-3>", self.popup_menu)
        self.house.bind("<Button-1>", self.house_click)
        self.house.bind("<Button-3>", self.house_right)
        self.house.bind("<Motion>", self.house_motion)
        self.house.bind("<Leave>", lambda e: self.set_hover(None))
        self.frame_label.bind("<Motion>", self.frame_hover, add="+")
        self.frame_label.bind("<ButtonRelease-1>", self.frame_click, add="+")
        self.buttons = {}
        for key, action in (("water", self.water_all), ("seed", self.plant_empty), ("light", self.cycle_light)):
            lb = tk.Label(self.root, bd=0, highlightthickness=0, cursor="hand2")
            lb.bind("<Button-1>", lambda e, a=action: a())
            lb.bind("<Enter>", lambda e, k=key: self.draw_button(k, True))
            lb.bind("<Leave>", lambda e, k=key: self.draw_button(k, False))
            lb.bind("<Button-3>", self.popup_menu)
            self.buttons[key] = lb
        self.pmenu = PixelMenu(self.root, self.menu_theme, title="GREENHOUSE - MENU")
        self.layout()
        self.root.after(1000 // FPS, self.tick)
        self.root.after(2000, self.watch_colorway)

    @property
    def pots(self):
        return self.cfg["pots"]

    def save(self):
        self.cfg["saved_at"] = time.time()
        save_config(self.cfg)

    # --- 色 ---
    def cmap(self):
        return colorway_cmap(COLOR_BASE, self.colorway)

    def col(self, role):
        c = PAL[role]
        return (self.cmap() or {}).get(c, c)

    def menu_theme(self):
        if self.colorway != "original" or is_night_time():
            return colorway_theme(self.colorway, COLOR_BASE)
        return dict(face=PAL["face"], out=PAL["out"], light=PAL["light"], title=PAL["title"], title2=PAL["title2"],
                    title_text=PAL["out"], accent=PAL["accent"], sub=mix(PAL["out"], PAL["face"], 0.45),
                    text=PAL["out"], field=PAL["light"], select=PAL["accent"], select_text=PAL["light"])

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
        img = recolor(render_window(), self.cmap()).resize((W * p, H * p), Image.NEAREST)
        self.frame_photo = ImageTk.PhotoImage(img)
        self.frame_label.config(image=self.frame_photo)
        self.frame_label.place(x=0, y=0, width=W * p, height=H * p)
        self.house.place(x=TX * p, y=TY * p, width=TW * p, height=TH * p)
        for key, (x, w) in BUTTONS.items():
            self.draw_button(key)
            self.buttons[key].place(x=x * p, y=ROW * p)
        self.status.place(x=3 * p, y=ROW2 * p, width=(W - 6) * p, height=11 * p)
        self.draw_status()

    def draw_button(self, key, hover=False):
        x, w = BUTTONS[key]
        icon, text = {"water": ("drop", "WATER"), "seed": ("seed", "SEED"),
                      "light": ({"auto": "auto", "day": "sun", "night": "moon"}[self.cfg["light"]], "LIGHT")}[key]
        img = recolor(render_button(icon, text, w, hover), self.cmap())
        img = ImageTk.PhotoImage(img.resize((w * self.p, 11 * self.p), Image.NEAREST))
        self.pimgs[key] = img
        self.buttons[key].config(image=img)

    def draw_status(self):
        sw = W - 6
        im = Image.new("RGB", (sw, 11), self.col("face"))
        d = ImageDraw.Draw(im)
        if self.hover is not None and self.pots[self.hover]:
            pl = self.pots[self.hover]
            txt = ROMAJI[pl["species"]] + f" {pl['stage']}/4"
            if is_wilted(pl):
                txt = "THIRSTY!"
        else:
            grown = sum(1 for pl in self.pots if pl and pl["stage"] == 4)
            txt = f"GROWN {grown}/5"
            n = sum(1 for pl in self.pots if pl)
            right = f"PLANTS {n}"
            px_text(d, sw - px_text_w(right) - 1, 3, right, self.col("out"))
        px_text(d, 1, 3, txt, self.col("out"))
        img = ImageTk.PhotoImage(im.resize((sw * self.p, 11 * self.p), Image.NEAREST))
        self.pimgs["status"] = img
        self.status.config(image=img)

    def is_night(self):
        if self.cfg["light"] == "auto":
            return is_night_time()   # ランチャーで決めた SugarOS の昼と夜に合わせる
        return self.cfg["light"] == "night"

    # --- 動き ---
    def tick(self):
        now = time.time()
        dt, self.last = now - self.last, now
        before = [pl and pl["stage"] for pl in self.pots]
        for pl in self.pots:
            grow(pl, dt, self.cfg["speed"])
        if [pl and pl["stage"] for pl in self.pots] != before:
            self.save()
            self.draw_status()
        t = now - self.t0
        for c in self.clouds:
            c["x"] += c["v"]
            if c["x"] > IW + 12:
                c["x"], c["y"] = -16, random.uniform(6, 36)
        for dr in list(self.drops):
            dr["y"] += 1.2
            if dr["y"] >= dr["stop"]:
                self.drops.remove(dr)
        blooms = [i for i, pl in enumerate(self.pots) if pl and pl["stage"] == 4 and not is_wilted(pl)]
        if blooms and not self.is_night() and not self.butterflies and random.random() < 0.004:
            i = random.choice(blooms)
            self.butterflies.append({"x": -4.0, "y": random.uniform(16, 40), "tx": POTS[i][0], "ty": POTS[i][1] - 28,
                                     "c": random.choice([(250, 240, 120), (250, 170, 210), (170, 220, 250)]),
                                     "p": random.random() * 6, "life": FPS * 25})
        for b in list(self.butterflies):
            b["life"] -= 1
            tx = b["tx"] if b["life"] > FPS * 6 else IW + 12
            ty = b["ty"] if b["life"] > FPS * 6 else 8
            b["x"] += max(-1.2, min(1.2, (tx - b["x"]) * 0.05)) + math.sin(t * 3 + b["p"]) * 0.4
            b["y"] += max(-1.0, min(1.0, (ty - b["y"]) * 0.05)) + math.sin(t * 5 + b["p"]) * 0.6
            if b["life"] <= 0 or b["x"] > IW + 8:
                self.butterflies.remove(b)
        img = render_house(t, self.pots, self.is_night(), self.drops, self.butterflies, self.clouds, self.hover,
                           load_weather())
        self.house_photo = ImageTk.PhotoImage(img.resize((TW * self.p, TH * self.p), Image.NEAREST))
        self.house.config(image=self.house_photo)
        if int(t * FPS) % (FPS * 30) == 0:
            self.save()
        self.root.after(1000 // FPS, self.tick)

    def pot_at(self, e):
        """マウスの下の鉢。上下の段が重なるところは、すぐ下にある棚の鉢を選ぶ。"""
        x, y = e.x / (self.p * TZ), e.y / (self.p * TZ)
        best = None
        for i, (cx, soil, shelf) in enumerate(POTS):
            if abs(x - cx) <= 12 and soil - 36 <= y <= shelf + 3:
                if best is None or shelf < POTS[best][2]:
                    best = i
        return best

    def set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.house.config(cursor="hand2" if i is not None else "")
            self.draw_status()

    def house_motion(self, e):
        self.set_hover(self.pot_at(e))

    def house_click(self, e):
        i = self.pot_at(e)
        if i is None:
            return
        if self.pots[i]:
            self.water(i)
        else:
            self.plant(i)

    def water(self, i):
        pl = self.pots[i]
        if not pl:
            return
        pl["water"] = 1.0
        pl["dry_for"] = 0.0
        cx, soil, _ = POTS[i]
        for _ in range(8):
            self.drops.append({"x": cx + random.uniform(-6, 6), "y": random.uniform(soil - 32, soil - 16), "stop": soil})
        self.save()
        self.draw_status()

    def water_all(self):
        for i, pl in enumerate(self.pots):
            if pl:
                self.water(i)

    def plant(self, i, species=None):
        self.pots[i] = new_plant(species)
        self.save()
        self.draw_status()

    def plant_empty(self):
        for i, pl in enumerate(self.pots):
            if not pl:
                self.plant(i)
                return

    def pull(self, i):
        self.pots[i] = None
        self.save()
        self.draw_status()

    def cycle_light(self):
        order = ["auto", "day", "night"]
        self.set_light(order[(order.index(self.cfg["light"]) + 1) % 3])

    def set_light(self, v):
        self.cfg["light"] = v
        save_config(self.cfg)
        self.draw_button("light")

    # --- メニュー ---
    def pot_items(self, i):
        pl = self.pots[i]
        kinds = [{"type": "cmd", "label": name, "cmd": lambda k=k: self.plant(i, k)} for k, name in SPECIES.items()]
        if not pl:
            return [{"type": "head", "label": f"{i + 1}番の鉢（空き）"},
                    {"type": "cmd", "label": "種をまく（ランダム）", "cmd": lambda: self.plant(i)},
                    {"type": "sub", "label": "種類を選んでまく", "items": kinds}]
        status = "しおれてる…" if is_wilted(pl) else STAGE_NAMES[pl["stage"]]
        return [{"type": "head", "label": f"{i + 1}番の鉢：{SPECIES[pl['species']]}（{status}）"},
                {"type": "cmd", "label": "水をあげる", "cmd": lambda: self.water(i),
                 "right": f"水 {round(pl['water'] * 100)}%"},
                {"type": "sep"},
                {"type": "cmd", "label": "植え替える（ランダム）", "cmd": lambda: self.plant(i)},
                {"type": "sub", "label": "種類を選んで植え替える", "items": kinds},
                {"type": "cmd", "label": "抜く", "cmd": lambda: self.pull(i)}]

    def menu_items(self):
        c = self.cfg
        return [
            {"type": "cmd", "label": "ぜんぶに水をあげる", "cmd": self.water_all},
            {"type": "cmd", "label": "空いている鉢に種をまく", "cmd": self.plant_empty,
             "enabled": not all(self.pots)},
            {"type": "sep"},
            {"type": "sub", "label": "育つ速さ", "right": next(n for n, v in SPEEDS if v == c["speed"]),
             "items": [{"type": "radio", "label": n, "checked": c["speed"] == v, "cmd": lambda v=v: self.set_speed(v)}
                       for n, v in SPEEDS]},
            {"type": "sub", "label": "照明", "right": next(n.split("（")[0] for n, k in LIGHTS if k == c["light"]),
             "items": [{"type": "radio", "label": n, "checked": c["light"] == k, "cmd": lambda k=k: self.set_light(k)}
                       for n, k in LIGHTS]},
            {"type": "sub", "label": "設定", "items": [
                {"type": "sub", "label": "カラー", "items": lambda: colorway_menu(self.colorway, self.set_colorway),
                 "right": next(n for n, k in COLORWAY_NAMES if k == self.colorway)},
                {"type": "sub", "label": "サイズ", "right": next(n for n, v in SCALES if v == c["scale"]),
                 "items": [{"type": "radio", "label": n, "checked": c["scale"] == v,
                            "cmd": lambda v=v: self.set_scale(v)} for n, v in SCALES]},
                {"type": "check", "label": "最前面に表示", "checked": c["topmost"], "cmd": self.toggle_topmost},
            ]},
            {"type": "sep"},
            {"type": "cmd", "label": "終了", "cmd": self.quit},
            {"type": "head", "label": f"ドット温室 ver.{APP_VERSION}"},
        ]

    def house_right(self, e):
        i = self.pot_at(e)
        if i is None:
            self.popup_menu(e)
        else:
            self.pmenu.popup(lambda: self.pot_items(i), e.x_root, e.y_root)

    def popup_menu(self, e):
        self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

    def set_speed(self, v):
        self.cfg["speed"] = v
        self.save()

    def set_scale(self, v):
        self.cfg["scale"] = v
        self.p = Scale(v)
        save_config(self.cfg)
        self.layout()

    def toggle_topmost(self):
        self.cfg["topmost"] = not self.cfg["topmost"]
        save_config(self.cfg)
        self.root.attributes("-topmost", self.cfg["topmost"])

    # --- ウィンドウ ---
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
        self.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        Greenhouse().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "greenhouse_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
