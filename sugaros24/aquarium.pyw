# -*- coding: utf-8 -*-
"""
ドット水槽 ver.1.1
デスクトップに置いておく、ドット絵の小さな水槽。魚が泳ぐだけ。

操作:
  水槽をクリック … エサを落とす
  FEED           … エサをまとめて落とす
  +FISH          … 魚を1匹ふやす
  LIGHT          … 照明（自動 / 昼 / 夜）
  ドラッグ       … ウィンドウを移動（フチの部分）
  右クリック     … メニュー（魚を減らす / 入れ替える / カラー / サイズ など）

必要なもの: pip install pillow
"""
import math
import os
import random
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from mushiboshi_ui import (COLORWAY_NAMES, dither_gradient, log_errors, is_night_time, PixelMenu, colorway_cmap, colorway_menu,
                           colorway_theme, load_colorway, load_weather, recolor, save_colorway, Scale, mix, px_pattern, px_text,
                           px_text_w, load_json, save_json)

APP_VERSION = "1.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "aquarium_config.json")
FPS = 12
MAX_FISH = 20

DEFAULT_CONFIG = {"fish": [], "light": "auto", "scale": 3, "topmost": True, "x": 200, "y": 200}
SCALES = [("ミニ", 1.5), ("小", 2), ("中", 3), ("大", 4)]
LIGHTS = [("自動（SugarOS の昼と夜）", "auto"), ("昼", "day"), ("夜", "night")]

# ---------- ドット絵の部品 ----------

_ICONS = {
    "fish": "...##..|.#####.#|########|.#####.#|...##..",
    "flake": ".#.#.|#.#.#|.#.#.",
    "plus": "..#..|..#..|#####|..#..|..#..",
    "sun": "#.#.#|.###.|#####|.###.|#.#.#",
    "moon": ".###.|##...|##...|##...|.###.",
    "auto": "###..|#.#..|###.#|#.#.#|#.#.#",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
}

PAL = dict(face=(238, 246, 250), out=(40, 64, 96), light=(255, 255, 255), shade=(186, 210, 226),
           title=(140, 200, 236), title2=(184, 226, 248), accent=(240, 104, 140), hover=(255, 216, 228),
           second=(96, 150, 200))
COLOR_BASE = {v: k for k, v in PAL.items() if k != "light"}

W, H = 166, 128
TX, TY, TW, TH = 3, 14, 160, 96          # 水槽（ウィンドウの中での大きさ）
IW, IH = 160, 96                          # 水槽の中身（ver.1.1 から等倍で、細かく描く）
TZ = TW // IW
ROW = 113
BUTTONS = {"feed": (3, 30), "add": (34, 33), "light": (68, 31)}
SAND_Y = 84


# ---------- 魚 ----------
# 魚の形は、体（だ円）・尾びれ・ひれの組み合わせで描いて、陰影とフチ取りを自動でつける。
# 色のキー：B=体 L=おなか D=しま模様 S=ネオンの線 R=赤 T=尾 F=ひれ（保存されている魚の色と同じ）

SPECIES = {
    "tetra": {"name": "ネオンテトラ", "speed": (0.9, 1.6), "size": (18, 9)},
    "goldfish": {"name": "金魚", "speed": (0.4, 0.8), "size": (22, 16)},
    "angel": {"name": "エンゼルフィッシュ", "speed": (0.3, 0.6), "size": (18, 24)},
    "guppy": {"name": "グッピー", "speed": (0.7, 1.3), "size": (18, 12)},
    "betta": {"name": "ベタ", "speed": (0.4, 0.9), "size": (22, 18)},
}
SWAY = [0, 1, 0, -1]          # 尾びれのゆれ（4コマ）
INK = (28, 34, 54)            # フチ取りに混ぜる色
EYE, EYE_HI = (20, 20, 30), (250, 250, 255)
GLOW = (80, 230, 255)         # 夜のネオンテトラ

VIVID = [(250, 90, 120), (80, 140, 250), (250, 180, 40), (160, 90, 230), (60, 200, 170), (250, 120, 60)]


