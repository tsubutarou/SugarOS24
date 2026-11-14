# -*- coding: utf-8 -*-
"""
ドットソリティア ver.1.1（CARDS.EXE）
SugarOS 24 のミニゲーム。むかしからあるトランプのひとり遊び（クロンダイク）。

遊び方:
  左上の山札をクリック … 1枚（または3枚）めくる。なくなったらクリックで戻す
  カードをクリック     … 置ける場所へ自動で動かす（組札が先、次に場札）
  カードをドラッグ     … 好きな場所へ動かす（場札は、そのカードから下をまとめて）
  UNDO                 … ひとつ戻す
  GAME / 右クリック    … メニュー（新しいゲーム、めくる枚数、記録、カラー、サイズ など）

  場札は、赤と黒を交互に、数字をひとつずつ小さく重ねる。空いた列にはキングだけ置ける。
  組札は、同じマークを A から K まで。全部のせたらクリア。

必要なもの: pip install pillow
"""
import copy
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
CONFIG_PATH = os.path.join(APP_DIR, "solitaire_config.json")

SCALES = [("ミニ", 1.5), ("小", 2), ("中", 3), ("大", 4)]
DEFAULT_CONFIG = {"draw": 1, "scale": 3, "topmost": False, "x": 320, "y": 100, "best": {}, "wins": 0, "plays": 0}

_ICONS = {
    "cards": "####.|#..##|#..#.|####.|.###.",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
    "down": "#####|.###.|..#..",
    "undo": "..#..|.##..|#####|.##.#|..#.#",
    "again": ".###.|#...#|#..##|#...#|.###.",
}
SUITS = "SHDC"   # スペード・ハート・ダイヤ・クラブ
SUIT_PAT = {
    "S": "..#..|.###.|#####|..#..|.###.",
    "H": ".#.#.|#####|#####|.###.|..#..",
    "D": "..#..|.###.|#####|.###.|..#..",
    "C": ".###.|#####|#####|..#..|.###.",
}
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
RED, BLACK = (226, 64, 92), (40, 32, 56)
CARD_FACE, CARD_EDGE = (252, 250, 252), (120, 104, 136)

PAL = dict(face=(244, 240, 250), out=(60, 44, 84), light=(255, 255, 255), shade=(200, 192, 222),
           title=(176, 206, 236), title2=(206, 228, 248), accent=(236, 88, 130), hover=(255, 214, 228),
           second=(120, 112, 170))
COLOR_BASE = {v: k for k, v in PAL.items() if k != "light"}
TABLE, TABLE2 = (70, 150, 128), (64, 140, 120)   # 場の色（フェルト）

CW, CH = 15, 21          # カードの大きさ
GAP = 2
DOWN_OFF, UP_OFF = 3, 6  # 場札で重ねたときのずらし（裏 / 表）
TOP = 13
ROW1_Y = 16              # 山札・捨て札・組札
TAB_Y = ROW1_Y + CH + 4  # 場札
W = 4 + 7 * (CW + GAP) - GAP + 4
FOOT_H = 11
H = TAB_Y + 6 * DOWN_OFF + 12 * UP_OFF + CH + 4 + FOOT_H


def col_x(i):
    return 4 + i * (CW + GAP)


def is_red(card):
    return card[1] in "HD"


# ---------- カードの絵 ----------

_card_cache = {}


