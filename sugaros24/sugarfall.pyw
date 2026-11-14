# -*- coding: utf-8 -*-
"""
ドットシュガーフォール ver.1.1（SUGAR.EXE）
SugarOS 24 のミニゲーム。上から落ちてくる角砂糖を積んで、横一列そろえると溶けて消える落ちモノパズル。
ブロックは 1〜3 マスの小さな角砂糖。ときどき落ちてくるキャンディは、着地したまわり 3×3 を溶かす。

遊び方:
  ← →        … 左右に動かす
  ↑ / X      … 回す
  ↓          … はやく落とす
  スペース   … 一気に落とす
  P          … 一時停止（ほかのウィンドウを触っても止まる）
  Enter      … ゲームオーバーのあと、もう一度
  GAME / 右クリック … メニュー（新しいゲーム、ベストスコア、カラー、サイズ など）

  10列消すごとにレベルが上がって、落ちるのがはやくなる。

必要なもの: pip install pillow
"""
import os
import random
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from mushiboshi_ui import (COLORWAY_NAMES, dither_bar, log_errors, is_night_time, PixelMenu, colorway_cmap, colorway_menu,
                           colorway_theme, load_colorway, recolor, save_colorway, Scale, mix, px_pattern, px_text,
                           px_text_w, load_json, save_json)

APP_VERSION = "1.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "sugarfall_config.json")

SCALES = [("ミニ", 1.5), ("小", 2), ("中", 3), ("大", 4)]
DEFAULT_CONFIG = {"scale": 3, "topmost": False, "x": 340, "y": 120, "best": 0}

_ICONS = {
    "cube": "#####|#..##|#.#.#|##..#|#####",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
    "down": "#####|.###.|..#..",
}

# 角砂糖の形（1〜3マス）。(x, y) のならび
SHAPES = {
    "one": [(0, 0)],
    "two": [(0, 0), (1, 0)],
    "three": [(0, 0), (1, 0), (2, 0)],
    "corner": [(0, 0), (0, 1), (1, 1)],
}
SHAPE_WEIGHTS = [("one", 2), ("two", 4), ("three", 4), ("corner", 5)]
CANDY_CHANCE = 1 / 14
FLAVORS = {   # 味ごとの色（地, ハイライト, 影）
    "berry": ((240, 110, 150), (255, 196, 214), (196, 72, 110)),
    "mint": ((110, 206, 170), (200, 244, 226), (70, 160, 130)),
    "lemon": ((250, 206, 90), (255, 240, 180), (210, 160, 50)),
    "soda": ((120, 168, 240), (206, 224, 255), (80, 120, 200)),
}
CANDY = "candy"

PAL = dict(face=(248, 240, 246), out=(70, 48, 84), light=(255, 255, 255), shade=(214, 198, 220),
           title=(240, 186, 210), title2=(250, 214, 230), accent=(236, 88, 130), hover=(255, 214, 228),
           second=(150, 116, 170))
COLOR_BASE = {v: k for k, v in PAL.items() if k != "light"}
WELL, WELL2 = (52, 40, 68), (60, 46, 78)   # 盤の地（夜でも昼でも、角砂糖が映える濃い色）
SUGAR_WHITE = (255, 255, 254)   # 角砂糖の光（夜の色に塗り替えられない白）

COLS, ROWS = 8, 14
C = 7                     # 1マス（ドット）
TOP = 13
BX, BY = 4, TOP + 4       # 盤の左上
SIDE_X = BX + COLS * C + 5
W = SIDE_X + 40 + 4
H = BY + ROWS * C + 5


def rotate(cells):
    """右に90度。回したあとも左上が (0, 0) になるようにそろえる。"""
    r = [(-y, x) for x, y in cells]
    mx, my = min(x for x, _ in r), min(y for _, y in r)
    return [(x - mx, y - my) for x, y in r]


# ---------- ゲーム ----------

class Piece:
    def __init__(self, shape, flavor):
        self.shape, self.flavor = shape, flavor
        self.cells = list(SHAPES["one"] if flavor == CANDY else SHAPES[shape])
        w = max(x for x, _ in self.cells) + 1
        self.x, self.y = (COLS - w) // 2, 0

    def blocks(self, dx=0, dy=0, cells=None):
        return [(self.x + x + dx, self.y + y + dy) for x, y in (cells or self.cells)]