def random_colors(species):
    """種類ごとに、それっぽい色をランダムに決める。"""
    r = random.random
    if species == "tetra":
        return {"B": (196, 206, 216), "L": (232, 236, 242), "S": (40, 200, 240), "R": (230, 54, 66),
                "T": (200, 212, 222)}
    if species == "goldfish":
        base = random.choice([(240, 116, 40), (250, 166, 56), (236, 70, 40), (246, 240, 228)])
        belly = mix(base, (255, 255, 255), 0.45)
        fin = mix(base, (255, 255, 255), 0.3) if r() < 0.6 else (246, 240, 228)
        return {"B": base, "L": belly, "T": fin, "F": fin}
    if species == "angel":
        base = random.choice([(232, 228, 210), (240, 200, 90), (70, 70, 84)])
        stripe = (60, 60, 72) if base != (70, 70, 84) else (150, 150, 170)
        return {"B": base, "D": stripe, "T": mix(base, (255, 255, 255), 0.3), "F": mix(base, (255, 255, 255), 0.3)}
    if species == "guppy":
        base = random.choice([(176, 176, 156), (220, 200, 120), (150, 170, 190)])
        return {"B": base, "L": mix(base, (255, 255, 255), 0.4), "T": random.choice(VIVID)}
    base = random.choice([(210, 40, 64), (52, 92, 222), (140, 62, 204), (240, 240, 250), (40, 170, 160)])
    return {"B": base, "F": mix(base, (255, 255, 255), 0.25), "T": mix(base, (255, 255, 255), 0.25)}


def _shape(species, s):
    """1コマぶんの形。(尾びれ, ひれのリスト, 体のだ円, 目) を返す。s は尾びれのゆれ。"""
    if species == "tetra":
        tail = [[(6, 4), (1, 1 + s), (3, 4)], [(6, 5), (1, 8 + s), (3, 5)]]
        return tail, [[(9, 3), (11, 0), (13, 3)], [(9, 7), (11, 8), (13, 7)]], (5, 2, 17, 7), (15, 4)
    if species == "goldfish":
        tail = [[(9, 7), (0, 1 + s), (3, 8), (0, 15 + s), (9, 9)]]
        return tail, [[(11, 4), (13, 0), (16, 1), (18, 4)], [(13, 11), (14, 14), (17, 12)]], (7, 3, 21, 13), (18, 7)
    if species == "angel":
        fins = [[(9, 8), (4, 0), (7, 0), (14, 7)], [(9, 15), (4, 23), (7, 23), (14, 16)]]
        return [[(6, 11), (1, 8 + s), (1, 15 + s)]], fins, (5, 6, 17, 17), (14, 10)
    if species == "guppy":
        tail = [[(9, 6), (2, 0 + s), (0, 3), (0, 8), (2, 11 + s)]]
        return tail, [[(11, 4), (13, 2), (15, 4)]], (8, 4, 17, 8), (15, 5)
    tail = [[(9, 7), (4, 2 + s), (1, 4 + s), (0, 9), (1, 14 + s), (4, 16 + s), (9, 10)]]   # ベタ：ひらひらの大きなひれ
    fins = [[(10, 6), (9, 3), (10, 1 + s), (13, 0), (16, 2), (18, 6)],
            [(10, 11), (7, 14), (6, 17 + s), (10, 17), (14, 16), (18, 11)]]
    return tail, fins, (8, 6, 21, 11), (18, 8)