def card_image(card, back=False):
    """card = (数 1〜13, マーク)。裏なら back=True。"""
    key = ("back",) if back else card
    if key in _card_cache:
        return _card_cache[key]
    im = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if back:
        d.rectangle([1, 0, CW - 2, CH - 1], fill=PAL["accent"])
        d.rectangle([0, 1, CW - 1, CH - 2], fill=PAL["accent"])
        for y in range(2, CH - 2):
            for x in range(2, CW - 2):
                if (x + y) % 4 == 0 or (x - y) % 4 == 0:
                    d.point((x, y), fill=PAL["hover"])
        d.rectangle([1, 1, CW - 2, CH - 2], outline=PAL["out"])
        d.rectangle([3, 3, CW - 4, CH - 4], outline=PAL["hover"])          # 内側のふち
        cx, cy = CW // 2, CH // 2                                           # まんなかのハート
        d.rectangle([cx - 3, cy - 3, cx + 3, cy + 3], fill=PAL["accent"])
        px_pattern(d, cx - 2, cy - 2, ".#.#.|#####|.###.|..#..", PAL["face"])
    else:
        rank, suit = card
        col = RED if suit in "HD" else BLACK
        d.rectangle([1, 0, CW - 2, CH - 1], fill=CARD_FACE)
        d.rectangle([0, 1, CW - 1, CH - 2], fill=CARD_FACE)
        d.point((1, 1), fill=CARD_EDGE)
        d.point((CW - 2, 1), fill=CARD_EDGE)
        d.point((1, CH - 2), fill=CARD_EDGE)
        d.point((CW - 2, CH - 2), fill=CARD_EDGE)
        d.line([(2, 0), (CW - 3, 0)], fill=CARD_EDGE)
        d.line([(2, CH - 1), (CW - 3, CH - 1)], fill=CARD_EDGE)
        d.line([(0, 2), (0, CH - 3)], fill=CARD_EDGE)
        d.line([(CW - 1, 2), (CW - 1, CH - 3)], fill=CARD_EDGE)
        if rank == 10:   # 「10」は詰めて書いて、マークとのあいだをあける
            px_text(d, 1, 1, "1", col)
            px_text(d, 4, 1, "0", col)
        else:
            px_text(d, 2, 1, RANKS[rank - 1], col)
        px_pattern(d, CW - 6, 1, SUIT_PAT[suit], col)   # 「10」とも重ならないよう、右に寄せる
        if rank > 10:   # 絵札は、まんなかにかんむり
            px_pattern(d, 5, 9, "#.#.#|#####|#####", (236, 180, 60))
            px_pattern(d, 5, 13, SUIT_PAT[suit], col)
        else:
            px_pattern(d, 3, 9, SUIT_PAT[suit], col, 2)
    _card_cache[key] = im
    return im


def slot_image(label=None):
    """カードがない場所のわく。"""
    im = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    edge = mix(TABLE, (255, 255, 255), 0.35)
    for x in range(1, CW - 1, 2):
        d.point((x, 0), fill=edge)
        d.point((x, CH - 1), fill=edge)
    for y in range(1, CH - 1, 2):
        d.point((0, y), fill=edge)
        d.point((CW - 1, y), fill=edge)
    if label in SUIT_PAT:
        px_pattern(d, 5, 8, SUIT_PAT[label], edge)
    elif label == "again":
        px_pattern(d, 5, 8, _ICONS["again"], edge)
    return im


# ---------- ゲーム ----------

