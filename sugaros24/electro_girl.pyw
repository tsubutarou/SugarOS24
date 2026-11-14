# -*- coding: utf-8 -*-
"""
エレクトロガール ver.1（ELECTRO GIRL）
デスクトップにいる、おやつ好きの女の子。SugarOS 24 の仲間。

遊び方:
  おやつ    … おやつをあげる（おなか・ごきげんが上がる）
  おはなし  … 話しかける（質問されたら「うん／ううん」で答える）
  でんき    … 電気を消すと眠る。つけると起きる（寝起き）
  ゲーム    … コントローラーを持って一緒に遊ぶ
  レコード  … 資料レコードで曲が流れていると、起きているときはときどきリズムに合わせてノる
  お天気    … ドットお天気が雨や雪だと、おへやの窓の外にも降る（降りはじめると、ひとこと）
  クリック  … なでる
  右クリック … メニュー（おへや／デスクトップの切り替え、しゃべる頻度、カラー、サイズ など）

自分で描いた絵や、ほかのAIに描いてもらった絵は「キャラ取り込み」（chara_import.pyw）で取り込める。
  右クリック →「だれといる？」→「キャラを取り込む…」からも開ける。描き方は electro_girl_data の「キャラの描き方.txt」

絵や会話は electro_girl_data フォルダの中身を差し替えれば変えられる:
  chara/<id>/atlas.png, atlas_map.json, meta.json … キャラの絵（64×64タイル）
    （body_groove_0 / body_groove_1 を描き足すと、ノっているときにその2枚を交互に使う）
  lines.json / topics.json / snacks.json            … ひとりごと・会話・おやつ
  chara/<id>/room.png, room_night.png               … その子のおへや（100×80。キャラ取り込みの「おへやの絵」で作れる）

必要なもの: pip install pillow
"""
import datetime as dt
import subprocess
import sys
import math
import os
import random
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageEnhance, ImageTk

from mushiboshi_ui import (COLORWAY_NAMES, dither_gradient, log_errors, is_night_time, PixelMenu, colorway_cmap, colorway_menu,
                           colorway_theme, load_colorway, load_now_playing, load_weather, draw_weather, recolor, save_colorway, ui_font, Scale,
                           PX_FONT, hexc, mix, px_pattern, px_text, load_json, save_json)

APP_VERSION = "1.6"
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def find_data_dir():
    """electro_girl_data を探す。zipを展開したときに二重フォルダになっていても見つける"""
    cands = [os.path.join(APP_DIR, "electro_girl_data")]
    for root, dirs, files in os.walk(APP_DIR):
        if root[len(APP_DIR):].count(os.sep) > 3:
            dirs[:] = []
            continue
        if os.path.basename(root) == "electro_girl_data" and "chara" in dirs:
            cands.insert(0, root)
            break
    for c in cands:
        if os.path.isdir(os.path.join(c, "chara")):
            return c
    return cands[-1]


DATA_DIR = find_data_dir()
CONFIG_PATH = os.path.join(APP_DIR, "electro_girl_config.json")
SAVE_PATH = os.path.join(APP_DIR, "electro_girl_save.json")
DOCK_PATH = os.path.join(APP_DIR, "mushiboshi_dock.json")   # ランチャーが書く、バーの位置
FPS = 12
T = 64
KEY = (255, 0, 255)   # デスクトップモードで透明にする色

DEFAULT_CONFIG = {"chara": "auto", "mode": "room", "scale": 3, "topmost": True, "chatter": "normal", "groove": True,
                  "x": 360, "y": 160}
SCALES = [("ミニ", 1.5), ("小", 2), ("中", 3), ("大", 4)]
CHARAS = [("オレンジ", "orange"), ("ブルー", "blue"), ("ミント", "mint"), ("ピンク", "pink")]   # 最初からいる4人


def chara_list():
    """選べるキャラ [(名前, id)]。むかしの4人（フォルダがあれば）のあとに、取り込んだキャラ（カラーの順→取り込んだ順）。"""
    root = os.path.join(DATA_DIR, "chara")
    out = [(n, k) for n, k in CHARAS if os.path.isdir(os.path.join(root, k))]
    extra = []
    try:
        for k in os.listdir(root):
            if k in dict((kk, n) for n, kk in CHARAS) or not os.path.isfile(os.path.join(root, k, "atlas.png")):
                continue
            meta = load_json(os.path.join(root, k, "meta.json"), {})
            seq = ["pink", "orange", "blue", "mint"]   # キャンディ・ドーナツ・ケーキ・アイスの順に
            order = seq.index(meta["colorway"]) if meta.get("colorway") in seq else 99
            extra.append(((order, meta.get("imported", "")), meta.get("name", k), k))
    except OSError:
        pass
    result, seen = [], {}
    for n, k in out + [(n, k) for _, n, k in sorted(extra)]:   # 同じ名前の子は「ケーキ（2）」のように番号をつける
        seen[n] = seen.get(n, 0) + 1
        result.append((n if seen[n] == 1 else f"{n}（{seen[n]}）", k))
    return result
CHATTER = [("よくしゃべる", "often", (20, 45)), ("ふつう", "normal", (45, 110)),
           ("しずか", "quiet", (150, 330)), ("しゃべらない", "off", None)]
# レコードが流れているときのノり方（秒）：かかってから最初にノるまで / ノっている長さ / 次にノるまでの休み
GROOVE_FIRST, GROOVE_LEN, GROOVE_REST = (5, 40), (15, 40), (60, 180)

_ICONS = {
    "plug": ".#.#.|.#.#.|#####|#####|.###.|..#..",
    "snack": "...#...|..###..|.#####.|#######|#.#.#.#|#######",
    "talk": ".#####.|#######|#######|.#####.|..#....|.#.....",
    "light": "..###..|.#####.|.#####.|..###..|..###..|...#...",
    "game": ".#####.|#######|#.###.#|##.#.##|#######|.#...#.",
    "heart": ".#.#.|#####|#####|.###.|..#..",
    "cake": "..#..|.###.|#####|#.#.#|#####",
    "star": "..#..|.###.|#####|.###.|.#.#.",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
}

PAL = dict(face=(244, 238, 250), out=(64, 44, 86), light=(255, 255, 255), shade=(206, 192, 226),
           title=(218, 176, 226), title2=(236, 210, 242), accent=(236, 88, 130), hover=(255, 214, 228),
           second=(140, 112, 180))
COLOR_BASE = {v: k for k, v in PAL.items() if k != "light"}

# おへやモードの窓
W, H = 106, 121
SX, SY, SW, SH = 3, 14, 100, 80
STAT_Y = 96
ROW = 107
BUTTONS = {"snack": 3, "talk": 28, "light": 53, "game": 78}
BTN_W = 25
FLOOR_Y = 77           # 足の位置（おへやの中）
# デスクトップモードの窓
DW, DH = 110, 84


def today():
    return dt.date.today().isoformat()


# ---------- キャラの絵 ----------

class Chara:
    def __init__(self, cid):
        base = os.path.join(DATA_DIR, "chara", cid)
        self.meta = load_json(os.path.join(base, "meta.json"), {})
        amap = load_json(os.path.join(base, "atlas_map.json"), {"slots": {}, "tile_size": [T, T]})
        tw, th = amap.get("tile_size", [T, T])
        self.tiles = {}
        try:
            atlas = Image.open(os.path.join(base, "atlas.png")).convert("RGBA")
            for name, s in amap.get("slots", {}).items():
                tile = atlas.crop((s["col"] * tw, s["row"] * th, s["col"] * tw + tw, s["row"] * th + th))
                if tile.getbbox():
                    self.tiles[name] = tile
        except OSError:
            pass
        self.name = self.meta.get("name", cid)
        self.cache = {}
        # その子のおへや（room.png / room_night.png）。なければ、いつものおへやを描く
        self.room_day = self._load_room(os.path.join(base, "room.png"))
        self.room_night = self._load_room(os.path.join(base, "room_night.png"))
        box = lambda key: tuple(self.meta[key]) if len(self.meta.get(key) or []) == 4 else None   # noqa: E731
        self.room_window, self.room_tv = box("room_window"), box("room_tv")   # 窓（雨や雪を降らせる）・テレビの場所
        self.room_lamps = [tuple(p) for p in self.meta.get("room_lamps") or [] if len(p) == 3]   # 夜に光るランプ (x, y, 半径)
        # 窓の空。もとの絵が夕焼けなら、room_sky_box（空のところ）と room_sky_time: "dusk" を書いておく
        self.room_sky_box = box("room_sky_box") or self.room_window
        self.room_sky_time = self.meta.get("room_sky_time", "day")
        warm = {"day": False, "night": "night"}.get(self.room_sky_time, True)
        self.room_sky = (find_sky(self.room_day, self.room_sky_box, warm=warm)
                         if self.room_day and self.room_sky_box else None)
        self.room_cache = {}

    @staticmethod
    def _load_room(path):
        try:
            with Image.open(path) as im:
                return im.convert("RGB").resize((SW, SH), Image.NEAREST) if im.size != (SW, SH) else im.convert("RGB")
        except (OSError, ValueError):
            return None

    def get(self, *names):
        for n in names:
            if n in self.tiles:
                return self.tiles[n]
        return None

    def compose(self, pose, eye, mouth, prop=None, flip=False):
        key = (pose, eye, mouth, prop, flip)
        if key in self.cache:
            return self.cache[key]
        im = Image.new("RGBA", (T, T), (0, 0, 0, 0))
        body = "body_" + pose
        if self.meta.get("full_pose"):   # 取り込んだキャラ：ポーズごとの1枚絵。まばたき・おしゃべりは「たち」の差分の絵で
            if pose == "idle" and eye == "eye_close" and "body_blink" in self.tiles:
                body = "body_blink"
            elif pose == "idle" and mouth == "mouth_1" and "body_talk" in self.tiles:
                body = "body_talk"
        for layer in (self.get(body, "body_idle"), self.get("clothes_" + pose, "clothes_idle")):
            if layer is not None:
                im.alpha_composite(layer)
        off = self.meta.get("face_offset", {}).get(pose, [0, 0])
        for name in (eye, mouth):
            layer = self.get(name)
            if layer is not None:
                im.alpha_composite(layer, (off[0], off[1]))
        if prop:
            layer = self.get(prop)
            if layer is not None:
                im.alpha_composite(layer)
        if flip:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if len(self.cache) > 200:
            self.cache.clear()
        self.cache[key] = im
        return im


