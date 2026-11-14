# -*- coding: utf-8 -*-
"""
資料シアター ver.1.3
Eagle ライブラリから選んだタグの動画・音声をランダムに流す常駐プレイヤー。

操作:
  PREV          … さっきの動画に戻る
  STOP / PLAY   … 停止と再生
  NEXT          … 次へ
  VIDEO / AUDIO … 動画モードと音声のみモードの切り替え
  スピーカー    … ミュート
  ドラッグ      … ウィンドウを移動
  ダブルクリック … 再生中のファイルを Eagle で開く
  右クリック    … メニュー（表示するタグ / 流し方 / 音量 / サイズ / 最前面 など）

必要なもの:
  VLC 本体（https://www.videolan.org/）
  pip install python-vlc pillow
"""
import json
import os
import queue
import random
import sys
import threading
import webbrowser
from collections import Counter, deque
import tkinter as tk
from tkinter import filedialog

from mushiboshi_ui import (COLORWAY_NAMES, dither_bar, mix, log_errors, is_night_time, THEMES, PixelMenu, ask_text, colorway_menu,
                           colorway_theme, load_colorway, make_colormap, pick_items, recolor, recolor_dict,
                           save_colorway, ui_font, Scale, PX_FONT, hexc, px_pattern, px_text, px_text_w, save_json)

from PIL import Image, ImageDraw, ImageTk

def _add_vlc_dll_dirs():
    """Windows では Python 3.8 以降、VLC の DLL の場所を明示しないと読み込めないことがある。"""
    if not sys.platform.startswith("win") or not hasattr(os, "add_dll_directory"):
        return
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        d = os.path.join(base, "VideoLAN", "VLC")
        if os.path.isfile(os.path.join(d, "libvlc.dll")):
            try:
                os.add_dll_directory(d)
                os.environ.setdefault("PYTHON_VLC_MODULE_PATH", os.path.join(d, "plugins"))
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            except OSError:
                pass


_add_vlc_dll_dirs()
try:
    import vlc
    VLC_ERROR = None
except Exception as ex:  # VLC 本体が入っていない、32bit/64bit が合わない など
    vlc = None
    VLC_ERROR = str(ex)

APP_VERSION = "1.4"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "theater_config.json")
INDEX_PATH = os.path.join(APP_DIR, "theater_index.json")
FRAME_CONFIG_PATH = os.path.join(APP_DIR, "frame_config.json")  # フォトフレームの設定（ライブラリの場所を借りる）
INDEX_VERSION = 1

VIDEO_EXTS = {"mp4", "webm", "mov", "mkv", "avi", "m4v", "flv", "wmv", "mpg", "mpeg", "ts"}
AUDIO_EXTS = {"mp3", "wav", "m4a", "ogg", "flac", "aac", "opus", "wma"}

DEFAULT_CONFIG = {
    "library": "",
    "tags": ["参考資料"],
    "tag_choices": ["参考資料", "自力絵"],
    "kinds": "both",        # "both" / "video" / "audio" … 流すファイルの種類
    "audio_only": False,    # True なら映像を出さずに音だけ
    "clip_sec": 30,         # つまみ食いの長さ（秒）。0 なら最後まで
    "volume": 70,
    "muted": False,
    "width": 480,           # 映像部分の幅（px）
    "show_queue": True,     # 次に流れるリストを表示
    "skin": "pixeltube",    # 見た目 "pixeltube" / "netradio" / "darkweb"
    "topmost": True,
    "x": 140,
    "y": 140,
}
CLIPS = [("つまみ食い 15秒", 15), ("つまみ食い 30秒", 30), ("つまみ食い 1分", 60),
         ("つまみ食い 3分", 180), ("最後まで再生", 0)]
KINDS = [("動画と音声", "both"), ("動画だけ", "video"), ("音声ファイルだけ", "audio")]
VOLUMES = [("25%", 25), ("50%", 50), ("70%", 70), ("100%", 100)]
SIZES = [("ミニ", 240), ("小", 320), ("中", 480), ("大", 640)]
SKIN_TITLES = {"pixeltube": "PIXELTUBE", "netradio": "NETRADIO 24/7", "darkweb": "ROOT@ARCHIVE"}
SKIN_NAMES = [("PIXELTUBE（ミント）", "pixeltube"), ("ネットラジオ風", "netradio"), ("ダークウェブ風", "darkweb")]


# ---------- ドット絵 ----------

_ICONS = {
    "tv": ".#...#.|..#.#..|#######|#.....#|#.....#|#######",
    "note": "..##|..#.|..#.|###.|###.",
    "play": "#...|##..|###.|##..|#...",
    "pause": "#.#|#.#|#.#|#.#|#.#",
    "next": "#..#..|##.##.|######|##.##.|#..#..",
    "prev": "..#..#|.##.##|######|.##.##|..#..#",
    "sound": "..#..#.|.##...#|###.#.#|.##...#|..#..#.",
    "mute": "..#....|.##.#.#|###..#.|.##.#.#|..#....",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
}

SKINS = {
    "pixeltube": dict(
        face=(236, 246, 242), out=(40, 56, 72), light=(255, 255, 255),
        title=(140, 218, 196), title2=(186, 238, 222), accent=(232, 72, 128), hover=(255, 214, 228),
        second=(96, 196, 168), screen=(16, 20, 28), screen_text=(207, 216, 224),
        name_bg=(255, 255, 255), name_fg=(40, 56, 72), name_font="Yu Gothic UI",
        bar_track=(255, 255, 255), bar_fill=(232, 72, 128), bar_text=(40, 56, 72),
        eq=((96, 196, 168), (242, 201, 76), (232, 72, 128)),
        btn_face=(236, 246, 242), btn_out=(40, 56, 72), btn_hl=(255, 255, 255),
        btn_icon=(232, 72, 128), btn_text=(40, 56, 72),
        btn_hover=(255, 214, 228), btn_hover_icon=(40, 56, 72), btn_hover_text=(40, 56, 72),
        label_audio="AUDIO ONLY", label_play="NOW PLAYING"),
    "netradio": dict(
        face=(44, 48, 64), out=(10, 12, 18), light=(92, 100, 128),
        title=(58, 64, 84), title2=(70, 76, 98), accent=(255, 176, 64), hover=(120, 84, 30),
        second=(255, 176, 64), screen=(14, 20, 16), screen_text=(255, 176, 64),
        name_bg=(22, 34, 26), name_fg=(255, 186, 84), name_font="MS Gothic",
        bar_track=(22, 34, 26), bar_fill=(255, 176, 64), bar_text=(255, 176, 64),
        eq=((90, 220, 100), (255, 176, 64), (240, 72, 52)),
        btn_face=(58, 64, 84), btn_out=(10, 12, 18), btn_hl=(96, 104, 132),
        btn_icon=(255, 176, 64), btn_text=(232, 232, 240),
        btn_hover=(120, 84, 30), btn_hover_icon=(255, 236, 200), btn_hover_text=(255, 236, 200),
        label_audio="RADIO MODE", label_play="TUNED IN"),
    "darkweb": dict(
        face=(6, 10, 7), out=(0, 150, 72), light=(12, 18, 13),
        title=(6, 10, 7), title2=(10, 18, 12), accent=(0, 255, 120), hover=(0, 255, 120),
        second=(0, 200, 96), screen=(2, 6, 3), screen_text=(0, 255, 120),
        name_bg=(2, 6, 3), name_fg=(0, 255, 120), name_font="MS Gothic",
        bar_track=(2, 6, 3), bar_fill=(0, 220, 104), bar_text=(0, 255, 120),
        eq=((0, 90, 45), (0, 170, 85), (130, 255, 175)),
        btn_face=(4, 8, 5), btn_out=(0, 150, 72), btn_hl=None,
        btn_icon=(0, 255, 120), btn_text=(0, 255, 120),
        btn_hover=(0, 255, 120), btn_hover_icon=(0, 0, 0), btn_hover_text=(0, 0, 0),
        label_audio="> AUDIO_STREAM", label_play="> PLAYBACK"),
}
# タグ選びの画面などで使う色
FACE, OUT, PINK = SKINS["pixeltube"]["face"], SKINS["pixeltube"]["out"], SKINS["pixeltube"]["accent"]