class Game:
    def __init__(self, draw):
        deck = [(r, s) for s in SUITS for r in range(1, 14)]
        random.shuffle(deck)
        self.draw = draw
        self.tableau = []      # 列ごとに [(card, 表か), ...]
        for i in range(7):
            col = [[deck.pop(), False] for _ in range(i + 1)]
            col[-1][1] = True
            self.tableau.append(col)
        self.stock = deck      # 末尾が上
        self.waste = []
        self.found = {s: [] for s in SUITS}
        self.moves = 0
        self.t0 = None
        self.t1 = None
        self.history = []

    # --- ルール ---
    def can_found(self, card):
        pile = self.found[card[1]]
        return card[0] == (pile[-1][0] + 1 if pile else 1)

    def can_tab(self, card, i):
        col = self.tableau[i]
        if not col:
            return card[0] == 13
        top, up = col[-1]
        return up and top[0] == card[0] + 1 and is_red(top) != is_red(card)

    # --- 動かす ---
    def snapshot(self):
        self.history.append(copy.deepcopy((self.tableau, self.stock, self.waste, self.found, self.moves)))
        if len(self.history) > 300:
            self.history.pop(0)

    def undo(self):
        if self.history and not self.won():
            self.tableau, self.stock, self.waste, self.found, self.moves = self.history.pop()
            return True
        return False

    def started(self):
        if self.t0 is None:
            self.t0 = time.time()

    def flip_tops(self):
        for col in self.tableau:
            if col and not col[-1][1]:
                col[-1][1] = True

    def deal(self):
        """山札をめくる。なければ捨て札を山札に戻す。"""
        if not self.stock and not self.waste:
            return False
        self.snapshot()
        self.started()
        if self.stock:
            for _ in range(min(self.draw, len(self.stock))):
                self.waste.append(self.stock.pop())
        else:
            self.stock = self.waste[::-1]
            self.waste = []
        self.moves += 1
        return True

    def take(self, src):
        """src から動かすカードの列。src = ("waste",) / ("found", マーク) / ("tab", 列, 何枚目から)"""
        if src[0] == "waste":
            return [self.waste[-1]] if self.waste else []
        if src[0] == "found":
            pile = self.found[src[1]]
            return [pile[-1]] if pile else []
        col = self.tableau[src[1]]
        cards = col[src[2]:]
        return [c for c, up in cards] if cards and all(up for _, up in cards) else []

    def can_move(self, src, dst):
        cards = self.take(src)
        if not cards or src[:2] == dst[:2]:
            return False
        if dst[0] == "found":
            return len(cards) == 1 and cards[0][1] == dst[1] and self.can_found(cards[0])
        return self.can_tab(cards[0], dst[1])

    def move(self, src, dst):
        if not self.can_move(src, dst):
            return False
        self.snapshot()
        self.started()
        cards = self.take(src)
        if src[0] == "waste":
            self.waste.pop()
        elif src[0] == "found":
            self.found[src[1]].pop()
        else:
            del self.tableau[src[1]][src[2]:]
        if dst[0] == "found":
            self.found[dst[1]].append(cards[0])
        else:
            self.tableau[dst[1]].extend([c, True] for c in cards)
        self.flip_tops()
        self.moves += 1
        if self.won() and self.t1 is None:
            self.t1 = time.time()
        return True

    def best_target(self, src):
        """クリックしたときの行き先。組札 → 場札（カードのある列 → 空いた列）の順。"""
        cards = self.take(src)
        if not cards or src[0] == "found":   # 組札から下ろすのは、ドラッグのときだけ
            return None
        if len(cards) == 1 and src[0] != "found" and self.can_move(src, ("found", cards[0][1])):
            return ("found", cards[0][1])
        order = sorted(range(7), key=lambda i: (not self.tableau[i], i))
        for i in order:
            if self.can_move(src, ("tab", i)):
                return ("tab", i)
        return None

    def won(self):
        return all(len(p) == 13 for p in self.found.values())

    def can_finish(self):
        """裏のカードも山札も残っていなければ、あとは自動でのせられる。"""
        return not self.stock and not self.waste and all(up for col in self.tableau for _, up in col) \
            and not self.won()

    def elapsed(self):
        if self.t0 is None:
            return 0
        return int((self.t1 or time.time()) - self.t0)


# ---------- アプリ ----------

