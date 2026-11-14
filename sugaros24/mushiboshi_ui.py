# -*- coding: utf-8 -*-
"""
SugarOS 24 共通のドット絵UI部品

  PixelMenu   … 右クリックメニュー（サブメニュー付き）
  PixelDialog … 小窓（タイトルバー・閉じるボタン・ドラッグ移動付き）
  ask_text    … 文字を入力してもらう小窓
  pick_items  … 一覧から選んでもらう小窓（絞り込み・複数選択）
  log_errors  … 動いている途中のエラーも、ツールごとの _error.txt に書き残す
  is_night_time / load_weather / load_now_playing … SugarOS 共通の「いまの状態」（昼夜・天気・音楽）
  draw_weather … 窓の外や屋外のシーンに、雨・雪・くもりなどの演出を描く
  PX_FONT / px_text / px_pattern … 3×5 ドットの文字と、ドット絵を描く小さな道具
  load_json / save_json … 設定などの読み書き。保存は別名で書いてから差し替えるので、途中で閉じても壊れない

日本語のドット風フォント「DotGothic16」が入っていれば、それを使う（Google Fonts で無料）。
"""
import json
import math
import os
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageTk

UNIT = 2          # 1ドットの大きさ（px）
FONT_PX = 16      # 文字の大きさ（px）

FONT_CANDIDATES = ("DotGothic16", "PixelMplus12", "PixelMplus10", "BIZ UDGothic", "MS Gothic", "Yu Gothic UI")

_ICONS = {
    "check": ".....#|....##|#..##.|####..|.##...",
    "dot": ".##.|####|####|.##.",
    "arrow": "#...|##..|###.|##..|#...",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
    "up": "..#..|.###.|#####",
    "down": "#####|.###.|..#..",
}

# テーマ（見た目の色）。各ツールの見た目から選ぶ
THEMES = {
    "pixelsns": dict(face=(255, 252, 246), out=(70, 60, 90), light=(255, 255, 255),
                     title=(186, 226, 240), title2=(206, 238, 248), title_text=(70, 60, 90),
                     accent=(240, 96, 140), sub=(150, 140, 168), text=(58, 50, 78),
                     field=(255, 255, 255), select=(240, 96, 140), select_text=(255, 255, 255)),
    "pixelwin": dict(face=(244, 238, 255), out=(64, 48, 92), light=(255, 255, 255),
                     title=(255, 176, 206), title2=(255, 210, 228), title_text=(64, 48, 92),
                     accent=(232, 72, 128), sub=(150, 136, 180), text=(64, 48, 92),
                     field=(255, 255, 255), select=(232, 72, 128), select_text=(255, 255, 255)),
    "freeware": dict(face=(192, 192, 192), out=(0, 0, 0), light=(255, 255, 255),
                     title=(0, 0, 128), title2=(16, 132, 208), title_text=(255, 255, 255),
                     accent=(0, 0, 128), sub=(96, 96, 96), text=(0, 0, 0),
                     field=(255, 255, 255), select=(0, 0, 128), select_text=(255, 255, 255)),
    "pixeltube": dict(face=(236, 246, 242), out=(40, 56, 72), light=(255, 255, 255),
                      title=(140, 218, 196), title2=(186, 238, 222), title_text=(40, 56, 72),
                      accent=(232, 72, 128), sub=(110, 130, 140), text=(40, 56, 72),
                      field=(255, 255, 255), select=(232, 72, 128), select_text=(255, 255, 255)),
    "netradio": dict(face=(44, 48, 64), out=(10, 12, 18), light=(92, 100, 128),
                     title=(58, 64, 84), title2=(70, 76, 98), title_text=(255, 176, 64),
                     accent=(255, 176, 64), sub=(150, 150, 170), text=(232, 232, 240),
                     field=(22, 34, 26), select=(255, 176, 64), select_text=(20, 20, 28)),
    "darkweb": dict(face=(6, 10, 7), out=(0, 150, 72), light=(12, 18, 13),
                    title=(6, 10, 7), title2=(10, 18, 12), title_text=(0, 255, 120),
                    accent=(0, 255, 120), sub=(0, 130, 64), text=(0, 255, 120),
                    field=(2, 6, 3), select=(0, 255, 120), select_text=(0, 0, 0)),
    "notepad": dict(face=(250, 244, 232), out=(76, 58, 50), light=(255, 255, 255),
                    title=(255, 190, 120), title2=(255, 216, 168), title_text=(76, 58, 50),
                    accent=(226, 92, 70), sub=(160, 136, 124), text=(62, 48, 44),
                    field=(255, 252, 240), select=(226, 92, 70), select_text=(255, 255, 255)),
    "sns": dict(face=(255, 252, 246), out=(70, 60, 90), light=(255, 255, 255),
                title=(186, 226, 240), title2=(206, 238, 248), title_text=(70, 60, 90),
                accent=(240, 96, 140), sub=(150, 140, 168), text=(58, 50, 78),
                field=(255, 255, 255), select=(240, 96, 140), select_text=(255, 255, 255)),
}


class Scale(float):
    """ドットの倍率。1.5倍のような半端な倍率でも、整数との掛け算は整数のピクセルにする"""
    def __mul__(self, o):
        r = float(self) * o
        return round(r) if isinstance(o, int) and not isinstance(o, bool) else r

    __rmul__ = __mul__


def hexc(c):
    return "#%02x%02x%02x" % tuple(c)


def mix(c, target, t):
    """c と target を t の割合で混ぜた色。"""
    return tuple(round(a + (b - a) * t) for a, b in zip(c, target))