def random_piece():
    if random.random() < CANDY_CHANCE:
        return Piece("one", CANDY)
    shape = random.choices([s for s, _ in SHAPE_WEIGHTS], [w for _, w in SHAPE_WEIGHTS])[0]
    return Piece(shape, random.choice(list(FLAVORS)))


class Game:
    def __init__(self):
        self.grid = [[None] * COLS for _ in range(ROWS)]
        self.piece = random_piece()
        self.next = random_piece()
        self.score = 0
        self.lines = 0
        self.state = "play"   # play / pause / over
        self.flash = []       # 消えるところのきらきら [(x, y, 時刻)]

    @property
    def level(self):
        return self.lines // 10 + 1

    def interval(self):
        return max(0.08, 0.7 - (self.level - 1) * 0.06)

    def fits(self, blocks):
        return all(0 <= x < COLS and 0 <= y < ROWS and self.grid[y][x] is None for x, y in blocks)

    def shift(self, dx):
        if self.state == "play" and self.fits(self.piece.blocks(dx, 0)):
            self.piece.x += dx
            return True
        return False

    def turn(self):
        if self.state != "play":
            return
        cells = rotate(self.piece.cells)
        for kick in (0, -1, 1, -2):   # 壁ぎわでは、少しずらして回す
            if self.fits(self.piece.blocks(kick, 0, cells)):
                self.piece.cells = cells
                self.piece.x += kick
                return

    def fall(self):
        """1マス落とす。落ちられなければ置く。置いたら True。"""
        if self.state != "play":
            return False
        if self.fits(self.piece.blocks(0, 1)):
            self.piece.y += 1
            return False
        self.lock()
        return True

    def drop(self):
        if self.state != "play":
            return
        n = 0
        while self.fits(self.piece.blocks(0, 1)):
            self.piece.y += 1
            n += 1
        self.score += n * 2
        self.lock()

    def ghost_y(self):
        dy = 0
        while self.fits(self.piece.blocks(0, dy + 1)):
            dy += 1
        return dy

    def lock(self):
        now = time.time()
        p = self.piece
        if p.flavor == CANDY:   # キャンディ：まわり3×3を溶かして、上のものを落とす
            cx, cy = p.blocks()[0]
            melted = 0
            for y in range(cy - 1, cy + 2):
                for x in range(cx - 1, cx + 2):
                    if 0 <= x < COLS and 0 <= y < ROWS:
                        if self.grid[y][x] is not None:
                            melted += 1
                        self.grid[y][x] = None
                        self.flash.append((x, y, now))
            for x in range(cx - 1, cx + 2):
                if 0 <= x < COLS:
                    stack = [self.grid[y][x] for y in range(ROWS) if self.grid[y][x] is not None]
                    for y in range(ROWS):
                        self.grid[y][x] = None
                    for k, v in enumerate(reversed(stack)):
                        self.grid[ROWS - 1 - k][x] = v
            self.score += melted * 10 * self.level
        else:
            for x, y in p.blocks():
                self.grid[y][x] = p.flavor
        self.clear_rows(now)
        self.piece, self.next = self.next, random_piece()
        if not self.fits(self.piece.blocks()):
            self.state = "over"

    def clear_rows(self, now):
        full = [y for y in range(ROWS) if all(self.grid[y])]
        if not full:
            return
        for y in full:
            self.flash.extend((x, y, now) for x in range(COLS))
        self.grid = [[None] * COLS for _ in full] + [row for y, row in enumerate(self.grid) if y not in full]
        n = len(full)   # いっしょに消えた列が多いほど、点が大きい
        self.score += {1: 100, 2: 300, 3: 600}.get(n, 1000) * self.level
        self.lines += n


# ---------- 絵 ----------

_cube_cache = {}


