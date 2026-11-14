# -*- coding: utf-8 -*-
"""
ドットお天気 ver.1.1（WEATHER.EXE）
いま住んでいる所の天気を、ドット絵の空で見せる小窓。SugarOS 24 の天気担当。
ここで取ってきた天気は、ほかのツール（温室・一方その頃 など）にも伝わって、雨や雪が降る。

操作:
  UPDATE     … 今すぐ天気を取り直す
  ドラッグ   … ウィンドウを移動
  右クリック … メニュー（場所を変える / 更新の間隔 / ためしに降らせる / カラー / サイズ など）

天気は Open-Meteo（https://open-meteo.com/ 無料・登録なし）から取ってくる。インターネットが必要。
必要なもの: pip install pillow
"""
import json
import math
import os
import queue
import random
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
from datetime import date

from PIL import Image, ImageDraw, ImageTk

from mushiboshi_ui import (COLORWAY_NAMES, dither_bar, dither_gradient, WEATHER_KINDS, log_errors, is_night_time, PixelMenu, ask_text,
                           colorway_cmap, colorway_menu, colorway_theme, draw_weather, load_colorway, pick_items,
                           recolor, save_colorway, save_weather, show_message, ui_font, Scale, hexc, mix,
                           px_pattern, px_text, px_text_w, load_json, save_json)

APP_VERSION = "1.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "weather_config.json")
FPS = 10

DEFAULT_CONFIG = {"place": "東京", "lat": 35.6895, "lon": 139.6917, "every_min": 30, "last": None,
                  "scale": 3, "topmost": True, "x": 320, "y": 160}
SCALES = [("ミニ", 1.5), ("小", 2), ("中", 3), ("大", 4)]
EVERY_MINS = [("15分", 15), ("30分", 30), ("1時間", 60)]
KIND_NAMES = dict((k, n) for n, k in WEATHER_KINDS)

_ICONS = {
    "sun": "#.#.#|.###.|#####|.###.|#.#.#",
    "update": ".###.|#...#|#..##|#...#|.###.",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
}
# 予報の小さなアイコン（9×7）。y=太陽 c=雲 g=雨雲 b=雨 w=雪 l=霧
_SMALL = {
    "clear": ["...yyy...", "..yyyyy..", ".yyyyyyy.", ".yyyyyyy.", ".yyyyyyy.", "..yyyyy..", "...yyy..."],
    "partly": [".yyy.....", "yyyyy....", "yyyy.cc..", ".yyccccc.", "..ccccccc", ".cccccccc", "..ccccccc"],
    "cloudy": [".........", "...cc....", "..cccc.c.", ".cccccccc", "ccccccccc", ".cccccccc", "........."],
    "rain": ["...gg....", "..gggg.g.", ".gggggggg", "ggggggggg", ".........", ".b..b..b.", "b..b..b.."],
    "thunder": ["...gg....", "..gggg.g.", ".gggggggg", "gggyggggg", "...yy....", "....y....", "...y....."],
    "snow": ["...cc....", "..cccc.c.", ".cccccccc", "ccccccccc", ".........", ".w..w..w.", "...w..w.."],
    "fog": [".........", "lllllll..", ".........", "..lllllll", ".........", "lllllll..", "........."],
}
_SMALL_COLORS = {"y": (250, 186, 60), "c": (176, 186, 206), "g": (120, 128, 150), "b": (80, 150, 240),
                 "w": (140, 170, 230), "l": (160, 166, 180)}
WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

PAL = dict(face=(240, 246, 252), out=(44, 56, 96), light=(255, 255, 255), shade=(192, 206, 230),
           title=(150, 190, 240), title2=(194, 220, 250), accent=(240, 120, 90), hover=(255, 222, 210),
           second=(100, 140, 210))
COLOR_BASE = {v: k for k, v in PAL.items() if k != "light"}

W, H = 106, 123
SX, SY, SW, SH = 3, 14, 100, 56          # 空の画面
CAP_Y = 72                               # 場所と今日の天気（日本語）
FC_Y, FC_W, FC_H = 83, 32, 23            # 3日分の予報
ROW = 109
BUTTONS = {"update": (3, 43)}


# ---------- 天気を取ってくる ----------

def kind_of(code):
    """WMO の天気コード → このツールの天気の種類。"""
    code = int(code or 0)
    if code <= 1:
        return "clear"
    if code == 2:
        return "partly"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "thunder"
    return "cloudy"