# ---------- 会話データ ----------

class Talk:
    def __init__(self):
        self.lines = load_json(os.path.join(DATA_DIR, "lines.json"), {}).get("lines", [])
        self.topics = load_json(os.path.join(DATA_DIR, "topics.json"), {}).get("topics", [])
        snacks = load_json(os.path.join(DATA_DIR, "snacks.json"), {}).get("snacks", [])
        self.snacks = []
        for s in snacks:
            try:
                icon = Image.open(os.path.join(DATA_DIR, "snacks", s.get("icon", ""))).convert("RGBA")
            except OSError:
                icon = None
            self.snacks.append(dict(s, image=icon))

    def line(self, tag):
        cands = [l["text"] for l in self.lines if tag in l.get("tags", [])]
        return random.choice(cands) if cands else None

    def unlocked(self, topic, st):
        return unlock_ok(topic.get("unlock", {"type": "always"}) or {"type": "always"}, st)


def _hhmm(s):
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def unlock_ok(u, st):
    typ = (u.get("type") or "always").strip()
    if typ == "always":
        return True
    if typ == "affection_gte":
        return st["affection"] >= float(u.get("value", 0))
    if typ == "days_since_first_gte":
        return (time.time() - st["first_ts"]) / 86400 >= float(u.get("value", 0))
    if typ == "flag":
        return bool(st["flags"].get(u.get("name", "")))
    if typ == "time_range":
        fr, to = _hhmm(u.get("from", "")), _hhmm(u.get("to", ""))
        if fr is None or to is None:
            return False
        now = dt.datetime.now()
        m = now.hour * 60 + now.minute
        return fr <= m <= to if fr <= to else (m >= fr or m <= to)
    if typ in ("all", "and"):
        return all(unlock_ok(c, st) for c in u.get("conds", []) if isinstance(c, dict))
    if typ in ("any", "or"):
        return any(unlock_ok(c, st) for c in u.get("conds", []) if isinstance(c, dict))
    return False


# ---------- おへや ----------

def sky_colors(hour):
    if 6 <= hour < 16:
        return (110, 170, 240), (200, 228, 252), "day"
    if 16 <= hour < 19:
        return (120, 100, 180), (252, 170, 130), "dusk"
    return (24, 22, 60), (60, 50, 110), "night"


WINDOW_SKY = (8, 8, 33, 32)   # おへやの窓の、空が見えるところ
INK = (84, 48, 86)            # おへやの線の色
# 壁の上のガーランドの電球 (x, y, 色)
FAIRY = [(x, 3 + round(2.2 * math.sin((x - 40) / 60 * math.pi * 2) ** 2), c)
         for x, c in zip(range(42, 100, 6), [(255, 150, 180), (255, 220, 120), (150, 220, 255), (190, 160, 255)] * 3)]


def draw_window_frame(d):
    """窓わく・窓辺・カーテン。窓の外に天気を描いたあと、もう一度上から描く。"""
    frame, frame_d = (250, 248, 252), (206, 194, 220)
    d.rectangle([7, 7, 34, 33], outline=frame)
    d.line([(21, 7), (21, 33)], fill=frame)
    d.line([(7, 20), (34, 20)], fill=frame)
    d.line([(22, 8), (22, 32)], fill=frame_d)
    d.line([(8, 21), (33, 21)], fill=frame_d)
    for gx, gy in ((10, 12), (24, 12)):   # ガラスの映り込み
        d.line([(gx, gy + 2), (gx + 2, gy)], fill=(236, 244, 255))
    # 窓辺と、小さなサボテン
    d.rectangle([5, 33, 36, 35], fill=(232, 222, 238))
    d.line([(5, 33), (36, 33)], fill=(250, 246, 252))
    d.line([(6, 36), (35, 36)], fill=(170, 150, 196))
    d.rectangle([27, 30, 31, 32], fill=(236, 150, 120))
    d.line([(27, 30), (31, 30)], fill=(250, 186, 160))
    d.rectangle([28, 26, 30, 29], fill=(110, 180, 110))
    d.point((29, 25), fill=(250, 130, 180))
    # カーテン（ひだの縦じま、すそは波）
    folds = [(244, 160, 190), (232, 140, 176), (250, 186, 208)]
    for x0 in (2, 33):
        for x in range(x0, x0 + 6):
            col = folds[(x - x0) % 3]
            bottom = 39 + (1 if (x - x0) % 2 else 0)
            d.line([(x, 5), (x, bottom)], fill=col)
        d.line([(x0, 26), (x0 + 5, 26)], fill=(196, 84, 130))   # タッセル
        d.point((x0 + 2, 27), fill=(196, 84, 130))
    d.line([(1, 4), (41, 4)], fill=(150, 110, 150))
    d.point((1, 3), fill=(150, 110, 150))
    d.point((41, 3), fill=(150, 110, 150))