def cube(flavor, t=0):
    """1マスの角砂糖（7×7）。"""
    key = (flavor, int(t * 4) % 2 if flavor == CANDY else 0)
    if key in _cube_cache:
        return _cube_cache[key]
    im = Image.new("RGB", (C, C), WELL)
    d = ImageDraw.Draw(im)
    if flavor == CANDY:   # ぐるぐるキャンディ
        a, b = (SUGAR_WHITE, (240, 90, 140)) if key[1] else ((240, 90, 140), SUGAR_WHITE)
        d.ellipse([0, 0, C - 1, C - 1], fill=a)
        d.arc([1, 1, C - 2, C - 2], 0, 270, fill=b)
        d.point((3, 3), fill=b)
        d.arc([2, 2, C - 3, C - 3], 90, 360, fill=b)
    else:
        base, hi, sh = FLAVORS[flavor]
        d.rectangle([0, 0, C - 2, C - 2], fill=base)
        d.line([(0, 0), (C - 3, 0)], fill=hi)
        d.line([(0, 0), (0, C - 3)], fill=hi)
        d.point((1, 1), fill=SUGAR_WHITE)
        d.line([(1, C - 2), (C - 2, C - 2)], fill=sh)
        d.line([(C - 2, 1), (C - 2, C - 2)], fill=sh)
        for (x, y) in ((3, 2), (2, 4), (4, 4)):   # 砂糖のつぶ
            d.point((x, y), fill=hi)
    _cube_cache[key] = im
    return im


