# -*- coding: utf-8 -*-
"""
一方その頃 ver.1.2（MEANWHILE.EXE）
作業しているあいだ、どこか別の場所の様子が小さく流れ続けるウインドウ。防犯カメラ風。

操作:
  ◀ / ▶   … 場所を切り替える
  AUTO    … 数分ごとに自動で巡回
  CAM     … CAM 表示（REC・時刻）のオン・オフ
  ドラッグ … ウィンドウを移動
  右クリック … メニュー（場所を選ぶ / 巡回の間隔 / カラー / サイズ など）

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
                           ui_font, Scale, hexc, mix, vgrad, px_pattern, px_text, px_text_w, load_json, save_json)

APP_VERSION = "1.2"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "meanwhile_config.json")
FPS = 10

DEFAULT_CONFIG = {"scene": 0, "auto": True, "auto_min": 10, "cam": True, "scale": 3,
                  "topmost": True, "x": 280, "y": 120}
SCALES = [("ミニ", 1.5), ("小", 2), ("中", 3), ("大", 4)]
AUTO_MINS = [("3分", 3), ("10分", 10), ("30分", 30)]

_ICONS = {
    "cam": "######.|#....###|#..#.###|#....###|######.",
    "prev": "..#..#|.##.##|######|.##.##|..#..#",
    "next": "#..#..|##.##.|######|##.##.|#..#..",
    "auto": ".###.|#...#|#.#.#|#...#|.###.",
    "rec": ".#.|###|.#.",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
}

PAL = dict(face=(242, 240, 248), out=(52, 48, 76), light=(255, 255, 255), shade=(200, 196, 220),
           title=(196, 186, 226), title2=(222, 214, 242), accent=(236, 88, 120), hover=(255, 216, 226),
           second=(120, 112, 170))
COLOR_BASE = {v: k for k, v in PAL.items() if k != "light"}

W, H = 166, 147
SX, SY, SW, SH = 3, 14, 160, 104
IW, IH = 160, 104                         # 画面の中身（ver.1.1 から等倍で、細かく描く）
CAP_Y, ROW = 120, 133
BUTTONS = {"prev": (3, 15), "next": (19, 15), "auto": (35, 31), "cam": (67, 30)}


# ---------- 場所 ----------

INK = (24, 22, 40)   # フチや影に混ぜる色


class Scene:
    name = ""
    caption = ""
    hour = 0          # その場所の時刻（時）。None なら ??:??
    sky = None        # 天気の演出を描く範囲（屋外や窓の外）。None なら屋内で、天気は関係ない

    def __init__(self):
        self.rnd = random.Random(hash(self.name) & 0xffff)
        self.bg = self.build()

    def build(self):
        return Image.new("RGB", (IW, IH))

    def frame(self, t, weather=None):
        im = self.bg.copy()
        self.animate(ImageDraw.Draw(im), t, im)
        if self.sky:
            draw_weather(im, self.sky, weather, t, night=self.hour is not None and not 6 <= self.hour < 18)
        return im

    def animate(self, d, t, im):
        pass


def glow(im, box, color, alpha):
    """やわらかい光。だ円を少しずつ小さくして4回重ねるので、まんなかほど明るく、ふちはぼんやり。"""
    over = Image.new("RGBA", im.size, (0, 0, 0, 0))
    o = ImageDraw.Draw(over)
    x0, y0, x1, y1 = box
    for k in range(4):
        ix, iy = (x1 - x0) * k / 10, (y1 - y0) * k / 10
        o.ellipse([x0 + ix, y0 + iy, x1 - ix, y1 - iy], fill=color + (alpha // 4,))
    im.paste(Image.alpha_composite(im.convert("RGBA"), over).convert("RGB"))


class Diner(Scene):
    name = "DINER"
    caption = "一方その頃、深夜のダイナーでは…"
    hour = 2
    sky = (10, 10, 90, 50)   # 窓の外

    def build(self):
        im = Image.new("RGB", (IW, IH))
        d = ImageDraw.Draw(im)
        wall, wall2 = (36, 70, 82), (42, 78, 90)
        d.rectangle([0, 0, IW - 1, 66], fill=wall)
        for x in range(0, IW, 8):   # 壁の板
            d.line([(x, 0), (x, 66)], fill=wall2)
            d.line([(x + 1, 0), (x + 1, 66)], fill=mix(wall, INK, 0.2))
        d.rectangle([0, 58, IW - 1, 60], fill=(200, 210, 220))      # クロームのレール
        d.line([(0, 58), (IW - 1, 58)], fill=(240, 244, 250))
        # 窓の外の夜の街
        dither_gradient(d, 10, 10, 90, 50, (10, 14, 36), (34, 38, 76), steps=5)
        for _ in range(14):
            d.point((self.rnd.randint(11, 89), self.rnd.randint(11, 26)), fill=(220, 220, 255))
        d.ellipse([72, 13, 81, 22], fill=(250, 240, 200))
        d.ellipse([75, 12, 84, 20], fill=(14, 18, 40))
        self.city_windows = []
        for layer, col, hmin, hmax in ((0, (34, 38, 70), 14, 28), (1, (22, 24, 48), 8, 20)):
            x = 10
            while x < 90:
                bw, bh = self.rnd.randint(8, 15), self.rnd.randint(hmin, hmax)
                d.rectangle([x, 50 - bh, min(90, x + bw), 50], fill=col)
                if layer == 1:
                    d.line([(x, 50 - bh), (min(90, x + bw), 50 - bh)], fill=mix(col, (255, 255, 255), 0.12))
                for wy in range(50 - bh + 3, 49, 4):
                    for wx in range(x + 2, min(89, x + bw - 1), 3):
                        if self.rnd.random() < 0.4:
                            d.rectangle([wx, wy, wx + 1, wy + 1], fill=(240, 210, 120))
                            self.city_windows.append((wx, wy))
                x += bw + self.rnd.randint(1, 3)
        frame, frame_hi = (190, 200, 212), (240, 244, 250)
        d.rectangle([8, 8, 92, 52], outline=frame)
        d.rectangle([9, 9, 91, 51], outline=mix(frame, INK, 0.4))
        d.rectangle([49, 8, 51, 52], fill=frame)
        d.line([(8, 8), (92, 8)], fill=frame_hi)
        # 看板の下地（ネオン管は動きの中で描く）
        d.rectangle([100, 10, 152, 46], fill=mix(wall, INK, 0.45), outline=(70, 90, 100))
        # カウンター
        d.rectangle([0, 66, IW - 1, 69], fill=(210, 216, 226))
        d.line([(0, 66), (IW - 1, 66)], fill=(246, 248, 252))
        d.line([(0, 69), (IW - 1, 69)], fill=(150, 156, 170))
        d.rectangle([0, 70, IW - 1, 85], fill=(170, 44, 58))
        for x in range(3, IW, 6):   # 赤いビニールのタック
            d.line([(x, 71), (x, 84)], fill=(146, 34, 48))
            d.point((x + 1, 72), fill=(206, 80, 92))
        d.line([(0, 71), (IW - 1, 71)], fill=(200, 70, 84))
        d.rectangle([0, 85, IW - 1, 87], fill=(200, 208, 220))
        # 床（白黒の市松）
        for y in range(88, IH):
            for x in range(IW):
                d.point((x, y), fill=(232, 232, 226) if ((x // 4) + (y - 88) // 4) % 2 else (40, 40, 48))
        # スツール
        for sx in (20, 52, 84):
            d.rectangle([sx - 1, 80, sx + 1, 97], fill=(190, 200, 212))
            d.line([(sx - 1, 80), (sx - 1, 97)], fill=(240, 244, 250))
            d.ellipse([sx - 7, 96, sx + 7, 100], fill=(170, 180, 194), outline=(110, 116, 130))
            d.ellipse([sx - 8, 74, sx + 8, 81], fill=(220, 60, 76), outline=(120, 30, 40))
            d.line([(sx - 5, 75), (sx + 3, 75)], fill=(250, 130, 140))
        # ジュークボックス
        d.rounded_rectangle([118, 48, 150, 88], radius=12, fill=(130, 66, 44), outline=(60, 30, 20))
        d.rounded_rectangle([122, 52, 146, 70], radius=9, fill=(46, 30, 26))
        for gx in range(124, 145, 3):   # スピーカーの網
            d.line([(gx, 74), (gx, 84)], fill=(90, 46, 32))
        d.rectangle([121, 71, 147, 72], fill=(220, 200, 150))
        # ケーキのショーケース
        d.rectangle([30, 62, 46, 65], fill=(250, 236, 200))
        d.polygon([(34, 64), (42, 64), (42, 60)], fill=(236, 90, 110))
        d.line([(34, 64), (42, 60)], fill=(250, 220, 160))
        d.arc([28, 52, 48, 72], 180, 360, fill=(200, 230, 240))
        d.point((33, 56), fill=(255, 255, 255))
        # コーヒー
        d.ellipse([60, 64, 72, 66], fill=(240, 240, 236))
        d.rectangle([62, 59, 69, 64], fill=(250, 250, 246))
        d.line([(62, 59), (69, 59)], fill=(110, 70, 50))
        d.arc([68, 60, 72, 63], 270, 90, fill=(250, 250, 246))
        # ペンダントライト
        for lx in (28, 70):
            d.line([(lx, 0), (lx, 5)], fill=(20, 20, 24))
            d.polygon([(lx - 6, 11), (lx + 6, 11), (lx + 2, 5), (lx - 2, 5)], fill=(60, 64, 70))
            d.line([(lx - 6, 11), (lx + 6, 11)], fill=(240, 220, 160))
        glow(im, (8, 8, 90, 70), (255, 230, 170), 18)
        return im

    def animate(self, d, t, im):
        # 車のライトが窓の外を通る
        cyc = t % 9
        if cyc < 3:
            x = 10 + cyc / 3 * 86
            for k in range(10):
                xx = x - k * 2
                if 10 <= xx <= 90:
                    c = mix((255, 240, 200), (22, 24, 48), k / 10)
                    d.rectangle([xx, 47, xx + 1, 48], fill=c)
        # ネオンサイン（ときどきチカチカ）
        flick = (int(t * 10) % 37 in (0, 2)) or (int(t * 10) % 113 < 3)
        col = (255, 96, 176) if not flick else (110, 60, 90)
        if not flick:
            glow(im, (96, 6, 156, 34), (255, 96, 176), 30)
            d = ImageDraw.Draw(im)
        px_text(d, 106, 14, "DINER", col, 2)
        if not flick:
            d.line([(104, 12), (148, 12)], fill=(200, 80, 150))
            d.line([(104, 26), (148, 26)], fill=(200, 80, 150))
        px_text(d, 114, 32, "24H", (120, 230, 250) if int(t) % 2 else (60, 130, 150), 2)
        # ジュークボックスの光
        colors = [(255, 90, 120), (255, 200, 80), (90, 220, 160), (100, 160, 255), (220, 120, 255)]
        for i in range(7):
            c = colors[(i + int(t * 3)) % 5]
            d.rectangle([124 + i * 3, 56, 125 + i * 3, 57], fill=c)
            d.rectangle([124 + i * 3, 64, 125 + i * 3, 65], fill=colors[(i + int(t * 3) + 2) % 5])
        # 湯気
        for k in range(4):
            yy = 57 - ((t * 6 + k * 3) % 12)
            d.point((65 + math.sin(t * 2 + k) * 1.8, yy), fill=(200, 210, 214))
        # 窓のあかりが、ときどき消えたりつく
        for i, (wx, wy) in enumerate(self.city_windows):
            if (int(t / 3) + i * 7) % 41 == 0:
                d.rectangle([wx, wy, wx + 1, wy + 1], fill=(30, 34, 62))


class Rooftop(Scene):
    name = "ROOFTOP"
    caption = "一方その頃、夕暮れのビルの屋上では…"
    hour = 18
    sky = (0, 0, IW - 1, IH - 1)

    def build(self):
        im = Image.new("RGB", (IW, IH))
        d = ImageDraw.Draw(im)
        sky_top, sky_bottom = (70, 66, 140), (252, 160, 120)
        dither_gradient(d, 0, 0, IW - 1, 64, sky_top, sky_bottom)
        # レトロな夕日（下半分に横すじ）
        d.ellipse([92, 22, 128, 58], fill=(255, 206, 128))
        d.ellipse([96, 24, 112, 36], fill=(255, 226, 170))
        for k, y in enumerate((44, 48, 51, 54, 56)):
            d.line([(90, y), (130, y)], fill=mix(sky_top, sky_bottom, y / 64))
        for y, x0, x1 in ((14, 10, 70), (20, 30, 96), (30, 120, 156)):   # すじ雲
            d.line([(x0, y), (x1, y)], fill=(250, 190, 186))
            d.line([(x0 + 6, y + 1), (x1 - 8, y + 1)], fill=(226, 150, 160))
        # 奥のビル
        x = 0
        while x < IW:
            bw, bh = self.rnd.randint(10, 18), self.rnd.randint(14, 34)
            d.rectangle([x, 64 - bh, x + bw, 68], fill=(124, 92, 144))
            d.line([(x, 64 - bh), (x + bw, 64 - bh)], fill=(170, 120, 160))
            x += bw + self.rnd.randint(0, 3)
        # 手前のビル（窓のあかりは動きの中で）
        self.windows = []
        x = 0
        while x < IW:
            bw, bh = self.rnd.randint(10, 20), self.rnd.randint(10, 26)
            d.rectangle([x, 68 - bh, x + bw, 70], fill=(64, 44, 86))
            d.line([(x + bw, 68 - bh), (x + bw, 70)], fill=(48, 32, 66))
            for wy in range(68 - bh + 3, 67, 4):
                for wx in range(x + 2, x + bw - 1, 3):
                    self.windows.append((wx, wy, self.rnd.random()))
            x += bw + 1
        # 電波塔
        d.line([(58, 18), (54, 58)], fill=(56, 38, 76))
        d.line([(58, 18), (62, 58)], fill=(56, 38, 76))
        for y in range(24, 58, 6):
            w = (y - 18) / 40 * 4
            d.line([(58 - w, y), (58 + w, y + 5)], fill=(56, 38, 76))
            d.line([(58 + w, y), (58 - w, y + 5)], fill=(56, 38, 76))
        d.line([(58, 10), (58, 18)], fill=(56, 38, 76))
        # 屋上の床
        d.rectangle([0, 70, IW - 1, IH - 1], fill=(150, 140, 152))
        for y in range(70, IH, 8):
            d.line([(0, y), (IW - 1, y)], fill=(136, 126, 140))
        for x in range(0, IW, 16):
            d.line([(x, 70), (x - 10, IH - 1)], fill=(136, 126, 140))
        d.ellipse([96, 90, 132, 98], fill=mix(sky_bottom, (150, 140, 152), 0.4))   # 水たまりに夕焼け
        d.line([(104, 92), (120, 92)], fill=(255, 220, 170))
        # フェンス（金網）
        d.rectangle([0, 48, IW - 1, 49], fill=(214, 214, 226))
        for x in range(0, IW, 16):
            d.rectangle([x, 48, x + 1, 72], fill=(180, 176, 200))
        for y in range(52, 72, 4):
            for x in range(0, IW, 4):
                d.point((x + (y // 4) % 2 * 2, y), fill=(176, 170, 196))
                d.point((x + 1 + (y // 4) % 2 * 2, y + 1), fill=(176, 170, 196))
        d.line([(0, 72), (IW - 1, 72)], fill=(120, 110, 126))
        # 給水タンク
        d.rectangle([8, 28, 34, 54], fill=(184, 178, 190), outline=(110, 104, 122))
        for y in (34, 42, 50):
            d.line([(9, y), (33, y)], fill=(156, 150, 166))
        d.line([(12, 29), (12, 53)], fill=(214, 210, 222))
        d.ellipse([8, 24, 34, 32], fill=(200, 196, 208), outline=(110, 104, 122))
        for lx in (12, 30):
            d.line([(lx, 54), (lx, 76)], fill=(110, 104, 122))
        for y in range(56, 76, 4):   # はしご
            d.line([(36, y), (40, y)], fill=(110, 104, 122))
        d.line([(36, 30), (36, 76)], fill=(110, 104, 122))
        d.line([(40, 30), (40, 76)], fill=(110, 104, 122))
        # 物干しロープ
        d.line([(80, 62), (152, 58)], fill=(90, 80, 96))
        # ベンチと鉢植え
        d.rectangle([130, 86, 154, 88], fill=(170, 120, 90))
        d.line([(132, 89), (132, 94)], fill=(110, 80, 60))
        d.line([(152, 89), (152, 94)], fill=(110, 80, 60))
        d.polygon([(114, 88), (122, 88), (121, 96), (115, 96)], fill=(200, 110, 80))
        d.ellipse([111, 79, 125, 89], fill=(90, 150, 100))
        d.point((115, 82), fill=(150, 200, 140))
        return im

    def animate(self, d, t, im):
        for wx, wy, r in self.windows:
            if (math.sin(t * 0.2 + r * 40) + r) > 0.9:
                d.rectangle([wx, wy, wx + 1, wy + 1], fill=(255, 220, 140))
        if int(t * 2) % 2:   # 電波塔のランプ
            d.rectangle([57, 8, 59, 10], fill=(255, 60, 60))
        # 洗濯物
        for i, (cx, col) in enumerate(((96, (250, 250, 246)), (116, (130, 190, 240)), (134, (250, 170, 190)))):
            sw = math.sin(t * 2 + i) * 2.4
            y0 = 62 - (cx - 80) * 4 // 72
            d.polygon([(cx - 6, y0), (cx + 6, y0), (cx + 6 + sw, y0 + 12), (cx - 6 + sw, y0 + 12)], fill=col)
            d.line([(cx - 6, y0), (cx + 6, y0)], fill=mix(col, INK, 0.3))
            d.point((cx - 3, y0), fill=(200, 160, 120))
            d.point((cx + 3, y0), fill=(200, 160, 120))
        # 鳥
        bx = (t * 12) % (IW + 80) - 40
        for k, (ox, oy) in enumerate(((0, 0), (10, 4), (-8, 6))):
            x, y = bx + ox, 16 + oy + math.sin(t * 3 + k) * 1.2
            flap = int(t * 6 + k) % 2
            d.line([(x - 3, y - 2 * flap), (x, y)], fill=(40, 30, 60))
            d.line([(x, y), (x + 3, y - 2 * flap)], fill=(40, 30, 60))


class Backrooms(Scene):
    name = "LEVEL 0"
    caption = "一方その頃、どこかの黄色い廊下では…"
    hour = None
    BACK = (64, 40, 96, 66)

    def build(self):
        im = Image.new("RGB", (IW, IH))
        d = ImageDraw.Draw(im)
        bx0, by0, bx1, by1 = self.BACK
        ceil, wall, wall2, floor = (214, 206, 150), (206, 190, 104), (190, 176, 96), (164, 146, 92)
        d.polygon([(0, 0), (IW - 1, 0), (bx1, by0), (bx0, by0)], fill=ceil)
        d.polygon([(0, 0), (bx0, by0), (bx0, by1), (0, IH - 1)], fill=wall)
        d.polygon([(IW - 1, 0), (bx1, by0), (bx1, by1), (IW - 1, IH - 1)], fill=wall2)
        d.polygon([(0, IH - 1), (bx0, by1), (bx1, by1), (IW - 1, IH - 1)], fill=floor)
        d.rectangle([bx0, by0, bx1, by1], fill=(196, 182, 100))
        d.rectangle([75, 50, 85, 66], fill=(70, 60, 34))       # 奥の出入り口
        d.line([(75, 50), (85, 50)], fill=(120, 106, 60))

        def lerp(a, b, k):
            return a + (b - a) * k
        # 天井の格子（奥へ向かう線と、横の線）
        for i in range(-4, 5):
            x_near = IW / 2 + i * 22
            x_far = lerp(bx0, bx1, (i + 4) / 8)
            d.line([(x_near, 0), (x_far, by0)], fill=mix(ceil, (150, 140, 90), 0.4))
        for k in (0.12, 0.3, 0.5, 0.68, 0.84):
            y = by0 * k
            d.line([(lerp(0, bx0, k), y), (lerp(IW - 1, bx1, k), y)], fill=mix(ceil, (150, 140, 90), 0.4))
        # 壁紙の縦じまと、小さな模様
        for i in range(1, 17):
            k = i / 17
            for side, base in ((0, wall), (1, wall2)):
                x = lerp(0, bx0, k) if side == 0 else lerp(IW - 1, bx1, k)
                y0 = lerp(0, by0, k)
                y1 = lerp(IH - 1, by1, k)
                d.line([(x, y0 + 1), (x, y1 - 1)], fill=mix(base, (150, 130, 60), 0.22))
                if i % 2 and k < 0.7:
                    for yy in range(int(y0) + 4, int(y1) - 2, 7):
                        d.point((x + (2 if side == 0 else -2), yy), fill=mix(base, (240, 230, 160), 0.4))
        # 横の出入り口
        for side, k0 in ((0, 0.42), (1, 0.58)):
            k1 = k0 + 0.16
            xa = lerp(0, bx0, k0) if side == 0 else lerp(IW - 1, bx1, k0)
            xb = lerp(0, bx0, k1) if side == 0 else lerp(IW - 1, bx1, k1)
            d.polygon([(xa, lerp(0, by0, k0) + 10), (xb, lerp(0, by0, k1) + 8),
                       (xb, lerp(IH - 1, by1, k1)), (xa, lerp(IH - 1, by1, k0))], fill=(96, 84, 44))
        # 幅木
        d.line([(0, IH - 2), (bx0, by1)], fill=(140, 120, 60))
        d.line([(IW - 1, IH - 2), (bx1, by1)], fill=(140, 120, 60))
        # カーペット（湿ったしみと毛羽立ち）
        px = im.load()
        for _ in range(900):
            x, y = self.rnd.randrange(IW), self.rnd.randrange(by1 + 1, IH)
            if px[x, y] == floor:
                px[x, y] = mix(floor, (120, 104, 60), self.rnd.random() * 0.5)
        for cx, cy, r in ((40, 92, 7), (118, 84, 5), (88, 98, 4)):
            d.ellipse([cx - r * 2, cy - r, cx + r * 2, cy + r], fill=mix(floor, (110, 96, 56), 0.35))
        return im

    def animate(self, d, t, im):
        bx0, by0, bx1, by1 = self.BACK
        tick = int(t * 10)
        for i, k in enumerate((0.12, 0.34, 0.56, 0.76, 0.9)):
            # 天井の蛍光灯（奥へ行くほど小さく）
            y = by0 * k + 1
            half = (80 - (80 - (bx1 - bx0) / 2) * k) * 0.34
            off = (tick + i * 7) % 97 < 2 or (i == 2 and (tick % 53) < 4 and (tick // 53) % 3 == 0)
            col = (255, 252, 230) if not off else (190, 180, 130)
            thick = 3 if k < 0.3 else 2 if k < 0.6 else 1
            d.rectangle([80 - half, y, 80 + half, y + thick - 1], fill=col)
            if not off and k < 0.6:
                d.line([(80 - half - 1, y + thick), (80 + half + 1, y + thick)], fill=mix(col, (214, 206, 150), 0.6))
        # 全体がふっと暗くなる
        if tick % 211 < 2:
            dark = Image.new("RGB", (IW, IH), (40, 36, 10))
            im.paste(Image.blend(im, dark, 0.35))
        # ほこり
        for k in range(10):
            x = (k * 17 + t * 3) % IW
            y = (k * 11 + math.sin(t * 0.7 + k) * 6 + t * 1.2) % IH
            d.point((x, y), fill=(240, 236, 200))


class BallPool(Scene):
    name = "PLAYROOM"
    caption = "一方その頃、閉園後のボールプールでは…"
    hour = 20
    COLORS = [(240, 80, 90), (250, 200, 60), (80, 170, 240), (110, 210, 120), (240, 140, 200)]

    def build(self):
        im = Image.new("RGB", (IW, IH))
        d = ImageDraw.Draw(im)
        dither_gradient(d, 0, 0, IW - 1, 64, (200, 214, 238), (236, 232, 246), steps=5)
        # 壁の絵（雲と星と虹）
        for cx, cy in ((26, 16), (118, 24)):
            for dx, r in ((0, 6), (7, 8), (15, 6)):
                d.ellipse([cx + dx - r, cy - r, cx + dx + r, cy + r], fill=(250, 250, 255))
            d.line([(cx - 4, cy + 5), (cx + 19, cy + 5)], fill=(226, 230, 246))
        for k, c in enumerate([(240, 120, 130), (250, 200, 110), (140, 210, 150), (130, 170, 240)]):
            d.arc([56 + k * 2, 10 + k * 2, 100 - k * 2, 54 - k * 2], 180, 360, fill=c, width=2)
        for sx, sy in ((48, 8), (92, 32), (14, 36), (146, 8), (138, 44)):
            px_pattern(d, sx, sy, "..#..|.###.|#####|.###.|.#.#.", (250, 220, 100))
        d.line([(0, 64), (IW - 1, 64)], fill=(170, 180, 210))
        # 床のマット
        mats = [(120, 200, 180), (250, 170, 120), (140, 170, 240)]
        for x in range(0, IW, 20):
            c = mats[(x // 20) % 3]
            d.rectangle([x, 65, x + 19, IH - 1], fill=c)
            d.line([(x, 65), (x + 19, 65)], fill=mix(c, (255, 255, 255), 0.35))
            d.line([(x + 19, 65), (x + 19, IH - 1)], fill=mix(c, INK, 0.2))
        # すべり台
        d.rectangle([124, 28, 132, 82], fill=(110, 170, 230), outline=(70, 120, 180))
        for y in range(32, 82, 6):
            d.line([(124, y), (132, y)], fill=(80, 130, 190))
        d.polygon([(132, 28), (142, 28), (158, 80), (148, 82)], fill=(250, 200, 70), outline=(200, 150, 40))
        d.line([(135, 30), (151, 78)], fill=(255, 230, 140))
        # ボールプール
        d.rectangle([12, 46, 116, 88], fill=(240, 236, 244))
        self.balls = []
        for y in range(50, 82, 4):
            for x in range(16, 114, 4):
                if self.rnd.random() < 0.95:
                    c = self.rnd.choice(self.COLORS)
                    xx, yy = x + self.rnd.randint(-1, 1), y + self.rnd.randint(-1, 0)
                    d.ellipse([xx - 2, yy - 2, xx + 2, yy + 2], fill=c, outline=mix(c, INK, 0.3))
                    d.point((xx - 1, yy - 1), fill=mix(c, (255, 255, 255), 0.6))
        d.rectangle([10, 44, 118, 90], outline=(90, 160, 220), width=2)
        d.line([(10, 44), (118, 44)], fill=(150, 200, 240))
        for x in range(12, 118, 5):   # 手前のネット
            d.line([(x, 66), (x, 88)], fill=(200, 220, 240))
        d.line([(10, 66), (118, 66)], fill=(90, 160, 220))
        # 閉園後なので、少しうす暗く
        im.paste(Image.blend(im, Image.new("RGB", im.size, (40, 40, 90)), 0.18))
        return im

    def animate(self, d, t, im):
        # ガーランド
        d.line([(2, 20), (110, 20)], fill=(150, 140, 170))
        for i in range(13):
            x = 4 + i * 8
            y = 20 + math.sin(t * 1.5 + i) * 0.8
            d.polygon([(x, y), (x + 6, y), (x + 3, y + 6)], fill=self.COLORS[i % 5])
        # ときどき1個だけ跳ねるボール
        cyc = t % 7
        if cyc < 1.4:
            k = cyc / 1.4
            x = 40 + int(t // 7) * 22 % 68
            y = 52 - math.sin(k * math.pi) * 24
            c = self.COLORS[int(t // 7) % 5]
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=c, outline=mix(c, INK, 0.3))
            d.point((x - 1, y - 1), fill=mix(c, (255, 255, 255), 0.6))


class Meadow(Scene):
    name = "MEADOW"
    caption = "一方その頃、どこまでも続く丘の上では…"
    hour = 12
    sky = (0, 0, IW - 1, IH - 1)

    def build(self):
        im = Image.new("RGB", (IW, IH))
        d = ImageDraw.Draw(im)
        dither_gradient(d, 0, 0, IW - 1, IH - 1, (40, 110, 220), (190, 222, 252))
        glow(im, (104, -30, 188, 54), (255, 250, 220), 90)   # 太陽のあかり
        d = ImageDraw.Draw(im)
        d.ellipse([140, 6, 152, 18], fill=(255, 250, 220))
        for x in range(IW):   # 遠くの山
            y = int(54 + 6 * math.sin(x / 23 + 2) + 3 * math.sin(x / 9))
            d.line([(x, y), (x, IH - 1)], fill=(150, 180, 222))
            d.point((x, y), fill=(196, 214, 240))
        self.hill = []
        for x in range(IW):
            hy = int(56 + 12 * math.sin((x + 20) / 52) + 4 * math.sin(x / 18))
            self.hill.append(hy)
            for y in range(hy, IH):
                depth = (y - hy) / (IH - hy + 1)
                d.point((x, y), fill=mix((120, 206, 70), (44, 136, 44), depth))
            d.point((x, hy), fill=(170, 230, 110))
        for _ in range(60):   # 小さな花
            x = self.rnd.randrange(IW)
            y = self.rnd.randint(self.hill[x] + 3, IH - 1)
            d.point((x, y), fill=self.rnd.choice([(255, 255, 255), (255, 230, 110), (250, 170, 200)]))
        # 丘の上の木
        tx = 116
        ty = self.hill[tx]
        d.rectangle([tx - 1, ty - 10, tx + 1, ty + 1], fill=(120, 90, 60))
        for dx, dy, r, c in ((0, -16, 9, (60, 140, 60)), (-6, -12, 6, (70, 150, 66)), (6, -12, 6, (54, 130, 56)),
                             (-2, -19, 5, (110, 190, 90))):
            d.ellipse([tx + dx - r, ty + dy - r, tx + dx + r, ty + dy + r], fill=c)
        d.ellipse([tx - 10, ty - 1, tx + 10, ty + 2], fill=(70, 150, 60))
        return im

    def animate(self, d, t, im):
        # 雲（白に、うすい青のかげ）
        for k, (y, r, sp) in enumerate(((16, 8, 2.0), (28, 6, 1.2), (10, 6, 1.6))):
            x = (k * 62 + t * sp) % (IW + 60) - 30
            for dx, rr in ((0, r), (r, r + 2), (r * 2, r)):
                d.ellipse([x + dx - rr, y - rr + 2, x + dx + rr, y + rr - 2], fill=(250, 252, 255))
            d.line([(x - r + 2, y + r - 3), (x + r * 3 - 2, y + r - 3)], fill=(210, 226, 246))
        # 風の波
        for x in range(IW):
            hy = self.hill[x]
            for y in range(hy + 1, IH, 2):
                if math.sin(x * 0.12 - t * 2.2 + y * 0.2) > 0.9:
                    d.point((x, y), fill=mix(im.getpixel((x, y)), (200, 245, 140), 0.5))


class Vapor(Scene):
    name = "VAPOR"
    caption = "一方その頃、終わらない夕焼けの向こうでは…"
    hour = None
    HY = 60                     # 水平線
    SUN = (80, 52, 27)          # 太陽のまんなかと半径
    GRID = (255, 40, 170)       # マゼンタの格子

    def build(self):
        im = Image.new("RGB", (IW, IH))
        d = ImageDraw.Draw(im)
        hy = self.HY
        # 空：黒 → 夜の青 → 水平線ぎわのマゼンタ
        dither_gradient(d, 0, 0, IW - 1, 30, (6, 2, 20), (30, 22, 96), steps=5)
        dither_gradient(d, 0, 31, IW - 1, hy - 1, (30, 22, 96), (196, 36, 140), steps=6)
        self.stars = [(self.rnd.randrange(IW), self.rnd.randint(1, 30), self.rnd.random()) for _ in range(34)]
        for x, y, r in self.stars:
            d.point((x, y), fill=mix((120, 120, 220), (255, 255, 255), r))
        glow(im, (20, hy - 46, 140, hy + 16), (255, 60, 160), 60)   # 太陽の後ろのぼんやりした光
        # 太陽（グラデーションだけ先に作っておく。横すじは動きの中で切る）
        cx, cy, r = self.SUN
        self.sun = Image.new("RGB", (r * 2 + 1, r * 2 + 1))
        sd = ImageDraw.Draw(self.sun)
        self.sun_vis = hy - (cy - r)   # 水平線から上に見えている高さ
        half = self.sun_vis // 2
        dither_gradient(sd, 0, 0, r * 2, half, (255, 244, 120), (255, 150, 50), steps=4)        # 黄 → オレンジ
        dither_gradient(sd, 0, half + 1, r * 2, r * 2, (255, 150, 50), (255, 40, 150), steps=4)  # オレンジ → マゼンタ
        # 地面：黒。奥へ集まる縦の線は止まったまま
        d.rectangle([0, hy + 1, IW - 1, IH - 1], fill=(8, 2, 18))
        for i in range(-14, 15):
            xb = IW / 2 + i * 16
            d.line([(IW / 2 + i * 1.2, hy + 1), (xb, IH - 1)], fill=mix(self.GRID, (8, 2, 18), 0.25))
        dither_gradient(d, 0, hy + 1, IW - 1, hy + 9, (120, 20, 110), (8, 2, 18), steps=4)   # 地平のもや
        for i in range(-14, 15):   # もやの上から、うすく縦線をもう一度
            xb = IW / 2 + i * 16
            for y in range(hy + 1, hy + 10):
                k = (y - hy) / (IH - 1 - hy)
                d.point((IW / 2 + i * 1.2 + (xb - IW / 2 - i * 1.2) * k, y), fill=(200, 40, 150))
        # 山（手前に重ねる絵。青い面にシアンの線で、ワイヤーフレーム風）
        self.mountains = Image.new("RGBA", (IW, IH), (0, 0, 0, 0))
        md = ImageDraw.Draw(self.mountains)
        for x0, x1, peaks in ((-6, 58, ((10, 18), (30, 11), (46, 20))), (102, 166, ((116, 21), (134, 13), (152, 17)))):
            pts = [(x0, hy)] + [(px, hy - h) for px, h in peaks] + [(x1, hy)]
            md.polygon(pts, fill=(22, 16, 74, 255))
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                md.line([(ax, ay), (bx, by)], fill=(70, 220, 255, 255))
            for px, h in peaks:   # 峰から裾へのすじ
                for fx in (px - h * 0.9, px - h * 0.3, px + h * 0.4, px + h * 0.9):
                    md.line([(px, hy - h), (fx, hy)], fill=(50, 90, 210, 255))
                md.line([(px, hy - h), (px, hy)], fill=(70, 220, 255, 160))
        md.line([(0, hy), (IW - 1, hy)], fill=(255, 120, 200, 255))   # 光る水平線
        return im

    def palm(self, d, bx, by, height, lean, sway, scale=1.0):
        """ヤシの木のシルエット。幹は少し曲がり、葉は風でゆれる。ふちだけ夕日の色。"""
        dark, bark, rim = (16, 4, 34), (40, 12, 70), (255, 80, 180)
        lit = 1 if lean < 0 else -1   # 太陽のある側（まんなか寄り）
        n = int(height)
        top = (bx, by)
        for s in range(n):   # 幹（根もとは太く、上は細く）
            k = s / n
            x = bx + lean * k * k * height
            y = by - s
            w = (4 - 2 * k) * scale
            d.line([(x - w / 2, y), (x + w / 2, y)], fill=bark if s % 4 else dark)   # 4段ごとにふし
            d.point((x + w / 2 * lit, y), fill=rim if s % 4 else mix(rim, dark, 0.5))
            top = (x, y)
        cx, cy = top
        # 葉：上へ伸びてから、先が垂れる。羽根のように両側へ小さな葉
        for a, ln, droop in ((172, 30, 0.6), (148, 26, 0.5), (118, 18, 0.35), (62, 18, 0.35), (32, 26, 0.5),
                             (8, 30, 0.6), (200, 18, 0.3), (-20, 18, 0.3)):
            ln *= scale
            rad = math.radians(a + sway * (1 if a < 90 else -1))
            pts = []
            for s in range(int(ln) + 1):
                k = s / ln
                pts.append((cx + math.cos(rad) * s, cy - math.sin(rad) * s + k * k * ln * droop))
            for i in range(1, len(pts)):
                k = i / len(pts)
                (x0, y0), (x, y) = pts[i - 1], pts[i]
                d.line([(x0, y0), (x, y)], fill=dark, width=2 if k < 0.6 else 1)
                if i % 2 == 0 and 0.15 < k < 0.95:
                    leaf = (1 - abs(k - 0.5) * 1.6) * 3.5 * scale   # まんなかの葉がいちばん長い
                    d.line([(x, y), (x - leaf * 0.5, y + leaf)], fill=dark)
                    d.line([(x, y), (x + leaf * 0.5, y + leaf)], fill=dark)
                if i % 2 == 1:
                    d.point((x, y - 1), fill=mix(rim, dark, 0.3))   # 葉の背に夕日
        d.ellipse([cx - 2, cy - 1, cx + 2, cy + 2], fill=dark)

    def animate(self, d, t, im):
        hy = self.HY
        # 星のまたたき
        for i, (x, y, r) in enumerate(self.stars):
            if math.sin(t * (1 + r * 2) + i) > 0.85:
                d.point((x, y), fill=(255, 255, 255))
                if r > 0.7:
                    for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        d.point((x + ox, y + oy), fill=(150, 140, 230))
        # 太陽：下半分の横すじが、ゆっくり下へ流れて沈んでいく
        cx, cy, r = self.SUN
        mask = Image.new("L", self.sun.size, 0)
        m = ImageDraw.Draw(mask)
        m.ellipse([0, 0, r * 2, r * 2], fill=255)
        vis = self.sun_vis
        start = vis * 0.42
        y = start + (t * 2.2) % 5
        while y < vis:
            gap = 1 + (y - start) / (vis - start) * 3   # 下ほど太いすじ
            m.rectangle([0, int(y), r * 2, int(y + gap) - 1], fill=0)
            y += 5
        m.rectangle([0, vis + 1, r * 2, r * 2], fill=0)   # 水平線より下は見せない
        im.paste(self.sun, (cx - r, cy - r), mask)
        im.paste(self.mountains, (0, 0), self.mountains)
        d = ImageDraw.Draw(im)
        # 地面の横線：手前へ流れてくる
        phase = (t * 1.6) % 1
        for k in range(14):
            z = k + 1 - phase
            y = hy + 43 / z
            if y > IH - 1 or y < hy + 1:
                continue
            near = min(1, 4 / z)
            d.line([(0, y), (IW - 1, y)], fill=mix((90, 10, 90), self.GRID, near))
        # 水平線のすぐ下に、太陽のうつりこみ
        for i, (w, yy) in enumerate(((18, hy + 2), (12, hy + 4), (7, hy + 7))):
            jit = math.sin(t * 3 + i * 2) * 2
            d.line([(cx - w + jit, yy), (cx + w + jit, yy)], fill=(255, 170, 80) if i == 0 else (255, 90, 160))
        # ヤシの木
        sway = math.sin(t * 0.9) * 4
        self.palm(d, 20, IH + 2, 64, 0.16, sway)
        self.palm(d, 140, IH + 2, 54, -0.14, -sway * 0.8)
        self.palm(d, 124, IH + 2, 34, -0.08, -sway * 0.6, scale=0.7)


SCENES = [Diner, Rooftop, Backrooms, BallPool, Meadow, Vapor]
SCENE_NAMES = ["深夜のダイナー", "夕暮れの屋上", "バックルームズ", "閉園後のボールプール", "青空の丘", "終わらない夕焼け"]

_SCAN = Image.new("L", (IW, IH), 0)   # 走査線：1行おきに少し暗く
for _y in range(0, IH, 2):
    ImageDraw.Draw(_SCAN).line([(0, _y), (IW - 1, _y)], fill=255)


def cam_overlay(im, scene_index, scene, t):
    im.paste(im.point(lambda v: max(0, v - 12)), (0, 0), _SCAN)
    d = ImageDraw.Draw(im)
    label = f"CAM 0{scene_index + 1}"
    px_text(d, 6, 6, label, (20, 20, 20), 2)
    px_text(d, 4, 4, label, (250, 250, 250), 2)
    if int(t * 2) % 2:
        d.ellipse([IW - 37, 4, IW - 30, 11], fill=(250, 50, 50))
    px_text(d, IW - 26, 4, "REC", (250, 250, 250), 2)
    lt = time.localtime()
    if scene.hour is None:
        stamp = "??:??:??"
    else:
        stamp = f"{scene.hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d}"
    px_text(d, IW - px_text_w(stamp, 2) - 2, IH - 12, stamp, (20, 20, 20), 2)
    px_text(d, IW - px_text_w(stamp, 2) - 4, IH - 14, stamp, (250, 250, 250), 2)
    return im


# ---------- 窓 ----------

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
    px_pattern(d, 4, 4, _ICONS["cam"], k["out"])
    px_text(d, 14, 5, "MEANWHILE.EXE", k["out"])
    bx0 = W - 3 - 3 * 9
    for i, icon in enumerate(("min", "max", "close")):
        x0 = bx0 + i * 9
        d.rectangle([x0, 3, x0 + 7, 10], fill=k["hover"] if icon == "close" else k["face"], outline=k["out"])
        px_pattern(d, x0 + 1, 4, _ICONS[icon], k["out"])
    d.line([(1, 12), (W - 2, 12)], fill=k["out"])
    d.rectangle([SX - 1, SY - 1, SX + SW, SY + SH], outline=k["out"])
    d.rectangle([SX, CAP_Y - 1, SX + SW - 1, CAP_Y + 9], fill=k["light"], outline=k["out"])
    return im


def render_button(icon, text, width, hover=False, lit=False):
    k = PAL
    iw = len(_ICONS[icon].split("|")[0])
    w, h = width, 11
    fill = k["hover"] if (hover or lit) else k["face"]
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


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_PATH, {}))
    cfg["scene"] = cfg["scene"] % len(SCENES)
    return cfg


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


class Meanwhile:
    def __init__(self):
        self.cfg = load_config()
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.p = Scale(self.cfg["scale"])
        self.scenes = [S() for S in SCENES]
        self.prev_frame = None
        self.fade = 0
        self.t0 = time.time()
        self.next_switch = time.time() + self.cfg["auto_min"] * 60
        self.pimgs = {}

        self.root = tk.Tk()
        log_errors(self.root, "meanwhile_error.txt")
        self.root.title(f"一方その頃 ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "meanwhile.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])
        self.frame_label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.screen = tk.Label(self.root, bd=0, highlightthickness=0)
        self.cap = tk.Label(self.root, anchor="w", bd=0)
        for w in (self.root, self.frame_label, self.screen, self.cap):
            w.bind("<ButtonPress-1>", self.drag_start)
            w.bind("<B1-Motion>", self.drag_move)
            w.bind("<ButtonRelease-1>", self.drag_end)
            w.bind("<Button-3>", self.popup_menu)
        self.frame_label.bind("<Motion>", self.frame_hover, add="+")
        self.frame_label.bind("<ButtonRelease-1>", self.frame_click, add="+")
        self.buttons = {}
        for key, action in (("prev", lambda: self.switch(-1)), ("next", lambda: self.switch(1)),
                            ("auto", self.toggle_auto), ("cam", self.toggle_cam)):
            lb = tk.Label(self.root, bd=0, highlightthickness=0, cursor="hand2")
            lb.bind("<Button-1>", lambda e, a=action: a())
            lb.bind("<Enter>", lambda e, k=key: self.draw_button(k, True))
            lb.bind("<Leave>", lambda e, k=key: self.draw_button(k, False))
            lb.bind("<Button-3>", self.popup_menu)
            self.buttons[key] = lb
        self.pmenu = PixelMenu(self.root, self.menu_theme, title="MEANWHILE - MENU")
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
        self.screen.place(x=SX * p, y=SY * p, width=SW * p, height=SH * p)
        self.cap.config(bg=hexc(self.col("light")), fg=hexc(self.col("out")),
                        font=ui_font(self.root, max(12, int(p * 5))))
        self.cap.place(x=(SX + 2) * p, y=CAP_Y * p, width=(SW - 4) * p, height=8 * p)
        for key, (x, w) in BUTTONS.items():
            self.draw_button(key)
            self.buttons[key].place(x=x * p, y=ROW * p)
        self.update_caption()

    def draw_button(self, key, hover=False):
        x, w = BUTTONS[key]
        icon, text, lit = {"prev": ("prev", "", False), "next": ("next", "", False),
                           "auto": ("auto", "AUTO", self.cfg["auto"]),
                           "cam": ("cam", "CAM", self.cfg["cam"])}[key]
        img = recolor(render_button(icon, text, w, hover, lit), self.cmap())
        img = ImageTk.PhotoImage(img.resize((w * self.p, 11 * self.p), Image.NEAREST))
        self.pimgs[key] = img
        self.buttons[key].config(image=img)

    def update_caption(self):
        self.cap.config(text=self.scenes[self.cfg["scene"]].caption)

    # --- 動き ---
    def current_frame(self, t):
        sc = self.scenes[self.cfg["scene"]]
        im = sc.frame(t, load_weather())
        if self.cfg["cam"]:
            im = cam_overlay(im, self.cfg["scene"], sc, t)
        return im

    def tick(self):
        t = time.time() - self.t0
        im = self.current_frame(t)
        if self.fade > 0 and self.prev_frame is not None:   # ふわっと切り替え
            im = Image.blend(im, self.prev_frame, self.fade / 10)
            self.fade -= 1
        self.photo = ImageTk.PhotoImage(im.resize((SW * self.p, SH * self.p), Image.NEAREST))
        self.screen.config(image=self.photo)
        if self.cfg["auto"] and time.time() >= self.next_switch:
            self.switch(1)
        self.root.after(1000 // FPS, self.tick)

    def switch(self, step, to=None):
        t = time.time() - self.t0
        self.prev_frame = self.current_frame(t)
        self.fade = 10
        self.cfg["scene"] = (self.cfg["scene"] + step) % len(SCENES) if to is None else to
        self.next_switch = time.time() + self.cfg["auto_min"] * 60
        save_config(self.cfg)
        self.update_caption()

    def toggle_auto(self):
        self.cfg["auto"] = not self.cfg["auto"]
        self.next_switch = time.time() + self.cfg["auto_min"] * 60
        save_config(self.cfg)
        self.draw_button("auto", True)

    def toggle_cam(self):
        self.cfg["cam"] = not self.cfg["cam"]
        save_config(self.cfg)
        self.draw_button("cam", True)

    # --- メニュー ---
    def menu_items(self):
        c = self.cfg
        return [
            {"type": "head", "label": "場所"},
            *[{"type": "radio", "label": n, "checked": c["scene"] == i, "cmd": lambda i=i: self.switch(0, i)}
              for i, n in enumerate(SCENE_NAMES)],
            {"type": "sep"},
            {"type": "check", "label": "自動で巡回", "checked": c["auto"], "cmd": self.toggle_auto},
            {"type": "sub", "label": "巡回の間隔", "right": f"{c['auto_min']}分",
             "items": [{"type": "radio", "label": n, "checked": c["auto_min"] == v,
                        "cmd": lambda v=v: self.set_auto_min(v)} for n, v in AUTO_MINS]},
            {"type": "check", "label": "CAM表示（REC・時刻）", "checked": c["cam"], "cmd": self.toggle_cam},
            {"type": "sep"},
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
            {"type": "head", "label": f"一方その頃 ver.{APP_VERSION}"},
        ]

    def popup_menu(self, e):
        self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

    def set_auto_min(self, v):
        self.cfg["auto_min"] = v
        self.next_switch = time.time() + v * 60
        save_config(self.cfg)

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
        save_config(self.cfg)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        Meanwhile().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "meanwhile_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
