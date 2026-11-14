# -*- coding: utf-8 -*-
"""
ドットマインスイーパ ver.1.1（MINES.EXE）
SugarOS 24 のミニゲーム。真ん中はおなじみのにこちゃんボタン。

遊び方:
  左クリック   … マスを開ける（最初の1マスは必ず安全）
  右クリック   … 旗を立てる／外す
  数字をクリック … まわりの旗が数字と同じなら、残りをまとめて開ける
  顔ボタン     … やり直し
  GAME / 右クリック（盤面の外） … メニュー（むずかしさ、ベストタイム、カラー、サイズ など）

必要なもの: pip install pillow
"""
import os
import random
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from mushiboshi_ui import (COLORWAY_NAMES, dither_bar, log_errors, is_night_time, PixelMenu, colorway_cmap, colorway_menu,
                           colorway_theme, load_colorway, recolor, save_colorway, Scale, PX_FONT, mix, px_pattern,
                           px_text, load_json, save_json)

APP_VERSION = "1.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "minesweeper_config.json")

LEVELS = [("かんたん", "easy", 9, 9, 10), ("ふつう", "normal", 16, 16, 40), ("むずかしい", "hard", 30, 16, 99)]
SCALES = [("ミニ", 1.5), ("小", 2), ("中", 3), ("大", 4)]
DEFAULT_CONFIG = {"level": "easy", "scale": 3, "topmost": False, "x": 300, "y": 140, "best": {}}

_ICONS = {
    "bomb": ".....#.|..###.#|.#####.|###.###|#######|.#####.|..###..",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
    "down": "#####|.###.|..#..",
}
# 7セグ風の大きい数字（3×5 を 2倍）
NUM_COLORS = {1: (64, 96, 224), 2: (40, 150, 80), 3: (226, 64, 92), 4: (60, 48, 160),
              5: (150, 50, 70), 6: (30, 140, 150), 7: (40, 30, 48), 8: (130, 120, 140)}

PAL = dict(face=(240, 236, 248), out=(60, 44, 84), light=(255, 255, 255), shade=(200, 192, 222),
           title=(196, 180, 232), title2=(222, 212, 244), accent=(236, 88, 130), hover=(255, 214, 228),
           second=(130, 112, 180))
COLOR_BASE = {v: k for k, v in PAL.items() if k != "light"}
LCD_BG, LCD_FG = (40, 30, 52), (255, 110, 160)

C = 9          # 1マスの大きさ（ドット）
TOP = 13       # タイトルバーの下
PANEL_H = 30
FACE = 26


def bevel(d, x0, y0, x1, y1, up=True, fill=None):
    k = PAL
    if fill is not None:
        d.rectangle([x0, y0, x1, y1], fill=fill)
    a, b = (k["light"], k["shade"]) if up else (k["shade"], k["light"])
    d.line([(x0, y0), (x1, y0)], fill=a)
    d.line([(x0, y0), (x0, y1)], fill=a)
    d.line([(x0, y1), (x1, y1)], fill=b)
    d.line([(x1, y0), (x1, y1)], fill=b)


# ---------- 顔ボタン（にこちゃん） ----------
FACE_OUT, FACE_Y, FACE_S = (60, 44, 84), (255, 214, 92), (236, 168, 60)


def smiley(mood):
    im = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([2, 2, 21, 21], fill=FACE_Y, outline=FACE_OUT)
    o = FACE_OUT
    if mood == "win":      # サングラス
        d.rectangle([5, 8, 10, 11], fill=o)
        d.rectangle([13, 8, 18, 11], fill=o)
        d.line([(3, 8), (20, 8)], fill=o)
        d.point((6, 9), fill=(255, 255, 255))
        d.point((14, 9), fill=(255, 255, 255))
        d.arc([7, 11, 16, 17], 20, 160, fill=o)
    elif mood == "lose":   # ×目
        for cx in (8, 15):
            d.line([(cx - 2, 7), (cx + 1, 10)], fill=o)
            d.line([(cx + 1, 7), (cx - 2, 10)], fill=o)
        d.arc([7, 14, 16, 20], 200, 340, fill=o)
    else:
        d.rectangle([7, 8, 8, 10], fill=o)
        d.rectangle([15, 8, 16, 10], fill=o)
        if mood == "oh":
            d.ellipse([10, 13, 13, 17], fill=o)
        else:
            d.arc([7, 10, 16, 17], 20, 160, fill=o)
    return im


# ---------- 盤面 ----------

