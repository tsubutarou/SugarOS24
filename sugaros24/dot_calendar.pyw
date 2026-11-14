# -*- coding: utf-8 -*-
"""
ドットカレンダー ver.1.1（CALENDAR.EXE）
ひと月ぶんを見わたせる、ドット絵の小さなカレンダー。SugarOS 24 のカレンダー担当。
今日のしるし、土日・祝日（振替休日・国民の休日も）の色分けつき。予定の同期はまだ（あとで足す予定）。

操作:
  ◀ / ▶      … 前の月 / 次の月（マウスホイールでもめくれる）
  ●          … 今月に戻る（右クリックメニューからも）
  日付をクリック … その日を選ぶ（下に曜日と祝日の名前が出る）
  ドラッグ   … ウィンドウを移動
  右クリック … メニュー（週のはじまり / 祝日 / カラー / サイズ など）

必要なもの: pip install pillow
"""
import calendar
import os
import tkinter as tk
from datetime import date, timedelta

from PIL import Image, ImageDraw, ImageTk

from mushiboshi_ui import (COLORWAY_NAMES, dither_bar, log_errors, is_night_time, PixelMenu, colorway_cmap, colorway_menu,
                           colorway_theme, load_colorway, recolor, save_colorway, ui_font, Scale, hexc, mix,
                           px_pattern, px_text, px_text_w, load_json, save_json)

APP_VERSION = "1.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "calendar_config.json")

DEFAULT_CONFIG = {"week_start": "sun", "holidays": True, "scale": 3, "topmost": False, "x": 380, "y": 140}
SCALES = [("ミニ", 1.5), ("小", 2), ("中", 3), ("大", 4)]
WEEKDAY_JA = "月火水木金土日"
MONTH_EN = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

_ICONS = {
    "cal": "#####|#.#.#|#####|#.#.#|#####",
    "prev": "..#|.##|###|.##|..#",
    "next": "#..|##.|###|##.|#..",
    "today": ".##.|####|####|.##.",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
}

# 月ごとの小さな絵：[(模様, 色, ずらしx, ずらしy), ...]
MONTH_ICONS = {
    1: [(".#.#.#.|..###..|#######|..###..|.#.#.#.", (120, 170, 230), 0, 1)],                      # 雪の結晶
    2: [(".##.##.|#######|#######|.#####.|..###..|...#...", (240, 96, 140), 0, 0)],               # ハート
    3: [(".#.#.|#####|.#.#.|#####|.#.#.", (246, 150, 180), 1, 0), ("#", (250, 210, 90), 3, 2)],    # 桃の花
    4: [(".#.#.|##.##|..#..|##.##|.#.#.", (250, 180, 200), 1, 0), ("#", (240, 120, 150), 3, 2)],   # 桜
    5: [("...##|..###|.###.|###..|#....", (110, 190, 110), 1, 0)],                                # 若葉
    6: [(".###.|#####|..#..|..#..|.##..", (120, 150, 230), 1, 0)],                                # 傘
    7: [("..#..|#####|.###.|.#.#.", (250, 200, 90), 1, 1)],                                       # 星
    8: [("#.#.#|.###.|#####|.###.|#.#.#", (250, 170, 60), 1, 0)],                                 # 太陽
    9: [(".###.|##...|##...|##...|.###.", (240, 210, 120), 1, 0)],                                # 月
    10: [(".###.|#####|#####|.###.", (250, 150, 60), 1, 1), ("#", (110, 170, 90), 3, 0)],         # かぼちゃ
    11: [("..#..|#.#.#|#####|.###.|..#..", (230, 100, 70), 1, 0)],                                # もみじ
    12: [("..#..|.###.|#####|.###.|#####", (90, 170, 100), 1, 1), ("#", (250, 210, 90), 3, 0)],   # ツリー
}
PAL = dict(face=(250, 244, 246), out=(72, 50, 84), light=(255, 255, 255), shade=(226, 204, 216),
           title=(246, 178, 196), title2=(252, 210, 222), accent=(236, 96, 128), hover=(255, 224, 232),
           second=(160, 120, 170))