# レイアウト（ドット単位）。映像は 160×90 ドット
VID_X, VID_Y, VID_W, VID_H = 3, 14, 160, 90
WIN_W, WIN_H = 166, 139
NAME_Y, BAR_Y, BTN_Y = 106, 117, 125
BUTTONS = {"prev": (3, 13), "play": (17, 27), "next": (45, 29), "mode": (75, 34), "mute": (110, 13)}
VOL_X, VOL_W = 125, 37          # 音量バー
QX, QW, Q_ROW = 166, 68, 18     # 次に流れるリスト（5行）
QUEUE_LEN = 4


def resize_grip(d, x1, y1, dark, light):
    """右下の、ななめのつまみ。"""
    for k in (0, 3, 6):
        for i in range(k + 1):
            d.point((x1 - k + i, y1 - i), fill=dark)
            if i < k:
                d.point((x1 - k + i + 1, y1 - i), fill=light)


def window_width(show_queue):
    return WIN_W + (QW + 3 if show_queue else 0)


COLOR_BASE = {
    "pixeltube": {(236, 246, 242): "face", (40, 56, 72): "out", (140, 218, 196): "title",
                  (186, 238, 222): "title2", (232, 72, 128): "accent", (255, 214, 228): "hover",
                  (96, 196, 168): "second"},
}


def render_window(p, key, show_queue=False, cmap=None):
    return recolor(_render_window(p, key, show_queue), cmap)