class Board:
    def __init__(self, cols, rows, mines):
        self.cols, self.rows, self.mines = cols, rows, mines
        self.mine = [[False] * cols for _ in range(rows)]
        self.open = [[False] * cols for _ in range(rows)]
        self.flag = [[False] * cols for _ in range(rows)]
        self.placed = False
        self.state = "ready"     # ready / play / win / lose
        self.boom = None
        self.t0 = None
        self.t1 = None

    def neighbors(self, x, y):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dx or dy) and 0 <= x + dx < self.cols and 0 <= y + dy < self.rows:
                    yield x + dx, y + dy

    def count(self, x, y):
        return sum(self.mine[ny][nx] for nx, ny in self.neighbors(x, y))

    def place(self, sx, sy):
        safe = {(sx, sy)} | set(self.neighbors(sx, sy))
        cells = [(x, y) for y in range(self.rows) for x in range(self.cols) if (x, y) not in safe]
        for x, y in random.sample(cells, min(self.mines, len(cells))):
            self.mine[y][x] = True
        self.placed = True
        self.state = "play"
        self.t0 = time.time()

    def reveal(self, x, y):
        if self.state in ("win", "lose") or self.flag[y][x] or self.open[y][x]:
            return
        if not self.placed:
            self.place(x, y)
        if self.mine[y][x]:
            self.open[y][x] = True
            self.boom = (x, y)
            self.end("lose")
            return
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if self.open[cy][cx] or self.flag[cy][cx]:
                continue
            self.open[cy][cx] = True
            if self.count(cx, cy) == 0:
                stack.extend(p for p in self.neighbors(cx, cy) if not self.open[p[1]][p[0]])
        self.check_win()

    def chord(self, x, y):
        if not self.open[y][x] or self.state != "play":
            return
        n = self.count(x, y)
        if n and sum(self.flag[ny][nx] for nx, ny in self.neighbors(x, y)) == n:
            for nx, ny in self.neighbors(x, y):
                if not self.open[ny][nx] and not self.flag[ny][nx]:
                    self.reveal(nx, ny)

    def toggle_flag(self, x, y):
        if self.state in ("win", "lose") or self.open[y][x]:
            return
        self.flag[y][x] = not self.flag[y][x]

    def check_win(self):
        if self.state != "play":
            return
        for y in range(self.rows):
            for x in range(self.cols):
                if not self.mine[y][x] and not self.open[y][x]:
                    return
        for y in range(self.rows):
            for x in range(self.cols):
                if self.mine[y][x]:
                    self.flag[y][x] = True
        self.end("win")

    def end(self, state):
        self.state = state
        self.t1 = time.time()

    def elapsed(self):
        if self.t0 is None:
            return 0
        return int((self.t1 or time.time()) - self.t0)

    def flags_left(self):
        return self.mines - sum(map(sum, self.flag))


# ---------- アプリ ----------