def vgrad(d, x0, y0, x1, y1, top, bottom):
    """縦のグラデーション。"""
    for y in range(y0, y1 + 1):
        d.line([(x0, y), (x1, y)], fill=mix(top, bottom, (y - y0) / max(1, y1 - y0)))


BAYER = [[0, 2], [3, 1]]   # 2×2 の網点
BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]   # 4×4 の網点


def dither_bar(d, x0, y0, x1, y1, left, right):
    """左は left、右へ行くほど right がふえる網点の帯（タイトルバーなど）。2色だけで描くので、カラーで塗り替えられる。"""
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            t = (x - x0) / max(1, x1 - x0)
            d.point((x, y), fill=right if BAYER4[y % 4][x % 4] / 16 < t else left)


def dither_gradient(d, x0, y0, x1, y1, top, bottom, steps=8):
    """縦のグラデーションを steps 段に分けて、段のあいだを網点でなめらかにつなぐ（ドット絵らしい空や水）。"""
    for y in range(y0, y1 + 1):
        k = (y - y0) / max(1, y1 - y0) * steps
        lo = int(k)
        c1, c2 = mix(top, bottom, lo / steps), mix(top, bottom, min(steps, lo + 1) / steps)
        frac = k - lo
        for x in range(x0, x1 + 1):
            d.point((x, y), fill=c2 if frac * 4 > BAYER[y % 2][x % 2] + 0.5 else c1)


# ---------- ドット文字 ----------

PX_FONT = {   # 3×5 ドットの小さな文字（全ツール共通）
    "A": ".#.|#.#|###|#.#|#.#", "B": "##.|#.#|##.|#.#|##.", "C": ".##|#..|#..|#..|.##",
    "D": "##.|#.#|#.#|#.#|##.", "E": "###|#..|##.|#..|###", "F": "###|#..|##.|#..|#..",
    "G": ".##|#..|#.#|#.#|.##", "H": "#.#|#.#|###|#.#|#.#", "I": "###|.#.|.#.|.#.|###",
    "J": "..#|..#|..#|#.#|.#.", "K": "#.#|#.#|##.|#.#|#.#", "L": "#..|#..|#..|#..|###",
    "M": "#.#|###|###|#.#|#.#", "N": "##.|#.#|#.#|#.#|#.#", "O": ".#.|#.#|#.#|#.#|.#.",
    "P": "##.|#.#|##.|#..|#..", "Q": ".#.|#.#|#.#|##.|.##", "R": "##.|#.#|##.|#.#|#.#",
    "S": ".##|#..|.#.|..#|##.", "T": "###|.#.|.#.|.#.|.#.", "U": "#.#|#.#|#.#|#.#|###",
    "V": "#.#|#.#|#.#|#.#|.#.", "W": "#.#|#.#|###|###|#.#", "X": "#.#|#.#|.#.|#.#|#.#",
    "Y": "#.#|#.#|.#.|.#.|.#.", "Z": "###|..#|.#.|#..|###", "0": "###|#.#|#.#|#.#|###",
    "1": ".#.|##.|.#.|.#.|###", "2": "##.|..#|.#.|#..|###", "3": "##.|..#|.#.|..#|##.",
    "4": "#.#|#.#|###|..#|..#", "5": "###|#..|##.|..#|##.", "6": ".##|#..|###|#.#|###",
    "7": "###|..#|.#.|.#.|.#.", "8": "###|#.#|###|#.#|###", "9": "###|#.#|###|..#|##.",
    " ": "...|...|...|...|...", "!": ".#.|.#.|.#.|...|.#.", "#": "#.#|###|#.#|###|#.#",
    "'": ".#.|.#.|...|...|...", "(": ".#.|#..|#..|#..|.#.", ")": ".#.|..#|..#|..#|.#.",
    "*": "...|#.#|.#.|#.#|...", "+": "...|.#.|###|.#.|...", ",": "...|...|...|.#.|#..",
    "-": "...|...|###|...|...", ".": "...|...|...|...|.#.", "/": "..#|..#|.#.|#..|#..",
    ":": "...|.#.|...|.#.|...", "<": "..#|.#.|#..|.#.|..#", "=": "...|###|...|###|...",
    ">": "#..|.#.|..#|.#.|#..", "?": "##.|..#|.#.|...|.#.", "@": ".#.|#.#|###|#..|.##",
    "[": "##.|#..|#..|#..|##.", "]": ".##|..#|..#|..#|.##", "_": "...|...|...|...|###",
    "~": "...|.#.|#.#|...|...", "°": "##.|##.|...|...|...", "&": ".#.|#.#|.##|#.#|.##",
}


def px_pattern(d, x, y, pat, color, scale=1):
    """pat（"行|行|行" の形）の # の所に点を打つ。scale で大きく描ける。"""
    for ry, row in enumerate(pat.split("|")):
        for rx, ch in enumerate(row):
            if ch == "#":
                if scale == 1:
                    d.point((x + rx, y + ry), fill=color)
                else:
                    d.rectangle([x + rx * scale, y + ry * scale, x + rx * scale + scale - 1,
                                 y + ry * scale + scale - 1], fill=color)


def px_text(d, x, y, text, color, scale=1, max_w=None, missing="?"):
    """3×5 ドットの文字を書く。max_w を超える文字は書かない。書いた幅を返す。"""
    cx = x
    for ch in text.upper():
        if max_w is not None and cx + 3 * scale > x + max_w:
            break
        px_pattern(d, cx, y, PX_FONT.get(ch, PX_FONT[missing]), color, scale)
        cx += 4 * scale
    return cx - x