def _render_window(p, key, show_queue=False):
    k = SKINS[key]
    W, H = window_width(show_queue), WIN_H
    im = Image.new("RGB", (W, H), k["face"])
    d = ImageDraw.Draw(im)
    if key == "darkweb":                       # 走査線
        for y in range(0, H, 2):
            d.line([(0, y), (W, y)], fill=k["light"])
    d.rectangle([0, 0, W - 1, H - 1], outline=k["out"])
    if key != "darkweb":
        d.line([(1, 1), (W - 2, 1)], fill=k["light"])
        d.line([(1, 1), (1, H - 2)], fill=k["light"])

    # タイトルバー
    if key == "pixeltube":
        dither_bar(d, 2, 2, W - 3, 11, k["title2"], k["title"])   # 左の明るい色から、右へ網点でなめらかに
        px_pattern(d, 5, 5, _ICONS["tv"], k["light"])
        px_pattern(d, 4, 4, _ICONS["tv"], k["out"])
        px_text(d, 15, 6, "PIXELTUBE.EXE", k["light"])
        px_text(d, 14, 5, "PIXELTUBE.EXE", k["out"])
        bx0 = W - 3 - 3 * 9
        hx = bx0 - 13   # 「HD」のバッジ
        d.rectangle([hx, 3, hx + 10, 10], fill=k["accent"], outline=k["out"])
        px_text(d, hx + 2, 4, "HD", k["light"])
        for i, icon in enumerate(("min", "max", "close")):
            x0 = bx0 + i * 9
            d.rectangle([x0, 3, x0 + 7, 10], fill=k["hover"] if icon == "close" else k["face"], outline=k["out"])
            px_pattern(d, x0 + 1, 4, _ICONS[icon], k["out"])
    elif key == "netradio":
        for y in range(2, 12):                 # ヘアライン仕上げの金属っぽく
            d.line([(2, y), (W - 3, y)], fill=k["title"] if y % 2 else k["title2"])
        px_pattern(d, 4, 4, _ICONS["note"], k["accent"])
        px_text(d, 12, 6, "NETRADIO 24/7", k["out"])   # 刻印のかげ
        px_text(d, 11, 5, "NETRADIO 24/7", k["accent"])
        lamp = "ON AIR"
        lx = W - 6 - px_text_w(lamp) - 3
        d.rectangle([lx, 3, W - 5, 10], fill=(214, 36, 36), outline=k["out"])
        d.line([(lx + 1, 4), (W - 6, 4)], fill=(240, 96, 86))   # ランプのつや
        px_text(d, lx + 2, 4, lamp, (255, 236, 230))
        for x in range(64, lx - 6, 3):   # 周波数の目盛り
            d.line([(x, 8 if x % 15 else 6), (x, 10)], fill=k["light"])
    else:
        px_text(d, 4, 4, "ROOT@ARCHIVE:~#", k["accent"])
        d.rectangle([4 + px_text_w("ROOT@ARCHIVE:~#") + 2, 4, 4 + px_text_w("ROOT@ARCHIVE:~#") + 4, 8],
                    fill=k["accent"])        # カーソル
        tag = "[SECURE]"
        px_text(d, W - 5 - px_text_w(tag), 4, tag, k["second"])
        ping = "PING 24MS"
        px_text(d, (W - px_text_w(ping)) // 2 + 14, 4, ping, mix(k["second"], k["face"], 0.55))
    d.line([(1, 12), (W - 2, 12)], fill=k["out"])

    # 画面と曲名欄
    d.rectangle([VID_X - 1, VID_Y - 1, VID_X + VID_W, VID_Y + VID_H], outline=k["out"])
    d.rectangle([VID_X, NAME_Y - 1, VID_X + VID_W - 1, NAME_Y + 9], fill=k["name_bg"], outline=k["out"])
    if key == "darkweb":   # 画面の四すみに、照準のようなかぎ
        x0, y0, x1, y1 = VID_X - 1, VID_Y - 1, VID_X + VID_W, VID_Y + VID_H
        for cx, cy, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            d.line([(cx, cy), (cx + 4 * sx, cy)], fill=k["accent"])
            d.line([(cx, cy), (cx, cy + 4 * sy)], fill=k["accent"])
    elif key == "netradio":   # 四すみのねじ
        for cx, cy in ((3, H - 4), (W - 5, H - 4)):
            d.rectangle([cx, cy, cx + 1, cy + 1], fill=k["light"])
            d.point((cx + 1, cy + 1), fill=k["out"])
    elif show_queue:   # 右下のつまみ（リストを出していないときは、音量バーの下にかくれるので描かない）
        resize_grip(d, W - 3, H - 3, k["second"], k["light"])

    if not show_queue:
        return im.resize((W * p, H * p), Image.NEAREST)

    # 次に流れるリストの枠
    d.rectangle([QX - 1, VID_Y - 1, QX + QW, VID_Y + VID_H], fill=k["name_bg"], outline=k["out"])
    for i in range(1, 5):
        y = VID_Y + i * Q_ROW - 1
        d.line([(QX, y), (QX + QW - 1, y)], fill=k["out"] if key == "darkweb" else k["light"])
    px_text(d, QX + 1, NAME_Y + 1, "PLAYLIST", k["second"] if key != "pixeltube" else k["out"])
    # リストの下の飾り
    x0 = QX + 1
    if key == "pixeltube":
        px_text(d, x0, BTN_Y + 3, "CH", k["out"])
        for i in range(5):
            d.rectangle([x0 + 11 + i * 7, BTN_Y + 2, x0 + 15 + i * 7, BTN_Y + 8],
                        fill=k["second"] if i < 3 else k["face"], outline=k["out"])
    elif key == "netradio":
        px_text(d, x0, BTN_Y + 3, "FM", k["accent"])
        for i in range(5):
            top = BTN_Y + 8 - (i + 1) * 1 - i
            d.rectangle([x0 + 11 + i * 7, top, x0 + 15 + i * 7, BTN_Y + 9],
                        fill=k["accent"] if i < 4 else k["title2"], outline=k["out"])
    else:
        px_text(d, x0, BTN_Y + 3, "NODE 07", k["second"])
        d.rectangle([x0 + 30, BTN_Y + 3, x0 + 32, BTN_Y + 7], fill=k["accent"])
    return im.resize((W * p, H * p), Image.NEAREST)


def find_thumbnail(path):
    """Eagle が動画ごとに作っているサムネイル（〇〇_thumbnail.png）を探す。"""
    folder = os.path.dirname(path)
    try:
        for fn in os.listdir(folder):
            if fn.lower().endswith("_thumbnail.png"):
                return os.path.join(folder, fn)
    except OSError:
        pass
    return None


def load_thumb(path, w, h):
    tp = find_thumbnail(path)
    if not tp:
        return None
    with Image.open(tp) as im:
        im = im.convert("RGB")
        from PIL import ImageOps
        return ImageOps.fit(im, (w, h), Image.LANCZOS)


def render_button(p, key, icon, text, width, hover=False, cmap=None):
    return recolor(_render_button(p, key, icon, text, width, hover), cmap)


def _render_button(p, key, icon, text, width, hover=False):
    k = SKINS[key]
    iw = len(_ICONS[icon].split("|")[0])
    w, h = width, 11
    fill = k["btn_hover"] if hover else k["btn_face"]
    icon_c = k["btn_hover_icon"] if hover else k["btn_icon"]
    text_c = k["btn_hover_text"] if hover else k["btn_text"]
    im = Image.new("RGB", (w, h), fill)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], fill=fill, outline=k["btn_out"])
    if k["btn_hl"] and not hover:
        d.line([(1, 1), (w - 2, 1)], fill=k["btn_hl"])
        d.line([(1, h - 2), (w - 2, h - 2)], fill=tuple(round(v * 0.85) for v in fill))
    iy = (h - len(_ICONS[icon].split("|"))) // 2
    if text:
        px_pattern(d, 3, iy, _ICONS[icon], icon_c)
        px_text(d, 3 + iw + 2, 3, text, text_c)
    else:
        px_pattern(d, (w - iw) // 2, iy, _ICONS[icon], icon_c)
    return im.resize((w * p, h * p), Image.NEAREST)


def fmt_time(ms):
    s = max(0, int(ms // 1000))
    if s >= 3600:
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


# ---------- 設定とインデックス ----------

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        # 初回は、フォトフレームの設定からライブラリとタグを借りる
        try:
            with open(FRAME_CONFIG_PATH, encoding="utf-8") as f:
                fc = json.load(f)
            for key in ("library", "tag_choices"):
                if fc.get(key):
                    cfg[key] = fc[key]
        except (OSError, ValueError):
            pass
    for t in cfg["tags"]:
        if t not in cfg["tag_choices"]:
            cfg["tag_choices"].append(t)
    return cfg


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


def load_index(library):
    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") == INDEX_VERSION and data.get("library") == library:
            return data.get("items", [])
    except (OSError, ValueError):
        pass
    return None


def save_index(library, items):
    save_json(INDEX_PATH, {"version": INDEX_VERSION, "library": library, "items": items}, pretty=False)


def is_library(path):
    return bool(path) and os.path.isdir(os.path.join(path, "images"))


def find_media_file(info_dir, name, ext):
    path = os.path.join(info_dir, f"{name}.{ext}")
    if os.path.exists(path):
        return path
    try:
        for fn in os.listdir(info_dir):
            if fn.lower().rsplit(".", 1)[-1] == ext:
                return os.path.join(info_dir, fn)
    except OSError:
        pass
    return None


def scan_library(library, progress=None):
    """タグ付きの動画・音声を [id, path, name, tags, kind] のリストで返す。"""
    items = []
    count = 0
    with os.scandir(os.path.join(library, "images")) as it:
        for entry in it:
            if not entry.name.endswith(".info") or not entry.is_dir():
                continue
            count += 1
            if progress and count % 500 == 0:
                progress(count, len(items))
            try:
                with open(os.path.join(entry.path, "metadata.json"), encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                continue
            if meta.get("isDeleted"):
                continue
            ext = str(meta.get("ext", "")).lower()
            if ext in VIDEO_EXTS:
                kind = "video"
            elif ext in AUDIO_EXTS:
                kind = "audio"
            else:
                continue
            tags = [t for t in (meta.get("tags") or []) if isinstance(t, str)]
            if not tags:
                continue
            path = find_media_file(entry.path, meta.get("name", ""), ext)
            if path:
                items.append([meta.get("id", ""), path, meta.get("name", ""), tags, kind])
    return items


# ---------- 本体 ----------

class Theater:
    def __init__(self):
        self.cfg = load_config()
        self.p = Scale(self.cfg["width"] / VID_W)
        self.items, self.pool = [], []
        self.recent = deque(maxlen=40)
        self.queue = []                  # 次に流れる予定
        self.played = deque(maxlen=50)   # 流し終わった（PREV で戻れる）
        self.thumbs = {}                 # id → サムネイル（PIL 画像）
        self.current = None
        self.clip_start = 0
        self.clip_end = None
        self.need_seek = False
        self.resume_ms = None
        self.wait_ticks = 0
        self.scanning = False
        self.q = queue.Queue()
        self.pimgs = {}
        self.eq = [0.0] * 20

        self.root = tk.Tk()
        log_errors(self.root, "theater_error.txt")
        self.root.title(f"資料シアター ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:   # タグ選びなどの小窓に付くアイコン
            self.root.iconbitmap(default=os.path.join(APP_DIR, "video_theater.ico"))
        except tk.TclError:
            pass
        self.root.configure(bg="#000000")
        self.root.attributes("-topmost", self.cfg["topmost"])

        self.var_paused = tk.BooleanVar(value=False)
        self.var_topmost = tk.BooleanVar(value=self.cfg["topmost"])
        self.var_clip = tk.IntVar(value=self.cfg["clip_sec"])
        self.var_kinds = tk.StringVar(value=self.cfg["kinds"])
        self.var_volume = tk.IntVar(value=self.cfg["volume"])
        self.var_width = tk.IntVar(value=self.cfg["width"])
        if self.cfg["skin"] not in SKINS:
            self.cfg["skin"] = "pixeltube"
        self.var_skin = tk.StringVar(value=self.cfg["skin"])

        self.frame_label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.video = tk.Frame(self.root, bd=0, highlightthickness=0)
        self.eq_canvas = tk.Canvas(self.root, bd=0, highlightthickness=0)
        self.name = tk.Label(self.root, anchor="w", bd=0)
        self.bar = tk.Canvas(self.root, bd=0, highlightthickness=0, cursor="hand2")
        self.vol = tk.Canvas(self.root, bd=0, highlightthickness=0, cursor="hand2")
        for w in (self.root, self.frame_label, self.video, self.eq_canvas, self.name):
            self.bind_events(w)
        # 再生位置バーと音量バーは、ドラッグでウィンドウではなくつまみを動かす
        for w, fn in ((self.bar, self.seek_at), (self.vol, self.volume_at)):
            w.bind("<Button-1>", fn)
            w.bind("<B1-Motion>", fn)
            w.bind("<Button-3>", self.popup_menu)
        # 次に流れるリスト
        self.qrows = []
        for i in range(QUEUE_LEN + 1):
            thumb = tk.Label(self.root, bd=0, highlightthickness=0, cursor="hand2")
            name = tk.Label(self.root, bd=0, highlightthickness=0, anchor="nw", justify="left", cursor="hand2")
            for w in (thumb, name):
                w.bind("<Button-1>", lambda e, i=i: self.jump_to(i))
                w.bind("<Button-3>", self.popup_menu)
            self.qrows.append({"thumb": thumb, "name": name})
        self.frame_label.bind("<Motion>", self.frame_hover, add="+")
        self.frame_label.bind("<ButtonRelease-1>", self.frame_click, add="+")
        self.buttons = {}
        for key, action in (("prev", self.prev_item), ("play", self.toggle_play), ("next", self.next_item),
                            ("mode", self.toggle_mode), ("mute", self.toggle_mute)):
            lb = tk.Label(self.root, bd=0, highlightthickness=0, cursor="hand2")
            lb.bind("<Button-1>", lambda e, a=action: a())
            lb.bind("<Enter>", lambda e, k=key: self.draw_button(k, True))
            lb.bind("<Leave>", lambda e, k=key: self.draw_button(k, False))
            lb.bind("<Button-3>", self.popup_menu)
            self.buttons[key] = lb

        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.root.after(2000, self.watch_colorway)
        self.pmenu = PixelMenu(self.root, self.menu_theme,
                               title=f"{SKIN_TITLES[self.cfg['skin']]} - MENU")
        self.layout()

        self.player = None
        self.vlc_problem = VLC_ERROR
        if vlc:
            try:
                self.vlc = vlc.Instance("--quiet", "--no-video-title-show")
            except Exception as ex:
                self.vlc, self.vlc_problem = None, str(ex)
            if self.vlc is None and not self.vlc_problem:
                self.vlc_problem = "VLC の起動に失敗しました"
        if vlc and self.vlc:
            self.player = self.vlc.media_player_new()
            self.player.video_set_mouse_input(False)
            self.player.video_set_key_input(False)
            self.root.update_idletasks()
            self.attach_video()
            self.player.audio_set_volume(self.cfg["volume"])

        self.root.after(250, self.poll)
        self.root.after(120, self.animate_eq)
        self.root.after(200, self.start)

    # --- 見た目 ---
    @property
    def sk(self):
        k = SKINS[self.cfg["skin"]]
        cm = self.cmap()
        if not cm:
            return k
        k = recolor_dict(k, cm)
        k["eq"] = tuple(cm.get(c, c) for c in k["eq"])
        return k

    # --- カラー ---
    def cmap(self):
        return make_colormap(COLOR_BASE.get(self.cfg["skin"]), self.colorway)

    def menu_theme(self):
        if (self.colorway != "original" or is_night_time()) and self.cfg["skin"] in COLOR_BASE:
            return colorway_theme(self.colorway, COLOR_BASE[self.cfg["skin"]])
        return THEMES[self.cfg["skin"]]

    def set_colorway(self, name):
        save_colorway(name)
        self.apply_colorway(name)

    def apply_colorway(self, name):
        self.colorway = name
        self.layout()

    def watch_colorway(self):
        look = (load_colorway(), is_night_time())   # 色を変えたとき・昼夜が切り替わったときに着替える
        if look != self.look:
            self.look = look
            self.apply_colorway(look[0])
        self.root.after(2000, self.watch_colorway)

    def layout(self):
        p = self.p
        k = self.sk
        self.root.configure(bg=hexc(k["face"]))
        self.video.config(bg=hexc(k["screen"]))
        self.eq_canvas.config(bg=hexc(k["screen"]))
        self.bar.config(bg=hexc(k["face"]))
        self.name.config(bg=hexc(k["name_bg"]), fg=hexc(k["name_fg"]))
        self.vol.config(bg=hexc(k["face"]))
        W = window_width(self.cfg["show_queue"])
        self.root.geometry(f"{W * p}x{WIN_H * p}+{self.cfg['x']}+{self.cfg['y']}")
        self.frame_photo = ImageTk.PhotoImage(render_window(p, self.cfg["skin"], self.cfg["show_queue"],
                                                                self.cmap()))
        self.frame_label.config(image=self.frame_photo)
        self.frame_label.place(x=0, y=0, width=W * p, height=WIN_H * p)
        self.vol.place(x=VOL_X * p, y=BTN_Y * p, width=VOL_W * p, height=11 * p)
        self.draw_volume()
        for i, row in enumerate(self.qrows):
            if self.cfg["show_queue"]:
                y = VID_Y + i * Q_ROW
                row["thumb"].place(x=(QX + 1) * p, y=(y + 1) * p, width=24 * p, height=15 * p)
                row["name"].place(x=(QX + 27) * p, y=(y + 1) * p, width=(QW - 28) * p, height=15 * p)
                row["name"].config(font=ui_font(self.root, max(10, int(p * 3.4))), wraplength=(QW - 29) * p)
            else:
                row["thumb"].place_forget()
                row["name"].place_forget()
        self.update_queue_panel()
        self.video.place(x=VID_X * p, y=VID_Y * p, width=VID_W * p, height=VID_H * p)
        self.eq_canvas.place(x=VID_X * p, y=VID_Y * p, width=VID_W * p, height=VID_H * p)
        self.name.config(font=(k["name_font"], max(8, p * 3)))
        self.name.place(x=(VID_X + 2) * p, y=NAME_Y * p, width=(VID_W - 4) * p, height=8 * p)
        self.bar.place(x=VID_X * p, y=BAR_Y * p, width=VID_W * p, height=6 * p)
        for key, (x, w) in BUTTONS.items():
            self.draw_button(key)
            self.buttons[key].place(x=x * p, y=BTN_Y * p)
        self.update_screen()
        self.draw_bar(0, 0)

    def attach_video(self):
        wid = self.video.winfo_id()
        if sys.platform.startswith("win"):
            self.player.set_hwnd(wid)
        elif sys.platform == "darwin":
            self.player.set_nsobject(wid)
        else:
            self.player.set_xwindow(wid)

    def draw_button(self, key, hover=False):
        x, w = BUTTONS[key]
        if key == "play":
            icon, text = ("play", "PLAY") if self.var_paused.get() else ("pause", "STOP")
        elif key == "next":
            icon, text = "next", "NEXT"
        elif key == "prev":
            icon, text = "prev", ""
        elif key == "mode":
            icon, text = ("note", "AUDIO") if self.cfg["audio_only"] else ("tv", "VIDEO")
        else:
            icon, text = ("mute" if self.cfg["muted"] else "sound"), ""
        img = ImageTk.PhotoImage(render_button(self.p, self.cfg["skin"], icon, text, w, hover,
                                                   self.cmap()))
        self.pimgs[key] = img
        self.buttons[key].config(image=img)

    def showing_eq(self):
        return self.cfg["audio_only"] or not self.current or self.current[4] == "audio"

    def update_screen(self):
        if self.showing_eq():
            tk.Misc.lift(self.eq_canvas)   # Canvas の lift は図形用なので、ウィジェット用を呼ぶ
            for b in self.buttons.values():
                b.lift()
        else:
            tk.Misc.lower(self.eq_canvas, self.video)

    def message(self, text):
        self.current = None
        self.update_screen()
        self.eq_canvas.delete("all")
        p = self.p
        self.eq_canvas.create_text(VID_W * p // 2, VID_H * p // 2, text=text, fill=hexc(self.sk["screen_text"]),
                                   font=("Yu Gothic UI", max(9, p * 3)), justify="center",
                                   width=(VID_W - 10) * p, tags="msg")
        self.name.config(text="")
        self.update_queue_panel()

    def canvas_text(self, cv, x, y, text, color, tag):
        p = self.p
        for i, ch in enumerate(text.upper()):
            for ry, row in enumerate(PX_FONT.get(ch, PX_FONT["?"]).split("|")):
                for rx, c in enumerate(row):
                    if c == "#":
                        X, Y = (x + i * 4 + rx) * p, (y + ry) * p
                        cv.create_rectangle(X, Y, X + p, Y + p, fill=color, width=0, tags=tag)

    def animate_eq(self):
        if self.current and self.showing_eq():
            p = self.p
            cv = self.eq_canvas
            cv.delete("all")
            playing = not self.var_paused.get()
            n = len(self.eq)
            bw = 6
            x0 = (VID_W - n * bw) // 2
            if self.cfg["skin"] == "darkweb":
                for yy in range(0, VID_H, 2):
                    cv.create_line(0, yy * p, VID_W * p, yy * p, fill="#06120a")
            for i in range(n):
                target = random.uniform(0.15, 1.0) if playing else 0.05
                self.eq[i] += (target - self.eq[i]) * 0.5
                hgt = max(1, int(self.eq[i] * 12))
                for j in range(hgt):
                    y = 70 - j * 4
                    low, mid, high = self.sk["eq"]
                    color = hexc(high) if j >= 9 else hexc(low) if j < 5 else hexc(mid)
                    cv.create_rectangle((x0 + i * bw) * p, y * p, (x0 + i * bw + 4) * p, (y + 3) * p,
                                        fill=color, width=0)
            label = self.sk["label_audio"] if self.cfg["audio_only"] else self.sk["label_play"]
            self.canvas_text(cv, 6, 6, label, hexc(self.sk["screen_text"]), "t")
        self.root.after(120, self.animate_eq)

    def draw_volume(self):
        cv, p, k = self.vol, self.p, self.sk
        cv.delete("all")
        v = 0 if self.cfg["muted"] else self.cfg["volume"]
        cv.create_rectangle(p, 4 * p, (VOL_W - 2) * p, 7 * p, fill=hexc(k["bar_track"]),
                            outline=hexc(k["out"]), width=max(1, p // 2))
        fw = int((VOL_W - 4) * v / 100)
        if fw > 0:
            cv.create_rectangle(2 * p, 5 * p, (2 + fw) * p, 6 * p, fill=hexc(k["bar_fill"]), width=0)
        kx = 1 + int((VOL_W - 5) * v / 100)
        cv.create_rectangle(kx * p, 1 * p, (kx + 3) * p, 10 * p, fill=hexc(k["face"]),
                            outline=hexc(k["out"]), width=max(1, p // 2))

    def volume_at(self, e):
        v = round(min(1, max(0, (e.x / self.p - 2) / (VOL_W - 4))) * 100)
        self.cfg["volume"] = v
        self.var_volume.set(v)
        if self.cfg["muted"]:
            self.cfg["muted"] = False
            self.draw_button("mute")
        if self.player:
            self.player.audio_set_mute(False)
            self.player.audio_set_volume(v)
        self.draw_volume()
        save_config(self.cfg)

    def seek_at(self, e):
        if not (self.player and self.current):
            return
        x = e.x / self.p
        if x > 108:
            return
        length = self.player.get_length()
        if length <= 0:
            return
        start, end = self.clip_start, (self.clip_end or length)
        t = int(start + min(1, max(0, (x - 1) / 106)) * (end - start))
        self.player.set_time(t)
        self.draw_bar(t - start, end - start)

    def draw_bar(self, pos, total):
        cv, p = self.bar, self.p
        cv.delete("all")
        track_w = 108
        k = self.sk
        cv.create_rectangle(0, p, track_w * p, 5 * p, fill=hexc(k["bar_track"]), outline=hexc(k["out"]),
                            width=max(1, p // 2))
        if total > 0:
            fw = int((track_w - 2) * min(1, pos / total))
            if fw > 0:
                cv.create_rectangle(p, 2 * p, (1 + fw) * p, 4 * p, fill=hexc(k["bar_fill"]), width=0)
        label = f"{fmt_time(pos)}/{fmt_time(total)}" if total > 0 else "--:--"
        self.canvas_text(cv, VID_W - px_text_w(label), 1, label, hexc(k["bar_text"]), "time")

    # --- メニュー ---
    def menu_items(self):
        c = self.cfg

        def pick(var, value, fn):
            return lambda: (var.set(value), fn())

        def short(text, n=10):
            return text if len(text) <= n else text[:n - 1] + "…"

        tag_items = [{"type": "check", "label": t, "checked": t in c["tags"],
                      "cmd": lambda t=t: self.toggle_tag(t)} for t in c["tag_choices"]]
        tag_items += [{"type": "sep"}, {"type": "cmd", "label": "タグを追加…", "cmd": self.add_tag}]
        if len(c["tag_choices"]) > 1:
            tag_items.append({"type": "sub", "label": "メニューから外す",
                              "items": [{"type": "cmd", "label": t, "cmd": lambda t=t: self.remove_tag_choice(t)}
                                        for t in c["tag_choices"]]})
        kind_items = [{"type": "radio", "label": n, "checked": c["kinds"] == k,
                       "cmd": pick(self.var_kinds, k, self.set_kinds)} for n, k in KINDS]
        clip_items = [{"type": "radio", "label": n, "checked": c["clip_sec"] == v,
                       "cmd": pick(self.var_clip, v, self.set_clip)} for n, v in CLIPS]
        clip_items += [{"type": "sep"}, {"type": "cmd", "label": "つまみ食いの長さを自由に設定…", "cmd": self.ask_clip}]
        vol_items = [{"type": "radio", "label": n, "checked": c["volume"] == v,
                      "cmd": pick(self.var_volume, v, self.set_volume)} for n, v in VOLUMES]
        look_items = [{"type": "radio", "label": n, "checked": c["skin"] == k,
                       "cmd": pick(self.var_skin, k, self.set_skin)} for n, k in SKIN_NAMES]
        size_items = [{"type": "radio", "label": f"{n}（幅 {w}px）", "checked": c["width"] == w,
                       "cmd": pick(self.var_width, w, self.set_width)} for n, w in SIZES]
        clip_now = next((n.replace("つまみ食い ", "") for n, v in CLIPS if v == c["clip_sec"]),
                        f"{c['clip_sec']}秒")
        settings = [
            {"type": "sub", "label": "カラー", "items": lambda: colorway_menu(
                self.colorway, self.set_colorway, self.cfg["skin"] in COLOR_BASE),
             "right": next(n for n, k in COLORWAY_NAMES if k == self.colorway)},
            {"type": "sub", "label": "見た目", "items": look_items,
             "right": next((n.split("（")[0] for n, k in SKIN_NAMES if k == c["skin"]), "")},
            {"type": "sub", "label": "サイズ", "items": size_items,
             "right": next((n for n, w in SIZES if w == c["width"]), "")},
            {"type": "check", "label": "次に流れるリストを表示", "checked": c["show_queue"],
             "cmd": self.toggle_queue},
            {"type": "check", "label": "最前面に表示", "checked": c["topmost"],
             "cmd": pick(self.var_topmost, not c["topmost"], self.set_topmost)},
        ]
        library = [{"type": "cmd", "label": "リストを再読み込み", "cmd": lambda: self.load_items(force=True)},
                   {"type": "cmd", "label": "ライブラリを選び直す", "cmd": self.rechoose_library}]
        paused = self.var_paused.get()
        return [
            {"type": "cmd", "label": "次へ", "cmd": self.next_item},
            {"type": "cmd", "label": "前へ", "cmd": self.prev_item, "enabled": bool(self.played)},
            {"type": "cmd", "label": "再生する" if paused else "一時停止", "cmd": self.toggle_play,
             "enabled": bool(self.current)},
            {"type": "cmd", "label": "音声のみにする" if not c["audio_only"] else "映像も出す",
             "cmd": self.toggle_mode},
            {"type": "cmd", "label": "この動画を Eagle で開く", "cmd": self.open_in_eagle,
             "enabled": bool(self.current)},
            {"type": "sep"},
            {"type": "head", "label": "流すもの"},
            {"type": "sub", "label": "タグ", "items": tag_items,
             "right": short("＋".join(c["tags"])) if c["tags"] else "なし"},
            {"type": "sub", "label": "流すファイル", "items": kind_items,
             "right": next((n for n, k in KINDS if k == c["kinds"]), "")},
            {"type": "sub", "label": "流し方", "items": clip_items, "right": clip_now},
            {"type": "sub", "label": "音量", "items": vol_items,
             "right": "ミュート" if c["muted"] else f"{c['volume']}%"},
            {"type": "sep"},
            {"type": "sub", "label": "設定", "items": settings},
            {"type": "sub", "label": "ライブラリ", "items": library},
            {"type": "sep"},
            {"type": "cmd", "label": "終了", "cmd": self.quit},
            {"type": "head", "label": f"資料シアター ver.{APP_VERSION}"},
        ]

    def popup_menu(self, e):
        self.pmenu.title = f"{SKIN_TITLES[self.cfg['skin']]} - MENU"
        self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

    # フチに描いてあるボタン
    def frame_hotspots(self):
        sk = self.cfg["skin"]
        W = window_width(self.cfg["show_queue"])
        if sk == "pixeltube":
            bx0 = W - 3 - 3 * 9
            return {"min": (bx0, 3, bx0 + 7, 10), "close": (bx0 + 18, 3, bx0 + 25, 10)}
        if sk == "netradio":
            lx = W - 6 - px_text_w("ON AIR") - 3
            return {"menu": (lx, 3, W - 5, 10)}
        x0 = W - 5 - px_text_w("[SECURE]")
        return {"menu": (x0, 3, W - 5, 9)}

    def hotspot_at(self, e):
        x = (e.x_root - self.root.winfo_rootx()) / self.p
        y = (e.y_root - self.root.winfo_rooty()) / self.p
        for name, (x0, y0, x1, y1) in self.frame_hotspots().items():
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
            self.minimize()
        elif spot == "menu":
            self.popup_menu(e)

    def minimize(self):
        self.root.overrideredirect(False)
        self.root.iconify()

        def restore(ev):
            if ev.widget is self.root and self.root.state() == "normal":
                self.root.overrideredirect(True)
                self.root.unbind("<Map>")
        self.root.bind("<Map>", restore)

    def bind_events(self, w):
        w.bind("<ButtonPress-1>", self.drag_start)
        w.bind("<B1-Motion>", self.drag_move)
        w.bind("<ButtonRelease-1>", self.drag_end)
        w.bind("<Double-Button-1>", lambda e: self.open_in_eagle())
        w.bind("<Button-3>", self.popup_menu)

    def drag_start(self, e):
        self._press = (e.x_root, e.y_root)
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def drag_end(self, e):
        self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        save_config(self.cfg)

    # --- 読み込み ---
    def start(self):
        if not self.player:
            hint = ""
            if self.vlc_problem and ("193" in self.vlc_problem or "%1" in self.vlc_problem):
                hint = "\n（Python と VLC の 64bit / 32bit が合っていないかも）"
            self.message("VLC が見つからないよ。\nVLC を入れて、\npip install python-vlc\nを実行してね" + hint)
            log_error(f"VLC: {self.vlc_problem}")
            return
        if not self.cfg["library"]:
            self.choose_library()
        self.load_items()

    def choose_library(self):
        self.message("Eagle のライブラリ（〇〇.library）を選んでね")
        self.root.attributes("-topmost", False)
        path = filedialog.askdirectory(parent=self.root, title="Eagle のライブラリフォルダを選択")
        self.root.attributes("-topmost", self.cfg["topmost"])
        if path and is_library(os.path.normpath(path)):
            self.cfg["library"] = os.path.normpath(path)
            save_config(self.cfg)
        elif path:
            self.message("そのフォルダは Eagle のライブラリじゃないみたい")

    def rechoose_library(self):
        self.choose_library()
        self.load_items()

    def load_items(self, force=False):
        lib = self.cfg["library"]
        if not lib:
            self.message("ライブラリが未設定だよ。\n右クリック →「ライブラリを選び直す」")
            return
        if not is_library(lib):
            self.message("ライブラリが見つからないよ。\n外付けHDDはつながってる？\n（1分ごとに再確認するね）")
            self.root.after(60_000, self.load_items)
            return
        if not force:
            cached = load_index(lib)
            if cached is not None:
                self.items = cached
                self.apply_filter()
                return
        if self.scanning:
            return
        self.scanning = True
        self.message("ライブラリを読み込んでいます…\n（初回は数分かかるかも）")

        def work():
            try:
                items = scan_library(lib, progress=lambda n, h: self.q.put(("progress", n, h)))
                save_index(lib, items)
                self.q.put(("scanned", items))
            except OSError as ex:
                self.q.put(("scan_error", str(ex)))

        threading.Thread(target=work, daemon=True).start()

    def apply_filter(self, announce=False):
        tags = set(self.cfg["tags"])
        kinds = self.cfg["kinds"]
        self.pool = [it for it in self.items
                     if tags.intersection(it[3]) and (kinds == "both" or it[4] == kinds)]
        if not tags:
            self.stop_player()
            self.message("表示するタグが選ばれていないよ。\n右クリック →「表示するタグ」")
            return
        if not self.pool:
            self.stop_player()
            self.message(f"「{'＋'.join(self.cfg['tags'])}」の動画・音声が見つからなかったよ")
            return
        self.queue = [x for x in self.queue if x in self.pool]
        if announce or not self.current:
            self.queue = []
            self.next_item()
        else:
            self.fill_queue()

    # --- 再生 ---
    def pick_item(self):
        busy = {x[0] for x in self.queue} | ({self.current[0]} if self.current else set())
        item = random.choice(self.pool)
        for _ in range(20):
            if item[0] not in self.recent and item[0] not in busy:
                break
            item = random.choice(self.pool)
        self.recent.append(item[0])
        return item

    def fill_queue(self):
        while len(self.queue) < QUEUE_LEN and self.pool:
            self.queue.append(self.pick_item())
        for it in [self.current] + self.queue:
            if it and it[0] not in self.thumbs:
                self.thumbs[it[0]] = None   # 読み込み中
                p = self.p

                def work(it=it, p=p):
                    try:
                        img = load_thumb(it[1], 24 * p, 15 * p)
                    except Exception:
                        img = None
                    self.q.put(("thumb", it[0], img))
                threading.Thread(target=work, daemon=True).start()
        self.update_queue_panel()

    def placeholder(self, item):
        k, p = self.sk, self.p
        im = Image.new("RGB", (24, 15), k["screen"])
        d = ImageDraw.Draw(im)
        px_pattern(d, 10, 5, _ICONS["note" if item and item[4] == "audio" else "tv"], k["screen_text"])
        return im.resize((24 * p, 15 * p), Image.NEAREST)

    def update_queue_panel(self):
        if not self.cfg["show_queue"]:
            return
        k = self.sk
        t = self.menu_theme()
        rows = [self.current] + self.queue[:QUEUE_LEN]
        new_imgs = []   # 古い画像は、ラベルが新しい画像に切り替わるまで残しておく
        for i, row in enumerate(self.qrows):
            it = rows[i] if i < len(rows) else None
            now = i == 0 and it is not None
            bg = hexc(t["select"]) if now else hexc(k["name_bg"])
            fg = hexc(t["select_text"]) if now else hexc(k["name_fg"])
            row["name"].config(bg=bg, fg=fg, text=(("▶ " if now else "") + it[2]) if it else "")
            row["thumb"].config(bg=bg)
            if it:
                pic = self.thumbs.get(it[0]) or self.placeholder(it)
                img = ImageTk.PhotoImage(pic)
                new_imgs.append(img)
                row["thumb"].config(image=img)
            else:
                row["thumb"].config(image="")
        self.qimgs = new_imgs

    def jump_to(self, i):
        """リストの i 行目（0 は再生中）をクリックしたとき。"""
        if i == 0 or not self.player or i - 1 >= len(self.queue):
            return
        if self.current:
            self.played.append(self.current)
        item = self.queue.pop(i - 1)
        self.play_item(item)
        self.fill_queue()

    def prev_item(self):
        if not self.played or not self.player:
            return
        if self.current:
            self.queue.insert(0, self.current)
            del self.queue[QUEUE_LEN:]
        self.play_item(self.played.pop())
        self.fill_queue()

    def play_item(self, item, start_ms=None, keep_clip=False):
        if not self.player:
            return
        self.current = item
        media = self.vlc.media_new(item[1])
        if self.cfg["audio_only"]:
            media.add_option(":no-video")
        self.player.set_media(media)
        self.player.audio_set_mute(self.cfg["muted"])
        self.player.play()
        self.wait_ticks = 0
        if keep_clip:
            self.need_seek = start_ms is not None
            self.resume_ms = start_ms
        else:
            self.clip_start, self.clip_end = 0, None
            self.need_seek = True
            self.resume_ms = None
        self.name.config(text=("♪ " if item[4] == "audio" or self.cfg["audio_only"] else "▶ ") + item[2])
        self.var_paused.set(False)
        self.draw_button("play")
        self.update_screen()

    def next_item(self):
        if not self.pool:
            return
        if self.current:
            self.played.append(self.current)
        item = self.queue.pop(0) if self.queue else self.pick_item()
        self.play_item(item)
        self.fill_queue()

    def stop_player(self):
        if self.player:
            self.player.stop()
        self.draw_bar(0, 0)

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "progress":
                    self.message(f"ライブラリを読み込んでいます…\n{msg[1]:,} 件確認済み / {msg[2]:,} 件ヒット")
                elif msg[0] == "scanned":
                    self.scanning = False
                    self.items = msg[1]
                    self.current = None
                    self.apply_filter()
                elif msg[0] == "scan_error":
                    self.scanning = False
                    self.message(f"読み込みに失敗したよ\n{msg[1]}")
                elif msg[0] == "thumb":
                    self.thumbs[msg[1]] = msg[2]
                    self.update_queue_panel()
        except queue.Empty:
            pass

        if self.player and self.current and not self.var_paused.get():
            state = self.player.get_state()
            length = self.player.get_length()
            now = self.player.get_time()
            if state in (vlc.State.Ended, vlc.State.Error):
                self.next_item()
            elif state == vlc.State.Playing and length > 0:
                if self.need_seek:
                    self.need_seek = False
                    if self.resume_ms is not None:          # モード切り替え後の続きから
                        self.player.set_time(int(self.resume_ms))
                    else:
                        clip = self.cfg["clip_sec"] * 1000
                        if clip and length > clip + 2000:
                            self.clip_start = random.randint(0, length - clip - 1000)
                            self.clip_end = self.clip_start + clip
                            self.player.set_time(self.clip_start)
                        else:
                            self.clip_start, self.clip_end = 0, None
                end = self.clip_end or length
                self.draw_bar(now - self.clip_start, end - self.clip_start)
                if self.clip_end and now >= self.clip_end:
                    self.next_item()
            else:
                self.wait_ticks += 1
                if self.wait_ticks > 40:   # 10秒たっても再生が始まらないファイルは飛ばす
                    self.next_item()
        self.root.after(250, self.poll)

    # --- ボタン ---
    def toggle_play(self):
        if not self.player or not self.current:
            return
        paused = not self.var_paused.get()
        self.var_paused.set(paused)
        self.player.set_pause(1 if paused else 0)
        self.draw_button("play", True)

    def toggle_mode(self):
        self.cfg["audio_only"] = not self.cfg["audio_only"]
        save_config(self.cfg)
        self.draw_button("mode", True)
        if self.player and self.current:
            # 今のファイルを同じ位置から、モードを変えて再生し直す
            self.play_item(self.current, start_ms=self.player.get_time(), keep_clip=True)
        self.update_screen()

    def toggle_mute(self):
        self.cfg["muted"] = not self.cfg["muted"]
        save_config(self.cfg)
        if self.player:
            self.player.audio_set_mute(self.cfg["muted"])
        self.draw_button("mute", True)
        self.draw_volume()

    # --- メニュー操作 ---
    def toggle_tag(self, t):
        on = set(self.cfg["tags"]) ^ {t}
        self.cfg["tags"] = [x for x in self.cfg["tag_choices"] if x in on]
        save_config(self.cfg)
        self.apply_filter(announce=True)

    def remove_tag_choice(self, t):
        if len(self.cfg["tag_choices"]) <= 1:
            return
        self.cfg["tag_choices"].remove(t)
        if t in self.cfg["tags"]:
            self.cfg["tags"].remove(t)
        save_config(self.cfg)
        self.apply_filter(announce=True)

    def add_tag(self):
        """動画・音声に付いているタグを件数つきで一覧にして、そこから選ぶ。"""
        counts = Counter(t for it in self.items for t in it[3])
        if not counts:
            self.message("タグの付いた動画・音声がまだ見つかっていないよ")
            return
        entries = [(t, f"{t}（{n:,}件）", t in self.cfg["tags"]) for t, n in counts.most_common()]
        picked = pick_items(self.root, self.menu_theme(), "流すタグを選ぶ",
                            "流したいタグを選んでね", entries, near=self.root)
        if not picked:
            return
        for t in picked:
            if t not in self.cfg["tag_choices"]:
                self.cfg["tag_choices"].append(t)
            if t not in self.cfg["tags"]:
                self.cfg["tags"].append(t)
        save_config(self.cfg)
        self.apply_filter(announce=True)

    def set_kinds(self):
        self.cfg["kinds"] = self.var_kinds.get()
        save_config(self.cfg)
        self.apply_filter(announce=True)

    def set_clip(self):
        self.cfg["clip_sec"] = self.var_clip.get()
        save_config(self.cfg)

    def ask_clip(self):
        text = ask_text(self.root, self.menu_theme(), "つまみ食いの長さ",
                        "何秒ずつ流す？（5〜3600）", initial=str(self.cfg["clip_sec"] or 30), near=self.root)
        try:
            v = int(str(text).strip().translate(str.maketrans("０１２３４５６７８９", "0123456789")).rstrip("秒"))
        except ValueError:
            v = 0
        if 5 <= v <= 3600:
            self.var_clip.set(v)
            self.set_clip()

    def set_volume(self):
        self.cfg["volume"] = self.var_volume.get()
        save_config(self.cfg)
        if self.player:
            self.player.audio_set_volume(self.cfg["volume"])
        self.draw_volume()

    def set_width(self):
        self.cfg["width"] = self.var_width.get()
        self.p = Scale(self.cfg["width"] / VID_W)
        self.thumbs = {}
        save_config(self.cfg)
        self.layout()
        self.fill_queue()

    def toggle_queue(self):
        self.cfg["show_queue"] = not self.cfg["show_queue"]
        save_config(self.cfg)
        self.layout()

    def set_skin(self):
        self.cfg["skin"] = self.var_skin.get()
        save_config(self.cfg)
        self.layout()

    def set_topmost(self):
        self.cfg["topmost"] = self.var_topmost.get()
        save_config(self.cfg)
        self.root.attributes("-topmost", self.cfg["topmost"])

    def open_in_eagle(self):
        if not self.current or not self.current[0]:
            return
        if self.player and not self.var_paused.get():
            self.toggle_play()   # Eagle で見るときは一時停止しておく
        url = f"eagle://item/{self.current[0]}"
        try:
            os.startfile(url)
        except (AttributeError, OSError):
            webbrowser.open(url)

    def quit(self):
        save_config(self.cfg)
        if self.player:
            self.player.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


LOG_PATH = os.path.join(APP_DIR, "theater_error.txt")


def log_error(text):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass


if __name__ == "__main__":
    try:
        Theater().run()
    except Exception:
        import traceback
        detail = traceback.format_exc()
        log_error(detail)
        try:
            from tkinter import messagebox
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("資料シアター", "起動中にエラーが起きたよ。\n\n"
                                 f"{detail[-800:]}\n\n（theater_error.txt にも保存したよ）")
            r.destroy()
        except Exception:
            pass