def build_room(hour):
    im = Image.new("RGB", (SW, SH))
    d = ImageDraw.Draw(im)
    # 壁紙（小さなひし形のもよう）
    wall, wall2, dot = (204, 190, 228), (198, 183, 224), (216, 204, 238)
    d.rectangle([0, 0, SW - 1, 45], fill=wall)
    for x in range(0, SW, 8):
        d.line([(x, 0), (x, 45)], fill=wall2)
    for y in range(4, 45, 8):
        for x in range(4 + (y // 8 % 2) * 4, SW, 8):
            px_pattern(d, x - 1, y - 1, ".#.|#.#|.#.", dot)
    # 腰壁
    d.line([(0, 45), (SW - 1, 45)], fill=(232, 222, 244))
    d.line([(0, 46), (SW - 1, 46)], fill=(160, 136, 186))
    d.rectangle([0, 47, SW - 1, 59], fill=(186, 168, 214))
    for x in range(4, SW, 10):
        d.rectangle([x, 49, x + 7, 57], outline=(176, 158, 206))
        d.line([(x + 1, 50), (x + 6, 50)], fill=(198, 182, 224))
    d.rectangle([0, 60, SW - 1, 61], fill=(150, 124, 170))
    d.line([(0, 60), (SW - 1, 60)], fill=(176, 152, 196))
    # 木の床（板の継ぎ目と木目）
    for y in range(62, SH):
        row = (y - 62) // 4
        base = (222, 178, 170) if row % 2 else (214, 168, 162)
        d.line([(0, y), (SW - 1, y)], fill=base)
        if (y - 62) % 4 == 0:
            d.line([(0, y), (SW - 1, y)], fill=(196, 148, 146))
        for jx in range((row * 11) % 18, SW, 18):
            if (y - 62) % 4:
                d.point((jx, y), fill=(196, 148, 146))
        for gx in range((row * 7) % 13 + 3, SW, 13):
            if (y - 62) % 4 == 2:
                d.line([(gx, y), (gx + 2, y)], fill=mix(base, (196, 148, 146), 0.5))
    # 窓の外
    top, bot, kind = sky_colors(hour)
    dither_gradient(d, 8, 8, 33, 32, top, bot, steps=4)
    rnd = random.Random(7)
    if kind == "night":
        for _ in range(10):
            d.point((rnd.randint(9, 32), rnd.randint(9, 30)), fill=(250, 240, 200))
        d.ellipse([24, 11, 30, 17], fill=(250, 240, 190))
        d.ellipse([26, 10, 32, 16], fill=top)
    elif kind == "day":
        for cx in (14, 27):
            d.ellipse([cx - 4, 23, cx + 4, 27], fill=(255, 255, 255))
            d.line([(cx - 3, 27), (cx + 3, 27)], fill=(214, 230, 248))
        d.line([(8, 31), (33, 31)], fill=(170, 210, 150))   # 遠くの木々
        d.line([(8, 32), (33, 32)], fill=(140, 190, 130))
    else:
        d.ellipse([18, 24, 26, 32], fill=(255, 210, 140))
        d.line([(8, 31), (33, 31)], fill=(150, 90, 120))
    draw_window_frame(d)
    # 窓から差しこむ光（昼は陽だまり、夕方は橙、夜は月あかり）
    patch = {"day": (255, 250, 220, 44), "dusk": (255, 190, 140, 36), "night": (170, 180, 255, 22)}[kind]
    over = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(over).polygon([(9, 62), (32, 62), (46, SH - 1), (16, SH - 1)], fill=patch)
    im.paste(Image.alpha_composite(im.convert("RGBA"), over).convert("RGB"))
    d = ImageDraw.Draw(im)
    # ガーランド（電球は、ときどき動きの中できらっとする）
    d.line([(x, y) for x, y, _ in FAIRY], fill=(150, 120, 160))
    for x, y, c in FAIRY:
        d.point((x, y + 1), fill=c)
        d.point((x, y + 2), fill=mix(c, INK, 0.3))
    # 額の絵（ショートケーキ）
    d.rectangle([40, 26, 51, 37], fill=(176, 126, 96))
    d.rectangle([41, 27, 50, 36], fill=(255, 246, 236))
    d.polygon([(42, 34), (49, 34), (49, 30)], fill=(255, 250, 244))
    d.line([(42, 34), (49, 30)], fill=(250, 210, 160))
    d.line([(43, 33), (49, 32)], fill=(240, 120, 140))
    d.point((48, 29), fill=(230, 60, 90))
    # たな（金具と小物）
    d.rectangle([64, 24, 97, 26], fill=(176, 126, 124))
    d.line([(64, 24), (97, 24)], fill=(206, 160, 156))
    for bx in (68, 92):
        d.line([(bx, 27), (bx, 30)], fill=(120, 90, 110))
        d.line([(bx, 30), (bx + 2, 27)], fill=(120, 90, 110))
    d.rectangle([67, 18, 74, 23], fill=(255, 250, 240), outline=INK)          # ケーキの箱とリボン
    d.line([(70, 18), (70, 23)], fill=(236, 90, 130))
    d.line([(67, 20), (74, 20)], fill=(236, 90, 130))
    d.point((69, 17), fill=(236, 90, 130))
    d.point((71, 17), fill=(236, 90, 130))
    for i, (bc, h) in enumerate((((120, 190, 220), 7), ((250, 200, 110), 9), ((170, 140, 220), 8))):   # 本
        x = 77 + i * 3
        d.rectangle([x, 24 - h, x + 2, 23], fill=bc, outline=INK)
        d.point((x + 1, 25 - h), fill=mix(bc, (255, 255, 255), 0.5))
    d.rectangle([89, 19, 94, 23], fill=(200, 150, 110), outline=INK)          # 植木鉢と、垂れる葉
    d.ellipse([87, 13, 96, 19], fill=(110, 190, 110))
    d.point((89, 14), fill=(170, 230, 160))
    for k, y in enumerate((20, 23, 26, 29)):
        d.point((96 - (k % 2), y), fill=(90, 170, 100))
    # コンセント
    d.rectangle([58, 52, 61, 56], fill=(240, 236, 246), outline=(150, 130, 176))
    # テレビ台（引き出しとつまみ）
    d.rectangle([68, 54, 97, 62], fill=(170, 120, 120))
    d.line([(68, 54), (97, 54)], fill=(206, 156, 150))
    d.line([(68, 55), (97, 55)], fill=(196, 146, 140))
    d.rectangle([70, 57, 81, 61], outline=(140, 96, 100))
    d.rectangle([84, 57, 95, 61], outline=(140, 96, 100))
    d.point((75, 59), fill=(236, 210, 170))
    d.point((89, 59), fill=(236, 210, 170))
    # ブラウン管（アンテナ・つや・ボタン）
    d.line([(83, 37), (79, 30)], fill=(120, 110, 140))
    d.line([(85, 37), (90, 31)], fill=(120, 110, 140))
    d.point((79, 29), fill=(236, 88, 130))
    d.rounded_rectangle([71, 37, 96, 54], radius=3, fill=(236, 226, 240), outline=INK)
    d.line([(73, 38), (93, 38)], fill=(252, 248, 255))
    d.rectangle([74, 40, 90, 52], fill=(196, 184, 210))
    d.rectangle([75, 41, 89, 51], fill=(40, 40, 60))
    d.line([(76, 42), (78, 42)], fill=(80, 80, 110))
    d.point((76, 43), fill=(80, 80, 110))
    d.point((92, 44), fill=(236, 72, 100))
    d.point((92, 47), fill=(140, 120, 160))
    d.line([(92, 50), (94, 50)], fill=(180, 168, 196))
    # ラグ（輪のもようと、ふさ）
    d.ellipse([18, 66, 82, 79], fill=(250, 196, 214))
    d.ellipse([22, 67, 78, 78], outline=(240, 170, 196))
    d.ellipse([28, 69, 72, 76], fill=(252, 214, 228))
    d.ellipse([40, 71, 60, 74], outline=(246, 186, 208))
    for fx in range(22, 80, 3):
        d.point((fx, 79), fill=(250, 210, 224))
    # ビーズクッション
    d.ellipse([3, 65, 20, 78], fill=(150, 196, 230), outline=(100, 140, 190))
    d.arc([5, 66, 17, 74], 200, 300, fill=(200, 230, 250))
    return im


def draw_fairy_twinkle(d, now):
    """ガーランドの電球が、順番にきらっとする。"""
    for i, (x, y, c) in enumerate(FAIRY):
        if (int(now * 3) + i * 4) % 9 == 0:
            d.point((x, y + 1), fill=(255, 255, 240))
            d.point((x - 1, y + 1), fill=mix(c, (255, 255, 255), 0.5))
            d.point((x + 1, y + 1), fill=mix(c, (255, 255, 255), 0.5))


def wall_clock(d, x, y):
    now = dt.datetime.now()
    d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(255, 250, 244), outline=(84, 48, 86))
    for a in range(12):
        r = math.radians(a * 30)
        d.point((x + round(math.sin(r) * 5), y - round(math.cos(r) * 5)), fill=(200, 170, 200))
    hr = math.radians((now.hour % 12 + now.minute / 60) * 30)
    mr = math.radians(now.minute * 6)
    d.line([(x, y), (x + round(math.sin(hr) * 3), y - round(math.cos(hr) * 3))], fill=(84, 48, 86))
    d.line([(x, y), (x + round(math.sin(mr) * 5), y - round(math.cos(mr) * 5))], fill=(236, 88, 130))


def darken(im, amount, tint=(30, 26, 70)):
    return Image.blend(im, Image.new("RGB", im.size, tint), amount)


# ---------- 取り込んだおへやを、時間と天気で描きかえる ----------

def find_sky(room, box, warm=False):
    """窓の中で空に見えるところ {(x, y): 雲なら True}。青っぽい点が空、白っぽい点が雲。
    warm：夕焼けの空（True）か夜空（"night"）。夕焼けは、明るいオレンジが空、黄色っぽく明るいところが雲や太陽。"""
    x0, y0, x1, y1 = box
    sky = {}
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            r, g, b = room.getpixel((x, y))
            if warm == "night":   # 夜空：紺色が空、星や月も空として塗りかえる、紫っぽいところは雲
                if (b > r + 25 and b > g + 15) or (r >= 150 and g >= 120):
                    sky[(x, y)] = False
                elif b > r + 10 and r >= 90:
                    sky[(x, y)] = True
            elif warm:
                if r >= 200 and g >= 110:
                    sky[(x, y)] = g >= 190
            elif b > r + 15 and b >= g - 5 and not (b - g > 40 and g - r < 25):   # 青紫の窓わくは空にしない
                sky[(x, y)] = False
            elif min(r, g, b) >= 215 and b >= r - 4:
                sky[(x, y)] = True
    return sky


def room_glow(day, night, lamps):
    """夜のおへやに、ランプのあたたかい光。ランプのまわりだけ、昼の絵をあかね色にして戻す。"""
    mask = Image.new("L", day.size, 0)
    md = ImageDraw.Draw(mask)
    for x, y, r in lamps:
        for k in range(6):   # 外ほどうすく
            rr = r * (1 - k / 6)
            md.ellipse([x - rr, y - rr * 0.8, x + rr, y + rr * 0.8], fill=40 + k * 30)
    warm = Image.blend(day, Image.new("RGB", day.size, (255, 196, 130)), 0.18)
    return Image.composite(warm, night, mask)


def room_scene(ch, hour, weather):
    """その子のおへやの、時間と天気にあわせた絵（動かないところだけ。キャッシュする）。"""
    kind = sky_colors(hour)[2]
    gloomy = weather in ("cloudy", "rain", "thunder", "snow", "fog")
    key = (kind, 6 <= hour < 9, gloomy)
    if key in ch.room_cache:
        return ch.room_cache[key]
    day = ch.room_day
    if ch.room_sky_time == "night" and kind != "night":   # 夜の絵なら、明かりをつけたように明るくしてから
        day = Image.blend(ImageEnhance.Brightness(day).enhance(1.45), Image.new("RGB", day.size, (255, 246, 255)), 0.10)
    if kind == "night" and ch.room_night is not None:
        im = ch.room_night.copy()
    elif kind == "night" and ch.room_sky_time == "night":   # もとの絵が夜なら、そのまま
        im = day.copy()
    elif kind == "night":
        im = darken(day, 0.55, (24, 20, 64))
        if ch.room_lamps:
            im = room_glow(day, im, ch.room_lamps)
    elif kind == "dusk":   # もとの絵が夕焼けなら、そのまま
        im = day.copy() if ch.room_sky_time == "dusk" else \
            Image.blend(day, Image.new("RGB", day.size, (255, 160, 110)), 0.14)
    elif key[1]:   # 朝は、ほんのり明るいレモン色
        im = Image.blend(day, Image.new("RGB", day.size, (255, 244, 205)), 0.10)
    elif ch.room_sky_time == "dusk":   # 夕焼けの絵の昼は、少しすっきりさせる
        im = Image.blend(day, Image.new("RGB", day.size, (236, 240, 255)), 0.10)
    else:
        im = day.copy()
    if gloomy and kind != "night":   # くもりや雨の日は、へやが少しうす暗い
        im = darken(im, 0.12, (120, 124, 150))
    if ch.room_sky and ch.room_night is None:   # 窓の空を、その時間の空に塗りかえる
        top, bottom, _ = sky_colors(hour)
        x0, y0, x1, y1 = ch.room_sky_box
        for (x, y), cloud in ch.room_sky.items():
            t = (y - y0) / max(1, y1 - y0)
            if kind == ch.room_sky_time and not key[1]:
                continue   # もとの絵と同じ時間なら、もとの空のまま
            if kind == "day" and key[1]:   # 朝：うすい水色から、地平線は桃色
                c = mix((150, 200, 245), (255, 214, 200), t)
            elif kind == "day":
                c = mix((120, 178, 240), (196, 226, 252), t)
            else:
                c = mix(top, bottom, t)
            if cloud:
                c = mix(c, (255, 214, 196) if kind == "dusk" else
                        (255, 255, 255) if kind == "day" else (90, 86, 140), 0.6)
            im.putpixel((x, y), c)
    ch.room_cache[key] = im
    return im


def room_stars(im, ch, now):
    """夜の窓の星と月。星はゆっくりまたたく。"""
    pts = [p for p, cloud in ch.room_sky.items() if not cloud]
    if not pts:
        return
    sky = set(pts)
    x0, y0, x1, y1 = ch.room_window
    for x, y in pts:
        h = (x * 73 + y * 151) % 23
        if h == 0 or (h == 7 and (int(now * 2) + x) % 5 == 0):
            im.putpixel((x, y), (255, 250, 220) if h == 0 else (190, 200, 255))
    for mx in range(x1 - 3, x0 + 2, -1):   # 右上の、空が3×3あいているところに三日月
        for my in range(y0, y0 + 6):
            if all((mx + i, my + j) in sky for i in range(3) for j in range(3)):
                for i, j in ((1, 0), (2, 0), (0, 1), (0, 2), (1, 2), (2, 2), (1, 1)):
                    im.putpixel((mx + i, my + j), (255, 240, 170) if (i, j) != (1, 1) else (230, 214, 150))
                return


# ---------- 窓（ドット絵） ----------

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
    px_pattern(d, 4, 4, _ICONS["plug"], k["accent"])
    px_text(d, 11, 5, "ELECTRO GIRL", k["out"])
    bx0 = W - 3 - 3 * 9
    for i, icon in enumerate(("min", "max", "close")):
        x0 = bx0 + i * 9
        d.rectangle([x0, 3, x0 + 7, 10], fill=k["hover"] if icon == "close" else k["face"], outline=k["out"])
        px_pattern(d, x0 + 1, 4, _ICONS[icon], k["out"])
    d.line([(1, 12), (W - 2, 12)], fill=k["out"])
    d.rectangle([SX - 1, SY - 1, SX + SW, SY + SH], outline=k["out"])
    return im


def render_status(st):
    k = PAL
    w, h = SW, 8
    im = Image.new("RGB", (w, h), k["face"])
    d = ImageDraw.Draw(im)
    vals = [("cake", st["hunger"]), ("heart", st["mood"]), ("star", 100 - st["sleepy"])]
    for i, (icon, v) in enumerate(vals):
        x = i * 34
        px_pattern(d, x, 1, _ICONS[icon], k["accent"])
        full = max(0, min(5, round(v / 20)))
        for j in range(5):
            x0 = x + 7 + j * 5
            d.rectangle([x0, 2, x0 + 3, 5], outline=k["out"], fill=k["accent"] if j < full else k["light"])
    return im


def render_button(icon, hover=False, lit=False):
    k = PAL
    w, h = BTN_W - 2, 11
    fill = k["hover"] if (hover or lit) else k["face"]
    im = Image.new("RGB", (w, h), fill)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], fill=fill, outline=k["out"])
    d.line([(1, 1), (w - 2, 1)], fill=k["light"])
    d.line([(1, h - 2), (w - 2, h - 2)], fill=tuple(round(v * 0.88) for v in fill))
    pat = _ICONS[icon]
    iw, ih = len(pat.split("|")[0]), len(pat.split("|"))
    px_pattern(d, (w - iw) // 2, (h - ih) // 2, pat, k["out"] if hover else k["accent"])
    return im


NOTES = ["..##|..#.|..#.|###.|###.", "#####|#...#|#...#|##.##|##.##"]   # 音符（♪ と ♫）


def heart_sprite(d, x, y, color=(240, 90, 130)):
    px_pattern(d, x, y, _ICONS["heart"], color)


# ---------- 本体 ----------

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_PATH, {}))
    return cfg


