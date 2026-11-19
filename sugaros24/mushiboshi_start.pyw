# -*- coding: utf-8 -*-
"""
SugarOS 24 ランチャー ver.1.12
SugarOS 24 のツールを起動する、タスクバー風のランチャー。
バーは START・MENU・時計だけのすっきりした形（ツールは MENU のメニュー画面から起動する）。
設定で「バーにツールのボタンを出す」をオンにすると、前のように「ピン留め」と「起動中」のツールも並ぶ。
起動するときは読み込み中の画面、終了するときは「GOOD NIGHT」の画面が出る（クリックでとばせる。設定でオフにもできる）。

操作:
  START          … スタートメニュー（系統ごとのツール / ぜんぶ起動 / ぜんぶ終了 / カラー / 設定 など）
  MENU           … メニュー画面（大きなアイコンが並ぶ。クリックで起動、右クリックで終了・ピン留め）
                   もう一度押すか、Esc・「とじる」で閉じる。デスクトップの「SugarOS メニュー」からも開ける
  ツールのボタン … 起動。起動中はへこんだ見た目になる。右クリックで終了・ピン留め
  ドラッグ       … 移動（浮かせて置いているとき）
  右クリック     … スタートメニュー

必要なもの: pip install pillow
このファイルを、ツールと同じフォルダに置いてね。
"""
import os
import random
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog

from PIL import Image, ImageDraw, ImageTk

from mushiboshi_ui import (COLORWAY_NAMES, BAYER4, load_weather, load_now_playing, log_errors, PixelMenu, colorway_full, colorway_theme, is_night_time,
                           load_colorway, load_time_settings, recolor, save_colorway, save_time_settings, mix,
                           px_text, px_text_w, load_json, save_json, hexc, ui_font, dither_bar)

APP_VERSION = "1.12"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "launcher_config.json")
DOCK_PATH = os.path.join(APP_DIR, "mushiboshi_dock.json")
MENU_REQUEST = os.path.join(APP_DIR, "mushiboshi_menu_request.json")   # sugar_menu.pyw が置く「メニューを開いて」の合図

TOOLS = [  # (key, メニューでの名前, バーでの名前, スクリプト, アイコン)
    ("photo", "資料フォトフレーム", "PHOTO FRAME", "photo_frame.pyw", "photo_frame.ico"),
    ("theater", "資料シアター", "THEATER", "video_theater.pyw", "video_theater.ico"),
    ("kotonoha", "資料ことのは", "KOTONOHA", "kotonoha.pyw", "kotonoha.ico"),
    ("record", "資料レコード", "RECORD", "record_player.pyw", "record_player.ico"),
    ("aqua", "ドット水槽", "AQUARIUM", "aquarium.pyw", "aquarium.ico"),
    ("green", "ドット温室", "GREENHOUSE", "greenhouse.pyw", "greenhouse.ico"),
    ("meanwhile", "一方その頃", "MEANWHILE", "meanwhile.pyw", "meanwhile.ico"),
    ("nozoki", "のぞき窓", "NOZOKI", "nozokimado.pyw", "nozokimado.ico"),
    ("girl", "エレクトロガール", "ELECTRO GIRL", "electro_girl.pyw", "electro_girl.ico"),
    ("mines", "ドットマインスイーパ", "MINES", "minesweeper.pyw", "minesweeper.ico"),
    ("cards", "ドットソリティア", "CARDS", "solitaire.pyw", "solitaire.ico"),
    ("sugar", "ドットシュガーフォール", "SUGAR", "sugarfall.pyw", "sugarfall.ico"),
    ("weather", "ドットお天気", "WEATHER", "weather.pyw", "weather.ico"),
    ("calendar", "ドットカレンダー", "CALENDAR", "dot_calendar.pyw", "calendar.ico"),
]

# START メニューでの系統（アイデア帳の分け方）
GROUPS = [("資料を流す", ["photo", "theater", "kotonoha", "record"]), ("眺める", ["aqua", "green", "meanwhile", "nozoki"]),
          ("住人", ["girl"]), ("遊ぶ", ["mines", "cards", "sugar"]), ("道具", ["weather", "calendar"])]

DEFAULT_CONFIG = {"dock": "float", "topmost": True, "x": 40, "y": 600, "show_clock_seconds": False, "show_tools": False, "show_splash": True,
                  "pinned": ["photo", "kotonoha", "record", "girl", "weather", "calendar"]}

P = 2                       # 1ドットの大きさ（px）
H = 22                      # バーの高さ（ドット）
START_W, TOOL_W, MENU_W = 38, 76, 34
MENU_ICON = ["pp.mm", "pp.mm", ".....", "bb.yy", "bb.yy"]   # MENU ボタンの、4つのタイルの絵

FACE, LIGHT, SOFT = (212, 212, 228), (255, 255, 255), (234, 234, 244)
SHADOW, DARK = (136, 136, 168), (44, 40, 72)
PINK, NAVY = (232, 72, 128), (40, 52, 120)

# カラーで塗り替える元の色（バーの地は帯の色を薄めたもの）
COLOR_BASE = {FACE: "bar", SOFT: "bar_soft", SHADOW: "bar_shadow", DARK: "out", NAVY: "out", PINK: "accent"}

MENU_THEME = dict(face=(236, 236, 246), out=DARK, light=LIGHT,
                  title=(64, 80, 168), title2=(96, 120, 200), title_text=LIGHT,
                  accent=PINK, sub=(130, 126, 160), text=DARK,
                  field=LIGHT, select=(64, 80, 168), select_text=LIGHT)
# オリジナルの夜の色は、この色から作る
MENU_BASE = {MENU_THEME["face"]: "face", DARK: "out", MENU_THEME["title"]: "title", MENU_THEME["title2"]: "title2",
             PINK: "accent"}


# --- メニュー画面（START で開く、大きなアイコンの画面） ---
HOME_NAMES = {"photo": "フォトフレーム", "theater": "シアター", "kotonoha": "ことのは", "record": "レコード",
              "aqua": "水槽", "green": "温室", "meanwhile": "一方その頃", "nozoki": "のぞき窓",
              "girl": "エレクトロガール", "mines": "マインスイーパ", "cards": "ソリティア",
              "sugar": "シュガーフォール", "weather": "お天気", "calendar": "カレンダー"}
GROUP_COLORS = {"資料を流す": (255, 200, 218), "眺める": (190, 234, 214), "住人": (255, 216, 176),
                "遊ぶ": (200, 212, 255), "道具": (250, 234, 164)}