class Solitaire:
    def __init__(self):
        self.cfg = dict(DEFAULT_CONFIG)
        self.cfg.update(load_json(CONFIG_PATH, {}))
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.p = Scale(self.cfg["scale"])
        self.drag = None
        self.hover = None
        self.finishing = False
        self.new_game()

        self.root = tk.Tk()
        log_errors(self.root, "solitaire_error.txt")
        self.root.title(f"ドットソリティア ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "solitaire.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])
        self.label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.label.pack()
        self.label.bind("<ButtonPress-1>", self.on_press)
        self.label.bind("<B1-Motion>", self.on_motion)
        self.label.bind("<ButtonRelease-1>", self.on_release)
        self.label.bind("<Motion>", self.on_hover)
        self.label.bind("<Button-3>", lambda e: self.pmenu.popup(self.menu_items, e.x_root, e.y_root))
        self.pmenu = PixelMenu(self.root, self.menu_theme, title="CARDS - MENU")
        self.place_window()
        self.redraw()
        self.root.after(1000, self.tick)
        self.root.after(2000, self.watch_colorway)

    def new_game(self):
        self.game = Game(self.cfg["draw"])
        self.counted = False   # 1手目を動かしたら「1ゲーム遊んだ」に数える
        self.recorded = False
        self.finishing = False

    def save(self):
        save_json(CONFIG_PATH, self.cfg)

    def place_window(self):
        self.root.geometry(f"{W * self.p}x{H * self.p}+{self.cfg['x']}+{self.cfg['y']}")

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

    # --- 位置 ---
    def game_btn_rect(self):
        return W - 3 - 3 * 9 - 26, 3, W - 3 - 3 * 9 - 4, 10

    def undo_rect(self):
        return W - 4 - 28, H - FOOT_H + 1, W - 5, H - 3

    def tab_positions(self, i):
        """場札 i 列目の、各カードの (y, 見えている高さ)。"""
        out, y = [], TAB_Y
        col = self.game.tableau[i]
        for k, (_, up) in enumerate(col):
            step = UP_OFF if up else DOWN_OFF
            out.append((y, CH if k == len(col) - 1 else step))
            y += step
        return out

    def hit(self, x, y):
        """その点にあるもの。("stock",) / ("waste",) / ("found", s) / ("tab", 列, 何枚目) / ("tab_empty", 列)"""
        g = self.game
        if ROW1_Y <= y < ROW1_Y + CH:
            if col_x(0) <= x < col_x(0) + CW:
                return ("stock",)
            wx = col_x(1) + self.waste_fan_offset()
            if g.waste and wx <= x < wx + CW:
                return ("waste",)
            for k, s in enumerate(SUITS):
                if col_x(3 + k) <= x < col_x(3 + k) + CW:
                    return ("found", s)
        for i in range(7):
            if col_x(i) <= x < col_x(i) + CW:
                pos = self.tab_positions(i)
                for k in range(len(pos) - 1, -1, -1):
                    cy, hgt = pos[k]
                    if cy <= y < cy + hgt:
                        return ("tab", i, k)
                if not pos and TAB_Y <= y < TAB_Y + CH:
                    return ("tab_empty", i)
        return None

    def drop_target(self, x, y):
        """ドラッグしたカードの左上が (x, y) のときの置き先。いちばん重なっている場所を選ぶ。"""
        cx, cy = x + CW / 2, y + CH / 2
        if cy < TAB_Y - 2:
            for k, s in enumerate(SUITS):
                if abs(cx - (col_x(3 + k) + CW / 2)) < CW:
                    return ("found", s)
            return None
        i = min(range(7), key=lambda i: abs(cx - (col_x(i) + CW / 2)))
        return ("tab", i) if abs(cx - (col_x(i) + CW / 2)) < CW else None

    def waste_fan_offset(self):
        """3枚めくりのとき、捨て札をずらして見せるぶん（いちばん上のカードの位置）。"""
        if self.game.draw == 1 or not self.game.waste:
            return 0
        return 4 * (min(3, len(self.game.waste)) - 1)

    # --- 描画 ---
    def render(self):
        k = PAL
        g = self.game
        night = is_night_time()
        im = Image.new("RGB", (W, H), k["face"])
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W - 1, H - 1], outline=k["out"])
        d.line([(1, 1), (W - 2, 1)], fill=k["light"])
        d.line([(1, 1), (1, H - 2)], fill=k["light"])
        dither_bar(d, 2, 2, W - 3, 11, k["title2"], k["title"])   # 左の明るい色から、右へ網点でなめらかに
        px_pattern(d, 5, 5, _ICONS["cards"], k["light"])
        px_pattern(d, 4, 4, _ICONS["cards"], k["out"])
        px_text(d, 12, 6, "CARDS.EXE", k["light"])
        px_text(d, 11, 5, "CARDS.EXE", k["out"])
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
        # フェルト
        table, table2 = (mix(TABLE, (10, 20, 40), 0.45), mix(TABLE2, (10, 20, 40), 0.45)) if night else (TABLE, TABLE2)
        d.rectangle([2, TOP, W - 3, H - FOOT_H - 1], fill=table)
        for y in range(TOP, H - FOOT_H, 2):
            for x in range(2 + (y // 2) % 2, W - 2, 4):
                d.point((x, y), fill=table2)
        d.line([(2, TOP), (W - 3, TOP)], fill=mix(table, (0, 0, 0), 0.25))       # フェルトのふちのかげ
        d.line([(2, TOP), (2, H - FOOT_H - 1)], fill=mix(table, (0, 0, 0), 0.25))
        d.line([(2, H - FOOT_H), (W - 3, H - FOOT_H)], fill=k["out"])
        im = im.convert("RGBA")
        sd = ImageDraw.Draw(im)
        shadow = mix(table, (0, 0, 0), 0.35)

        def put(card_im, xy):   # カードの右下に、うすいかげをつけて置く
            x, y = xy
            sd.line([(x + 2, y + CH), (x + CW, y + CH)], fill=shadow)
            sd.line([(x + CW, y + 2), (x + CW, y + CH)], fill=shadow)
            im.alpha_composite(card_im, (x, y))
        moving = self.drag["src"] if self.drag and self.drag["moved"] else None
        # 山札
        if g.stock:
            put(card_image(None, back=True), (col_x(0), ROW1_Y))
        else:
            im.alpha_composite(slot_image("again" if g.waste else None), (col_x(0), ROW1_Y))
        # 捨て札（3枚めくりなら、上の3枚をずらして）
        shown = g.waste[-(3 if g.draw == 3 else 1):]
        if moving and moving[0] == "waste":
            shown = shown[:-1]
        if not shown:
            im.alpha_composite(slot_image(), (col_x(1), ROW1_Y))
        for n, c in enumerate(shown):
            put(card_image(c), (col_x(1) + (4 * n if g.draw == 3 else 0), ROW1_Y))
        # 組札
        for n, s in enumerate(SUITS):
            pile = g.found[s]
            if moving and moving == ("found", s):
                pile = pile[:-1]
            if pile:
                put(card_image(pile[-1]), (col_x(3 + n), ROW1_Y))
            else:
                im.alpha_composite(slot_image(s), (col_x(3 + n), ROW1_Y))
        # 場札
        for i, col in enumerate(g.tableau):
            if not col:
                im.alpha_composite(slot_image(), (col_x(i), TAB_Y))
            for n, ((c, up), (cy, _)) in enumerate(zip(col, self.tab_positions(i))):
                if moving and moving[0] == "tab" and moving[1] == i and n >= moving[2]:
                    break
                put(card_image(c, back=not up), (col_x(i), cy))
        # ドラッグ中のカード
        if moving:
            for n, c in enumerate(g.take(moving)):
                put(card_image(c), (round(self.drag["x"]), round(self.drag["y"]) + n * UP_OFF))
        im = im.convert("RGB")
        d = ImageDraw.Draw(im)
        # 下の欄：手数・時間・UNDO
        fy = H - FOOT_H + 3
        t = g.elapsed()
        px_text(d, 5, fy, f"MOVES {g.moves}", k["out"])
        px_text(d, 50, fy, f"{t // 60}:{t % 60:02d}", k["second"])
        ux0, uy0, ux1, uy1 = self.undo_rect()
        on = self.hover == "undo" and g.history and not g.won()
        d.rectangle([ux0, uy0, ux1, uy1], fill=k["hover"] if on else k["face"], outline=k["out"])
        px_pattern(d, ux0 + 2, uy0 + 2, _ICONS["undo"], k["accent"] if g.history else k["shade"])
        px_text(d, ux0 + 9, uy0 + 2, "UNDO", k["out"] if g.history else k["shade"])
        if g.won():
            self.draw_win(d, t, g.moves)
        return recolor(im, self.cmap())

    def draw_win(self, d, t, moves):
        k = PAL
        y0 = TAB_Y + 30
        d.rectangle([12, y0, W - 13, y0 + 30], fill=k["face"], outline=k["out"])
        d.rectangle([13, y0 + 1, W - 14, y0 + 9], fill=k["title"])
        msg = "CLEAR!"
        px_text(d, (W - px_text_w(msg, 2)) // 2, y0 + 12, msg, k["accent"], 2)
        sub = f"{t // 60}:{t % 60:02d}  {moves} MOVES"
        px_text(d, (W - px_text_w(sub)) // 2, y0 + 3, sub, k["out"])

    def redraw(self):
        img = self.render().resize((W * self.p, H * self.p), Image.NEAREST)
        self.photo = ImageTk.PhotoImage(img)
        self.label.config(image=self.photo)

    def tick(self):
        g = self.game
        if g.t0 is not None and not g.won() and not self.drag:
            self.redraw()
        self.root.after(1000, self.tick)

    # --- マウス ---
    def pos(self, e):
        return e.x / self.p, e.y / self.p

    def in_rect(self, x, y, r):
        return r[0] <= x <= r[2] + 1 and r[1] <= y <= r[3] + 1

    def on_hover(self, e):
        x, y = self.pos(e)
        h = "undo" if self.in_rect(x, y, self.undo_rect()) else None
        if h != self.hover:
            self.hover = h
            self.redraw()

    def on_press(self, e):
        x, y = self.pos(e)
        self.drag = None
        self._win_drag = None
        if self.finishing:
            return
        target = self.hit(x, y)
        g = self.game
        if target is None:
            bx0 = W - 3 - 3 * 9
            if y < TOP and not self.in_rect(x, y, self.game_btn_rect()) and x < bx0:
                self._win_drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
            return
        src = None
        if target[0] == "waste":
            src = ("waste",)
        elif target[0] == "found":
            src = ("found", target[1])
        elif target[0] == "tab":
            src = ("tab", target[1], target[2])
        if src and g.take(src):
            if src[0] == "tab":
                ox, oy = col_x(src[1]), self.tab_positions(src[1])[src[2]][0]
            elif src[0] == "waste":
                ox, oy = col_x(1) + self.waste_fan_offset(), ROW1_Y
            else:
                ox, oy = col_x(3 + SUITS.index(src[1])), ROW1_Y
            self.drag = {"src": src, "dx": x - ox, "dy": y - oy, "x": ox, "y": oy, "moved": False,
                         "start": (x, y)}
        self._target = target

    def on_motion(self, e):
        if self._win_drag:
            self.root.geometry(f"+{e.x_root - self._win_drag[0]}+{e.y_root - self._win_drag[1]}")
            return
        if not self.drag:
            return
        x, y = self.pos(e)
        dr = self.drag
        if not dr["moved"] and abs(x - dr["start"][0]) + abs(y - dr["start"][1]) < 2:
            return
        dr["moved"] = True
        dr["x"], dr["y"] = x - dr["dx"], y - dr["dy"]
        self.redraw()

    def on_release(self, e):
        x, y = self.pos(e)
        g = self.game
        if self._win_drag:
            self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
            self.save()
            self._win_drag = None
            return
        if self.finishing:
            return
        dr, self.drag = self.drag, None
        if dr and dr["moved"]:   # ドラッグで置く
            dst = self.drop_target(dr["x"], dr["y"])
            if dst:
                g.move(dr["src"], dst)
            self.after_move()
            return
        if dr:                   # クリックで、置ける所へ
            dst = g.best_target(dr["src"])
            if dst:
                g.move(dr["src"], dst)
            self.after_move()
            return
        if self.in_rect(x, y, self.undo_rect()):
            g.undo()
            self.redraw()
            return
        if self.hit(x, y) == ("stock",):
            g.deal()
            self.count_play()
            self.redraw()
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

    def count_play(self):
        if not self.counted and self.game.t0 is not None:
            self.counted = True
            self.cfg["plays"] = self.cfg.get("plays", 0) + 1
            self.save()

    def after_move(self):
        g = self.game
        self.count_play()
        if g.won():
            self.record()
        elif g.can_finish():   # 残りは自動で組札へ
            self.finishing = True
            self.root.after(150, self.finish_step)
        self.redraw()

    def finish_step(self):
        g = self.game
        for i in range(7):
            if g.tableau[i]:
                src = ("tab", i, len(g.tableau[i]) - 1)
                card = g.take(src)[0]
                if g.can_move(src, ("found", card[1])):
                    g.move(src, ("found", card[1]))
                    break
        else:
            self.finishing = False
        if g.won():
            self.finishing = False
            self.record()
        self.redraw()
        if self.finishing:
            self.root.after(120, self.finish_step)

    def record(self):
        if self.recorded:
            return
        self.recorded = True
        g = self.game
        key = str(g.draw)
        best = self.cfg.setdefault("best", {})
        t = g.elapsed()
        if key not in best or t < best[key]["time"]:
            best[key] = {"time": t, "moves": g.moves}
        self.cfg["wins"] = self.cfg.get("wins", 0) + 1
        self.save()

    # --- メニュー ---
    def menu_items(self):
        c = self.cfg
        best = c.get("best", {})

        def best_text(key):
            b = best.get(key)
            return f"{b['time'] // 60}:{b['time'] % 60:02d}・{b['moves']}手" if b else "—"
        return [
            {"type": "cmd", "label": "新しいゲーム", "cmd": lambda: (self.new_game(), self.redraw())},
            {"type": "cmd", "label": "ひとつ戻す", "cmd": lambda: (self.game.undo(), self.redraw()),
             "enabled": bool(self.game.history) and not self.game.won()},
            {"type": "sep"},
            {"type": "head", "label": "山札からめくる枚数（次のゲームから）"},
            {"type": "radio", "label": "1枚ずつ（やさしい）", "checked": c["draw"] == 1, "cmd": lambda: self.set_draw(1)},
            {"type": "radio", "label": "3枚ずつ（むずかしい）", "checked": c["draw"] == 3, "cmd": lambda: self.set_draw(3)},
            {"type": "sep"},
            {"type": "head", "label": f"クリア {c.get('wins', 0)}回 ／ {c.get('plays', 0)}ゲーム"},
            {"type": "head", "label": f"ベスト（1枚）　{best_text('1')}"},
            {"type": "head", "label": f"ベスト（3枚）　{best_text('3')}"},
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
            {"type": "head", "label": f"ドットソリティア ver.{APP_VERSION}"},
        ]

    def set_draw(self, n):
        self.cfg["draw"] = n
        self.save()

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
        Solitaire().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "solitaire_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