def render_fish(species, colors, frame):
    """右向きの1コマ。陰影・模様・フチ取りつき。(絵, 夜に光るところ) を返す。"""
    w, h = SPECIES[species]["size"]
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    B = colors["B"]
    T, F = colors.get("T", B), colors.get("F", colors.get("T", B))
    tail, fins, body, eye = _shape(species, SWAY[frame])
    for poly in tail:
        d.polygon(poly, fill=T + (255,))
    for poly in fins:
        d.polygon(poly, fill=F + (255,))
    if species in ("guppy", "betta"):   # 大きなひれの、明るいすじ
        for poly in tail + fins:
            x0, y0 = poly[0]
            for x1, y1 in poly[1:]:
                d.line([(x0, y0), ((x0 + x1) / 2, (y0 + y1) / 2)], fill=mix(T, (255, 255, 255), 0.35) + (255,))
    d.ellipse(body, fill=B + (255,))
    bx0, by0, bx1, by1 = body
    cy = (by0 + by1) / 2
    px = im.load()
    for y in range(by0, by1 + 1):
        for x in range(bx0, bx1 + 1):
            if px[x, y][3] == 0:
                continue
            c = px[x, y][:3]
            if c != B:
                continue
            if y <= by0 + 1:                       # 背中のハイライト
                c = mix(B, (255, 255, 255), 0.35)
            elif y > cy and "L" in colors:          # おなか
                c = colors["L"]
            elif y > cy + 1:
                c = mix(B, (0, 0, 0), 0.15)
            px[x, y] = c + (255,)
    if species == "tetra":   # ネオンの線と、うしろ半分の赤
        for x in range(bx0 + 2, bx1 - 1):
            px[x, by0 + 2] = colors["S"] + (255,)
        for x in range(bx0 + 1, bx0 + 7):
            for y in (by0 + 3, by0 + 4):
                if px[x, y][3]:
                    px[x, y] = colors["R"] + (255,)
    if species == "angel":   # たてじま（ひれまで）
        for x in (8, 12):
            for y in range(h):
                if px[x, y][3]:
                    px[x, y] = colors["D"] + (255,)
    if species == "guppy":   # 尾びれの水玉
        for x, y in ((3, 3), (5, 7), (2, 8), (6, 4)):
            if px[x, y][3]:
                px[x, y] = mix(T, (255, 255, 255), 0.5) + (255,)
    # フチ取り：外側に面した点を、少し暗く
    alpha = [[px[x, y][3] for x in range(w)] for y in range(h)]
    for y in range(h):
        for x in range(w):
            if alpha[y][x] and any(not (0 <= x + dx < w and 0 <= y + dy < h) or not alpha[y + dy][x + dx]
                                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                px[x, y] = mix(px[x, y][:3], INK, 0.55) + (255,)
    ex, ey = eye
    px[ex, ey] = EYE + (255,)
    px[ex, ey - 1] = mix(EYE_HI, B, 0.3) + (255,)
    glow = None
    if species == "tetra":
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gp = glow.load()
        for x in range(w):
            for y in range(h):
                if px[x, y][:3] == colors["S"]:
                    gp[x, y] = GLOW + (255,)
    return im, glow


class Fish:
    def __init__(self, species=None, colors=None):
        self.species = species or random.choice(list(SPECIES))
        self.colors = {k: tuple(v) for k, v in (colors or random_colors(self.species)).items()}
        frames = [render_fish(self.species, self.colors, i) for i in range(len(SWAY))]
        # 右向き・左向き × 4コマ
        flip = lambda im: im.transpose(Image.FLIP_LEFT_RIGHT) if im else None   # noqa: E731
        self.sprites = {1: [f for f, _ in frames], -1: [flip(f) for f, _ in frames]}
        self.glows = {1: [g for _, g in frames], -1: [flip(g) for _, g in frames]}
        self.w, self.h = self.sprites[1][0].size
        self.speed = random.uniform(*SPECIES[self.species]["speed"])
        self.x = random.uniform(6, IW - self.w - 6)
        self.y = random.uniform(10, SAND_Y - self.h - 6)
        self.ty = self.y
        self.dir = random.choice((1, -1))
        self.phase = random.uniform(0, 6.28)
        self.rest = 0
        self.scared = 0
        self.full = 0   # 食べたあと少しのあいだはエサを追わない

    def to_json(self):
        return {"species": self.species, "colors": {k: list(v) for k, v in self.colors.items()}}

    def update(self, t, food):
        target = None
        self.full = max(0, self.full - 1)
        visible = [f for f in food if f["age"] > 12]
        if visible and not self.full:   # 近くのエサに寄っていく
            near = min(visible, key=lambda f: abs(f["x"] - self.cx()) + abs(f["y"] - self.cy()))
            if abs(near["x"] - self.cx()) + abs(near["y"] - self.cy()) < 60:
                target = near
        if target:
            self.dir = 1 if target["x"] > self.cx() else -1
            self.ty = target["y"] - self.h / 2
            sp = self.speed * 1.4
            if self.x - 2 <= target["x"] <= self.x + self.w + 2 and self.y - 2 <= target["y"] <= self.y + self.h + 2:
                food.remove(target)
                self.full = random.randint(20, 40)
                return "ate"
        else:
            sp = self.speed * (2.6 if self.scared else 1)
            if self.rest > 0:
                self.rest -= 1
                sp *= 0.1
            elif random.random() < 0.004:
                self.rest = random.randint(10, 40)
            if random.random() < 0.01:
                self.ty = random.uniform(10, SAND_Y - self.h - 4)
            if random.random() < 0.003:
                self.dir *= -1
        self.scared = max(0, self.scared - 1)
        self.x += sp * self.dir
        if self.x < 2:
            self.x, self.dir = 2, 1
        elif self.x > IW - self.w - 2:
            self.x, self.dir = IW - self.w - 2, -1
        self.y += (self.ty - self.y) * 0.05
        self.y = max(8, min(SAND_Y - self.h, self.y))
        return None

    def cx(self):
        return self.x + self.w / 2

    def cy(self):
        return self.y + self.h / 2

    def pose(self, t):
        frame = int(t * (12 if self.scared else 6) + self.phase) % len(SWAY)
        return frame, (int(self.x), int(self.y + math.sin(t * 2 + self.phase) * 1.2))

    def draw(self, im, t):
        frame, xy = self.pose(t)
        spr = self.sprites[self.dir][frame]
        im.paste(spr, xy, spr)

    def draw_glow(self, im, t):
        frame, xy = self.pose(t)
        g = self.glows[self.dir][frame]
        if g is not None:
            im.paste(g, xy, g)


# ---------- 背景 ----------

def sand_top(x):
    return SAND_Y + int(2 * math.sin(x / 14) + 1.5 * math.sin(x / 6 + 1))


def draw_rock(d, cx, w, h, col):
    x0, y0, x1, y1 = cx - w // 2, SAND_Y - h + 3, cx + w // 2, SAND_Y + 5
    d.ellipse([x0, y0, x1, y1], fill=col, outline=mix(col, INK, 0.5))
    d.ellipse([x0 + 2, y0 + 1, x0 + w // 2, y0 + h // 2], fill=mix(col, (255, 255, 255), 0.25))   # 上のハイライト
    d.arc([x0 + 1, y0 + 1, x1 - 1, y1 - 1], 20, 160, fill=mix(col, INK, 0.25))                   # 下の影
    for dx in range(2, w - 2, 3):   # こけ
        d.point((x0 + dx, y0 + (1 if dx % 2 else 2)), fill=(110, 170, 110))


def draw_teacup(d, x, y):
    """砂にしずんだティーカップ（SugarRoom24 の）。"""
    pink, rim, shade, gold = (246, 192, 206), (255, 246, 248), (220, 150, 170), (236, 200, 120)
    d.ellipse([x - 3, y + 7, x + 22, y + 12], fill=rim, outline=mix(rim, INK, 0.45))           # ソーサー
    d.polygon([(x, y), (x + 16, y), (x + 14, y + 9), (x + 2, y + 9)], fill=pink)                # カップ（横だおし）
    d.line([(x, y), (x + 16, y)], fill=rim)
    d.line([(x + 1, y + 1), (x + 15, y + 1)], fill=gold)
    d.line([(x + 14, y + 2), (x + 13, y + 8)], fill=shade)
    d.arc([x + 14, y + 1, x + 21, y + 7], 270, 90, fill=pink)                                    # とって
    d.arc([x + 15, y + 2, x + 20, y + 6], 270, 90, fill=shade)
    d.line([(x + 2, y + 9), (x + 14, y + 9)], fill=mix(pink, INK, 0.45))
    d.line([(x, y), (x + 2, y + 9)], fill=mix(pink, INK, 0.45))
    for k, c in ((5, (255, 255, 255)), (6, (255, 220, 230))):   # ハートのもよう
        d.point((x + k, y + 4), fill=c)
    px_pattern(d, x + 6, y + 3, "#.#|###|.#.", (236, 110, 140))


def build_background(seed=24):
    rnd = random.Random(seed)
    im = Image.new("RGB", (IW, IH))
    d = ImageDraw.Draw(im)
    water_top, water_bottom = (172, 230, 246), (44, 120, 178)
    dither_gradient(d, 0, 0, IW - 1, IH - 1, water_top, water_bottom)
    d.rectangle([0, 0, IW - 1, 3], fill=(214, 240, 248))     # 水面より上
    d.line([(0, 4), (IW - 1, 4)], fill=(236, 250, 255))
    # 奥の水草のかげ（うすく。根もとが太く、先が細い葉）
    shadow = mix(water_bottom, (30, 90, 96), 0.35)
    for k in range(16):
        x = rnd.randrange(IW)
        top = rnd.randint(26, 58)
        for y in range(top, SAND_Y + 2):
            k2 = (y - top) / (SAND_Y + 2 - top)
            sx = x + int(math.sin(y / 9 + k) * 3 * (1 - k2))
            for dx in range(1 + int(k2 * 2.5)):
                px_ = (sx + dx) % IW
                d.point((px_, y), fill=mix(im.getpixel((px_, y)), shadow, 0.4))
    # 砂（2色の網点と小石）
    sand, sand2, sand_hi = (236, 214, 160), (222, 198, 144), (250, 236, 198)
    for x in range(IW):
        top = sand_top(x)
        for y in range(top, IH):
            d.point((x, y), fill=sand2 if (x + y) % 2 and (y - top) % 4 > 1 else sand)
        d.point((x, top), fill=sand_hi)
    for _ in range(90):
        x, y = rnd.randrange(IW), rnd.randrange(SAND_Y + 2, IH)
        c = rnd.choice([(206, 182, 130), (190, 166, 124), (250, 242, 220), (196, 166, 160), (170, 190, 204),
                        (232, 186, 196)])
        d.point((x, y), fill=c)
        if rnd.random() < 0.3:
            d.point((x + 1, y), fill=mix(c, INK, 0.25))
    for x, y in ((40, SAND_Y + 6), (96, SAND_Y + 8), (70, SAND_Y + 4)):   # 貝がら
        px_pattern(d, x, y, ".#.|###", (255, 236, 240))
        d.point((x + 1, y + 1), fill=(236, 180, 196))
    # 岩とティーカップ
    draw_rock(d, 118, 24, 14, (122, 130, 144))
    draw_rock(d, 134, 14, 9, (146, 152, 162))
    draw_rock(d, 22, 16, 10, (132, 122, 128))
    draw_teacup(d, 62, SAND_Y - 7)
    for cx in (52, 88):   # まりも
        d.ellipse([cx - 3, SAND_Y - 3, cx + 3, SAND_Y + 3], fill=(84, 150, 84), outline=mix((84, 150, 84), INK, 0.4))
        d.point((cx - 1, SAND_Y - 1), fill=(150, 210, 140))
    # エアストーン
    d.rounded_rectangle([145, SAND_Y + 1, 153, SAND_Y + 4], radius=1, fill=(150, 150, 160), outline=(90, 90, 104))
    # ガラスの映り込み（ななめのうすい光）
    for y in range(6, IH - 2):
        for x in (3 + y // 12, 4 + y // 12):
            if x < IW:
                d.point((x, y), fill=mix(im.getpixel((x, y)), (255, 255, 255), 0.25))
    return im


# 水草：(種類, 根もとの x, 高さ, 色)
PLANTS = [("ribbon", 10, 52, (70, 170, 90)), ("ribbon", 14, 40, (96, 196, 110)), ("round", 30, 34, (110, 200, 120)),
          ("ribbon", 98, 46, (60, 150, 100)), ("red", 104, 30, (236, 128, 120)), ("round", 140, 40, (90, 180, 110)),
          ("ribbon", 156, 36, (70, 160, 90)), ("red", 46, 22, (240, 150, 140))]


def draw_plants(d, t):
    for i, (kind, x0, height, col) in enumerate(PLANTS):
        base = sand_top(x0) + 1
        dark, light = mix(col, INK, 0.3), mix(col, (255, 255, 255), 0.3)
        prev = None
        for s in range(height):
            k = s / height
            x = x0 + math.sin(t * 1.2 + i + s * 0.12) * 3 * k * k
            y = base - s
            if kind == "ribbon":   # 細長い葉が2本、ゆらゆら
                d.point((x, y), fill=col)
                d.point((x + 1, y), fill=dark if s % 7 < 4 else col)
                if s > height * 0.3:
                    d.point((x - 3 * k + 1, y + 2), fill=light)
            else:                  # 茎に丸い葉が、互い違いにつく
                if prev:
                    d.line([prev, (x, y)], fill=dark)
                if s % 5 == 2:
                    side = 2 if (s // 5) % 2 else -3
                    leaf = col if kind == "round" else mix(col, (255, 255, 255), 0.1 * (s % 3))
                    d.ellipse([x + side, y - 1, x + side + 2, y + 1], fill=leaf)
                    d.point((x + side + 1, y - 1), fill=light)
                prev = (x, y)


# 天気で水槽の照明が変わる：(混ぜる色, 混ぜる割合)
WEATHER_LIGHT = {"cloudy": ((150, 160, 176), 0.12), "rain": ((96, 110, 140), 0.2), "thunder": ((60, 64, 92), 0.28),
                 "snow": ((226, 234, 248), 0.12), "fog": ((214, 220, 228), 0.18)}
BUBBLE, BUBBLE_HI = (214, 240, 250), (255, 255, 255)


def render_tank(bg, t, fishes, food, bubbles, night, weather=None):
    im = bg.copy()
    over = Image.new("RGBA", (IW, IH), (0, 0, 0, 0))
    o = ImageDraw.Draw(over)
    # 光の筋（ゆっくり動く）
    for i in range(3):
        x = (i * 62 + t * 4) % (IW + 60) - 30
        o.polygon([(x, 4), (x + 10, 4), (x - 22, SAND_Y), (x - 38, SAND_Y)], fill=(255, 255, 255, 22))
    # 砂にゆれる光の網目
    for x in range(0, IW, 2):
        y = sand_top(x) + 2 + int(math.sin(x * 0.3 + t * 1.5) * 1.5)
        if math.sin(x * 0.21 + t * 0.9) > 0.55:
            o.point((x, y), fill=(255, 255, 230, 70))
    im = Image.alpha_composite(im.convert("RGBA"), over).convert("RGB")
    d = ImageDraw.Draw(im)
    draw_plants(d, t)
    # 水面のゆらぎ
    for x in range(IW):
        if math.sin(x * 0.35 + t * 3) > 0.6:
            d.point((x, 5), fill=(236, 250, 255))
        if math.sin(x * 0.2 - t * 2) > 0.85:
            d.point((x, 6), fill=(214, 242, 252))
    # エサ（2×2 のつぶ）
    for f in food:
        x, y = int(f["x"]), int(f["y"])
        d.rectangle([x, y, x + 1, y + 1], fill=f["c"])
        d.point((x + 1, y + 1), fill=mix(f["c"], INK, 0.3))
    # 魚
    for fish in fishes:
        fish.draw(im, t)
    # 泡（大きさ3しゅるい、光るふちつき）
    for b in bubbles:
        x, y = b["x"] + math.sin(t * 4 + b["p"]) * 1.0, b["y"]
        xi, yi, r = int(x), int(y), b["r"]
        if r == 0:
            d.point((xi, yi), fill=BUBBLE)
        else:
            d.ellipse([xi - r, yi - r, xi + r, yi + r], outline=BUBBLE)
            d.point((xi - r + 1, yi - r + 1), fill=BUBBLE_HI)
    if night:
        dark = Image.new("RGB", im.size, (10, 20, 60))
        im = Image.blend(im, dark, 0.55)
        for fish in fishes:   # ネオンテトラはうっすら光る
            fish.draw_glow(im, t)
    if weather in WEATHER_LIGHT:   # くもりや雨の日は、部屋の光が水槽にも映る
        col, a = WEATHER_LIGHT[weather]
        im = Image.blend(im, Image.new("RGB", im.size, mix(col, (10, 20, 60), 0.5) if night else col), a)
        if weather == "thunder" and t % 7 < 0.18:   # 稲光
            im = Image.blend(im, Image.new("RGB", im.size, (250, 250, 255)), 0.45)
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
    px_pattern(d, 4, 4, _ICONS["fish"], k["out"])
    px_text(d, 15, 5, "AQUA.EXE", k["out"])
    bx0 = W - 3 - 3 * 9
    for i, icon in enumerate(("min", "max", "close")):
        x0 = bx0 + i * 9
        d.rectangle([x0, 3, x0 + 7, 10], fill=k["hover"] if icon == "close" else k["face"], outline=k["out"])
        px_pattern(d, x0 + 1, 4, _ICONS[icon], k["out"])
    d.line([(1, 12), (W - 2, 12)], fill=k["out"])
    # 水槽のガラス枠と台
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
    return cfg


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


# ---------- 本体 ----------

class Aquarium:
    def __init__(self):
        self.cfg = load_config()
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.p = Scale(self.cfg["scale"])
        self.fishes = []
        for f in self.cfg["fish"]:
            try:
                self.fishes.append(Fish(f["species"], f["colors"]))
            except (KeyError, TypeError, ValueError):
                continue
        if not self.fishes:   # はじめての水槽
            self.fishes = [Fish(s) for s in ("tetra", "tetra", "tetra", "goldfish", "guppy", "angel")]
            self.save_fish()
        self.food = []
        self.bubbles = []
        self.bg = build_background()
        self.t0 = time.time()
        self.pimgs = {}

        self.root = tk.Tk()
        log_errors(self.root, "aquarium_error.txt")
        self.root.title(f"ドット水槽 ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "aquarium.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])
        self.frame_label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.tank = tk.Label(self.root, bd=0, highlightthickness=0, cursor="hand2")
        self.status = tk.Label(self.root, bd=0, highlightthickness=0)
        for w in (self.root, self.frame_label, self.status):
            w.bind("<ButtonPress-1>", self.drag_start)
            w.bind("<B1-Motion>", self.drag_move)
            w.bind("<ButtonRelease-1>", self.drag_end)
            w.bind("<Button-3>", self.popup_menu)
        self.tank.bind("<Button-1>", self.tank_click)
        self.tank.bind("<Button-3>", self.popup_menu)
        self.frame_label.bind("<Motion>", self.frame_hover, add="+")
        self.frame_label.bind("<ButtonRelease-1>", self.frame_click, add="+")
        self.buttons = {}
        for key, action in (("feed", self.feed), ("add", self.add_fish), ("light", self.cycle_light)):
            lb = tk.Label(self.root, bd=0, highlightthickness=0, cursor="hand2")
            lb.bind("<Button-1>", lambda e, a=action: a())
            lb.bind("<Enter>", lambda e, k=key: self.draw_button(k, True))
            lb.bind("<Leave>", lambda e, k=key: self.draw_button(k, False))
            lb.bind("<Button-3>", self.popup_menu)
            self.buttons[key] = lb
        self.pmenu = PixelMenu(self.root, self.menu_theme, title="AQUA.EXE - MENU")
        self.layout()
        self.root.after(1000 // FPS, self.tick)
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
        self.tank.place(x=TX * p, y=TY * p, width=TW * p, height=TH * p)
        for key, (x, w) in BUTTONS.items():
            self.draw_button(key)
            self.buttons[key].place(x=x * p, y=ROW * p)
        sx = 100
        self.status.place(x=sx * p, y=ROW * p, width=(W - 3 - sx) * p, height=11 * p)
        self.draw_status()

    def draw_button(self, key, hover=False):
        x, w = BUTTONS[key]
        icon, text = {"feed": ("flake", "FEED"), "add": ("plus", "FISH"),
                      "light": ({"auto": "auto", "day": "sun", "night": "moon"}[self.cfg["light"]], "LIGHT")}[key]
        img = recolor(render_button(icon, text, w, hover), self.cmap())
        img = ImageTk.PhotoImage(img.resize((w * self.p, 11 * self.p), Image.NEAREST))
        self.pimgs[key] = img
        self.buttons[key].config(image=img)

    def draw_status(self):
        sw = W - 3 - 100
        im = Image.new("RGB", (sw, 11), self.col("face"))
        d = ImageDraw.Draw(im)
        temp = 24.6 + 0.4 * math.sin(time.time() / 600)
        px_text(d, 1, 3, f"FISH {len(self.fishes)}", self.col("out"))
        txt = f"{temp:.1f}'C"
        px_text(d, sw - px_text_w(txt) - 1, 3, txt, self.col("out"))
        img = ImageTk.PhotoImage(im.resize((sw * self.p, 11 * self.p), Image.NEAREST))
        self.pimgs["status"] = img
        self.status.config(image=img)

    def is_night(self):
        if self.cfg["light"] == "auto":
            return is_night_time()   # ランチャーで決めた SugarOS の昼と夜に合わせる
        return self.cfg["light"] == "night"

    # --- 動き ---
    def tick(self):
        t = time.time() - self.t0
        for fish in self.fishes:
            if fish.update(t, self.food) == "ate":
                fish.rest = 0
        if not self.food:   # 重なりすぎた魚は、ちがう深さへ散らす
            for i, a in enumerate(self.fishes):
                for b in self.fishes[i + 1:]:
                    if abs(a.cx() - b.cx()) < 10 and abs(a.cy() - b.cy()) < 6 and random.random() < 0.05:
                        b.ty = random.uniform(8, SAND_Y - b.h)
        for f in list(self.food):
            f["age"] += 1
            if f["y"] < SAND_Y:
                f["y"] += 0.24
                f["x"] += math.sin(t * 2 + f["p"]) * 0.1
            else:
                f["life"] -= 1
                if f["life"] <= 0:
                    self.food.remove(f)
        if random.random() < 0.25:
            self.bubbles.append({"x": 149 + random.uniform(-1, 1), "y": SAND_Y,
                                 "r": random.choice((0, 0, 1, 1, 2)), "p": random.uniform(0, 6.28),
                                 "v": random.uniform(0.5, 0.9)})
        for b in list(self.bubbles):
            b["y"] -= b["v"]
            if b["y"] < 6:
                self.bubbles.remove(b)
        img = render_tank(self.bg, t, self.fishes, self.food, self.bubbles, self.is_night(),
                          load_weather())
        self.tank_photo = ImageTk.PhotoImage(img.resize((TW * self.p, TH * self.p), Image.NEAREST))
        self.tank.config(image=self.tank_photo)
        if int(t) % 5 == 0 and int(t * FPS) % FPS == 0:
            self.draw_status()
        self.root.after(1000 // FPS, self.tick)

    def drop_food(self, x, n=1):
        for _ in range(n):
            self.food.append({"x": max(2, min(IW - 3, x + random.uniform(-4, 4))), "y": random.uniform(6, 10),
                              "p": random.uniform(0, 6.28), "life": FPS * 20, "age": 0,
                              "c": random.choice([(214, 120, 60), (180, 90, 50), (230, 170, 80)])})
        del self.food[:-60]

    def tank_click(self, e):
        self.drop_food(e.x / (self.p * TZ), 2)

    def feed(self):
        for _ in range(4):
            self.drop_food(random.uniform(16, IW - 16), 2)

    def add_fish(self, species=None):
        if len(self.fishes) >= MAX_FISH:
            return
        f = Fish(species)
        f.x = IW - f.w - 2 if random.random() < 0.5 else 2
        f.y = 10
        self.fishes.append(f)
        self.save_fish()
        self.draw_status()

    def remove_fish(self):
        if len(self.fishes) > 1:
            self.fishes.pop(random.randrange(len(self.fishes)))
            self.save_fish()
            self.draw_status()

    def shuffle_fish(self):
        n = len(self.fishes)
        self.fishes = [Fish() for _ in range(n)]
        self.save_fish()

    def save_fish(self):
        self.cfg["fish"] = [f.to_json() for f in self.fishes]
        save_config(self.cfg)

    def cycle_light(self):
        order = ["auto", "day", "night"]
        self.set_light(order[(order.index(self.cfg["light"]) + 1) % 3])

    def set_light(self, v):
        self.cfg["light"] = v
        save_config(self.cfg)
        self.draw_button("light")

    # --- メニュー ---
    def menu_items(self):
        c = self.cfg
        counts = {}
        for f in self.fishes:
            counts[f.species] = counts.get(f.species, 0) + 1
        add_items = [{"type": "cmd", "label": "ランダム", "cmd": self.add_fish}, {"type": "sep"}]
        add_items += [{"type": "cmd", "label": sp["name"], "right": f"{counts.get(k, 0)}匹",
                       "cmd": lambda k=k: self.add_fish(k)} for k, sp in SPECIES.items()]
        return [
            {"type": "cmd", "label": "エサをあげる", "cmd": self.feed},
            {"type": "sub", "label": "魚をふやす", "items": add_items, "right": f"{len(self.fishes)}/{MAX_FISH}"},
            {"type": "cmd", "label": "魚を1匹へらす", "cmd": self.remove_fish, "enabled": len(self.fishes) > 1},
            {"type": "cmd", "label": "魚をぜんぶ入れ替える", "cmd": self.shuffle_fish},
            {"type": "sep"},
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
            {"type": "head", "label": f"ドット水槽 ver.{APP_VERSION}"},
        ]

    def popup_menu(self, e):
        self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

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
        self.save_fish()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        Aquarium().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "aquarium_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