HOME_COLS, TILE_W, TILE_H = 5, 62, 58
HOME_PAD, HOME_TILES_Y = 9, 50
HOME_BUTTONS = [("all", "ぜんぶ起動"), ("stopall", "ぜんぶ終了"), ("settings", "せってい"), ("close", "とじる")]


def pill(d, x0, y0, x1, y1, fill, outline):
    """角の丸い名札（ドットで角を落とす）。"""
    d.rectangle([x0 + 1, y0, x1 - 1, y1], fill=fill)
    d.rectangle([x0, y0 + 1, x1, y1 - 1], fill=fill)
    d.line([(x0 + 2, y0), (x1 - 2, y0)], fill=outline)
    d.line([(x0 + 2, y1), (x1 - 2, y1)], fill=outline)
    d.line([(x0, y0 + 2), (x0, y1 - 2)], fill=outline)
    d.line([(x1, y0 + 2), (x1, y1 - 2)], fill=outline)
    d.point([(x0 + 1, y0 + 1), (x1 - 1, y0 + 1), (x0 + 1, y1 - 1), (x1 - 1, y1 - 1)], fill=outline)


class HomeMenu:
    """一太郎スマイルみたいな、大きなアイコンが並ぶメニュー画面。"""

    def __init__(self, app):
        self.app = app
        self.hover = None
        self.regions = []
        self.keys = [k for _, keys in GROUPS for k in keys]
        self.group_of = {k: g for g, keys in GROUPS for k in keys}
        rows = (len(self.keys) + HOME_COLS - 1) // HOME_COLS
        self.W = HOME_PAD * 2 + HOME_COLS * TILE_W
        self.btn_y = HOME_TILES_Y + rows * TILE_H + 4
        self.H = self.btn_y + 18
        t = self.t = tk.Toplevel(app.root)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        self.canvas = c = tk.Canvas(t, width=self.W * P, height=self.H * P, highlightthickness=0, bd=0)
        c.pack()
        self.img_id = c.create_image(0, 0, anchor="nw")
        self.font = ui_font(app.root, 11, bold=True)
        self.small = ui_font(app.root, 10, bold=True)
        self.text_ids = {}
        for key in self.keys:
            self.text_ids[key] = c.create_text(0, 0, text=HOME_NAMES.get(key, key), font=self.font)
        for key, label in HOME_BUTTONS:
            self.text_ids[key] = c.create_text(0, 0, text=label, font=self.small)
        self.title_id = c.create_text(0, 0, anchor="w", text="SugarOS 24 メニュー", font=self.small)
        c.bind("<Motion>", self.on_motion)
        c.bind("<Leave>", lambda e: self.set_hover(None))
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Button-3>", self.on_right)
        t.bind("<Escape>", lambda e: self.close())
        left, top, right, bottom = work_area(app.root)
        x = left + (right - left - self.W * P) // 2
        y = top + max(0, (bottom - top - self.H * P) // 2 - 20)
        t.geometry(f"{self.W * P}x{self.H * P}+{x}+{y}")
        self.redraw()
        t.focus_force()

    def tile_pos(self, i):
        return HOME_PAD + (i % HOME_COLS) * TILE_W, HOME_TILES_Y + (i // HOME_COLS) * TILE_H

    def redraw(self):
        W, H, app = self.W, self.H, self.app
        cmap = app.cmap()
        col = lambda c: (cmap or {}).get(c, c)   # noqa: E731  文字の色も、バーと同じように着替える
        im = Image.new("RGB", (W, H), FACE)
        d = ImageDraw.Draw(im)
        for y in range(H):   # 地：うすい市松の網点
            for x in range(W):
                if BAYER4[y % 4][x % 4] < 3:
                    d.point((x, y), fill=SOFT)
        d.rectangle([0, 0, W - 1, H - 1], outline=DARK)
        d.line([(1, 1), (W - 2, 1)], fill=LIGHT)
        d.line([(1, 1), (1, H - 2)], fill=LIGHT)
        dither_bar(d, 2, 2, W - 3, 12, NAVY, (96, 120, 200))   # タイトルバー
        px_color(d, 4, 3, CHERRY)
        self.regions = []
        cx = W - 12   # とじるボタン（×）
        on = self.hover == "x"
        d.rectangle([cx, 3, cx + 8, 11], fill=PINK if on else FACE, outline=DARK)
        for k in range(5):
            d.point([(cx + 2 + k, 5 + k), (cx + 6 - k, 5 + k)], fill=LIGHT if on else DARK)
        self.regions.append(("x", cx, 3, cx + 8, 11))
        # 看板：しましまの帯に、大きな SUGAROS 24
        bx0, by0, bx1, by1 = HOME_PAD, 17, W - HOME_PAD - 1, 43
        d.rectangle([bx0, by0, bx1, by1], fill=PINK)
        for y in range(by0 + 2, by1 - 1, 3):
            d.line([(bx0 + 2, y), (bx1 - 2, y)], fill=mix(PINK, LIGHT, 0.35))
        d.rectangle([bx0, by0, bx1, by1], outline=DARK)
        text = "SUGAROS 24"
        tw = px_text_w(text, 3)
        tx = (W - tw) // 2
        px_text(d, tx + 2, 23, text, DARK, 3)
        px_text(d, tx, 21, text, LIGHT, 3)
        # ツールのタイル
        for i, key in enumerate(self.keys):
            x, y = self.tile_pos(i)
            running = app.running(key)
            exists = os.path.exists(os.path.join(APP_DIR, app.tools[key][3]))
            if self.hover == key and exists:
                down = getattr(self, "_pressing", False)
                d.rectangle([x + 3, y + 1, x + TILE_W - 4, y + TILE_H - 3], fill=LIGHT if not down else SOFT)
                bevel(d, x + 3, y + 1, x + TILE_W - 4, y + TILE_H - 3, raised=not down)
            icon = app.icons.get(key)
            if icon is not None:
                ix, iy = x + (TILE_W - 32) // 2, y + 4
                shadow = Image.new("RGBA", icon.size, DARK + (0,))
                shadow.putalpha(icon.getchannel("A").point(lambda a: 70 if a > 128 else 0))
                im.paste(shadow, (ix + 2, iy + 2), shadow)   # ふわっと浮いて見える影
                im.paste(icon, (ix, iy), icon)
            if running:   # 起動中のしるし
                d.rectangle([x + TILE_W - 15, y + 4, x + TILE_W - 10, y + 9], fill=PINK, outline=DARK)
            fill = PINK if running else GROUP_COLORS.get(self.group_of[key], LIGHT)
            pill(d, x + 5, y + 40, x + TILE_W - 6, y + 51, fill, DARK)
            c = self.canvas
            c.coords(self.text_ids[key], (x + TILE_W / 2) * P, (y + 46) * P)
            c.itemconfigure(self.text_ids[key], fill=hexc((255, 255, 255) if running else DARK if exists else SHADOW))   # 名札の地は着替えないので、文字も固定
            self.regions.append((key, x + 3, y + 1, x + TILE_W - 4, y + TILE_H - 3))
        # 下のボタン
        d.line([(HOME_PAD, self.btn_y - 3), (W - HOME_PAD - 1, self.btn_y - 3)], fill=SHADOW)
        d.line([(HOME_PAD, self.btn_y - 2), (W - HOME_PAD - 1, self.btn_y - 2)], fill=LIGHT)
        bw = 50
        xs = [HOME_PAD, HOME_PAD + bw + 4, W - HOME_PAD - 2 * bw - 5, W - HOME_PAD - bw - 1]
        for (key, _label), x in zip(HOME_BUTTONS, xs):
            y0, y1 = self.btn_y + 2, self.btn_y + 13
            on = self.hover == key
            enabled = key != "stopall" or any(app.running(k) for k in self.keys)
            pill(d, x, y0, x + bw, y1, (NAVY if on else FACE) if enabled else SOFT, DARK)
            d.ellipse([x + 3, y0 + 3, x + 8, y0 + 8], fill=PINK if key != "close" else LIGHT, outline=DARK)
            self.canvas.coords(self.text_ids[key], (x + bw / 2 + 4) * P, (y0 + y1 + 1) / 2 * P)
            self.canvas.itemconfigure(self.text_ids[key],
                                      fill=hexc(col(LIGHT) if on else col(DARK) if enabled else SHADOW))
            self.regions.append((key, x, y0, x + bw, y1))
        self.canvas.coords(self.title_id, 16 * P, 7.5 * P)
        self.canvas.itemconfigure(self.title_id, fill=hexc(col(LIGHT)))
        im = recolor(im, cmap)
        self.photo = ImageTk.PhotoImage(im.resize((W * P, H * P), Image.NEAREST))
        self.canvas.itemconfigure(self.img_id, image=self.photo)

    def region_at(self, e):
        x, y = e.x / P, e.y / P
        for name, x0, y0, x1, y1 in self.regions:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return name
        return None

    def set_hover(self, name):
        if name != self.hover:
            self.hover = name
            self.canvas.configure(cursor="hand2" if name else "")
            self.redraw()

    def on_motion(self, e):
        self.set_hover(self.region_at(e))

    def on_press(self, e):
        self._pressing = True
        self._press = (e.x_root, e.y_root, self.t.winfo_x(), self.t.winfo_y())
        self._drag = self.region_at(e) is None and e.y / P < 14   # タイトルバーをつかむと動かせる
        self.redraw()

    def on_drag(self, e):
        if getattr(self, "_drag", False):
            px, py, wx, wy = self._press
            self.t.geometry(f"+{wx + e.x_root - px}+{wy + e.y_root - py}")

    def on_release(self, e):
        if not getattr(self, "_pressing", False):
            return
        self._pressing = False
        name = self.region_at(e)
        self.redraw()
        if getattr(self, "_drag", False) or name is None:
            return
        app = self.app
        if name in ("x", "close"):
            self.close()
        elif name == "all":
            app.launch_all()
        elif name == "stopall":
            app.stop_all()
        elif name == "settings":
            app.menu.title = "SUGAROS 24"
            app.menu.popup(app.start_items, e.x_root, e.y_root)
        else:
            app.launch(name)
            self.t.after(300, self.redraw)

    def on_right(self, e):
        name = self.region_at(e)
        if name in self.app.tools:
            self.app.tool_menu(name, e.x_root, e.y_root, above=False)

    def close(self):
        self.app.menu.close_all()
        self.t.destroy()
        self.app.home = None
        self.app.redraw()


# --- 起動と終了の画面 ---
SPLASH_W, SPLASH_H = 156, 86
BOOT_STEPS = ["時計をあわせてるよ…", "色をえらんでるよ…", "ツールをならべてるよ…", "できたよ！"]
NIGHT_STEPS = ["ツールをかたづけてるよ…", "あかりを消してるよ…", "おつかれさま！"]
NIGHT_BG, NIGHT_BG2, NIGHT_OUT = (30, 32, 70), (44, 44, 92), (12, 12, 32)
NIGHT_LIGHT, NIGHT_TEXT, NIGHT_SUB = (96, 94, 160), (255, 236, 170), (176, 174, 226)
NIGHT_PANEL = (16, 18, 46)


def greeting():
    h = time.localtime().tm_hour
    if 5 <= h < 11:
        return "おはよう！"
    if 11 <= h < 17:
        return "こんにちは！"
    return "こんばんは！"


class Splash:
    """ランチャーの起動画面（boot）と、終了するときのおやすみ画面（night）。クリックでとばせる。"""

    def __init__(self, app, mode, on_done, length=1.8):
        self.app, self.mode, self.on_done, self.length = app, mode, on_done, length
        self.night = mode == "night"
        self.start = time.time()
        self.ending = False
        self.W, self.H = SPLASH_W, SPLASH_H
        rnd = random.Random(24)
        self.stars = [(rnd.randrange(10, self.W - 26), rnd.randrange(19, 45), rnd.random()) for _ in range(22)]
        t = self.t = tk.Toplevel(app.root)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        self.canvas = c = tk.Canvas(t, width=self.W * P, height=self.H * P, highlightthickness=0, bd=0, cursor="hand2")
        c.pack()
        self.img_id = c.create_image(0, 0, anchor="nw")
        big, small = ui_font(app.root, 12, bold=True), ui_font(app.root, 10, bold=True)
        title = "SugarOS 24 おやすみ" if self.night else "SugarOS 24 きどう中"
        self.title_id = c.create_text(17 * P, 7.5 * P, anchor="w", text=title, font=small)
        self.msg_id = c.create_text(self.W / 2 * P, 54 * P, font=big,
                                    text="おやすみなさい" if self.night else greeting())
        self.sub_id = c.create_text(self.W / 2 * P, 63.5 * P, font=small)
        c.bind("<ButtonRelease-1>", lambda e: self.finish())
        left, top, right, bottom = work_area(app.root)
        x = left + (right - left - self.W * P) // 2
        y = top + (bottom - top - self.H * P) // 2 - 20
        t.geometry(f"{self.W * P}x{self.H * P}+{x}+{y}")
        self.step()

    def colors(self):
        if self.night:
            return NIGHT_BG, NIGHT_BG2, NIGHT_OUT, NIGHT_LIGHT
        return FACE, SOFT, DARK, LIGHT

    def draw(self, p):
        W, H = self.W, self.H
        bg, bg2, out, light = self.colors()
        im = Image.new("RGB", (W, H), bg)
        d = ImageDraw.Draw(im)
        for y in range(H):   # 地：うすい網点
            for x in range(W):
                if BAYER4[y % 4][x % 4] < 3:
                    d.point((x, y), fill=bg2)
        d.rectangle([0, 0, W - 1, H - 1], outline=out)
        d.line([(1, 1), (W - 2, 1)], fill=light)
        d.line([(1, 1), (1, H - 2)], fill=light)
        bx0, by0, bx1, by1 = 8, 17, W - 9, 46
        now = time.time() - self.start
        if self.night:
            dither_bar(d, 2, 2, W - 3, 12, (20, 20, 52), (74, 68, 140))
            px_color(d, 5, 4, TRAY["moon"])
            d.rectangle([bx0, by0, bx1, by1], fill=NIGHT_PANEL, outline=out)
            for sx, sy, ph in self.stars:   # 星がちかちか
                v = (ph + now * 1.3) % 1
                if v < 0.75:
                    d.point((sx, sy), fill=mix(NIGHT_PANEL, NIGHT_TEXT, 0.3 + 0.7 * abs(0.375 - v) / 0.375))
                if v < 0.15:
                    d.point([(sx - 1, sy), (sx + 1, sy), (sx, sy - 1), (sx, sy + 1)], fill=(110, 108, 170))
            mx, my = bx1 - 14, by0 + 4   # 三日月
            d.ellipse([mx, my, mx + 10, my + 10], fill=NIGHT_TEXT)
            d.ellipse([mx + 4, my - 2, mx + 13, my + 8], fill=NIGHT_PANEL)
            text, tx = "GOOD NIGHT", bx0 + 6
            px_text(d, tx + 1, 30, text, (0, 0, 0), 3)
            px_text(d, tx, 29, text, NIGHT_TEXT, 3)
        else:
            dither_bar(d, 2, 2, W - 3, 12, NAVY, (96, 120, 200))
            px_color(d, 4, 3, CHERRY)
            d.rectangle([bx0, by0, bx1, by1], fill=PINK)
            for y in range(by0 + 2, by1 - 1, 3):
                d.line([(bx0 + 2, y), (bx1 - 2, y)], fill=mix(PINK, LIGHT, 0.35))
            k = int(now * 110) % (W + 60) - 20   # きらっと光が横切る
            for i in range(5):
                d.line([(k + i, by0 + 1), (k + i - 10, by1 - 1)], fill=mix(PINK, LIGHT, 0.6))
            d.rectangle([1, by0, bx0 - 1, by1], fill=bg)    # 帯からはみ出した光を消す
            d.rectangle([bx1 + 1, by0, W - 2, by1], fill=bg)
            d.rectangle([bx0, by0, bx1, by1], outline=DARK)
            text = "SUGAROS 24"
            tx = (W - px_text_w(text, 3)) // 2
            px_text(d, tx + 2, 26, text, DARK, 3)
            px_text(d, tx, 24, text, LIGHT, 3)
        # すすみぐあいのバー（起動はたまっていき、おやすみは減っていく）
        x0, y0, x1, y1 = 12, 71, W - 13, 79
        d.rectangle([x0, y0, x1, y1], fill=mix(bg, out, 0.25), outline=out)
        n = (x1 - x0 - 2) // 6
        lit = round(n * p)
        seg = NIGHT_TEXT if self.night else PINK
        pad = ((x1 - x0 - 2) - n * 6) // 2 + 1
        for i in (range(n - lit) if self.night else range(lit)):
            sx = x0 + 2 + pad + i * 6
            d.rectangle([sx, y0 + 2, sx + 4, y1 - 2], fill=seg)
            d.line([(sx, y0 + 2), (sx + 4, y0 + 2)], fill=mix(seg, LIGHT, 0.5))
        cmap = None if self.night else self.app.cmap()
        if cmap:
            im = recolor(im, cmap)
        self.photo = ImageTk.PhotoImage(im.resize((W * P, H * P), Image.NEAREST))
        c = self.canvas
        c.itemconfigure(self.img_id, image=self.photo)
        col = lambda c_: (cmap or {}).get(c_, c_)   # noqa: E731
        steps = NIGHT_STEPS if self.night else BOOT_STEPS
        c.itemconfigure(self.sub_id, text=steps[min(len(steps) - 1, int(p * (len(steps) - 1) + 0.0001))],
                        fill=hexc(NIGHT_SUB if self.night else col(SHADOW)))
        c.itemconfigure(self.msg_id, fill=hexc(NIGHT_TEXT if self.night else col(DARK)))
        c.itemconfigure(self.title_id, fill=hexc(NIGHT_SUB if self.night else col(LIGHT)))

    def step(self):
        if self.ending:
            return
        p = min(1.0, (time.time() - self.start) / self.length)
        self.draw(p)
        if p >= 1:
            self.t.after(500 if self.night else 300, self.finish)
            return
        self.t.after(40, self.step)

    def finish(self):
        if self.ending:
            return
        self.ending = True
        self.fade(1.0)

    def fade(self, a):
        a -= 0.12
        if a <= 0:
            self.t.destroy()
            self.on_done()
            return
        try:
            self.t.attributes("-alpha", a)
        except tk.TclError:
            pass
        self.t.after(30, lambda: self.fade(a))


def set_wallpaper(path):
    """Windows の壁紙を変える。少し時間がかかることがあるので、裏でやる。"""
    def work():
        try:
            import ctypes
            ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)   # 20=壁紙を変える、3=保存して全体に知らせる
        except (AttributeError, OSError):
            pass
    threading.Thread(target=work, daemon=True).start()


CHERRY = ["....ggg..", "...g.....", "..g.g....", ".g...g...",
          "rrr..rrr.", "rwrr.rwrr", "rrrr.rrrr", ".rr...rr."]
# トレイのアイコン（左から：天気、音楽、昼と夜）
TRAY = {
    "cherry": CHERRY,
    "clear": ["#.#.#..", ".yyy...", "#yyy#..", ".yyy...", "#.#.#.."],
    "partly": [".y.....", "yyycc..", ".ycccc.", "cccccc."],
    "cloudy": ["..cc...", ".cccc..", "cccccc.", ".cccc.."],
    "rain": ["..cc...", ".cccc..", "cccccc.", "b.b.b..", ".b.b..."],
    "thunder": ["..kk...", ".kkkk..", "kkkkkk.", "..y....", ".y....."],
    "snow": ["..cc...", ".cccc..", "cccccc.", "b..b...", "..b..b."],
    "fog": ["cccccc.", ".......", ".cccccc", ".......", "cccccc."],
    "note_on": ["..pp", "..p.", "..p.", "ppp.", "ppp."],
    "note_off": ["..ss", "..s.", "..s.", "sss.", "sss."],
    "sun": ["..y....", "y.y.y..", ".yyy...", "yyyyy..", ".yyy...", "y.y.y..", "..y...."],
    "moon": [".mmm...", "mm.....", "mm.....", "mm.....", ".mmm..."],
}
COLORS = {"g": (70, 150, 80), "P": (255, 160, 190), "M": (120, 210, 170), "B": (130, 160, 240), "Y": (240, 200, 90), "r": (220, 50, 70), "w": (255, 200, 210), "y": (240, 176, 50), "d": DARK,
          "#": (240, 176, 50), "c": (176, 186, 206), "k": (120, 128, 150), "b": (100, 150, 230),
          "m": (226, 196, 100), "p": PINK, "s": SHADOW}


def px_color(d, x, y, rows):
    for ry, row in enumerate(rows):
        for rx, c in enumerate(row):
            if c in COLORS:
                d.point((x + rx, y + ry), fill=COLORS[c])


def bevel(d, x0, y0, x1, y1, raised=True):
    tl, br = (LIGHT, DARK) if raised else (DARK, LIGHT)
    tl2, br2 = (SOFT, SHADOW) if raised else (SHADOW, SOFT)
    d.line([(x0, y1), (x0, y0), (x1, y0)], fill=tl)
    d.line([(x1, y0), (x1, y1), (x0, y1)], fill=br)
    d.line([(x0 + 1, y1 - 1), (x0 + 1, y0 + 1), (x1 - 1, y0 + 1)], fill=tl2)
    d.line([(x1 - 1, y0 + 1), (x1 - 1, y1 - 1), (x0 + 1, y1 - 1)], fill=br2)


def load_icon(path):
    """ツールの .ico から 32px の絵を取り出す。"""
    try:
        with Image.open(path) as im:
            if hasattr(im, "ico") and (32, 32) in im.ico.sizes():
                return im.ico.getimage((32, 32)).convert("RGBA")
            return im.convert("RGBA").resize((32, 32), Image.NEAREST)
    except (OSError, ValueError):
        return None


def work_area(root):
    """Windows のタスクバーを除いた画面の範囲。"""
    try:
        import ctypes
        from ctypes import wintypes
        r = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0):
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def pythonw():
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_PATH, {}))
    keys = [t[0] for t in TOOLS]
    cfg["pinned"] = [k for k in cfg["pinned"] if k in keys]   # 自分のリストにして、ないツールは外す
    return cfg


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