def new_state():
    now = time.time()
    return {"hunger": 70.0, "mood": 70.0, "sleepy": 20.0, "affection": 0.0, "flags": {},
            "lights": True, "asleep": False, "first_ts": now, "last_ts": now}


class ElectroGirl:
    def __init__(self):
        self.cfg = load_config()
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.p = Scale(self.cfg["scale"])
        self._chara_id = self.chara_id()
        self.chara = Chara(self._chara_id)
        self.talk = Talk()
        self.st = new_state()
        self.st.update(load_json(SAVE_PATH, {}))
        self.away = self.catch_up()

        # 動き
        self.x = 50.0 if self.cfg["mode"] == "room" else DW / 2
        self.dir = 1
        self.action = "sleep" if self.st["asleep"] else "idle"
        self.action_until = time.time() + 3
        self.walk_target = None
        self.blink_at = time.time() + 3
        self.particles = []
        self.music = None   # レコードで流れている曲（ノっているあいだだけ）
        self.groove_until = 0
        self.next_groove = None   # レコードが流れているとき、次にノりはじめる時刻
        self.last_weather = load_weather()   # 起動したときの天気には何も言わない
        self.snack = None
        self.game = False
        self.say_queue = []
        self.bubble_until = 0
        self.typing = None
        self.next_chatter = time.time() + 20
        self.room_cache = (None, None)
        self.pimgs = {}

        self.root = tk.Tk()
        log_errors(self.root, "electro_girl_error.txt")
        self.root.title(f"エレクトロガール ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "electro_girl.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])
        self.key_ok = True
        try:
            self.root.attributes("-transparentcolor", hexc(KEY))
        except tk.TclError:
            self.key_ok = False

        self.frame_label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.screen = tk.Label(self.root, bd=0, highlightthickness=0)
        self.status = tk.Label(self.root, bd=0, highlightthickness=0)
        for w in (self.root, self.frame_label, self.screen, self.status):
            w.bind("<ButtonPress-1>", self.press)
            w.bind("<B1-Motion>", self.drag_move)
            w.bind("<ButtonRelease-1>", self.release)
            w.bind("<Button-3>", self.popup_menu)
        self.frame_label.bind("<Motion>", self.frame_hover, add="+")
        self.buttons = {}
        for key, action in (("snack", self.snack_menu), ("talk", self.start_topic),
                            ("light", self.toggle_lights), ("game", self.toggle_game)):
            lb = tk.Label(self.root, bd=0, highlightthickness=0, cursor="hand2")
            lb.bind("<Button-1>", lambda e, a=action, k=key: a(e) if k == "snack" else a())
            lb.bind("<Enter>", lambda e, k=key: self.draw_button(k, True))
            lb.bind("<Leave>", lambda e, k=key: self.draw_button(k, False))
            lb.bind("<Button-3>", self.popup_menu)
            self.buttons[key] = lb
        # ふきだし
        self.bubble = tk.Frame(self.root, bd=0, highlightthickness=0)
        self.bubble_text = tk.Label(self.bubble, anchor="w", justify="left", bd=0)
        self.bubble_text.pack(fill="x", padx=1, pady=1)
        self.choice_row = tk.Frame(self.bubble, bd=0)
        self.choice_btns = []
        for i in range(2):
            b = tk.Label(self.choice_row, bd=0, cursor="hand2", padx=6)
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, i=i: self.answer(i))
            self.choice_btns.append(b)
        self.bubble.bind("<Button-1>", lambda e: self.skip_bubble())
        self.bubble_text.bind("<Button-1>", lambda e: self.skip_bubble())

        self.pmenu = PixelMenu(self.root, self.menu_theme, title="ELECTRO GIRL - MENU")
        self.layout()
        self.root.after(1000 // FPS, self.tick)
        self.root.after(2000, self.slow_tick)
        self.root.after(30000, self.autosave)
        self.root.after(700, self.greet)

    # --- 時間の経過 ---
    def catch_up(self):
        now = time.time()
        away = max(0.0, now - self.st.get("last_ts", now))
        self.advance(min(away, 12 * 3600) / 60)
        self.st["last_ts"] = now
        return away

    def advance(self, minutes):
        s = self.st
        s["hunger"] = max(0.0, s["hunger"] - 0.45 * minutes)
        if s["asleep"]:
            s["sleepy"] = max(0.0, s["sleepy"] - 2.0 * minutes)
        else:
            s["sleepy"] = min(100.0, s["sleepy"] + (0.6 if self_game(self) else 0.35) * minutes)
        drift = 0.0
        if s["hunger"] < 20:
            drift -= 0.4
        if s["sleepy"] > 90 and not s["asleep"]:
            drift -= 0.2
        if drift == 0:
            drift = 0.05 if s["mood"] < 60 else -0.02
        if self_game(self):
            drift += 0.3
        s["mood"] = max(0.0, min(100.0, s["mood"] + drift * minutes))

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
        self.reload_chara()
        self.layout()

    # --- キャラ ---
    def chara_id(self):
        c = self.cfg["chara"]
        if c == "auto":   # カラーに合わせる：そのカラーの取り込んだキャラがいれば、その子。いなければ最初からいる子
            cw = self.colorway if any(k == self.colorway for _, k in CHARAS) else "pink"
            c = next((k for _, k in reversed(chara_list())
                      if load_json(os.path.join(DATA_DIR, "chara", k, "meta.json"), {}).get("colorway") == cw
                      and load_json(os.path.join(DATA_DIR, "chara", k, "meta.json"), {}).get("full_pose")), cw)
        if not os.path.isdir(os.path.join(DATA_DIR, "chara", c)):
            for _, k in chara_list():
                return k
        return c

    def reload_chara(self):
        cid = self.chara_id()
        if cid != getattr(self, "_chara_id", None):
            self._chara_id = cid
            self.chara = Chara(cid)

    def open_importer(self):
        """キャラ取り込みを開く（取り込んだら、このメニューから選べる）。"""
        script = os.path.join(APP_DIR, "chara_import.pyw")
        if not os.path.exists(script):
            self.say("chara_import.pyw が見つからないよ。エレクトロガールと同じフォルダに置いてね", hold=8)
            return
        exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        subprocess.Popen([exe if os.path.exists(exe) else sys.executable, script], cwd=APP_DIR,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def set_chara(self, k):
        self.cfg["chara"] = k
        self.save()
        self.reload_chara()

    # --- 配置 ---
    def layout(self):
        p = self.p
        room = self.cfg["mode"] == "room"
        if room:
            self.root.geometry(f"{W * p}x{H * p}+{self.cfg['x']}+{self.cfg['y']}")
            img = recolor(render_window(), self.cmap()).resize((W * p, H * p), Image.NEAREST)
            self.frame_photo = ImageTk.PhotoImage(img)
            self.frame_label.config(image=self.frame_photo)
            self.frame_label.place(x=0, y=0, width=W * p, height=H * p)
            self.screen.place(x=SX * p, y=SY * p, width=SW * p, height=SH * p)
            self.status.place(x=SX * p, y=STAT_Y * p, width=SW * p, height=8 * p)
            for key, x in BUTTONS.items():
                self.draw_button(key)
                self.buttons[key].place(x=x * p, y=ROW * p)
            self.draw_status()
            self.x = min(max(self.x, 14), SW - 14)
        else:
            for w in [self.frame_label, self.status] + list(self.buttons.values()):
                w.place_forget()
            self.root.config(bg=hexc(KEY) if self.key_ok else hexc((204, 190, 228)))
            self.screen.config(bg=self.root.cget("bg"))
            self.screen.place(x=0, y=0, width=DW * p, height=DH * p)
            self.x = min(max(self.x, 14), DW - 14)
            self.dock()
        fill, out = self.col("light"), self.col("out")
        self.bubble.config(bg=hexc(out))
        self.bubble_text.config(bg=hexc(fill), fg=hexc(out), font=ui_font(self.root, max(12, int(p * 4.6))),
                                padx=p * 2, pady=p, wraplength=(SW - 10 if room else DW - 6) * p)
        self.choice_row.config(bg=hexc(fill), padx=p * 2, pady=p)
        for b in self.choice_btns:
            b.config(bg=hexc(self.col("hover")), fg=hexc(out), font=ui_font(self.root, max(12, int(p * 4.6))),
                     highlightthickness=max(1, p // 2), highlightbackground=hexc(out), highlightcolor=hexc(out))
        if self.bubble.winfo_ismapped():
            self.place_bubble()

    def dock(self):
        """デスクトップモード: ランチャーのバーの上に立つ"""
        p = self.p
        info = load_json(DOCK_PATH, None)
        if info and time.time() - info.get("ts", 0) < 15:
            x = info["x"] + info["w"] - DW * p - 40
            y = info["y"] - DH * p + p
        else:
            x, y = self.cfg["x"], self.cfg["y"]
        self.docked = bool(info and time.time() - info.get("ts", 0) < 15)
        self.root.geometry(f"{DW * p}x{DH * p}+{int(x)}+{int(y)}")

    def draw_button(self, key, hover=False):
        lit = (key == "game" and self.game) or (key == "light" and not self.st["lights"])
        img = recolor(render_button(key, hover, lit), self.cmap())
        img = ImageTk.PhotoImage(img.resize(((BTN_W - 2) * self.p, 11 * self.p), Image.NEAREST))
        self.pimgs[key] = img
        self.buttons[key].config(image=img)

    def draw_status(self):
        if self.cfg["mode"] != "room":
            return
        img = recolor(render_status(self.st), self.cmap()).resize((SW * self.p, 8 * self.p), Image.NEAREST)
        self.status_photo = ImageTk.PhotoImage(img)
        self.status.config(image=self.status_photo)

    # --- ふきだし ---
    def say(self, text, then=None, choices=None, hold=None):
        if not text:
            return
        self.say_queue.append((text, then, choices, hold))
        if self.typing is None and time.time() >= self.bubble_until:
            self.next_say()

    def say_tag(self, tag):
        self.say(self.talk.line(tag))

    def next_say(self):
        if not self.say_queue:
            self.bubble.place_forget()
            self.typing = None
            return
        text, then, choices, hold = self.say_queue.pop(0)
        self.typing = dict(text=text, n=0, then=then, choices=choices, hold=hold)
        self.bubble_text.config(text="")
        self.choice_row.pack_forget()
        self.place_bubble()

    def place_bubble(self):
        p = self.p
        if self.cfg["mode"] == "room":
            self.bubble.place(x=(SX + 3) * p, y=(SY + 2) * p, width=(SW - 6) * p)
        else:
            self.bubble.place(x=2 * p, y=0, width=(DW - 4) * p)
        self.bubble.lift()

    def type_step(self):
        ty = self.typing
        if ty is None:
            return
        if ty["n"] < len(ty["text"]):
            ty["n"] = min(len(ty["text"]), ty["n"] + 2)
            self.bubble_text.config(text=ty["text"][:ty["n"]])
            if ty["n"] >= len(ty["text"]):
                ty["done_at"] = time.time()
                if ty["choices"]:
                    yes, no = ty["choices"]
                    self.choice_btns[0].config(text=yes)
                    self.choice_btns[1].config(text=no)
                    self.choice_row.pack(fill="x")
            return
        if ty["choices"]:
            if time.time() - ty["done_at"] > 25:   # 答えがないときは、そっと閉じる
                self.finish_say(None)
            return
        hold = ty["hold"] or max(2.4, len(ty["text"]) * 0.09 + 1.6)
        if time.time() - ty["done_at"] > hold:
            self.finish_say(None)

    def finish_say(self, answer):
        ty = self.typing
        self.typing = None
        self.bubble_until = time.time() + 0.4
        if ty and ty["then"]:
            ty["then"](answer)
        if not self.say_queue:
            self.bubble.place_forget()
        else:
            self.root.after(400, self.next_say)

    def skip_bubble(self):
        ty = self.typing
        if not ty or ty["choices"]:
            return
        if ty["n"] < len(ty["text"]):
            ty["n"] = len(ty["text"])
            self.bubble_text.config(text=ty["text"])
            ty["done_at"] = time.time()
        else:
            self.finish_say(None)

    def answer(self, i):
        if self.typing and self.typing["choices"]:
            self.finish_say(i)

    def talking(self):
        return self.typing is not None and self.typing["n"] < len(self.typing["text"])

    # --- できごと ---
    def greet(self):
        if not self.chara.tiles:
            self.say(f"絵が見つからないよ…\n{os.path.join(DATA_DIR, 'chara', self.chara_id(), 'atlas.png')}"
                     " に置いてね", hold=30)
            return
        if self.st["asleep"]:
            return
        if self.away > 24 * 3600:
            self.say_tag("greet_long")
        elif self.away > 3 * 3600:
            self.say_tag("greet_short")
        for t in self.talk.topics:
            if "auto" in t.get("tags", []) and t.get("once_per_day") and self.talk.unlocked(t, self.st):
                key = "auto_done_" + t["id"]
                if self.st["flags"].get(key) != today():
                    self.st["flags"][key] = today()
                    self.run_topic(t)
                    break

    def set_action(self, name, secs):
        self.action = name
        self.action_until = time.time() + secs

    def pet(self):
        if self.st["asleep"]:
            self.wake()
            return
        self.st["mood"] = min(100.0, self.st["mood"] + 5)
        self.st["affection"] += 0.2
        self.set_action("happy", 1.6)
        self.particles.append(dict(kind="heart", x=self.x + random.randint(-6, 6), y=FLOOR_Y - 42, t=time.time()))
        if not self.typing and random.random() < 0.5:
            self.say_tag(random.choice(["react_pet", "tap"]))
        self.draw_status()

    def snack_menu(self, e=None):
        items = [{"type": "head", "label": "どれあげる？"}]
        for s in self.talk.snacks:
            items.append({"type": "cmd", "label": s["name"], "cmd": lambda s=s: self.feed(s)})
        if e is not None:
            self.pmenu.popup(items, e.x_root, e.y_root)
        else:
            self.pmenu.popup(items, self.root.winfo_pointerx(), self.root.winfo_pointery())

    def feed(self, s):
        if self.st["asleep"]:
            self.say("……zzz（ねてる）", hold=1.6)
            return
        if self.st["hunger"] >= 96:
            self.say_tag("full")
            return
        self.snack = dict(s, start=time.time())
        self.set_action("eat", 3.2)

    def finish_snack(self):
        s = self.snack
        self.snack = None
        st = self.st
        st["hunger"] = min(100.0, st["hunger"] + float(s.get("hunger", 15)))
        st["mood"] = min(100.0, st["mood"] + float(s.get("mood", 5)))
        st["affection"] += float(s.get("affection", 1))
        self.set_action("happy", 1.6)
        self.particles.append(dict(kind="heart", x=self.x, y=FLOOR_Y - 44, t=time.time()))
        self.say(self.talk.line(s.get("react_tag", "")) or self.talk.line("react_snack"))
        self.draw_status()

    def toggle_lights(self):
        self.st["lights"] = not self.st["lights"]
        if not self.st["lights"]:
            self.game_off(quiet=True)
            self.say_tag("react_lights_off")
            self.root.after(2500, self.fall_asleep)
        else:
            if self.st["asleep"]:
                self.wake()
            else:
                self.say_tag("react_lights_on")
        if self.cfg["mode"] == "room":
            self.draw_button("light")

    def fall_asleep(self):
        if self.st["lights"] and self.st["sleepy"] < 95:
            return
        self.st["asleep"] = True
        self.walk_target = None
        self.set_action("sleep", 1e9)
        self.bubble.place_forget()
        self.say_queue.clear()
        self.typing = None

    def wake(self):
        self.st["asleep"] = False
        self.set_action("drowsy", 3.0)
        self.say_tag("wake")
        if not self.st["lights"]:
            self.st["lights"] = True
            if self.cfg["mode"] == "room":
                self.draw_button("light")

    def toggle_game(self):
        if self.game:
            self.game_off()
            return
        if self.st["asleep"]:
            self.say("……zzz（ねてる）", hold=1.6)
            return
        self.game = True
        self.game_since = time.time()
        self.walk_target = None
        self.next_game_line = time.time() + random.uniform(25, 50)
        self.say_tag("react_game_start")
        if self.cfg["mode"] == "room":
            self.draw_button("game")

    def game_off(self, quiet=False):
        if not self.game:
            return
        self.game = False
        if not quiet:
            self.say_tag("react_game_end")
        if self.cfg["mode"] == "room":
            self.draw_button("game")

    def start_topic(self):
        if self.st["asleep"]:
            self.say("……zzz（ねてる）", hold=1.6)
            return
        if self.typing and self.typing["choices"]:
            return
        topics = [t for t in self.talk.topics if "auto" not in t.get("tags", []) and self.talk.unlocked(t, self.st)]
        if not topics:
            self.say_tag("idle")
            return
        seen = self.st["flags"].setdefault("seen_topics", [])
        fresh = [t for t in topics if t["id"] not in seen[-max(1, len(topics) - 1):]]
        t = random.choice(fresh or topics)
        seen.append(t["id"])
        del seen[:-20]
        self.st["affection"] += 1
        self.run_topic(t)

    def run_topic(self, t):
        for step in t.get("sequence", []):
            if "say" in step:
                self.say(step["say"])
            elif "ask" in step:
                def then(ans, step=step):
                    if ans is None:
                        return
                    if step.get("set_flag"):
                        self.st["flags"][step["set_flag"]] = "yes" if ans == 0 else "no"
                    self.say_queue.insert(0, (step.get("yes" if ans == 0 else "no", ""), None, None, None))
                self.say(step["ask"], then=then, choices=(step.get("yes_label", "うん"), step.get("no_label", "ううん")))

    # --- 毎フレーム ---
    def think(self, now):
        s = self.st
        if s["asleep"]:
            self.action = "sleep"
            if s["sleepy"] <= 5 and s["lights"]:
                self.wake()
            return
        if self.action in ("happy", "drowsy", "eat") and now < self.action_until:
            return
        if self.action == "eat" and self.snack:
            self.finish_snack()
            return
        if s["sleepy"] >= 100 and not self.game:
            self.fall_asleep()
            return
        if self.game:
            self.action = "game"
            if now >= self.next_game_line and not self.typing:
                self.say_tag("react_game")
                self.next_game_line = now + random.uniform(40, 90)
            return
        if self.think_music(now):
            return
        if self.walk_target is not None:
            self.action = "walk"
            return
        self.action = "drowsy" if s["sleepy"] > 85 else "idle"
        if now >= self.action_until:
            self.action_until = now + random.uniform(4, 9)
            if random.random() < 0.4 and not self.typing:
                lo, hi = (14, (SW if self.cfg["mode"] == "room" else DW) - 14)
                self.walk_target = random.uniform(lo, hi)
        self.chatter(now)

    def think_music(self, now):
        """レコードが流れていると、ときどきノる（ずっとではない）。ノっているあいだは True。
        寝ているときはここまで来ないので、ノらない。"""
        music = load_now_playing() if self.cfg["groove"] else None
        if not music:
            self.next_groove = None
            if self.action == "groove":   # 曲が止まった
                self.stop_groove(now)
                if not self.typing and not self.say_queue and random.random() < 0.6:
                    self.say_tag("music_off")
            return False
        if self.action == "groove":
            if now < self.groove_until:
                self.groove(now, music)
                return True
            self.stop_groove(now)   # ひと休み
            self.next_groove = now + random.uniform(*GROOVE_REST)
            return False
        if now < self.groove_until:   # なでられたあとなど、ノっている途中なら続きから
            self.action = "groove"
            self.music = music
            return True
        if self.next_groove is None:   # 曲がかかってから、少しして
            self.next_groove = now + random.uniform(*GROOVE_FIRST)
        if now >= self.next_groove and self.st["sleepy"] <= 85:
            self.groove_until = now + random.uniform(*GROOVE_LEN)
            self.groove(now, music)
            return True
        return False

    def stop_groove(self, now):
        self.music = None
        self.action = "idle"
        self.action_until = now + random.uniform(4, 9)

    def groove(self, now, music):
        """レコードの曲に合わせてノる。ノりはじめにひとこと、長くノっているとときどき音楽の話。"""
        self.music = music
        self.walk_target = None
        quiet = next((c for c in CHATTER if c[1] == self.cfg["chatter"]), CHATTER[1])[2] is None
        if self.action != "groove":
            self.action = "groove"
            self.next_chatter = now + random.uniform(30, 60)
            if not quiet and not self.typing and not self.say_queue and random.random() < 0.6:
                self.say_tag("music_on")
        elif not quiet and now >= self.next_chatter and not self.typing and not self.say_queue:
            self.next_chatter = now + random.uniform(40, 90)
            self.say_tag("music")

    def chatter(self, now):
        mode = next((c for c in CHATTER if c[1] == self.cfg["chatter"]), CHATTER[1])
        if mode[2] is None or now < self.next_chatter:
            return
        self.next_chatter = now + random.uniform(*mode[2])
        if self.typing or self.say_queue:
            return
        s = self.st
        if s["hunger"] < 25:
            tag = "hungry"
        elif s["sleepy"] > 80:
            tag = "sleepy"
        elif s["mood"] < 30:
            tag = "grumpy"
        else:
            tag = random.choice(["idle", "idle", "idle", "music"])
        self.say_tag(tag)

    def move(self, dt_):
        if self.walk_target is None or self.action != "walk":
            return
        d = self.walk_target - self.x
        if abs(d) < 0.6:
            self.walk_target = None
            self.action = "idle"
            return
        self.dir = 1 if d > 0 else -1
        self.x += self.dir * min(abs(d), 13 * dt_)

    def current_sprite(self, now):
        a = self.action
        s = self.st
        blink = now >= self.blink_at
        if now > self.blink_at + 0.15:
            self.blink_at = now + random.uniform(2.5, 5.5)
        talk_mouth = "mouth_1" if (self.talking() and int(now * 8) % 2) else None
        sad = s["mood"] < 30
        if a == "sleep":
            return self.chara.compose("sleep", "eye_close", "mouth_0"), 0
        if a == "walk":
            frame = ["walk_0", "walk_1", "walk_2", "walk_1"][int(now * 7) % 4]
            return self.chara.compose(frame, "eye_close" if blink else "eye_open",
                                      talk_mouth or "mouth_0", flip=self.dir < 0), 0
        if a == "eat":
            m = "mouth_2" if int(now * 4) % 2 else "mouth_0"
            return self.chara.compose("eat", "eye_happy", m, "prop_eat"), 0
        if a == "happy":
            return self.chara.compose("happy", "eye_happy", talk_mouth or "mouth_2"), 0
        if a == "game":
            m = talk_mouth or ("mouth_1" if int(now / 3) % 4 == 0 else "mouth_0")
            return self.chara.compose("game", "eye_close" if blink else "eye_open", m, "prop_game"), 0
        if a == "groove":
            beat = now * 2.0                 # 1秒に2拍（だいたい120BPM）
            k = int(beat)
            if self.chara.get("body_groove_0"):
                pose = f"groove_{k % 2}"
            else:                            # ノる絵がないときは、ごきげんの絵とふつうの絵で
                pose = "happy" if k % 2 == 0 else "idle"
            eye = "eye_happy" if pose != "idle" else ("eye_close" if blink else "eye_open")
            sway = (k // 2) % 2 == 1         # 2拍ごとに左右を向く
            return self.chara.compose(pose, eye, talk_mouth or "mouth_2", flip=sway), (1 if beat % 1 < 0.5 else 0)
        if a == "drowsy":
            eye = "eye_close" if int(now * 1.2) % 3 == 0 else "eye_half"
            return self.chara.compose("drowsy", eye, talk_mouth or "mouth_pout"), 0
        bob = 1 if int(now * 1.1) % 2 else 0
        eye = "eye_close" if blink else "eye_open"
        mouth = talk_mouth or ("mouth_pout" if sad else "mouth_0")
        return self.chara.compose("idle", eye, mouth, flip=self.dir < 0), bob

    def draw_extras(self, im, now, floor_y):
        d = ImageDraw.Draw(im)
        cx = round(self.x)
        if self.snack:
            icon = self.snack.get("image")
            k = (now - self.snack["start"]) / 3.2
            if icon is not None:
                bites = min(3, int(k * 4))
                ic = icon.copy()
                if bites:
                    ImageDraw.Draw(ic).rectangle([16 - bites * 4, 0, 15, 15], fill=(0, 0, 0, 0))
                hx, hy = self.chara.meta.get("snack_hand", [32, 38])
                im.paste(ic, (cx - 32 + hx - 8, floor_y - 62 + hy - 6), ic)
        if self.action == "sleep":
            for i in range(3):
                ph = (now * 0.6 + i / 3) % 1
                x = cx + 6 + round(ph * 10)
                y = floor_y - 34 - round(ph * 14)
                if 0 <= y:
                    px_pattern(d, x, y, PX_FONT["Z"], (250, 250, 255) if not self.st["lights"] else (120, 100, 170))
        if self.action == "groove":   # 音符がふわふわ出る（色はレコードのラベルの色）
            color = tuple(self.music["color"]) if self.music and self.music.get("color") else (240, 90, 130)
            for i in range(3):
                ph = (now * 0.5 + i / 3) % 1
                x = cx + (20 if i % 2 else -26) + round(math.sin(now * 2 + i) * 2)   # 頭の左右から
                y = floor_y - 30 - round(ph * 26)
                if 0 <= y and ph < 0.85:
                    note = NOTES[i % 2]
                    px_pattern(d, x + 1, y + 1, note, (60, 44, 86))   # 影をつけて見やすく
                    px_pattern(d, x, y, note, color)
        keep = []
        for pt in self.particles:
            age = now - pt["t"]
            if age > 1.4:
                continue
            keep.append(pt)
            heart_sprite(d, round(pt["x"]) - 2, round(pt["y"] - age * 10))
        self.particles = keep

    def frame_image(self, now):
        room = self.cfg["mode"] == "room"
        spr, bob = self.current_sprite(now)
        if room:
            hour = dt.datetime.now().hour
            kind = sky_colors(hour)[2]
            ch = self.chara
            if ch.room_day is not None:   # その子のおへや
                tv = ch.room_tv
                weather = load_weather()
                im = room_scene(ch, hour, weather).copy()   # 朝・昼・夕方・夜、くもりの日はうす暗く
                if (kind == "night" and ch.room_sky and ch.room_night is None and ch.room_sky_time != "night"
                        and weather in (None, "clear", "partly")):
                    room_stars(im, ch, now)
                if weather and ch.room_window:
                    draw_weather(im, ch.room_window, weather, now, kind == "night")
                d = ImageDraw.Draw(im)
            else:                         # いつものおへや
                tv = (75, 41, 89, 51)
                if self.room_cache[0] != hour:
                    self.room_cache = (hour, build_room(hour))
                im = self.room_cache[1].copy()
                weather = load_weather()
                if weather:   # 窓の外の雨や雪
                    draw_weather(im, WINDOW_SKY, weather, now, kind == "night")
                    draw_window_frame(ImageDraw.Draw(im))
                d = ImageDraw.Draw(im)
                wall_clock(d, 52, 14)
                draw_fairy_twinkle(d, now)
            if self.game and tv:   # テレビにゲーム画面
                x0, y0, x1, y1 = tv
                c = [(90, 200, 250), (250, 150, 200), (130, 230, 150)][int(now / 2) % 3]
                d.rectangle([x0, y0, x1, y1], fill=(30, 40, 80))
                d.rectangle([x0, y1 - 3, x1, y1], fill=c)
                bx = x0 + 3 + int(now * 3) % max(1, x1 - x0 - 5)
                d.rectangle([bx, y0 + 4, bx + 1, y0 + 6], fill=(255, 240, 120))
            floor_y = FLOOR_Y
            im = im.convert("RGBA")
            im.alpha_composite(spr, (round(self.x) - 32, floor_y - 62 + bob))
            self.draw_extras(im, now, floor_y)
            im = im.convert("RGB")
            if not self.st["lights"]:
                im = darken(im, 0.55)
                d = ImageDraw.Draw(im)
                if self.game and tv:
                    d.rectangle(list(tv), fill=(120, 160, 220))
            return im, (SW, SH)
        bg = KEY if self.key_ok else (204, 190, 228)
        im = Image.new("RGBA", (DW, DH), bg + (255,))
        floor_y = DH - 1
        im.alpha_composite(spr, (round(self.x) - 32, floor_y - 62 + bob))
        self.draw_extras(im, now, floor_y)
        return im.convert("RGB"), (DW, DH)

    def tick(self):
        now = time.time()
        dt_ = now - getattr(self, "_last_tick", now)
        self._last_tick = now
        self.think(now)
        self.move(dt_)
        self.type_step()
        if self.typing is None and self.say_queue and now >= self.bubble_until:
            self.next_say()
        im, (w, h) = self.frame_image(now)
        self.photo = ImageTk.PhotoImage(im.resize((w * self.p, h * self.p), Image.NEAREST))
        self.screen.config(image=self.photo)
        self.root.after(1000 // FPS, self.tick)

    def slow_tick(self):
        now = time.time()
        self.advance((now - self.st["last_ts"]) / 60)
        self.st["last_ts"] = now
        self.draw_status()
        look = (load_colorway(), is_night_time())   # 色を変えたとき・昼夜が切り替わったときに着替える
        if look != self.look:
            self.look = look
            self.colorway = look[0]
            self.reload_chara()
            self.layout()
        self.notice_weather()
        if self.cfg["mode"] == "desktop":
            self.dock()
        self.root.after(2000, self.slow_tick)

    def notice_weather(self):
        """雨・雪・かみなりが降りはじめたら、起きていればひとこと。"""
        weather = load_weather()
        if weather == self.last_weather:
            return
        self.last_weather = weather
        quiet = next((c for c in CHATTER if c[1] == self.cfg["chatter"]), CHATTER[1])[2] is None
        if weather in ("rain", "snow", "thunder") and not self.st["asleep"] and not quiet                 and not self.typing and not self.say_queue:
            self.say_tag("weather_" + weather)

    def autosave(self):
        self.save()
        self.root.after(30000, self.autosave)

    def save(self):
        self.st["last_ts"] = time.time()
        save_json(SAVE_PATH, self.st)
        save_json(CONFIG_PATH, self.cfg)

    # --- メニュー ---
    def gauge(self, v):
        n = max(0, min(5, round(v / 20)))
        return "●" * n + "○" * (5 - n)

    def menu_items(self):
        c, s = self.cfg, self.st
        mood = "ごきげん" if s["mood"] >= 70 else ("ふつう" if s["mood"] >= 35 else "ふきげん")
        return [
            {"type": "head", "label": f"{self.chara.name}の子　{'ねてる' if s['asleep'] else mood}"},
            {"type": "head", "label": f"おなか {self.gauge(s['hunger'])}　げんき {self.gauge(100 - s['sleepy'])}"},
            {"type": "sep"},
            {"type": "sub", "label": "おやつをあげる", "items": lambda: [
                {"type": "cmd", "label": sn["name"], "cmd": lambda sn=sn: self.feed(sn)} for sn in self.talk.snacks]},
            {"type": "cmd", "label": "おはなしする", "cmd": self.start_topic},
            {"type": "cmd", "label": "なでる", "cmd": self.pet},
            {"type": "check", "label": "電気を消す", "checked": not s["lights"], "cmd": self.toggle_lights},
            {"type": "check", "label": "いっしょにゲーム", "checked": self.game, "cmd": self.toggle_game},
            {"type": "sep"},
            {"type": "sub", "label": "だれといる？", "right": "カラーに合わせる" if c["chara"] == "auto" else self.chara.name,
             "items": [{"type": "radio", "label": "カラーに合わせる", "checked": c["chara"] == "auto",
                        "cmd": lambda: self.set_chara("auto")}, {"type": "sep"}] +
                      [{"type": "radio", "label": n, "checked": c["chara"] == k,
                        "cmd": lambda k=k: self.set_chara(k)} for n, k in chara_list()] +
                      [{"type": "sep"}, {"type": "cmd", "label": "キャラを取り込む…", "cmd": self.open_importer},
                       {"type": "head", "label": "カラーに合わせると、色を変えたら交代するよ"}]},
            {"type": "sub", "label": "いる場所", "right": "おへや" if c["mode"] == "room" else "デスクトップ", "items": [
                {"type": "radio", "label": "おへや（窓の中）", "checked": c["mode"] == "room",
                 "cmd": lambda: self.set_mode("room")},
                {"type": "radio", "label": "デスクトップ（ランチャーの上）", "checked": c["mode"] == "desktop",
                 "cmd": lambda: self.set_mode("desktop")},
                {"type": "sep"},
                {"type": "head", "label": "ランチャーがないときは、ドラッグで好きな所へ"},
            ]},
            {"type": "sub", "label": "おしゃべり", "right": next(n for n, k, _ in CHATTER if k == c["chatter"]),
             "items": [{"type": "radio", "label": n, "checked": c["chatter"] == k,
                        "cmd": lambda k=k: self.set_chatter(k)} for n, k, _ in CHATTER]},
            {"type": "check", "label": "レコードの曲にノる", "checked": c["groove"], "cmd": self.toggle_groove},
            {"type": "sub", "label": "設定", "items": [
                {"type": "sub", "label": "カラー", "items": lambda: colorway_menu(self.colorway, self.set_colorway),
                 "right": next(n for n, k in COLORWAY_NAMES if k == self.colorway)},
                {"type": "sub", "label": "サイズ", "right": next(n for n, v in SCALES if v == c["scale"]),
                 "items": [{"type": "radio", "label": n, "checked": c["scale"] == v,
                            "cmd": lambda v=v: self.set_scale(v)} for n, v in SCALES]},
                {"type": "check", "label": "最前面に表示", "checked": c["topmost"], "cmd": self.toggle_topmost},
            ]},
            {"type": "sep"},
            {"type": "cmd", "label": "またね（終了）", "cmd": self.quit},
            {"type": "head", "label": f"エレクトロガール ver.{APP_VERSION}"},
        ]

    def popup_menu(self, e):
        self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

    def set_mode(self, mode):
        if self.cfg["mode"] == mode:
            return
        if mode == "desktop":
            self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
            self.x = DW / 2
        else:
            self.x = SW / 2
        self.cfg["mode"] = mode
        self.walk_target = None
        self.save()
        self.layout()

    def toggle_groove(self):
        self.cfg["groove"] = not self.cfg["groove"]
        self.save()

    def set_chatter(self, k):
        self.cfg["chatter"] = k
        self.next_chatter = time.time() + 10
        self.save()

    def set_scale(self, v):
        self.cfg["scale"] = v
        self.p = Scale(v)
        self.save()
        self.layout()

    def toggle_topmost(self):
        self.cfg["topmost"] = not self.cfg["topmost"]
        self.save()
        self.root.attributes("-topmost", self.cfg["topmost"])

    # --- マウス ---
    def on_girl(self, e):
        """クリックした所に女の子がいるか"""
        p = self.p
        lx = (e.x_root - self.screen.winfo_rootx()) / p
        ly = (e.y_root - self.screen.winfo_rooty()) / p
        floor_y = FLOOR_Y if self.cfg["mode"] == "room" else DH - 1
        tx, ty = int(lx - (round(self.x) - 32)), int(ly - (floor_y - 62))
        if not (0 <= tx < T and 0 <= ty < T):
            return False
        spr, _ = self.current_sprite(time.time())
        return spr.getpixel((tx, ty))[3] > 0

    def press(self, e):
        self._press = (e.x_root, e.y_root)
        self._moved = False
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def drag_move(self, e):
        if self.cfg["mode"] == "desktop" and getattr(self, "docked", False):
            return
        if abs(e.x_root - self._press[0]) + abs(e.y_root - self._press[1]) > 4:
            self._moved = True
        if self._moved:
            self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def release(self, e):
        if getattr(self, "_moved", False):
            self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
            self.save()
            return
        if self.cfg["mode"] == "room":
            spot = self.hotspot_at(e)
            if spot == "close":
                self.quit()
                return
            if spot == "min":
                self.minimize()
                return
        if self.on_girl(e):
            self.pet()

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
        if self.st["asleep"]:
            self.root.destroy()
            return
        self.say_queue.clear()
        self.typing = None
        self.say(self.talk.line("bye") or "またね。", hold=1.2)
        self.root.after(1700, self.root.destroy)

    def run(self):
        self.root.mainloop()
        self.save()


def self_game(app):
    return bool(getattr(app, "game", False))


if __name__ == "__main__":
    try:
        ElectroGirl().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "electro_girl_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