def px_text_w(text, scale=1):
    return max(0, (len(text) * 4 - 1) * scale)


# ---------- JSON の読み書き ----------

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data, pretty=True):
    """別名（.tmp）に書いてから差し替える。書いている途中でツールを閉じても、元のファイルは壊れない。
    OneDrive などがファイルをつかんでいて差し替えられないときは、少し待ってやり直す。"""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2 if pretty else None)
        for i in range(5):
            try:
                os.replace(tmp, path)
                return True
            except PermissionError:
                time.sleep(0.05 * (i + 1))
    except OSError:
        pass
    finally:
        if os.path.exists(tmp):   # 差し替えられなかった書きかけは残さない
            try:
                os.remove(tmp)
            except OSError:
                pass
    return False


_font_cache = {}


def ui_font(root, size=FONT_PX, bold=False):
    fams = _font_cache.get("fams")
    if fams is None:
        try:
            fams = set(tkfont.families(root))
        except tk.TclError:
            fams = set()
        _font_cache["fams"] = fams
    family = next((f for f in FONT_CANDIDATES if f in fams), "TkDefaultFont")
    return (family, -size, "bold") if bold and family not in ("DotGothic16",) else (family, -size)


def has_dot_font(root):
    ui_font(root)
    return "DotGothic16" in _font_cache.get("fams", set())


_img_cache = {}