class Mines:
    def __init__(self):
        self.cfg = dict(DEFAULT_CONFIG)
        self.cfg.update(load_json(CONFIG_PATH, {}))
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.p = Scale(self.cfg["scale"])
        self.press = None          # 押しているマス
        self.face_down = False
        self.new_game()

        self.root = tk.Tk()
        log_errors(self.root, "minesweeper_error.txt")
        self.root.title(f"ドットマインスイーパ ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "minesweeper.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])
        self.label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.label.pack()
        self.label.bind("<ButtonPress-1>", self.on_press)
        self.label.bind("<B1-Motion>", self.on_motion)
        self.label.bind("<ButtonRelease-1>", self.on_release)
        self.label.bind("<Button-3>", self.on_right)
        self.label.bind("<Button-2>", self.on_middle)
        self.pmenu = PixelMenu(self.root, self.menu_theme, title="MINES - MENU")
        self.place_window()
        self.redraw()
        self.root.after(500, self.tick)
        self.root.after(2000, self.watch_colorway)

    # --- 設定 ---
    def level(self):
        return next((l for l in LEVELS if l[1] == self.cfg["level"]), LEVELS[0])

    def new_game(self):
        _, _, cols, rows, mines = self.level()
        self.board = Board(cols, rows, mines)

    def save(self):
        save_json(CONFIG_PATH, self.cfg)

    # --- 寸法 ---
    def size(self):
        b = self.board
        gw, gh = b.cols * C, b.rows * C
        w = max(gw + 12, 96)
        h = TOP + 3 + PANEL_H + 3 + gh + 6
        return w, h

    def grid_origin(self):
        w, _ = self.size()
        gw = self.board.cols * C
        return (w - gw) // 2, TOP + 3 + PANEL_H + 3 + 1

    def face_rect(self):
        w, _ = self.size()
        x0 = (w - FACE) // 2
        y0 = TOP + 3 + (PANEL_H - FACE) // 2
        return x0, y0, x0 + FACE - 1, y0 + FACE - 1

    def game_btn_rect(self):
        w, _ = self.size()
        return w - 3 - 3 * 9 - 26, 3, w - 3 - 3 * 9 - 4, 10

    def place_window(self):
        w, h = self.size()
        self.root.geometry(f"{w * self.p}x{h * self.p}+{self.cfg['x']}+{self.cfg['y']}")

    # --- 色 ---
    def cmap(self):
        return colorway_cmap(COLOR_BASE, self.colorway, shades=())

    def menu_theme(self):
        if self.colorway != "original" or is_night_time():
            return colorway_theme(self.colorway, COLOR_BASE)
        return dict(face=PAL["face"], out=PAL["out"], light=PAL["light"], title=PAL["title"], title2=PAL["title2"],
                    title_text=PAL["out"], accent=PAL["accent"], sub=mix(PAL["out"], PAL["face"], 0.45),
                    text=PAL["out"], field=PAL["light"], select=PAL["accent"], select_text=PAL["light"])

    def set_colorway(self, name):
        save_colorway(name)
        self.colorway = name
        self.redraw()

    def watch_colorway(self):
        look = (load_colorway(), is_night_time())   # 色を変えたとき・昼夜が切り替わったときに着替える
        if look != self.look:
            self.look = look
            self.colorway = look[0]
            self.redraw()
        self.root.after(2000, self.watch_colorway)

    # --- 描画 ---
    def render(self):
        k = PAL
        b = self.board
        w, h = self.size()
        im = Image.new("RGB", (w, h), k["face"])
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, w - 1, h - 1], outline=k["out"])
        d.line([(1, 1), (w - 2, 1)], fill=k["light"])
        d.line([(1, 1), (1, h - 2)], fill=k["light"])
        # タイトル
        dither_bar(d, 2, 2, w - 3, 11, k["title2"], k["title"])   # 左の明るい色から、右へ網点でなめらかに
        px_pattern(d, 5, 4, _ICONS["bomb"], k["light"])
        px_pattern(d, 4, 3, _ICONS["bomb"], k["out"])
        px_text(d, 14, 6, "MINES", k["light"])
        px_text(d, 13, 5, "MINES", k["out"])
        gx0, gy0, gx1, gy1 = self.game_btn_rect()
        d.rectangle([gx0, gy0, gx1, gy1], fill=k["face"], outline=k["out"])
        px_text(d, gx0 + 2, gy0 + 1, "GAME", k["out"])
        px_pattern(d, gx1 - 6, gy0 + 3, _ICONS["down"], k["accent"])
        bx0 = w - 3 - 3 * 9
        for i, icon in enumerate(("min", "max", "close")):
            x0 = bx0 + i * 9
            d.rectangle([x0, 3, x0 + 7, 10], fill=k["hover"] if icon == "close" else k["face"], outline=k["out"])
            px_pattern(d, x0 + 1, 4, _ICONS[icon], k["out"])
        d.line([(1, 12), (w - 2, 12)], fill=k["out"])
        # パネル
        py0 = TOP + 3
        bevel(d, 3, py0 - 1, w - 4, py0 + PANEL_H, up=False)
        self.lcd(d, 7, py0 + 10, b.flags_left())
        self.lcd(d, w - 7 - 3 * 8 - 1, py0 + 10, min(999, b.elapsed()))
        fx0, fy0, fx1, fy1 = self.face_rect()
        d.rectangle([fx0 - 1, fy0 - 1, fx1 + 1, fy1 + 1], fill=k["out"])
        bevel(d, fx0, fy0, fx1, fy1, up=not self.face_down, fill=k["hover"] if b.state == "win" else k["face"])
        mood = {"win": "win", "lose": "lose"}.get(b.state, "oh" if self.press else "normal")
        fimg = smiley(mood)
        im.paste(fimg, (fx0 + 1 + (1 if self.face_down else 0), fy0 + 1 + (1 if self.face_down else 0)), fimg)
        # 盤面
        ox, oy = self.grid_origin()
        bevel(d, ox - 2, oy - 2, ox + b.cols * C + 1, oy + b.rows * C + 1, up=False)
        d.rectangle([ox - 1, oy - 1, ox + b.cols * C, oy + b.rows * C], outline=k["out"])
        lose = b.state == "lose"
        for y in range(b.rows):
            for x in range(b.cols):
                self.cell(d, ox + x * C, oy + y * C, x, y, lose)
        return recolor(im, self.cmap())

    def lcd(self, d, x, y, n):
        d.rectangle([x - 2, y - 2, x + 3 * 8 + 1, y + 11], fill=LCD_BG, outline=PAL["out"])
        s = ("-" + f"{abs(n):02d}") if n < 0 else f"{n:03d}"
        for i, ch in enumerate(s[-3:]):
            px_pattern(d, x + i * 8, y, "###|###|###|###|###", mix(LCD_BG, LCD_FG, 0.15), 2)
            px_pattern(d, x + i * 8, y, PX_FONT.get(ch, PX_FONT["0"]), LCD_FG, 2)
        d.line([(x - 1, y - 1), (x + 6, y - 1)], fill=mix(LCD_BG, (255, 255, 255), 0.25))   # ガラスの映り込み
        d.point((x - 1, y), fill=mix(LCD_BG, (255, 255, 255), 0.25))

    def cell(self, d, x0, y0, x, y, lose):
        k = PAL
        b = self.board
        x1, y1 = x0 + C - 1, y0 + C - 1
        opened = b.open[y][x]
        pressed = self.press is not None and self.pressed_cell(x, y)
        if opened or pressed:
            d.rectangle([x0, y0, x1, y1], fill=k["light"])
            d.line([(x0, y0), (x1, y0)], fill=k["shade"])
            d.line([(x0, y0), (x0, y1)], fill=k["shade"])
            if not opened:
                return
            if b.mine[y][x]:
                if b.boom == (x, y):
                    d.rectangle([x0 + 1, y0 + 1, x1, y1], fill=(250, 90, 110))
                px_pattern(d, x0 + 1, y0 + 1, _ICONS["bomb"], (40, 30, 48))
                d.point((x0 + 3, y0 + 4), fill=(255, 255, 255))
                return
            n = b.count(x, y)
            if n:
                px_pattern(d, x0 + 3, y0 + 2, PX_FONT[str(n)], NUM_COLORS[n])
            return
        # まだ開いていないマス
        d.rectangle([x0, y0, x1, y1], fill=k["title2"])
        d.line([(x0, y0), (x1 - 1, y0)], fill=k["light"])
        d.line([(x0, y0), (x0, y1 - 1)], fill=k["light"])
        d.line([(x0 + 1, y1), (x1, y1)], fill=k["second"])
        d.line([(x1, y0 + 1), (x1, y1)], fill=k["second"])
        d.point((x0 + 1, y0 + 1), fill=k["light"])   # 左上の光
        d.point((x1 - 1, y1 - 1), fill=k["shade"])   # 右下のかげ
        if b.flag[y][x]:
            wrong = lose and not b.mine[y][x]
            d.line([(x0 + 3, y0 + 2), (x0 + 3, y0 + 7)], fill=k["out"])
            d.polygon([(x0 + 4, y0 + 2), (x0 + 7, y0 + 3), (x0 + 4, y0 + 5)], fill=k["accent"])
            d.point((x0 + 4, y0 + 3), fill=k["hover"])   # 旗のつや
            d.line([(x0 + 2, y0 + 7), (x0 + 6, y0 + 7)], fill=k["out"])
            d.line([(x0 + 2, y0 + 8), (x0 + 6, y0 + 8)], fill=k["second"])
            if wrong:
                d.line([(x0 + 1, y0 + 1), (x1 - 1, y1 - 1)], fill=(40, 30, 48))
                d.line([(x1 - 1, y0 + 1), (x0 + 1, y1 - 1)], fill=(40, 30, 48))
        elif lose and b.mine[y][x]:
            px_pattern(d, x0 + 1, y0 + 1, _ICONS["bomb"], (40, 30, 48))

    def pressed_cell(self, x, y):
        px, py, chord = self.press
        if chord:
            return abs(px - x) <= 1 and abs(py - y) <= 1 and not self.board.flag[y][x]
        return (px, py) == (x, y) and not self.board.flag[y][x]

    def redraw(self):
        w, h = self.size()
        img = self.render().resize((w * self.p, h * self.p), Image.NEAREST)
        self.photo = ImageTk.PhotoImage(img)
        self.label.config(image=self.photo)

    def tick(self):
        if self.board.state == "play":
            self.redraw()
        self.root.after(500, self.tick)

    # --- マウス ---
    def pos(self, e):
        return e.x / self.p, e.y / self.p

    def cell_at(self, e):
        x, y = self.pos(e)
        ox, oy = self.grid_origin()
        cx, cy = int((x - ox) // C), int((y - oy) // C)
        if x >= ox and y >= oy and 0 <= cx < self.board.cols and 0 <= cy < self.board.rows:
            return cx, cy
        return None

    def in_rect(self, e, r):
        x, y = self.pos(e)
        return r[0] <= x <= r[2] + 1 and r[1] <= y <= r[3] + 1

    def on_press(self, e):
        self._press_root = (e.x_root, e.y_root)
        self._drag = None
        x, y = self.pos(e)
        c = self.cell_at(e)
        if c and self.board.state not in ("win", "lose"):
            self.press = (c[0], c[1], self.board.open[c[1]][c[0]])
        elif self.in_rect(e, self.face_rect()):
            self.face_down = True
        elif y < TOP and not self.in_rect(e, self.game_btn_rect()) and x < self.size()[0] - 3 - 3 * 9:
            self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        self.redraw()

    def on_motion(self, e):
        if self._drag:
            self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")
            return
        if self.press is not None:
            c = self.cell_at(e)
            new = (c[0], c[1], self.board.open[c[1]][c[0]]) if c else None
            if new != self.press and new is not None:
                self.press = new
                self.redraw()

    def on_release(self, e):
        if self._drag:
            self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
            self.save()
            self._drag = None
            return
        b = self.board
        if self.press is not None:
            c = self.cell_at(e)
            self.press = None
            if c:
                x, y = c
                if b.open[y][x]:
                    b.chord(x, y)
                else:
                    b.reveal(x, y)
                if b.state == "win":
                    self.record()
        elif self.face_down:
            self.face_down = False
            if self.in_rect(e, self.face_rect()):
                self.new_game()
        elif self.in_rect(e, self.game_btn_rect()):
            r = self.game_btn_rect()
            self.pmenu.popup(self.menu_items, self.root.winfo_rootx() + r[0] * self.p,
                             self.root.winfo_rooty() + (r[3] + 2) * self.p)
        else:
            w = self.size()[0]
            bx0 = w - 3 - 3 * 9
            if self.in_rect(e, (bx0 + 18, 3, bx0 + 25, 10)):
                self.quit()
                return
            if self.in_rect(e, (bx0, 3, bx0 + 7, 10)):
                self.minimize()
                return
        self.redraw()

    def on_right(self, e):
        c = self.cell_at(e)
        if c:
            self.board.toggle_flag(*c)
            self.redraw()
        else:
            self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

    def on_middle(self, e):
        c = self.cell_at(e)
        if c:
            self.board.chord(*c)
            if self.board.state == "win":
                self.record()
            self.redraw()

    def record(self):
        key = self.cfg["level"]
        t = self.board.elapsed()
        best = self.cfg.setdefault("best", {})
        if key not in best or t < best[key]:
            best[key] = t
            self.save()
            self.new_record = True

    # --- メニュー ---
    def menu_items(self):
        c = self.cfg
        best = c.get("best", {})
        items = [{"type": "cmd", "label": "新しいゲーム", "cmd": lambda: (self.new_game(), self.redraw())},
                 {"type": "sep"}, {"type": "head", "label": "むずかしさ"}]
        for name, key, cols, rows, mines in LEVELS:
            items.append({"type": "radio", "label": name, "right": f"{cols}×{rows}・{mines}こ",
                          "checked": c["level"] == key, "cmd": lambda key=key: self.set_level(key)})
        items += [{"type": "sep"}, {"type": "head", "label": "ベストタイム"}]
        for name, key, *_ in LEVELS:
            items.append({"type": "head", "label": f"{name}　{str(best[key]) + '秒' if key in best else '—'}"})
        items += [
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
            {"type": "head", "label": f"ドットマインスイーパ ver.{APP_VERSION}"},
        ]
        return items

    def set_level(self, key):
        self.cfg["level"] = key
        self.save()
        self.new_game()
        self.place_window()
        self.redraw()

    def set_scale(self, v):
        self.cfg["scale"] = v
        self.p = Scale(v)
        self.save()
        self.place_window()
        self.redraw()

    def toggle_topmost(self):
        self.cfg["topmost"] = not self.cfg["topmost"]
        self.save()
        self.root.attributes("-topmost", self.cfg["topmost"])

    def minimize(self):
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
        Mines().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "minesweeper_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