class Launcher:
    def __init__(self):
        self.cfg = load_config()
        self.procs = {}
        self.hover = None
        self.regions = []
        self.icons = {key: load_icon(os.path.join(APP_DIR, ico)) for key, _, _, _, ico in TOOLS}
        self.tools = {t[0]: t for t in TOOLS}
        self.home = None

        self.root = tk.Tk()
        log_errors(self.root, "launcher_error.txt")
        self.root.title(f"SugarOS 24 ランチャー ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "mushiboshi_start.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])
        self.label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.label.pack()
        self.label.bind("<Motion>", self.on_motion)
        self.label.bind("<Leave>", lambda e: self.set_hover(None))
        self.label.bind("<ButtonPress-1>", self.on_press)
        self.label.bind("<B1-Motion>", self.on_drag)
        self.label.bind("<ButtonRelease-1>", self.on_release)
        self.label.bind("<Button-3>", self.on_right)
        self.colorway = load_colorway()
        self.night = None   # 最初の tick で、今の昼夜に合わせた壁紙にする
        self.menu = PixelMenu(self.root, self.menu_theme, title="SUGAROS 24")
        self.place()
        self.tick()
        self.watch_menu_request()

    # --- 置き場所 ---
    def bar_width(self):
        if self.cfg["dock"] == "bottom":
            left, top, right, bottom = work_area(self.root)
            return (right - left) // P
        return 2 + START_W + 2 + MENU_W + 3 + 4 + len(self.bar_keys()) * (self.tool_w() + 2) + 6 + self.tray_width() + 3

    def bar_keys(self):
        """バーに並べるツール：ピン留めしたものと、起動中のもの（START メニューの並び順）。"""
        if not self.cfg.get("show_tools", False):   # メニュー画面ができたので、ふだんはツールのボタンを出さない
            return []
        pinned = set(self.cfg["pinned"])
        return [key for key, *_ in TOOLS if key in pinned or self.running(key)]

    def tool_w(self):
        """ツールのボタンの幅。並べるツールが多くて画面に入りきらないときは、そのぶん縮める。"""
        left, top, right, bottom = work_area(self.root)
        fixed = 2 + START_W + 2 + MENU_W + 3 + 4 + 6 + self.tray_width() + 3
        fit = ((right - left) // P - fixed) // max(1, len(self.bar_keys())) - 2
        return max(24, min(TOOL_W, fit))

    def tray_width(self):
        return 3 * 9 + 3 + px_text_w("00:00") + 6

    def place(self):
        w = self.bar_width()
        if self.cfg["dock"] == "bottom":
            left, top, right, bottom = work_area(self.root)
            x, y = left, bottom - H * P
        else:
            x, y = self.cfg["x"], self.cfg["y"]
        self.root.geometry(f"{w * P}x{H * P}+{x}+{y}")
        self.redraw()
        self.write_dock()

    def write_dock(self):
        """エレクトロガールがバーの上に立てるように、バーの位置を書いておく"""
        try:
            self.root.update_idletasks()
            info = {"x": self.root.winfo_x(), "y": self.root.winfo_y(),
                    "w": self.root.winfo_width(), "h": self.root.winfo_height(), "ts": time.time()}
            save_json(DOCK_PATH, info, pretty=False)
        except (OSError, tk.TclError):
            pass

    # --- 描画 ---
    def running(self, key):
        p = self.procs.get(key)
        return p is not None and p.poll() is None

    def redraw(self):
        W = self.bar_width()
        im = Image.new("RGB", (W, H), FACE)
        d = ImageDraw.Draw(im)
        for y in range(2, H - 1):   # 上は明るく、下へ網点でなじむ地
            t = (y - 2) / (H - 4)
            for x in range(W):
                d.point((x, y), fill=FACE if BAYER4[y % 4][x % 4] / 16 < t + 0.25 else SOFT)
        d.line([(0, 0), (W - 1, 0)], fill=SOFT)
        d.line([(0, 1), (W - 1, 1)], fill=LIGHT)
        d.line([(0, H - 1), (W - 1, H - 1)], fill=SHADOW)
        self.regions = []
        # START
        x = 2
        down = self.hover == "start" and getattr(self, "_pressing", False)
        bevel(d, x, 3, x + START_W - 1, H - 4, raised=not down)
        o = 1 if down else 0
        px_color(d, x + 3 + o, 6 + o, CHERRY)
        px_text(d, x + 15 + o, 9 + o, "START", LIGHT)
        px_text(d, x + 14 + o, 8 + o, "START", DARK)
        if self.hover == "start" and not down:
            d.line([(x + 14, 14), (x + 32, 14)], fill=PINK)
        self.regions.append(("start", x, 3, x + START_W - 1, H - 4))
        x += START_W + 2
        # MENU（メニュー画面を開く）。開いている間は、へこんだまま
        down = (self.hover == "menu" and getattr(self, "_pressing", False)) or self.home is not None
        bevel(d, x, 3, x + MENU_W - 1, H - 4, raised=not down)
        o = 1 if down else 0
        px_color(d, x + 4 + o, 6 + o, [r.upper() for r in MENU_ICON])
        d.rectangle([x + 3 + o, 5 + o, x + 9 + o, 11 + o], outline=DARK)
        px_text(d, x + 14 + o, 9 + o, "MENU", LIGHT)
        px_text(d, x + 13 + o, 8 + o, "MENU", DARK)
        if self.hover == "menu" and not down:
            d.line([(x + 13, 14), (x + 28, 14)], fill=PINK)
        self.regions.append(("menu", x, 3, x + MENU_W - 1, H - 4))
        x += MENU_W + 3
        d.line([(x - 2, 4), (x - 2, H - 5)], fill=SHADOW)
        d.line([(x - 1, 4), (x - 1, H - 5)], fill=LIGHT)
        x += 4
        for gy in range(5, H - 5, 2):   # つまみの点々
            d.point((x - 3, gy), fill=SHADOW)
            d.point((x - 2, gy + 1), fill=LIGHT)
        # ツールのボタン
        tw = self.tool_w()
        shorts = {key: short for key, _, short, _, _ in TOOLS}
        for key in self.bar_keys():
            short = shorts[key]
            on = self.running(key)
            bevel(d, x, 3, x + tw - 1, H - 4, raised=not on)
            if on:   # 起動中は、昔の「選択中のタスク」みたいな市松模様
                for yy in range(5, H - 5):
                    for xx in range(x + 2 + (yy % 2), x + tw - 2, 2):
                        d.point((xx, yy), fill=LIGHT)
            elif self.hover == key:
                d.rectangle([x + 2, 5, x + tw - 3, H - 6], fill=SOFT)
            o = 1 if on else 0
            icon = self.icons.get(key)
            if icon is not None:
                small = icon.resize((16, 16), Image.NEAREST)
                im.paste(small, (x + 3 + o, 3 + o), small)
            label, room = short, tw - 24
            if px_text_w(label) > room:   # 入りきらない名前は「..」で省略する
                while label and px_text_w(label + "..") > room:
                    label = label[:-1]
                label = label.rstrip() + ".." if label else ""
            px_text(d, x + 21 + o, 9 + o, label, NAVY if on else DARK)
            if on:   # 起動中のしるし（下の細い線）
                d.line([(x + 4, H - 6), (x + tw - 5, H - 6)], fill=PINK)
            self.regions.append((key, x, 3, x + tw - 1, H - 4))
            x += tw + 2
        # 時計とトレイ
        tw = self.tray_width()
        tx = W - tw - 3
        bevel(d, tx, 3, W - 4, H - 4, raised=False)
        weather = load_weather()
        icons = (weather or "cherry", "note_on" if load_now_playing() else "note_off",
                 "moon" if is_night_time() else "sun")
        for i, name in enumerate(icons):   # 天気・音楽・昼と夜を、トレイに小さく
            rows = TRAY[name]
            px_color(d, tx + 4 + i * 9, 7 + (7 - len(rows)) // 2, rows)
        d.line([(tx + 30, 5), (tx + 30, H - 6)], fill=SHADOW)
        now = time.localtime()
        px_text(d, tx + 4 + 27 + 3, 5, time.strftime("%H:%M", now), DARK)
        px_text(d, tx + 4 + 27 + 3, 12, time.strftime("%m/%d", now), DARK)
        im = recolor(im, self.cmap())
        self.photo = ImageTk.PhotoImage(im.resize((W * P, H * P), Image.NEAREST))
        self.label.config(image=self.photo)

    def region_at(self, e):
        x, y = e.x / P, e.y / P
        for name, x0, y0, x1, y1 in self.regions:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return name
        return None

    def set_hover(self, name):
        if name != self.hover:
            self.hover = name
            self.label.config(cursor="hand2" if name else "")
            self.redraw()

    # --- マウス ---
    def on_motion(self, e):
        self.set_hover(self.region_at(e))

    def on_press(self, e):
        self._press = (e.x_root, e.y_root)
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()
        self._pressing = True
        self._moved = False
        self._drag_ok = self.region_at(e) is None   # ボタンの上から始めたときは動かさない
        self.redraw()

    def on_drag(self, e):
        if self.cfg["dock"] != "float" or not getattr(self, "_drag_ok", False):
            return
        if abs(e.x_root - self._press[0]) + abs(e.y_root - self._press[1]) > 3:
            self._moved = True
            self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def on_release(self, e):
        if not getattr(self, "_pressing", False):
            return   # 押していないのに「離した」だけ届いたときは何もしない
        self._pressing = False
        if self._moved:
            self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
            save_config(self.cfg)
            self.redraw()
            return
        name = self.region_at(e)
        self.redraw()
        if name == "start":
            self.open_start()
        elif name == "menu":
            self.toggle_home()
        elif name:
            self.launch(name)

    def on_right(self, e):
        name = self.region_at(e)
        if name in self.tools:
            self.tool_menu(name, e.x_root, self.root.winfo_rooty(), above=True)
        elif name == "menu":
            self.toggle_home()
        else:
            self.open_start()

    def tool_menu(self, name, x, y, above):
        """ツールの右クリックメニュー（バーとメニュー画面で共通）。"""
        if True:
            tool = self.tools[name]
            pinned = name in self.cfg["pinned"]
            items = [{"type": "cmd", "label": "起動する", "cmd": lambda: self.launch(name),
                      "enabled": not self.running(name)},
                     {"type": "cmd", "label": "終了する", "cmd": lambda: self.stop(name),
                      "enabled": self.running(name)},
                     {"type": "sep"},
                     {"type": "check", "label": "バーにピン留め", "checked": pinned,
                      "cmd": lambda: self.toggle_pin(name)}]
            self.menu.title = tool[1]
            self.menu.popup(items, x, y, above=above)

    # --- メニュー画面 ---
    def toggle_home(self):
        if self.home is not None:
            self.home.close()
        else:
            self.home = HomeMenu(self)
        self.redraw()   # MENU ボタンのへこみ

    def open_home(self):
        """デスクトップのアイコンから：閉じていれば開き、開いていれば前に出す。"""
        if getattr(self, "_bye", False):
            return
        if getattr(self, "_booting", False):   # 起動画面が終わってから開く
            self._open_after_boot = True
            return
        if self.home is None:
            self.toggle_home()
        else:
            self.home.t.lift()
            self.home.t.focus_force()

    def watch_menu_request(self):
        if os.path.exists(MENU_REQUEST):
            try:
                os.remove(MENU_REQUEST)
            except OSError:
                pass
            self.open_home()
        self.root.after(300, self.watch_menu_request)

    # --- スタートメニュー ---
    def open_start(self):
        self.menu.title = "SUGAROS 24"
        self.menu.popup(self.start_items, self.root.winfo_rootx(), self.root.winfo_rooty(), above=True)

    def start_items(self):
        c = self.cfg
        c_now = self.colorway
        items = [{"type": "head", "label": "SugarOS 24"},
                 {"type": "cmd", "label": "メニュー画面を開く", "cmd": lambda: self.home or self.toggle_home()}]
        tools = {t[0]: t for t in TOOLS}
        for group, keys in GROUPS:   # 系統ごとのサブメニュー
            sub = []
            for key in keys:
                _, name, _, script, _ = tools[key]
                exists = os.path.exists(os.path.join(APP_DIR, script))
                sub.append({"type": "cmd", "label": name, "cmd": lambda k=key: self.launch(k),
                            "right": "起動中" if self.running(key) else ("" if exists else "見つからない"),
                            "enabled": exists})
            n = sum(self.running(k) for k in keys)
            items.append({"type": "sub", "label": group, "items": sub, "right": f"{n}こ起動中" if n else ""})
        items += [
            {"type": "sep"},
            {"type": "cmd", "label": "ぜんぶ起動", "cmd": self.launch_all},
            {"type": "cmd", "label": "ぜんぶ終了", "cmd": self.stop_all,
             "enabled": any(self.running(k) for k, *_ in TOOLS)},
            {"type": "sep"},
            {"type": "sub", "label": "カラー（全ツール共通）",
             "right": next(n for n, k in COLORWAY_NAMES if k == c_now),
             "items": [{"type": "radio", "label": n, "checked": c_now == k, "cmd": lambda k=k: self.set_colorway(k)}
                       for n, k in COLORWAY_NAMES]},
            {"type": "sub", "label": "昼と夜（全ツール共通）", "right": "夜" if is_night_time() else "昼",
             "items": self.time_items},
            {"type": "sub", "label": "設定", "items": [
                {"type": "head", "label": "置き場所"},
                {"type": "radio", "label": "好きな所に浮かせる", "checked": c["dock"] == "float",
                 "cmd": lambda: self.set_dock("float")},
                {"type": "radio", "label": "画面の下にくっつける", "checked": c["dock"] == "bottom",
                 "cmd": lambda: self.set_dock("bottom")},
                {"type": "sep"},
                {"type": "check", "label": "バーにツールのボタンを出す", "checked": c.get("show_tools", False),
                 "cmd": self.toggle_show_tools},
                {"type": "sub", "label": "バーにピン留めするツール", "enabled": c.get("show_tools", False), "right": f"{len(c['pinned'])}こ",
                 "items": lambda: [{"type": "check", "label": name, "checked": key in self.cfg["pinned"],
                                    "cmd": lambda k=key: self.toggle_pin(k)} for key, name, *_ in TOOLS]
                 + [{"type": "head", "label": "起動中のツールは、ピン留めしなくてもバーに出るよ"}]},
                {"type": "check", "label": "最前面に表示", "checked": c["topmost"], "cmd": self.toggle_topmost},
                {"type": "check", "label": "起動と終了の画面を出す", "checked": c.get("show_splash", True),
                 "cmd": self.toggle_splash},
            ]},
            {"type": "sep"},
            {"type": "cmd", "label": "ランチャーを終了", "cmd": self.quit},
            {"type": "head", "label": f"SugarOS 24 ランチャー ver.{APP_VERSION}"},
        ]
        return items

    def time_items(self):
        t = load_time_settings()
        hours = lambda key, rng: [{"type": "radio", "label": f"{h}時", "checked": t[key] == h,   # noqa: E731
                                   "cmd": lambda h=h: self.set_time(**{key: h})} for h in rng]
        name = lambda path: os.path.basename(path) if path else "未設定"   # noqa: E731
        return [
            {"type": "head", "label": "今は夜" if is_night_time() else "今は昼"},
            {"type": "radio", "label": "時刻どおりに切り替える", "checked": t["mode"] == "auto",
             "cmd": lambda: self.set_time(mode="auto")},
            {"type": "radio", "label": "いつも昼", "checked": t["mode"] == "day", "cmd": lambda: self.set_time(mode="day")},
            {"type": "radio", "label": "いつも夜", "checked": t["mode"] == "night",
             "cmd": lambda: self.set_time(mode="night")},
            {"type": "sep"},
            {"type": "sub", "label": "朝になる時刻", "right": f"{t['day']}時", "items": hours("day", range(4, 11))},
            {"type": "sub", "label": "夜になる時刻", "right": f"{t['night']}時", "items": hours("night", range(16, 23))},
            {"type": "sep"},
            {"type": "check", "label": "壁紙も切り替える", "checked": t["wallpaper"],
             "cmd": lambda: self.set_time(wallpaper=not t["wallpaper"])},
            {"type": "cmd", "label": "昼の壁紙を選ぶ…", "right": name(t["wall_day"]),
             "cmd": lambda: self.pick_wallpaper("wall_day")},
            {"type": "cmd", "label": "夜の壁紙を選ぶ…", "right": name(t["wall_night"]),
             "cmd": lambda: self.pick_wallpaper("wall_night")},
            {"type": "head", "label": "全ツール共通。数秒でみんな切り替わるよ"},
        ]

    def set_time(self, **changes):
        t = load_time_settings()
        t.update(changes)
        save_time_settings(t)
        self.night = None   # 壁紙と見た目を、すぐ今の設定に合わせ直す
        self.check_time()

    def pick_wallpaper(self, key):
        path = filedialog.askopenfilename(
            parent=self.root, title="昼の壁紙" if key == "wall_day" else "夜の壁紙",
            filetypes=[("画像", "*.png *.jpg *.jpeg *.bmp"), ("すべてのファイル", "*.*")])
        if path:
            self.set_time(**{key: os.path.normpath(path), "wallpaper": True})

    def check_time(self):
        """昼と夜が切り替わったら、壁紙を替えて、バーも着替える。"""
        night = is_night_time()
        if night == self.night:
            return
        self.night = night
        t = load_time_settings()
        path = t["wall_night"] if night else t["wall_day"]
        if t["wallpaper"] and path and os.path.exists(path):
            set_wallpaper(path)
        self.redraw()

    # --- 起動と終了 ---
    def launch(self, key):
        if self.running(key):
            return
        tool = next(t for t in TOOLS if t[0] == key)
        script = os.path.join(APP_DIR, tool[3])
        if not os.path.exists(script):
            return
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.procs[key] = subprocess.Popen([pythonw(), script], cwd=APP_DIR, creationflags=flags)
        self.place()   # バーにボタンが増えるかもしれない
        if self.home is not None:
            self.home.redraw()

    def stop(self, key):
        p = self.procs.get(key)
        if p is not None and p.poll() is None:
            p.terminate()
        self.root.after(500, self.place)
        self.root.after(600, lambda: self.home and self.home.redraw())

    def launch_all(self):
        for i, (key, *_rest) in enumerate(TOOLS):
            self.root.after(i * 700, lambda k=key: self.launch(k))   # 少しずつずらして起動

    def stop_all(self):
        for key, *_ in TOOLS:
            self.stop(key)

    def toggle_pin(self, key):
        pinned = self.cfg["pinned"]
        if key in pinned:
            pinned.remove(key)
        else:
            pinned.append(key)
        save_config(self.cfg)
        self.place()

    def set_dock(self, mode):
        self.cfg["dock"] = mode
        save_config(self.cfg)
        self.place()

    def toggle_show_tools(self):
        self.cfg["show_tools"] = not self.cfg.get("show_tools", False)
        save_config(self.cfg)
        self.place()

    def toggle_splash(self):
        self.cfg["show_splash"] = not self.cfg.get("show_splash", True)
        save_config(self.cfg)

    def toggle_topmost(self):
        self.cfg["topmost"] = not self.cfg["topmost"]
        save_config(self.cfg)
        self.root.attributes("-topmost", self.cfg["topmost"])

    # --- カラー ---
    def cmap(self):
        night = is_night_time()
        if self.colorway not in ("blue", "mint", "pink", "orange") and not night:
            return None
        cw = colorway_full(self.colorway, MENU_BASE)
        mix = lambda c, t, r: tuple(round(a + (b - a) * r) for a, b in zip(c, t))   # noqa: E731
        roles = {"bar": mix(cw["title2"], cw["light"], 0.25), "bar_soft": mix(cw["title2"], cw["light"], 0.6),
                 "bar_shadow": cw["shade"] if night else mix(cw["title"], cw["out"], 0.35),
                 "out": cw["out"], "accent": cw["accent"]}
        m = {src: roles[r] for src, r in COLOR_BASE.items()}
        if night:
            m[LIGHT] = cw["light"]   # 白いハイライトも夜の色に
        return m

    def menu_theme(self):
        if self.colorway != "original" or is_night_time():
            return colorway_theme(self.colorway, MENU_BASE)
        return MENU_THEME

    def set_colorway(self, name):
        save_colorway(name)
        self.colorway = name
        self.redraw()
        if self.home is not None:
            self.home.redraw()

    def tick(self):
        if getattr(self, "_bye", False):   # おやすみ画面のあいだは、もう何もしない
            return
        name = load_colorway()   # ほかのツールで色が変わったら、こっちも着替える
        if name != self.colorway:
            self.colorway = name
        self.check_time()
        keys = self.bar_keys()
        if keys != getattr(self, "_shown_keys", None):   # ツールを閉じたら、バーのボタンも減らす
            self._shown_keys = keys
            self.place()
        else:
            self.redraw()   # 時計と起動中かどうかを更新
            self.write_dock()
        if self.home is not None:
            self.home.redraw()
        self.root.after(2000, self.tick)

    def boot(self, open_menu=False):
        """起動画面を出してから、バーを見せる。"""
        self._open_after_boot = open_menu
        if self.cfg.get("show_splash", True):
            try:
                self.root.attributes("-alpha", 0.0)
                self._booting = True
                Splash(self, "boot", self.boot_done)
                return
            except tk.TclError:
                pass
        self.boot_done()

    def boot_done(self):
        self._booting = False
        self.root.attributes("-alpha", 1.0)
        if self._open_after_boot:
            self._open_after_boot = False
            self.root.after(200, self.open_home)

    def quit(self):
        if getattr(self, "_bye", False):
            return
        save_config(self.cfg)
        self._bye = True
        try:
            os.remove(DOCK_PATH)
        except OSError:
            pass
        if self.cfg.get("show_splash", True):
            try:
                self.menu.close_all()
                if self.home is not None:
                    self.home.close()
                self.root.attributes("-alpha", 0.0)
                Splash(self, "night", self.root.destroy, length=2.0)
                return
            except tk.TclError:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        app = Launcher()
        app.boot(open_menu="--menu" in sys.argv)   # --menu：デスクトップの「SugarOS メニュー」から起動されたとき
        app.run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "launcher_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