def fetch_forecast(lat, lon):
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 3})
    with urllib.request.urlopen("https://api.open-meteo.com/v1/forecast?" + q, timeout=15) as r:
        data = json.load(r)
    cur, dl = data["current"], data["daily"]
    days = [{"date": dl["time"][i], "kind": kind_of(dl["weather_code"][i]),
             "max": dl["temperature_2m_max"][i], "min": dl["temperature_2m_min"][i],
             "pop": dl["precipitation_probability_max"][i]} for i in range(len(dl["time"]))]
    return {"temp": cur["temperature_2m"], "kind": kind_of(cur["weather_code"]), "days": days,
            "fetched": time.time()}


def search_places(name):
    """地名から候補を探す。「大阪」のように市を付けないと見つからないことがあるので、付けて探し直す。"""
    def ask(q):
        url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
            {"name": q, "count": 8, "language": "ja"})
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.load(r).get("results") or []
    res = ask(name)
    if not res and not name.endswith(("市", "区", "町", "村")):
        res = ask(name + "市")
    return [(p["name"], " ".join(x for x in (p.get("admin1"), p.get("country")) if x), p["latitude"], p["longitude"])
            for p in res]


# ---------- 空の画面 ----------

SKY = {  # (昼の上, 昼の下, 夜の上, 夜の下)
    "clear": ((64, 136, 232), (176, 214, 250), (14, 20, 56), (40, 56, 110)),
    "partly": ((84, 150, 230), (186, 218, 248), (20, 26, 60), (48, 60, 108)),
    "cloudy": ((140, 160, 190), (200, 212, 226), (40, 44, 70), (70, 76, 104)),
    "rain": ((112, 126, 156), (170, 180, 200), (30, 34, 56), (56, 62, 86)),
    "thunder": ((70, 72, 104), (130, 130, 158), (22, 22, 40), (48, 46, 72)),
    "snow": ((170, 184, 206), (226, 232, 242), (60, 66, 96), (100, 108, 140)),
    "fog": ((196, 204, 214), (226, 230, 236), (70, 76, 96), (100, 106, 124)),
}
CLOUD = {  # 雲の色 (昼, 夜) と数
    "partly": ((246, 248, 252), (90, 96, 130), 2), "cloudy": ((214, 220, 230), (70, 76, 104), 6),
    "rain": ((150, 158, 176), (50, 54, 78), 6), "thunder": ((110, 112, 136), (36, 36, 58), 6),
    "snow": ((226, 230, 238), (96, 102, 132), 6), "fog": ((220, 224, 230), (86, 92, 112), 3),
}
GROUND_Y = 45


def build_sky(kind, night):
    """動かない部分（空・星・街並み）。"""
    im = Image.new("RGB", (SW, SH))
    d = ImageDraw.Draw(im)
    dt, db, nt, nb = SKY.get(kind, SKY["clear"])
    dither_gradient(d, 0, 0, SW - 1, GROUND_Y, nt if night else dt, nb if night else db, steps=6)
    rnd = random.Random(24)
    stars = []
    if night and kind in ("clear", "partly"):
        for _ in range(30):
            xy = (rnd.randrange(SW), rnd.randrange(GROUND_Y - 12))
            d.point(xy, fill=rnd.choice([(255, 255, 220), (200, 210, 255)]))
            stars.append(xy)
    # 遠くの山なみ
    hill = (156, 176, 206) if not night else (34, 40, 72)
    for x in range(SW):
        y = int(GROUND_Y - 6 + 3 * math.sin(x / 13 + 1) + 2 * math.sin(x / 5))
        d.line([(x, y), (x, GROUND_Y + 4)], fill=hill)
        d.point((x, y), fill=mix(hill, (255, 255, 255), 0.25 if not night else 0.1))
    # 街並み（奥と手前の2列）
    far = (134, 150, 186) if not night else (40, 44, 80)
    near = (96, 108, 150) if not night else (26, 28, 54)
    windows = []
    for col, base, hmin, hmax in ((far, GROUND_Y + 2, 5, 12), (near, SH - 1, 6, 16)):
        x = -2
        while x < SW:
            bw, bh = rnd.randint(6, 11), rnd.randint(hmin, hmax)
            top = base - bh if col is near else GROUND_Y - bh + 4
            d.rectangle([x, top, x + bw, SH - 1], fill=col)
            d.line([(x, top), (x + bw, top)], fill=mix(col, (255, 255, 255), 0.15))   # 屋上のふち
            if col is near and rnd.random() < 0.35:   # 屋上のアンテナや給水タンク
                if rnd.random() < 0.5:
                    d.line([(x + 2, top - 4), (x + 2, top)], fill=col)
                    d.line([(x + 1, top - 3), (x + 3, top - 3)], fill=col)
                else:
                    d.rectangle([x + bw - 4, top - 3, x + bw - 2, top - 1], fill=col)
            if col is near:
                for wy in range(top + 2, SH - 2, 3):
                    for wx in range(x + 2, x + bw - 1, 2):
                        windows.append((wx, wy, rnd.random()))
            if kind == "snow":
                d.line([(x, top), (x + bw, top)], fill=(240, 244, 250) if not night else (170, 178, 206))
            x += bw + rnd.randint(0, 2)
    if night:   # 街灯と、足もとのあかり
        for lx in range(10, SW, 26):
            d.line([(lx, SH - 9), (lx, SH - 1)], fill=(70, 74, 100))
            d.line([(lx, SH - 9), (lx + 2, SH - 9)], fill=(70, 74, 100))
            d.point((lx + 2, SH - 8), fill=(255, 230, 160))
        over = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
        o = ImageDraw.Draw(over)
        for lx in range(10, SW, 26):
            o.ellipse([lx - 4, SH - 8, lx + 8, SH + 2], fill=(255, 220, 150, 40))
        im.paste(Image.alpha_composite(im.convert("RGBA"), over).convert("RGB"))
    return im, windows, stars