def icon_image(name, color, unit=UNIT):
    key = (name, tuple(color), unit)
    if key not in _img_cache:
        rows = _ICONS[name].split("|")
        im = Image.new("RGBA", (len(rows[0]), len(rows)), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for y, row in enumerate(rows):
            for x, c in enumerate(row):
                if c == "#":
                    d.point((x, y), fill=tuple(color) + (255,))
        _img_cache[key] = ImageTk.PhotoImage(im.resize((im.width * unit, im.height * unit), Image.NEAREST))
    return _img_cache[key]


def blank_image(w, h):
    key = ("blank", w, h)
    if key not in _img_cache:
        _img_cache[key] = ImageTk.PhotoImage(Image.new("RGBA", (w, h), (0, 0, 0, 0)))
    return _img_cache[key]


def dither_strip(width, height, c1, c2, unit=UNIT):
    """タイトルバー用の、ドットの市松模様が入った帯。"""
    key = ("strip", width, height, tuple(c1), tuple(c2), unit)
    if key not in _img_cache:
        w, h = max(1, width // unit), max(1, height // unit)
        im = Image.new("RGB", (w, h), tuple(c1))
        d = ImageDraw.Draw(im)
        for y in range(min(3, h)):
            for x in range(y % 2, w, 2):
                d.point((x, y), fill=tuple(c2))
        _img_cache[key] = ImageTk.PhotoImage(im.resize((w * unit, h * unit), Image.NEAREST))
    return _img_cache[key]


def framed(parent, t, thickness=UNIT, bg=None):
    """ドットの線で囲んだ枠。中身を入れる Frame を返す。"""
    outer = tk.Frame(parent, bg=hexc(t["out"]), padx=thickness, pady=thickness, bd=0, highlightthickness=0)
    inner = tk.Frame(outer, bg=hexc(bg or t["face"]), bd=0, highlightthickness=0)
    inner.pack(fill="both", expand=True)
    return outer, inner


class PixelButton:
    """ドットの線で囲んだボタン。マウスを乗せると色が変わる。"""
    def __init__(self, parent, t, text, command, root=None, primary=False, width=None):
        self.t, self.command = t, command
        self.outer, inner = framed(parent, t)
        self.normal = t["select"] if primary else t["face"]
        self.normal_fg = t["select_text"] if primary else t["text"]
        self.label = tk.Label(inner, text=text, bg=hexc(self.normal), fg=hexc(self.normal_fg),
                              font=ui_font(root or parent), padx=10, pady=2, cursor="hand2",
                              width=width or 0)
        self.label.pack(fill="both", expand=True)
        self.label.bind("<Enter>", lambda e: self.label.config(bg=hexc(t["title"]), fg=hexc(t["title_text"])))
        self.label.bind("<Leave>", lambda e: self.label.config(bg=hexc(self.normal), fg=hexc(self.normal_fg)))
        self.label.bind("<Button-1>", lambda e: self.command())

    def pack(self, **kw):
        self.outer.pack(**kw)
        return self


# ---------- メニュー ----------

class PixelMenu:
    """
    items はリスト、またはリストを返す関数。各項目は dict:
      {"type": "cmd",   "label": ..., "cmd": 関数, "right": "右側に出す文字", "enabled": True}
      {"type": "check", "label": ..., "checked": bool, "cmd": 関数}
      {"type": "radio", "label": ..., "checked": bool, "cmd": 関数}
      {"type": "sub",   "label": ..., "items": リスト or 関数, "right": "今の設定など"}
      {"type": "head",  "label": ...}   … 小さな見出し
      {"type": "sep"}                   … 区切り線
    """
    def __init__(self, root, theme_fn, title="MENU"):
        self.root = root
        self.theme_fn = theme_fn
        self.title = title
        self.levels = []

    # 開く・閉じる
    def popup(self, items, x, y, above=False):
        """above=True なら、(x, y) を左下にして上向きに開く（スタートメニュー用）。"""
        self.close_all()
        self.t = self.theme_fn()
        self._above = above
        self._open_level(items, x, y, title=self.title)

    def close_all(self):
        for lv in reversed(self.levels):
            try:
                lv["win"].grab_release()
            except tk.TclError:
                pass
            try:
                lv["win"].destroy()
            except tk.TclError:
                pass
        self.levels = []

    def _close_from(self, depth):
        while len(self.levels) > depth:
            lv = self.levels.pop()
            try:
                lv["win"].destroy()
            except tk.TclError:
                pass

    def _open_level(self, items, x, y, title=None, parent_row=None):
        t = self.t
        if callable(items):
            items = items()
        master = self.levels[0]["win"] if self.levels else self.root
        win = tk.Toplevel(master)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=hexc(t["out"]))
        outer, inner = framed(win, t)
        outer.pack(fill="both", expand=True)
        if title:
            bar = tk.Label(inner, text=title, bg=hexc(t["title"]), fg=hexc(t["title_text"]),
                           font=ui_font(self.root, 13), anchor="w", padx=8, pady=1)
            bar.pack(fill="x")
            tk.Frame(inner, bg=hexc(t["out"]), height=UNIT).pack(fill="x")
        body = tk.Frame(inner, bg=hexc(t["face"]), padx=UNIT * 2, pady=UNIT * 2)
        body.pack(fill="both", expand=True)
        depth = len(self.levels)
        level = {"win": win, "rows": []}
        self.levels.append(level)
        for it in items:
            self._add_row(body, it, depth, level)

        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        if parent_row is not None and x + w > sw:
            x = parent_row.winfo_rootx() - w + UNIT * 2
        if getattr(self, "_above", False):   # 上向きに開くメニューは、サブメニューも上へ伸ばす
            y = y - h
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        win.geometry(f"+{x}+{y}")
        if depth == 0:
            win.bind("<ButtonPress>", self._on_press_anywhere, add="+")
            win.bind("<Escape>", lambda e: self.close_all())
            win.after(10, lambda: self._grab(win))
        return win

    def _grab(self, win):
        try:
            win.focus_force()
            win.grab_set()
        except tk.TclError:
            pass

    def _on_press_anywhere(self, e):
        px, py = e.x_root, e.y_root
        for lv in self.levels:
            w = lv["win"]
            try:
                x0, y0 = w.winfo_rootx(), w.winfo_rooty()
                if x0 <= px < x0 + w.winfo_width() and y0 <= py < y0 + w.winfo_height():
                    return
            except tk.TclError:
                continue
        self.close_all()

    def _add_row(self, body, it, depth, level):
        t = self.t
        kind = it.get("type", "cmd")
        if kind == "sep":
            tk.Frame(body, bg=hexc(t["face"]), height=UNIT * 2).pack(fill="x")
            tk.Frame(body, bg=hexc(t["sub"]), height=UNIT).pack(fill="x", padx=UNIT * 2)
            tk.Frame(body, bg=hexc(t["face"]), height=UNIT * 2).pack(fill="x")
            return
        if kind == "head":
            tk.Label(body, text=it["label"], bg=hexc(t["face"]), fg=hexc(t["sub"]),
                     font=ui_font(self.root, 12), anchor="w", padx=UNIT * 2).pack(fill="x", pady=(UNIT, 0))
            return
        enabled = it.get("enabled", True)
        fg = t["text"] if enabled else t["sub"]
        row = tk.Frame(body, bg=hexc(t["face"]), cursor="hand2" if enabled else "")
        row.pack(fill="x")
        mark = tk.Label(row, bg=hexc(t["face"]), width=18, image=blank_image(12, 10))
        if kind == "check" and it.get("checked"):
            mark.config(image=icon_image("check", t["accent"]))
        elif kind == "radio" and it.get("checked"):
            mark.config(image=icon_image("dot", t["accent"]))
        mark.pack(side="left", padx=(UNIT, 0))
        label = tk.Label(row, text=it["label"], bg=hexc(t["face"]), fg=hexc(fg),
                         font=ui_font(self.root), anchor="w", padx=UNIT * 2, pady=UNIT)
        label.pack(side="left", fill="x", expand=True)
        right = None
        if kind == "sub":
            right = tk.Label(row, image=icon_image("arrow", t["text"]), bg=hexc(t["face"]), padx=UNIT * 3)
            right.pack(side="right")
        r2 = None
        if it.get("right"):
            r2 = tk.Label(row, text=it["right"], bg=hexc(t["face"]), fg=hexc(t["sub"]),
                          font=ui_font(self.root, 13), padx=UNIT * 2)
            r2.pack(side="right")
        parts = [w for w in row.winfo_children()] + [row]
        info = {"row": row, "parts": parts, "item": it, "kind": kind, "enabled": enabled,
                "label": label, "fg": fg, "right": right, "right_text": r2}
        level["rows"].append(info)

        def enter(_e):
            self._highlight(level, info)
            if not enabled:
                return
            self._close_from(depth + 1)
            if kind == "sub":
                self._open_sub(info, depth)

        def click(_e):
            if not enabled or kind == "sub":
                return
            self.close_all()
            cmd = it.get("cmd")
            if cmd:
                self.root.after(1, cmd)

        for w in parts:
            w.bind("<Enter>", enter)
            w.bind("<Button-1>", click)

    def _highlight(self, level, info):
        t = self.t
        for r in level["rows"]:
            on = r is info and r["enabled"]
            bg = hexc(t["select"] if on else t["face"])
            for w in r["parts"]:
                try:
                    w.config(bg=bg)
                except tk.TclError:
                    pass
            r["label"].config(fg=hexc(t["select_text"] if on else r["fg"]))
            if r["right"] is not None:
                r["right"].config(image=icon_image("arrow", t["select_text"] if on else t["text"]))
            if r["right_text"] is not None:
                r["right_text"].config(fg=hexc(t["select_text"] if on else t["sub"]))

    def _open_sub(self, info, depth):
        row = info["row"]
        win = self.levels[depth]["win"]
        x = win.winfo_rootx() + win.winfo_width() - UNIT
        y = row.winfo_rooty() - UNIT * 3
        if getattr(self, "_above", False):
            y = row.winfo_rooty() + row.winfo_height() + UNIT * 3
        self._open_level(info["item"]["items"], x, y, title=info["item"]["label"], parent_row=win)


# ---------- 小窓 ----------

class PixelDialog:
    """ドット絵のタイトルバーが付いた小窓。body に中身を入れて、add_button でボタンを並べる。"""
    def __init__(self, root, theme, title, near=None):
        self.root, self.t = root, theme
        t = theme
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=hexc(t["out"]))
        outer, inner = framed(self.win, t, thickness=UNIT)
        outer.pack(fill="both", expand=True)
        bar = tk.Frame(inner, bg=hexc(t["title"]))
        bar.pack(fill="x")
        self.title_label = tk.Label(bar, text=title, bg=hexc(t["title"]), fg=hexc(t["title_text"]),
                                    font=ui_font(root, 14), anchor="w", padx=8, pady=3)
        self.title_label.pack(side="left", fill="x", expand=True)
        close_box, close_in = framed(bar, t, bg=t["face"])
        close_box.pack(side="right", padx=4, pady=3)
        close = tk.Label(close_in, image=icon_image("close", t["text"]), bg=hexc(t["face"]),
                         cursor="hand2", padx=3, pady=3)
        close.pack()
        close.bind("<Button-1>", lambda e: self.close())
        tk.Frame(inner, bg=hexc(t["out"]), height=UNIT).pack(fill="x")
        for w in (bar, self.title_label):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
        self.body = tk.Frame(inner, bg=hexc(t["face"]), padx=12, pady=10)
        self.body.pack(fill="both", expand=True)
        self.btns = tk.Frame(inner, bg=hexc(t["face"]), padx=12)
        self.btns.pack(fill="x", pady=(0, 10))
        self.win.bind("<Escape>", lambda e: self.close())
        self.result = None
        self.near = near

    def _drag_start(self, e):
        self._dx = e.x_root - self.win.winfo_x()
        self._dy = e.y_root - self.win.winfo_y()

    def _drag_move(self, e):
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def label(self, text, sub=False, **kw):
        t = self.t
        lb = tk.Label(self.body, text=text, bg=hexc(t["face"]), fg=hexc(t["sub"] if sub else t["text"]),
                      font=ui_font(self.root, 13 if sub else FONT_PX), justify="left", anchor="w",
                      wraplength=kw.pop("wraplength", 380), **kw)
        lb.pack(fill="x", pady=(0, 6))
        return lb

    def entry(self, var):
        t = self.t
        box, inner = framed(self.body, t, bg=t["field"])
        box.pack(fill="x", pady=(0, 6))
        e = tk.Entry(inner, textvariable=var, bg=hexc(t["field"]), fg=hexc(t["text"]),
                     insertbackground=hexc(t["text"]), relief="flat", bd=4,
                     font=ui_font(self.root), highlightthickness=0)
        e.pack(fill="x")
        return e

    def listbox(self, height=14, width=34, multi=True):
        t = self.t
        box, inner = framed(self.body, t, bg=t["field"])
        box.pack(fill="both", expand=True, pady=(0, 6))
        lb = tk.Listbox(inner, selectmode="extended" if multi else "browse", height=height, width=width,
                        bg=hexc(t["field"]), fg=hexc(t["text"]), relief="flat", bd=4,
                        selectbackground=hexc(t["select"]), selectforeground=hexc(t["select_text"]),
                        activestyle="none", exportselection=False, highlightthickness=0,
                        font=ui_font(self.root))
        lb.pack(side="left", fill="both", expand=True)
        self._scroll_buttons(inner, lb)
        return lb

    def text(self, height=20, width=52):
        t = self.t
        box, inner = framed(self.body, t, bg=t["field"])
        box.pack(fill="both", expand=True, pady=(0, 6))
        tx = tk.Text(inner, wrap="char", height=height, width=width, bg=hexc(t["field"]),
                     fg=hexc(t["text"]), relief="flat", bd=0, padx=10, pady=8, highlightthickness=0,
                     insertbackground=hexc(t["text"]), font=ui_font(self.root),
                     selectbackground=hexc(t["select"]), selectforeground=hexc(t["select_text"]))
        tx.pack(side="left", fill="both", expand=True)
        self._scroll_buttons(inner, tx)
        return tx

    def _scroll_buttons(self, parent, widget):
        """ドット絵の ▲▼ ボタン（ホイールでも動く）。"""
        t = self.t
        col = tk.Frame(parent, bg=hexc(t["face"]))
        col.pack(side="right", fill="y")
        tk.Frame(col, bg=hexc(t["out"]), width=UNIT).pack(side="left", fill="y")
        inner = tk.Frame(col, bg=hexc(t["face"]))
        inner.pack(side="left", fill="y")
        for name, step in (("up", -3), ("down", 3)):
            b = tk.Label(inner, image=icon_image(name, t["text"]), bg=hexc(t["face"]),
                         cursor="hand2", padx=4, pady=6)
            b.pack(side="top" if name == "up" else "bottom")
            b.bind("<Button-1>", lambda e, s=step: widget.yview_scroll(s, "units"))

    def add_button(self, text, command, primary=False):
        PixelButton(self.btns, self.t, text, command, root=self.root, primary=primary).pack(side="right", padx=(6, 0))

    def show(self, focus=None):
        self.win.update_idletasks()
        if self.near is not None:
            x, y = self.near.winfo_x() + 24, self.near.winfo_y() + 24
        else:
            x = (self.win.winfo_screenwidth() - self.win.winfo_reqwidth()) // 2
            y = (self.win.winfo_screenheight() - self.win.winfo_reqheight()) // 3
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        x = max(0, min(x, sw - self.win.winfo_reqwidth()))
        y = max(0, min(y, sh - self.win.winfo_reqheight()))
        self.win.geometry(f"+{x}+{y}")
        self.win.lift()

        def grab_focus():
            try:
                self.win.focus_force()
                if focus is not None:
                    focus.focus_set()
            except tk.TclError:
                pass
        self.win.after(60, grab_focus)

    def close(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def wait(self):
        self.win.wait_window()
        return self.result


def ask_text(root, theme, title, message, initial="", near=None):
    """文字を入力してもらう。キャンセルなら None。"""
    dlg = PixelDialog(root, theme, title, near=near)
    dlg.label(message)
    var = tk.StringVar(value=initial)
    e = dlg.entry(var)
    e.select_range(0, "end")

    def ok(*_):
        dlg.result = var.get()
        dlg.close()
    e.bind("<Return>", ok)
    dlg.add_button("キャンセル", dlg.close)
    dlg.add_button("OK", ok, primary=True)
    dlg.show(focus=e)
    return dlg.wait()


def pick_items(root, theme, title, message, entries, near=None, ok_label="追加する"):
    """
    entries: [(値, 表示する文字, すでに選ばれているか), ...]
    選ばれた値のリストを返す（キャンセルなら []）。
    """
    dlg = PixelDialog(root, theme, title, near=near)
    dlg.label(message)
    dlg.label("文字を入れると絞り込めるよ。Ctrl / Shift で複数選べるよ", sub=True)
    query = tk.StringVar()
    e = dlg.entry(query)
    lb = dlg.listbox()
    shown = []

    def refill(*_):
        q = query.get().strip().lower()
        lb.delete(0, "end")
        shown.clear()
        for value, text, on in entries:
            if q in str(text).lower():
                lb.insert("end", ("✓ " if on else "　") + text)
                shown.append(value)

    def ok(*_):
        dlg.result = [shown[i] for i in lb.curselection()]
        dlg.close()

    query.trace_add("write", refill)
    lb.bind("<Double-Button-1>", ok)
    e.bind("<Return>", ok)
    dlg.add_button("キャンセル", dlg.close)
    dlg.add_button(ok_label, ok, primary=True)
    refill()
    dlg.show(focus=e)
    return dlg.wait() or []


def show_message(root, theme, title, message, near=None):
    dlg = PixelDialog(root, theme, title, near=near)
    dlg.label(message)
    dlg.add_button("OK", dlg.close, primary=True)
    dlg.show()
    return dlg


# ---------- エラーの記録 ----------

def log_errors(root, filename):
    """ボタンやアニメの途中で起きたエラーを filename（ツールと同じフォルダ）に書き残す。
    .pyw は画面に何も出ないので、これがないと「押しても何も起きない」だけに見える。
    同じエラーが何度も起きても、1回起動しているあいだは1回だけ書く。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    seen = set()

    def report(exc, val, tb):
        detail = "".join(traceback.format_exception(exc, val, tb))
        if detail in seen:
            return
        seen.add(detail)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 動いている途中のエラー\n{detail}\n")
        except OSError:
            pass

    root.report_callback_exception = report


# ---------- 昼と夜（全ツール共通） ----------

TIME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mushiboshi_time.json")
# mode: auto=時刻どおり / day=いつも昼 / night=いつも夜。day・night は切り替わる時（0〜23時）
# wallpaper: 壁紙も切り替えるか。wall_day / wall_night: 壁紙の画像
DEFAULT_TIME = {"mode": "auto", "day": 6, "night": 19, "wallpaper": False, "wall_day": "", "wall_night": ""}
_time_cache = [0.0, None]


def load_time_settings():
    """ランチャーで決めた昼夜の設定。何度も呼ばれるので、2秒のあいだは読み直さない。"""
    now = time.time()
    if _time_cache[1] is None or now - _time_cache[0] > 2:
        cfg = dict(DEFAULT_TIME)
        try:
            with open(TIME_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, ValueError):
            pass
        _time_cache[:] = [now, cfg]
    return dict(_time_cache[1])


def save_time_settings(cfg):
    save_json(TIME_PATH, cfg)
    _time_cache[:] = [time.time(), dict(cfg)]


def is_night_time():
    """今が夜かどうか。全ツールがこれを見て、窓の色や水槽の照明を切り替える。"""
    cfg = load_time_settings()
    if cfg["mode"] in ("day", "night"):
        return cfg["mode"] == "night"
    h, day, night = time.localtime().tm_hour, cfg["day"], cfg["night"]
    return not (day <= h < night) if day < night else night <= h < day


# ---------- 天気（全ツール共通） ----------

WEATHER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mushiboshi_weather.json")
WEATHER_KINDS = [("はれ", "clear"), ("はれときどきくもり", "partly"), ("くもり", "cloudy"), ("あめ", "rain"),
                 ("かみなり", "thunder"), ("ゆき", "snow"), ("きり", "fog")]
WEATHER_STALE = 3 * 3600   # お天気ツールがこれより長く更新していなければ、天気はわからないことにする
_weather_cache = [0.0, None]


def load_weather():
    """お天気ツールが書いた今の天気（clear / partly / cloudy / rain / thunder / snow / fog）。わからないときは None。"""
    now = time.time()
    if now - _weather_cache[0] > 2:
        try:
            with open(WEATHER_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        _weather_cache[:] = [now, data]
    data = _weather_cache[1] or {}
    if now - data.get("updated", 0) > WEATHER_STALE:
        return None
    kind = data.get("kind")
    return kind if kind in {k for _, k in WEATHER_KINDS} else None


def save_weather(info):
    """お天気ツールだけが使う。info: {"kind": ..., "temp": ..., "place": ...}"""
    data = dict(info, updated=time.time())
    save_json(WEATHER_PATH, data, pretty=False)
    _weather_cache[:] = [time.time(), data]


# ---------- 再生中の音楽（全ツール共通） ----------

MUSIC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mushiboshi_music.json")
MUSIC_STALE = 15   # レコードは再生中ずっと数秒おきに書き直す。止まったまま閉じられても、これで「止まった」になる
_music_cache = [0.0, None]


def save_now_playing(playing, title="", color=None):
    """レコードだけが使う。playing: 音が聞こえているか。color: 今のレコードのラベルの色。"""
    data = {"playing": bool(playing), "title": title, "color": list(color) if color else None, "updated": time.time()}
    save_json(MUSIC_PATH, data, pretty=False)
    _music_cache[:] = [time.time(), data]


def load_now_playing():
    """いま音楽が流れていれば {"title": ..., "color": ...}。流れていなければ None。"""
    now = time.time()
    if now - _music_cache[0] > 1:
        try:
            with open(MUSIC_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        _music_cache[:] = [now, data]
    data = _music_cache[1] or {}
    if not data.get("playing") or now - data.get("updated", 0) > MUSIC_STALE:
        return None
    return data


_WEATHER_TINT = {"cloudy": ((150, 156, 172), 0.25), "rain": ((104, 114, 138), 0.38),
                 "thunder": ((64, 66, 92), 0.5), "snow": ((220, 226, 238), 0.3), "fog": ((214, 218, 226), 0.55)}


def draw_weather(im, box, kind, t, night=False):
    """im の box（x0, y0, x1, y1。両端を含む）の中に天気の演出を描く。はれ・不明なら何もしない。
    空がくすんで、雨なら斜めの雨つぶ、雪ならふわふわ落ちる雪、霧なら流れるもや。"""
    if kind not in _WEATHER_TINT:
        return
    x0, y0, x1, y1 = box
    w, h = x1 - x0 + 1, y1 - y0 + 1
    region = im.crop((x0, y0, x1 + 1, y1 + 1)).convert("RGB")
    tint, a = _WEATHER_TINT[kind]
    if night:
        tint = mix(tint, (20, 24, 50), 0.6)
    region = Image.blend(region, Image.new("RGB", (w, h), tint), a)
    d = ImageDraw.Draw(region)
    if kind in ("rain", "thunder"):
        drop = (120, 140, 190) if night else (196, 212, 236)
        for i in range(max(6, w * h // 45)):
            sp = 34 + (i * 7) % 16                       # 1秒に落ちるドット数
            y = (i * 41 + t * sp) % (h + 6) - 3
            x = (i * 29 + i * i * 3 - y * 0.35) % w      # 少し斜めに降る
            d.line([(x, y), (x - 1, y + 2)], fill=drop)
        if kind == "thunder" and t % 7 < 0.18:           # ときどき稲光
            region = Image.blend(region, Image.new("RGB", (w, h), (250, 250, 255)), 0.55)
    elif kind == "snow":
        flake = (220, 226, 245) if night else (255, 255, 255)
        for i in range(max(5, w * h // 70)):
            y = (i * 37 + t * (5 + i % 5)) % (h + 2) - 1
            x = (i * 29 + i * i * 5 + math.sin(t * 1.3 + i) * 2) % w
            d.point((x, y), fill=flake)
            if i % 4 == 0:
                d.point((x + 1, y), fill=flake)
    elif kind == "fog":
        mist = (150, 156, 176) if night else (240, 242, 246)
        for k in range(4):
            y = (k * h // 4 + 2 + math.sin(t * 0.3 + k) * 2) % h
            for x in range(w):
                if math.sin((x + t * (3 + k)) / 4 + k * 2) > 0.2:
                    d.point((x, y), fill=mist)
    im.paste(region, (x0, y0))


# ---------- カラー（全ツール共通の配色） ----------

COLORWAY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mushiboshi_color.json")

# 各色の基本の色。title=帯の色 / title2=帯の模様 / accent=差し色 / hover=淡い差し色
COLORWAYS = {
    "blue":   dict(face=(238, 242, 252), out=(50, 44, 108), title=(118, 150, 226), title2=(164, 190, 240),
                   accent=(236, 96, 104), hover=(255, 216, 214), shade=(186, 196, 232)),
    "mint":   dict(face=(238, 250, 245), out=(60, 56, 92), title=(140, 220, 192), title2=(192, 240, 222),
                   accent=(226, 70, 158), hover=(248, 210, 236), shade=(180, 222, 208)),
    "pink":   dict(face=(255, 241, 247), out=(82, 44, 86), title=(240, 146, 190), title2=(250, 196, 222),
                   accent=(52, 170, 112), hover=(206, 242, 222), shade=(236, 196, 214)),
    "orange": dict(face=(255, 245, 234), out=(70, 50, 112), title=(242, 140, 84), title2=(250, 190, 140),
                   accent=(84, 108, 206), hover=(220, 228, 252), shade=(236, 206, 180)),
}
COLORWAY_NAMES = [("オリジナル", "original"), ("ブルー", "blue"), ("ミント", "mint"),
                  ("ピンク", "pink"), ("オレンジ", "orange")]


NIGHT_INK = (22, 20, 44)   # 夜の窓の地に混ぜる、深い紺


def _to_night(cw):
    """昼の基本の色から、夜の色を作る。地は暗く、文字とフチは明るくなる。色味（ブルー・ミントなど）は残す。"""
    return dict(cw,
                face=mix(cw["title"], NIGHT_INK, 0.82), shade=mix(cw["title"], (8, 8, 20), 0.9),
                light=mix(cw["title"], NIGHT_INK, 0.6), field=mix(cw["title"], NIGHT_INK, 0.9),
                title=mix(cw["title"], NIGHT_INK, 0.55), title2=mix(cw["title2"], NIGHT_INK, 0.62),
                out=mix(cw["title2"], (255, 255, 255), 0.55), accent=mix(cw["accent"], (255, 255, 255), 0.15),
                hover=mix(cw["accent"], NIGHT_INK, 0.6))


def colorway_full(name, base=None):
    """基本の色から、文字色・罫線などの派生色まで揃えた辞書。夜なら夜の色になる。
    オリジナルは、そのツールの元の色（base: {元の色: 役割}）を基本の色にする。"""
    if name in COLORWAYS:
        cw = dict(COLORWAYS[name])
    else:
        cw = dict(COLORWAYS["blue"])
        cw.update({role: tuple(src) for src, role in (base or {}).items() if role in cw})
    cw.setdefault("light", (255, 255, 255))
    cw.setdefault("field", (255, 255, 255))
    if is_night_time():
        cw = _to_night(cw)
    cw["text"] = cw["out"]
    cw["meta"] = mix(cw["out"], cw["face"], 0.45)
    cw["paper"] = mix(cw["face"], cw["light"], 0.5)
    cw["rule"] = mix(cw["title2"], cw["light"], 0.35)
    cw["margin"] = mix(cw["accent"], cw["light"], 0.5)
    cw["second"] = mix(cw["title"], cw["out"], 0.25)
    return cw


def colorway_cmap(base, name, shades=(0.88,)):
    """base: {元の色: 役割}。今のカラーと昼夜に合わせた置き換え表。オリジナルの昼は None（塗り替えない）。
    shades: ボタンの影など、元の色を暗くした色もいっしょに置き換える割合。"""
    night = is_night_time()
    if not base or (name == "original" and not night):
        return None
    cw = colorway_full(name, base)
    cmap = {tuple(src): cw[role] for src, role in base.items() if role in cw}
    for f in shades:
        cmap.update({tuple(round(v * f) for v in src): tuple(round(v * f) for v in cw[role])
                     for src, role in base.items() if role in cw})
    if night:
        cmap.setdefault((255, 255, 255), cw["light"])   # 白いハイライトも夜の色に
    return cmap


def load_colorway():
    try:
        with open(COLORWAY_PATH, encoding="utf-8") as f:
            name = json.load(f).get("colorway", "original")
    except (OSError, ValueError):
        name = "original"
    return name if name in COLORWAYS else "original"


def save_colorway(name):
    save_json(COLORWAY_PATH, {"colorway": name}, pretty=False)


def make_colormap(base, name):
    """base: {元の色: 役割}。元の色 → カラーの色、の置き換え表を作る（ボタンの影などの派生色も含む）。"""
    night = is_night_time()
    if not base or (name not in COLORWAYS and not night):
        return None
    cw = colorway_full(name, base)
    cmap = {(255, 255, 255): cw["light"]} if night else {}
    for src, role in base.items():
        dst = cw.get(role)
        if dst is None:
            continue
        cmap[tuple(src)] = tuple(dst)
        for f in (0.85, 0.88):
            cmap.setdefault(tuple(round(v * f) for v in src), tuple(round(v * f) for v in dst))
        cmap.setdefault(mix(src, (0, 0, 0), 0.12), mix(dst, (0, 0, 0), 0.12))
    return cmap


def recolor(im, cmap):
    """画像の色を置き換え表どおりに塗り替える（ドット絵なので色はぴったり一致する）。"""
    if not cmap:
        return im
    im = im.convert("RGB")
    im.putdata([cmap.get(px, px) for px in im.getdata()])
    return im


def recolor_dict(d, cmap):
    """skin の色の辞書を塗り替える。"""
    if not cmap:
        return d
    out = {}
    for k, v in d.items():
        if isinstance(v, tuple) and len(v) == 3 and all(isinstance(x, int) for x in v):
            out[k] = cmap.get(v, v)
        else:
            out[k] = v
    return out


def colorway_theme(name, base=None):
    """メニューや小窓の色。"""
    cw = colorway_full(name, base)
    return dict(face=cw["face"], out=cw["out"], light=cw["light"], title=cw["title"], title2=cw["title2"],
                title_text=cw["out"], accent=cw["accent"], sub=cw["meta"], text=cw["out"],
                field=cw["field"], select=cw["accent"], select_text=(255, 255, 255))


def colorway_menu(current, apply, supported=True):
    """カラーのサブメニュー。apply(name) を呼ぶ。"""
    items = []
    if not supported:
        items.append({"type": "head", "label": "今の見た目は、色が変わらないタイプだよ"})
    items += [{"type": "radio", "label": n, "checked": current == k, "cmd": lambda k=k: apply(k)}
              for n, k in COLORWAY_NAMES]
    items += [{"type": "sep"}, {"type": "head", "label": "全ツール共通。数秒でみんな着替えるよ"}]
    return items