COLOR_BASE = {v: k for k, v in PAL.items() if k != "light"}
ON_ACCENT = (255, 255, 254)   # 今日のしるしの上の文字（夜の色に塗り替えられない白）

W, H = 106, 118
HEAD_Y = 14                 # 月の見出し
WEEK_Y = 29                 # 曜日の行
GRID_X, GRID_Y = 4, 37      # 日付のマス
CELL_W, CELL_H = 14, 11
CAP_Y = 105                 # 選んだ日（日本語）
BUTTONS = {"prev": (66, 15, 11), "today": (79, 15, 11), "next": (92, 15, 11)}   # x, y, 幅


# ---------- 祝日 ----------

def _nth_monday(y, m, n):
    first = date(y, m, 1)
    return first + timedelta(days=(7 - first.weekday()) % 7 + 7 * (n - 1))


def _equinox(y, base):
    """春分・秋分の日（1980〜2099年で使える近似式）。"""
    return int(base + 0.242194 * (y - 1980) - (y - 1980) // 4)


def holidays_of(y):
    """その年の祝日 {date: 名前}。今の祝日法のきまりで計算する（振替休日・国民の休日も）。"""
    h = {date(y, 1, 1): "元日", _nth_monday(y, 1, 2): "成人の日", date(y, 2, 11): "建国記念の日",
         date(y, 3, _equinox(y, 20.8431)): "春分の日", date(y, 4, 29): "昭和の日",
         date(y, 5, 3): "憲法記念日", date(y, 5, 4): "みどりの日", date(y, 5, 5): "こどもの日",
         _nth_monday(y, 7, 3): "海の日", date(y, 8, 11): "山の日", _nth_monday(y, 9, 3): "敬老の日",
         date(y, 9, _equinox(y, 23.2488)): "秋分の日", _nth_monday(y, 10, 2): "スポーツの日",
         date(y, 11, 3): "文化の日", date(y, 11, 23): "勤労感謝の日"}
    if y >= 2020:
        h[date(y, 2, 23)] = "天皇誕生日"
    for d in sorted(h):   # 国民の休日：祝日にはさまれた平日
        mid = d + timedelta(days=1)
        if mid not in h and d + timedelta(days=2) in h and mid.weekday() != 6:
            h[mid] = "国民の休日"
    for d in sorted(h):   # 振替休日：日曜の祝日のあと、最初の祝日でない日
        if d.weekday() == 6:
            sub = d + timedelta(days=1)
            while sub in h:
                sub += timedelta(days=1)
            h[sub] = "振替休日"
    return h


_holiday_cache = {}


def holiday_name(d):
    if d.year not in _holiday_cache:
        _holiday_cache[d.year] = holidays_of(d.year)
    return _holiday_cache[d.year].get(d)


# ---------- 絵 ----------

def month_cells(y, m, week_start):
    """6週ぶんの日付（前後の月の日もふくむ）。"""
    cal = calendar.Calendar(firstweekday=6 if week_start == "sun" else 0)
    days = list(cal.itermonthdates(y, m))
    while len(days) < 42:
        days.append(days[-1] + timedelta(days=1))
    return days


def weekday_color(wd, night):
    """日曜は赤、土曜は青。ふつうの日は None（文字の色 out を使う）。夜は明るめにして読みやすく。"""
    if wd == 6:
        return (255, 140, 150) if night else (226, 72, 96)
    if wd == 5:
        return (140, 180, 255) if night else (64, 120, 220)
    return None


def day_color(d, show_holidays, night):
    if show_holidays and holiday_name(d):
        return weekday_color(6, night)
    return weekday_color(d.weekday(), night)


def render_window(shown, today, selected, week_start, show_holidays, night, hover, face_now, out_now):
    """face_now / out_now: いまのカラー・昼夜での本当の地の色と文字の色（前後の月の日を、地になじませるのに使う）"""
    k = PAL
    im = Image.new("RGB", (W, H), k["face"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W - 1, H - 1], outline=k["out"])
    d.line([(1, 1), (W - 2, 1)], fill=k["light"])
    d.line([(1, 1), (1, H - 2)], fill=k["light"])
    dither_bar(d, 2, 2, W - 3, 11, k["title2"], k["title"])   # 左の明るい色から、右へ網点でなめらかに
    px_pattern(d, 5, 5, _ICONS["cal"], k["light"])
    px_pattern(d, 4, 4, _ICONS["cal"], k["out"])
    px_text(d, 13, 6, "CALENDAR.EXE", k["light"])
    px_text(d, 12, 5, "CALENDAR.EXE", k["out"])
    bx0 = W - 3 - 3 * 9
    for i, icon in enumerate(("min", "max", "close")):
        x0 = bx0 + i * 9
        d.rectangle([x0, 3, x0 + 7, 10], fill=k["hover"] if icon == "close" else k["face"], outline=k["out"])
        px_pattern(d, x0 + 1, 4, _ICONS[icon], k["out"])
    d.line([(1, 12), (W - 2, 12)], fill=k["out"])
    # 見出し：大きな月、小さな年と英語の月
    y, m = shown
    px_text(d, 5, HEAD_Y + 2, str(m), k["accent"], 2)
    mx = 5 + px_text_w(str(m), 2) + 4
    px_text(d, mx, HEAD_Y + 2, MONTH_EN[m - 1], k["out"])
    px_text(d, mx, HEAD_Y + 8, str(y), k["second"])
    for pat, col, ox, oy in MONTH_ICONS[m]:   # 月の小さな絵
        px_pattern(d, 48 + ox, HEAD_Y + 2 + oy, pat, col)
    for key, (x, by, w) in BUTTONS.items():
        fill = k["hover"] if hover == key else k["face"]
        d.rectangle([x, by, x + w - 1, by + 10], fill=fill, outline=k["out"])
        d.line([(x + 1, by + 1), (x + w - 2, by + 1)], fill=k["light"])
        pat = _ICONS[key]
        pw, ph = len(pat.split("|")[0]), len(pat.split("|"))
        px_pattern(d, x + (w - pw) // 2, by + (11 - ph) // 2, pat, k["out"] if hover == key else k["accent"])
    # 曜日
    names = "SMTWTFS" if week_start == "sun" else "MTWTFSS"
    wkd = [6, 0, 1, 2, 3, 4, 5] if week_start == "sun" else [0, 1, 2, 3, 4, 5, 6]
    d.rectangle([GRID_X - 1, WEEK_Y - 1, GRID_X + 7 * CELL_W, WEEK_Y + 5], fill=k["shade"])
    for c in range(7):
        col = weekday_color(wkd[c], night) or k["out"]
        px_text(d, GRID_X + c * CELL_W + (CELL_W - 3) // 2, WEEK_Y, names[c], col)
    # 土日の列を、うっすら色づける
    for c in range(7):
        wc = weekday_color(wkd[c], night)
        if wc:
            x0 = GRID_X + c * CELL_W
            d.rectangle([x0 + 1, GRID_Y - 1, x0 + CELL_W - 2, GRID_Y + 6 * CELL_H - 2], fill=mix(face_now, wc, 0.08))
    # 日付
    for i, day in enumerate(month_cells(y, m, week_start)):
        x0, y0 = GRID_X + (i % 7) * CELL_W, GRID_Y + (i // 7) * CELL_H
        other = day.month != m
        col = day_color(day, show_holidays, night) or k["out"]
        if other:   # 前後の月の日は、地の色になじませて目立たなくする
            col = mix(day_color(day, show_holidays, night) or out_now, face_now, 0.6)
        if day == today:   # 今日のしるし（下にかげ、左上に光）
            d.rectangle([x0 + 1, y0, x0 + CELL_W - 2, y0 + CELL_H - 2], fill=k["accent"])
            d.line([(x0 + 2, y0 + CELL_H - 1), (x0 + CELL_W - 2, y0 + CELL_H - 1)], fill=k["shade"])
            d.point((x0 + 2, y0 + 1), fill=ON_ACCENT)
            col = ON_ACCENT
        if day == selected and day != today:
            d.rectangle([x0 + 1, y0, x0 + CELL_W - 2, y0 + CELL_H - 2], outline=k["accent"])
        s = str(day.day)
        px_text(d, x0 + (CELL_W - px_text_w(s)) // 2, y0 + 2, s, col)
        if show_holidays and not other and holiday_name(day) and day != today:   # 祝日の小さな点
            d.point((x0 + CELL_W // 2, y0 + 8), fill=col)
    d.rectangle([3, CAP_Y - 1, W - 4, CAP_Y + 8], fill=k["light"], outline=k["out"])
    return im


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_PATH, {}))
    return cfg


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


class Calendar:
    def __init__(self):
        self.cfg = load_config()
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.p = Scale(self.cfg["scale"])
        self.today = date.today()
        self.shown = (self.today.year, self.today.month)
        self.selected = self.today
        self.hover = None

        self.root = tk.Tk()
        log_errors(self.root, "calendar_error.txt")
        self.root.title(f"ドットカレンダー ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "calendar.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])
        self.frame_label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.cap = tk.Label(self.root, anchor="w", bd=0)
        for w in (self.root, self.frame_label, self.cap):
            w.bind("<ButtonPress-1>", self.drag_start)
            w.bind("<B1-Motion>", self.drag_move)
            w.bind("<ButtonRelease-1>", self.drag_end)
            w.bind("<Button-3>", self.popup_menu)
            w.bind("<MouseWheel>", lambda e: self.turn(-1 if e.delta > 0 else 1))
        self.frame_label.bind("<Motion>", self.frame_hover, add="+")
        self.frame_label.bind("<Leave>", lambda e: self.set_hover(None), add="+")
        self.frame_label.bind("<ButtonRelease-1>", self.frame_click, add="+")
        self.pmenu = PixelMenu(self.root, self.menu_theme, title="CALENDAR - MENU")
        self.layout()
        self.root.after(30_000, self.watch_day)
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

    def watch_day(self):
        """日付が変わったら、今日のしるしを動かす（今月を見ていたら、新しい月へ）。"""
        today = date.today()
        if today != self.today:
            if self.shown == (self.today.year, self.today.month):
                self.shown = (today.year, today.month)
            if self.selected == self.today:
                self.selected = today
            self.today = today
            self.redraw()
        self.root.after(30_000, self.watch_day)

    # --- 見た目 ---
    def layout(self):
        p = self.p
        self.root.geometry(f"{W * p}x{H * p}+{self.cfg['x']}+{self.cfg['y']}")
        self.frame_label.place(x=0, y=0, width=W * p, height=H * p)
        self.cap.config(bg=hexc(self.col("light")), fg=hexc(self.col("out")),
                        font=ui_font(self.root, max(12, int(p * 5))))
        self.cap.place(x=5 * p, y=CAP_Y * p, width=(W - 10) * p, height=8 * p)
        self.redraw()

    def redraw(self):
        img = render_window(self.shown, self.today, self.selected, self.cfg["week_start"], self.cfg["holidays"],
                            is_night_time(), self.hover, self.col("face"), self.col("out"))
        img = recolor(img, self.cmap()).resize((W * self.p, H * self.p), Image.NEAREST)
        self.frame_photo = ImageTk.PhotoImage(img)
        self.frame_label.config(image=self.frame_photo)
        d = self.selected
        text = f"{d.year}年{d.month}月{d.day}日（{WEEKDAY_JA[d.weekday()]}）"
        name = holiday_name(d) if self.cfg["holidays"] else None
        if name:
            text += f"　{name}"
        if d == self.today:
            text += "　きょう"
        self.cap.config(text=text)

    # --- 操作 ---
    def turn(self, step):
        y, m = self.shown
        m += step
        self.shown = (y + (m - 1) // 12, (m - 1) % 12 + 1)
        self.redraw()

    def go_today(self):
        self.shown = (self.today.year, self.today.month)
        self.selected = self.today
        self.redraw()

    def set_hover(self, key):
        if key != self.hover:
            self.hover = key
            self.redraw()

    # --- メニュー ---
    def menu_items(self):
        c = self.cfg
        return [
            {"type": "cmd", "label": "今月に戻る", "cmd": self.go_today},
            {"type": "sep"},
            {"type": "head", "label": "週のはじまり"},
            {"type": "radio", "label": "日曜日", "checked": c["week_start"] == "sun",
             "cmd": lambda: self.set_cfg(week_start="sun")},
            {"type": "radio", "label": "月曜日", "checked": c["week_start"] == "mon",
             "cmd": lambda: self.set_cfg(week_start="mon")},
            {"type": "sep"},
            {"type": "check", "label": "祝日を赤くする", "checked": c["holidays"],
             "cmd": lambda: self.set_cfg(holidays=not c["holidays"])},
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
            {"type": "head", "label": f"ドットカレンダー ver.{APP_VERSION}"},
        ]

    def popup_menu(self, e):
        self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

    def set_cfg(self, **changes):
        self.cfg.update(changes)
        save_config(self.cfg)
        self.redraw()

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
        if self.hotspot_at_press():   # ボタンや日付の上から始めたときは動かさない
            return
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def drag_end(self, e):
        self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        save_config(self.cfg)

    def hotspot_at_press(self):
        px, py = getattr(self, "_press", (None, None))
        if px is None:
            return None
        return self.hotspot_xy((px - self.root.winfo_rootx()) / self.p, (py - self.root.winfo_rooty()) / self.p)

    def hotspot_at(self, e):
        return self.hotspot_xy((e.x_root - self.root.winfo_rootx()) / self.p,
                               (e.y_root - self.root.winfo_rooty()) / self.p)

    def hotspot_xy(self, x, y):
        bx0 = W - 3 - 3 * 9
        for name, (x0, y0, x1, y1) in {"min": (bx0, 3, bx0 + 7, 10), "close": (bx0 + 18, 3, bx0 + 25, 10)}.items():
            if x0 <= x <= x1 + 1 and y0 <= y <= y1 + 1:
                return name
        for key, (bx, by, w) in BUTTONS.items():
            if bx <= x < bx + w and by <= y < by + 11:
                return key
        c, r = int((x - GRID_X) // CELL_W), int((y - GRID_Y) // CELL_H)
        if x >= GRID_X and y >= GRID_Y and 0 <= c < 7 and 0 <= r < 6:
            return ("day", r * 7 + c)
        return None

    def frame_hover(self, e):
        spot = self.hotspot_at(e)
        self.frame_label.config(cursor="hand2" if spot else "")
        self.set_hover(spot if spot in BUTTONS else None)

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
        elif spot == "prev":
            self.turn(-1)
        elif spot == "next":
            self.turn(1)
        elif spot == "today":
            self.go_today()
        elif isinstance(spot, tuple):
            day = month_cells(*self.shown, self.cfg["week_start"])[spot[1]]
            self.selected = day
            if (day.year, day.month) != self.shown:   # 前後の月の日をクリックしたら、その月へ
                self.shown = (day.year, day.month)
            self.redraw()

    def quit(self):
        save_config(self.cfg)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        Calendar().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "calendar_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