class SugarFall:
    def __init__(self):
        self.cfg = dict(DEFAULT_CONFIG)
        self.cfg.update(load_json(CONFIG_PATH, {}))
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.p = Scale(self.cfg["scale"])
        self.game = Game()
        self.last_fall = time.time()
        self.new_best = False

        self.root = tk.Tk()
        log_errors(self.root, "sugarfall_error.txt")
        self.root.title(f"ドットシュガーフォール ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "sugarfall.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])
        self.label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.label.pack()
        self.label.bind("<ButtonPress-1>", self.on_press)
        self.label.bind("<B1-Motion>", self.on_motion)
        self.label.bind("<ButtonRelease-1>", self.on_release)
        self.label.bind("<Button-3>", lambda e: self.pmenu.popup(self.menu_items, e.x_root, e.y_root))
        for keys, fn in ((("<Left>", "<a>"), lambda: self.game_shift(-1)), (("<Right>", "<d>"), lambda: self.game_shift(1)),
                         (("<Up>", "<x>", "<w>"), self.game_turn), (("<Down>", "<s>"), self.soft_drop),
                         (("<space>",), self.hard_drop), (("<p>", "<Escape>"), self.toggle_pause),
                         (("<Return>",), self.restart_if_over)):
            for k in keys:
                self.root.bind(k, lambda e, fn=fn: (fn(), self.redraw()))
        self.root.bind("<FocusOut>", lambda e: self.auto_pause())
        self.pmenu = PixelMenu(self.root, self.menu_theme, title="SUGAR - MENU")
        self.root.geometry(f"{W * self.p}x{H * self.p}+{self.cfg['x']}+{self.cfg['y']}")
        self.redraw()
        self.root.after(50, lambda: self.root.focus_force())
        self.root.after(30, self.tick)
        self.root.after(2000, self.watch_colorway)

    def save(self):
        save_json(CONFIG_PATH, self.cfg)

    # --- 色 ---
    def cmap(self):
        return colorway_cmap(COLOR_BASE, self.colorway)

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

    # --- 操作 ---
    def game_shift(self, dx):
        self.resume()
        self.game.shift(dx)

    def game_turn(self):
        self.resume()
        self.game.turn()

    def soft_drop(self):
        self.resume()
        if self.game.state == "play":
            self.game.score += 1
            self.game.fall()
            self.last_fall = time.time()
            self.after_lock()

    def hard_drop(self):
        self.resume()
        if self.game.state == "play":
            self.game.drop()
            self.last_fall = time.time()
            self.after_lock()

    def resume(self):
        if self.game.state == "pause":
            self.game.state = "play"
            self.last_fall = time.time()

    def toggle_pause(self):
        g = self.game
        if g.state == "play":
            g.state = "pause"
        else:
            self.resume()

    def auto_pause(self):
        if self.game.state == "play":
            self.game.state = "pause"
            self.redraw()

    def restart_if_over(self):
        if self.game.state == "over":
            self.new_game()

    def new_game(self):
        self.game = Game()
        self.new_best = False
        self.last_fall = time.time()
        self.root.focus_force()

    def after_lock(self):
        g = self.game
        if g.state == "over" and g.score > self.cfg.get("best", 0):
            self.cfg["best"] = g.score
            self.new_best = True
            self.save()

    def tick(self):
        g = self.game
        now = time.time()
        if g.state == "play" and now - self.last_fall >= g.interval():
            g.fall()
            self.last_fall = now
            self.after_lock()
        g.flash = [f for f in g.flash if now - f[2] < 0.35]
        self.redraw()
        self.root.after(33, self.tick)

    # --- 描画 ---
    def render(self):
        k = PAL
        g = self.game
        now = time.time()
        night = is_night_time()
        im = Image.new("RGB", (W, H), k["face"])
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W - 1, H - 1], outline=k["out"])
        d.line([(1, 1), (W - 2, 1)], fill=k["light"])
        d.line([(1, 1), (1, H - 2)], fill=k["light"])
        dither_bar(d, 2, 2, W - 3, 11, k["title2"], k["title"])   # 左の明るい色から、右へ網点でなめらかに
        px_pattern(d, 5, 5, _ICONS["cube"], k["light"])
        px_pattern(d, 4, 4, _ICONS["cube"], k["out"])
        px_text(d, 12, 6, "SUGAR.EXE", k["light"])
        px_text(d, 11, 5, "SUGAR.EXE", k["out"])
        gx0, gy0, gx1, gy1 = self.game_btn_rect()
        d.rectangle([gx0, gy0, gx1, gy1], fill=k["face"], outline=k["out"])
        px_text(d, gx0 + 2, gy0 + 1, "GAME", k["out"])
        px_pattern(d, gx1 - 6, gy0 + 3, _ICONS["down"], k["accent"])
        bx0 = W - 3 - 3 * 9
        for i, icon in enumerate(("min", "max", "close")):
            x0 = bx0 + i * 9
            d.rectangle([x0, 3, x0 + 7, 10], fill=k["hover"] if icon == "close" else k["face"], outline=k["out"])
            px_pattern(d, x0 + 1, 4, _ICONS[icon], k["out"])
        d.line([(1, 12), (W - 2, 12)], fill=k["out"])
        # 盤
        well, well2 = (mix(WELL, (10, 12, 30), 0.3), mix(WELL2, (10, 12, 30), 0.3)) if night else (WELL, WELL2)
        d.rectangle([BX - 1, BY - 1, BX + COLS * C, BY + ROWS * C], fill=well, outline=k["out"])
        for y in range(ROWS):
            for x in range(COLS):
                if (x + y) % 2:
                    d.rectangle([BX + x * C, BY + y * C, BX + x * C + C - 1, BY + y * C + C - 1], fill=well2)
        inner = mix(well, (0, 0, 0), 0.35)   # 盤の内側のかげ（上と左）
        d.line([(BX, BY), (BX + COLS * C - 1, BY)], fill=inner)
        d.line([(BX, BY), (BX, BY + ROWS * C - 1)], fill=inner)
        for y in range(ROWS):
            for x in range(COLS):
                if g.grid[y][x]:
                    im.paste(cube(g.grid[y][x], now), (BX + x * C, BY + y * C))
        if g.state != "over":
            p = g.piece
            gy = g.ghost_y()
            for x, y in p.blocks(0, gy):   # 落ちる場所のうすい影
                d.rectangle([BX + x * C, BY + y * C, BX + x * C + C - 2, BY + y * C + C - 2],
                            outline=mix(well, (255, 255, 255), 0.25))
            for x, y in p.blocks():
                im.paste(cube(p.flavor, now), (BX + x * C, BY + y * C))
        for x, y, t0 in g.flash:   # 消えるところのきらきら
            a = 1 - (now - t0) / 0.35
            d.rectangle([BX + x * C, BY + y * C, BX + x * C + C - 1, BY + y * C + C - 1],
                        fill=mix(well, (255, 250, 240), max(0, a)))
        # 横の欄
        sx = SIDE_X
        px_text(d, sx, BY, "NEXT", k["second"])
        d.rectangle([sx, BY + 7, sx + 25, BY + 7 + 25], fill=well, outline=k["out"])
        d.line([(sx + 1, BY + 8), (sx + 24, BY + 8)], fill=mix(well, (0, 0, 0), 0.35))
        nc = g.next.cells
        nw, nh = max(x for x, _ in nc) + 1, max(y for _, y in nc) + 1
        ox, oy = sx + 1 + (24 - nw * C) // 2, BY + 8 + (24 - nh * C) // 2
        for x, y in nc:
            im.paste(cube(g.next.flavor, now), (ox + x * C, oy + y * C))
        y0 = BY + 38
        for label, value in (("SCORE", g.score), ("LINES", g.lines), ("LEVEL", g.level), ("BEST", self.cfg.get("best", 0))):
            d.rounded_rectangle([sx - 2, y0 - 2, W - 4, y0 + 12], radius=2, fill=k["light"], outline=k["shade"])   # 数字の札
            px_text(d, sx, y0, label, k["second"])
            px_text(d, sx, y0 + 7, str(value), k["accent"] if label == "SCORE" else k["out"])
            y0 += 15
        if g.state in ("pause", "over"):
            self.banner(d, g)
        return recolor(im, self.cmap())

    def banner(self, d, g):
        k = PAL
        y0 = BY + ROWS * C // 2 - 14
        d.rectangle([BX + 2, y0, BX + COLS * C - 3, y0 + 26], fill=k["face"], outline=k["out"])
        d.rectangle([BX + 3, y0 + 1, BX + COLS * C - 4, y0 + 8], fill=k["title"])
        if g.state == "pause":
            title, sub = "PAUSE", "P: PLAY"
        else:
            title, sub = "GAME OVER", "NEW BEST!" if self.new_best else "ENTER: AGAIN"
        px_text(d, BX + (COLS * C - px_text_w(title)) // 2, y0 + 2, title, k["out"])
        px_text(d, BX + (COLS * C - px_text_w(sub)) // 2, y0 + 14, sub, k["accent"])

    def redraw(self):
        img = self.render().resize((W * self.p, H * self.p), Image.NEAREST)
        self.photo = ImageTk.PhotoImage(img)
        self.label.config(image=self.photo)

    # --- マウス ---
    def game_btn_rect(self):
        return W - 3 - 3 * 9 - 26, 3, W - 3 - 3 * 9 - 4, 10

    def pos(self, e):
        return e.x / self.p, e.y / self.p

    def in_rect(self, x, y, r):
        return r[0] <= x <= r[2] + 1 and r[1] <= y <= r[3] + 1

    def on_press(self, e):
        self.root.focus_force()
        x, y = self.pos(e)
        self._drag = None
        bx0 = W - 3 - 3 * 9
        if y < TOP and not self.in_rect(x, y, self.game_btn_rect()) and x < bx0:
            self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def on_motion(self, e):
        if self._drag:
            self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def on_release(self, e):
        x, y = self.pos(e)
        if self._drag:
            self._drag = None
            self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
            self.save()
            return
        if self.in_rect(x, y, self.game_btn_rect()):
            r = self.game_btn_rect()
            self.pmenu.popup(self.menu_items, self.root.winfo_rootx() + r[0] * self.p,
                             self.root.winfo_rooty() + (r[3] + 2) * self.p)
            return
        bx0 = W - 3 - 3 * 9
        if self.in_rect(x, y, (bx0 + 18, 3, bx0 + 25, 10)):
            self.quit()
        elif self.in_rect(x, y, (bx0, 3, bx0 + 7, 10)):
            self.minimize()
        elif self.game.state == "pause" and y >= TOP:   # 盤をクリックで再開
            self.resume()

    # --- メニュー ---
    def menu_items(self):
        c = self.cfg
        self.auto_pause()
        return [
            {"type": "cmd", "label": "新しいゲーム", "cmd": lambda: (self.new_game(), self.redraw())},
            {"type": "cmd", "label": "つづける", "cmd": lambda: (self.resume(), self.root.focus_force()),
             "enabled": self.game.state == "pause"},
            {"type": "sep"},
            {"type": "head", "label": f"ベストスコア　{c.get('best', 0)}"},
            {"type": "head", "label": "← → 動かす　↑ 回す　↓ はやく　スペース 一気に"},
            {"type": "head", "label": "キャンディは、まわり3×3を溶かすよ"},
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
            {"type": "head", "label": f"ドットシュガーフォール ver.{APP_VERSION}"},
        ]

    def set_scale(self, v):
        self.cfg["scale"] = v
        self.p = Scale(v)
        self.save()
        self.root.geometry(f"{W * self.p}x{H * self.p}+{self.cfg['x']}+{self.cfg['y']}")
        self.redraw()

    def toggle_topmost(self):
        self.cfg["topmost"] = not self.cfg["topmost"]
        self.save()
        self.root.attributes("-topmost", self.cfg["topmost"])

    def minimize(self):
        self.auto_pause()
        self.root.overrideredirect(False)
        self.root.iconify()

        def restore(ev):
            if ev.widget is self.root and self.root.state() == "normal":
                self.root.overrideredirect(True)
                self.root.unbind("<Map>")
                self.root.focus_force()
        self.root.bind("<Map>", restore)

    def quit(self):
        self.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        SugarFall().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "sugarfall_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