def draw_cloud(d, x, y, r, color):
    for dx, dy, rr in ((0, 0, r), (r, -r // 2, r + 1), (r * 2, 0, r), (r, 1, r)):
        d.ellipse([x + dx - rr, y + dy - rr + 1, x + dx + rr, y + dy + rr - 1], fill=color)


def render_sky(base, windows, stars, kind, night, temp, t):
    im = base.copy()
    d = ImageDraw.Draw(im)
    for i, (sx, sy) in enumerate(stars):   # 星がまたたく
        if (int(t * 2) + i * 5) % 11 == 0:
            d.point((sx, sy), fill=(255, 255, 255))
            d.point((sx - 1, sy), fill=(150, 160, 210))
            d.point((sx + 1, sy), fill=(150, 160, 210))
    # 太陽・月
    if kind in ("clear", "partly"):
        if night:
            d.ellipse([78, 5, 88, 15], fill=(250, 244, 206))
            d.ellipse([81, 3, 91, 13], fill=mix(SKY[kind][2], SKY[kind][3], 0.1))
        else:
            cx, cy = 82, 13
            for k in range(8):   # くるくる回る光
                a = t * 0.6 + k * math.pi / 4
                ln = 10 + (1 if (k + int(t * 2)) % 2 else 0)
                d.line([(cx + math.cos(a) * 8, cy + math.sin(a) * 8), (cx + math.cos(a) * ln, cy + math.sin(a) * ln)],
                       fill=(255, 226, 120))
            d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(255, 206, 80))
            d.ellipse([cx - 4, cy - 5, cx + 1, cy - 2], fill=(255, 232, 150))
    # 雲
    if kind in CLOUD:
        day_c, night_c, n = CLOUD[kind]
        col = night_c if night else day_c
        for k in range(n):
            r = 4 + (k * 3) % 3
            x = (k * 37 + t * (1.2 + k % 3 * 0.5)) % (SW + 30) - 18
            y = 6 + (k * 11) % 16 if n > 2 else 10 + k * 12
            draw_cloud(d, x, y, r, col)
    if kind in ("clear", "partly") and not night:   # 鳥がわたっていく
        bx = (t * 6) % (SW + 40) - 20
        for k, (ox, oy) in enumerate(((0, 0), (6, 3), (-5, 4))):
            x, y = bx + ox, 24 + oy + math.sin(t * 2 + k) * 1
            flap = int(t * 5 + k) % 2
            d.line([(x - 2, y - flap), (x, y)], fill=(60, 70, 100))
            d.line([(x, y), (x + 2, y - flap)], fill=(60, 70, 100))
    # 夜の街のあかり
    if night:
        for wx, wy, r in windows:
            if (math.sin(t * 0.15 + r * 40) + r) > 0.7:
                d.point((wx, wy), fill=(255, 220, 140))
    draw_weather(im, (0, 0, SW - 1, SH - 1), kind, t, night)
    if kind == "thunder" and t % 7 < 0.18:   # 稲妻
        x = 30 + int(t // 7) * 23 % 40
        d = ImageDraw.Draw(im)
        d.line([(x, 0), (x - 3, 8), (x + 1, 9), (x - 3, 20)], fill=(255, 250, 200), width=1)
    # 気温（大きく）
    if temp is not None:
        text = f"{round(temp)}°"
        d = ImageDraw.Draw(im)
        px_text(d, 5, 5, text, (20, 24, 40), 2)
        px_text(d, 4, 4, text, (255, 255, 255), 2)
    return im


# ---------- 窓 ----------

def render_window():
    k = PAL
    im = Image.new("RGB", (W, H), k["face"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W - 1, H - 1], outline=k["out"])
    d.line([(1, 1), (W - 2, 1)], fill=k["light"])
    d.line([(1, 1), (1, H - 2)], fill=k["light"])
    dither_bar(d, 2, 2, W - 3, 11, k["title2"], k["title"])   # 左の明るい色から、右へ網点でなめらかに
    px_pattern(d, 5, 5, _ICONS["sun"], k["light"])
    px_pattern(d, 4, 4, _ICONS["sun"], k["out"])
    px_text(d, 13, 6, "WEATHER.EXE", k["light"])
    px_text(d, 12, 5, "WEATHER.EXE", k["out"])
    bx0 = W - 3 - 3 * 9
    for i, icon in enumerate(("min", "max", "close")):
        x0 = bx0 + i * 9
        d.rectangle([x0, 3, x0 + 7, 10], fill=k["hover"] if icon == "close" else k["face"], outline=k["out"])
        px_pattern(d, x0 + 1, 4, _ICONS[icon], k["out"])
    d.line([(1, 12), (W - 2, 12)], fill=k["out"])
    d.rectangle([SX - 1, SY - 1, SX + SW, SY + SH], outline=k["out"])
    d.rectangle([SX, CAP_Y - 1, SX + SW - 1, CAP_Y + 8], fill=k["light"], outline=k["out"])
    return im


def render_forecast(days, status):
    """3日分の予報と、右下の更新時刻。"""
    k = PAL
    im = Image.new("RGB", (W - 4, H - FC_Y - 2), k["face"])
    d = ImageDraw.Draw(im)
    today = date.today()
    for i in range(3):
        x0 = 1 + i * (FC_W + 1)
        day = days[i] if days and i < len(days) else None
        is_today = bool(day) and day.get("date") == today.isoformat()
        d.rectangle([x0, 0, x0 + FC_W - 1, FC_H - 1], fill=k["light"], outline=k["accent"] if is_today else k["shade"])
        d.line([(x0 + 1, FC_H - 2), (x0 + FC_W - 2, FC_H - 2)], fill=k["shade"])   # 下のかげ
        if day is None:
            px_text(d, x0 + (FC_W - 3) // 2, 9, "?", k["shade"])
            continue
        try:
            dd = date.fromisoformat(day["date"])
            label = "TODAY" if dd == today else WEEKDAYS[dd.weekday()]
        except ValueError:
            label = "-"
        px_text(d, x0 + (FC_W - px_text_w(label)) // 2, 2, label, k["accent"] if label == "TODAY" else k["out"])
        for ry, row in enumerate(_SMALL.get(day["kind"], _SMALL["cloudy"])):
            for rx, ch in enumerate(row):
                if ch != ".":
                    d.point((x0 + 11 + rx, 8 + ry), fill=_SMALL_COLORS[ch])
        temps = f"{round(day['max'])}/{round(day['min'])}"
        px_text(d, x0 + (FC_W - px_text_w(temps)) // 2, 16, temps, k["out"])
    px_text(d, im.width - px_text_w(status) - 2, ROW - FC_Y + 3, status, k["second"])
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
    px_pattern(d, 3, (h - 5) // 2, _ICONS[icon], k["out"] if hover else k["accent"])
    px_text(d, 3 + iw + 2, 3, text, k["out"])
    return im


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_PATH, {}))
    return cfg


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


class Weather:
    def __init__(self):
        self.cfg = load_config()
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.p = Scale(self.cfg["scale"])
        self.trial = None          # 「ためしに降らせる」で選んだ天気（このツールを閉じると元に戻る）
        self.state = "ok" if self.cfg["last"] else "wait"
        self.q = queue.Queue()
        self.next_fetch = 0
        self.sky_key = None
        self.t0 = time.time()
        self.pimgs = {}

        self.root = tk.Tk()
        log_errors(self.root, "weather_error.txt")
        self.root.title(f"ドットお天気 ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "weather.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])
        self.frame_label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.screen = tk.Label(self.root, bd=0, highlightthickness=0)
        self.cap = tk.Label(self.root, anchor="w", bd=0)
        self.fc = tk.Label(self.root, bd=0, highlightthickness=0)
        for w in (self.root, self.frame_label, self.screen, self.cap, self.fc):
            w.bind("<ButtonPress-1>", self.drag_start)
            w.bind("<B1-Motion>", self.drag_move)
            w.bind("<ButtonRelease-1>", self.drag_end)
            w.bind("<Button-3>", self.popup_menu)
        self.frame_label.bind("<Motion>", self.frame_hover, add="+")
        self.frame_label.bind("<ButtonRelease-1>", self.frame_click, add="+")
        self.buttons = {}
        for key, action in (("update", self.fetch_now),):
            lb = tk.Label(self.root, bd=0, highlightthickness=0, cursor="hand2")
            lb.bind("<Button-1>", lambda e, a=action: a())
            lb.bind("<Enter>", lambda e, k=key: self.draw_button(k, True))
            lb.bind("<Leave>", lambda e, k=key: self.draw_button(k, False))
            lb.bind("<Button-3>", self.popup_menu)
            self.buttons[key] = lb
        self.pmenu = PixelMenu(self.root, self.menu_theme, title="WEATHER - MENU")
        self.layout()
        self.publish()
        self.root.after(1000 // FPS, self.tick)
        self.root.after(300, self.poll)
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

    # --- 天気 ---
    def kind(self):
        last = self.cfg["last"]
        return self.trial or (last["kind"] if last else None)

    def fetch_now(self):
        self.next_fetch = 0

    def poll(self):
        """取ってきた結果を受け取る。決まった間隔で取り直す。"""
        try:
            while True:
                kind, result, where = self.q.get_nowait()
                if where != (self.cfg["lat"], self.cfg["lon"]):
                    continue   # 取っているあいだに場所を変えたときは、前の場所の結果を捨てる
                if kind == "data":
                    self.cfg["last"] = result
                    self.state = "ok"
                    save_config(self.cfg)
                    self.publish()
                else:
                    self.state = "offline"
                self.update_info()
        except queue.Empty:
            pass
        if time.time() >= self.next_fetch:
            self.next_fetch = time.time() + self.cfg["every_min"] * 60
            self.start_fetch()
        self.root.after(500, self.poll)

    def start_fetch(self):
        where = (self.cfg["lat"], self.cfg["lon"])

        def work():
            try:
                self.q.put(("data", fetch_forecast(*where), where))
            except Exception:   # 通信できない・形が違うなどは、前の天気を出したまま OFFLINE にする
                self.q.put(("error", None, where))
        threading.Thread(target=work, daemon=True).start()

    def publish(self):
        """ほかのツールに今の天気を知らせる。古い天気しかないときは「わからない」にする。"""
        last = self.cfg["last"]
        fresh = last and time.time() - last.get("fetched", 0) < 3 * 3600
        kind = self.trial or (last["kind"] if fresh else None)
        save_weather({"kind": kind, "temp": last and last["temp"], "place": self.cfg["place"], "trial": bool(self.trial)})

    def set_trial(self, kind):
        self.trial = kind
        self.publish()
        self.update_info()

    def change_place(self):
        name = ask_text(self.root, self.menu_theme(), "場所を変える",
                        "天気を見たい場所の名前を入れてね（例：大阪市、札幌、Yokohama）", self.cfg["place"], near=self.root)
        if not name or not name.strip():
            return
        try:
            found = search_places(name.strip())
        except Exception:
            show_message(self.root, self.menu_theme(), "場所を変える", "いまは探せなかったよ。インターネットにつながっているか確かめてね",
                         near=self.root)
            return
        if not found:
            show_message(self.root, self.menu_theme(), "場所を変える", f"「{name}」は見つからなかったよ。市や区まで入れてみてね",
                         near=self.root)
            return
        entries = [(i, f"{n}（{area}）" if area else n, False) for i, (n, area, _, _) in enumerate(found)]
        picked = pick_items(self.root, self.menu_theme(), "場所を変える", "どこの天気にする？", entries,
                            near=self.root, ok_label="ここにする")
        if not picked:
            return
        n, _area, lat, lon = found[picked[0]]
        self.cfg.update(place=n, lat=lat, lon=lon, last=None)
        self.state = "wait"
        save_config(self.cfg)
        self.update_info()
        self.fetch_now()

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
        self.fc.place(x=2 * p, y=FC_Y * p)
        for key, (x, w) in BUTTONS.items():
            self.draw_button(key)
            self.buttons[key].place(x=x * p, y=ROW * p)
        self.sky_key = None
        self.update_info()

    def draw_button(self, key, hover=False):
        x, w = BUTTONS[key]
        img = recolor(render_button("update", "UPDATE", w, hover), self.cmap())
        img = ImageTk.PhotoImage(img.resize((w * self.p, 11 * self.p), Image.NEAREST))
        self.pimgs[key] = img
        self.buttons[key].config(image=img)

    def update_info(self):
        last = self.cfg["last"]
        kind = self.kind()
        if last:
            today = last["days"][0] if last.get("days") else None
            text = f"{self.cfg['place']}　{KIND_NAMES.get(kind, '')}"
            if today and today.get("pop") is not None:   # 最高・最低は下の TODAY に出ている
                text += f"　降水{today['pop']}%"
        else:
            text = f"{self.cfg['place']}　天気を取ってきているよ…" if self.state != "offline" else \
                f"{self.cfg['place']}　天気を取ってこられなかったよ"
        if self.trial:
            text = f"ためし中：{KIND_NAMES[self.trial]}"
        self.cap.config(text=text)
        if self.state == "offline":
            status = "OFFLINE"
        elif last:
            status = "UPD " + time.strftime("%H:%M", time.localtime(last.get("fetched", 0)))
        else:
            status = "..."
        img = recolor(render_forecast(last and last.get("days"), status), self.cmap())
        img = ImageTk.PhotoImage(img.resize((img.width * self.p, img.height * self.p), Image.NEAREST))
        self.pimgs["fc"] = img
        self.fc.config(image=img)

    # --- 動き ---
    def tick(self):
        t = time.time() - self.t0
        kind, night = self.kind() or "clear", is_night_time()
        if self.sky_key != (kind, night):
            self.sky_key = (kind, night)
            self.sky = build_sky(kind, night)
        last = self.cfg["last"]
        im = render_sky(*self.sky, kind, night, last and last["temp"], t)
        self.photo = ImageTk.PhotoImage(im.resize((SW * self.p, SH * self.p), Image.NEAREST))
        self.screen.config(image=self.photo)
        self.root.after(1000 // FPS, self.tick)

    # --- メニュー ---
    def menu_items(self):
        c = self.cfg
        return [
            {"type": "head", "label": f"場所：{c['place']}"},
            {"type": "cmd", "label": "場所を変える…", "cmd": self.change_place},
            {"type": "cmd", "label": "今すぐ更新", "cmd": self.fetch_now},
            {"type": "sub", "label": "更新の間隔", "right": next(n for n, v in EVERY_MINS if v == c["every_min"]),
             "items": [{"type": "radio", "label": n, "checked": c["every_min"] == v,
                        "cmd": lambda v=v: self.set_every(v)} for n, v in EVERY_MINS]},
            {"type": "sep"},
            {"type": "sub", "label": "ためしに降らせる", "right": KIND_NAMES[self.trial] if self.trial else "",
             "items": [{"type": "radio", "label": "本物の天気", "checked": self.trial is None,
                        "cmd": lambda: self.set_trial(None)},
                       {"type": "sep"},
                       *[{"type": "radio", "label": n, "checked": self.trial == k,
                          "cmd": lambda k=k: self.set_trial(k)} for n, k in WEATHER_KINDS],
                       {"type": "head", "label": "ほかのツールにも伝わるよ。閉じると元に戻る"}]},
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
            {"type": "head", "label": f"ドットお天気 ver.{APP_VERSION}"},
            {"type": "head", "label": "天気：Open-Meteo.com"},
        ]

    def popup_menu(self, e):
        self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

    def set_every(self, v):
        self.cfg["every_min"] = v
        self.next_fetch = time.time() + v * 60
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
        if self.trial:   # ためしの天気は、閉じるときに本物に戻しておく
            self.trial = None
            self.publish()
        save_config(self.cfg)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        Weather().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "weather_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
