# -*- coding: utf-8 -*-
"""
資料ことのは ver.1.7
ChatGPT のエクスポートや、Simplenote・ストーリープロッターなどの txt を読み込んで、
文章をランダムに流す常駐ウィンドウ。SugarOS 24 のテキスト担当。

操作:
  STOP / PLAY  … 停止と再生
  NEXT         … 次へ
  COPY         … 表示中の文章をコピー
  RADIO        … ラジオ番組風の読み上げ（要 pip install pywin32）
  SPD つまみ   … 文字を打ち込む速さ（一番左で一瞬で全部表示）。ラジオ中は VOL（読み上げの音量）
  ダブルクリック … 元の文章をまるごと表示
  ドラッグ     … ウィンドウを移動
  右クリック   … メニュー（ソースの追加 / ChatGPTの発言 / 間隔 / 見た目 / サイズ など）

必要なもの: pip install pillow
"""
import json
import os
import queue
import random
import re
import threading
import zipfile
from xml.sax.saxutils import escape as xml_escape
from collections import deque
from datetime import datetime
import tkinter as tk
from tkinter import filedialog

from mushiboshi_ui import (COLORWAY_NAMES, dither_bar, log_errors, is_night_time, THEMES, PixelDialog, PixelMenu, ask_text,
                           colorway_menu, colorway_theme, load_colorway, make_colormap, recolor, recolor_dict,
                           save_colorway, Scale, PX_FONT, hexc, px_pattern, px_text, px_text_w, load_json,
                           save_json)

from PIL import Image, ImageDraw, ImageTk

APP_VERSION = "1.7"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "kotonoha_config.json")
INDEX_PATH = os.path.join(APP_DIR, "kotonoha_index.json")
INDEX_VERSION = 2
TEXT_EXTS = {"txt", "md", "text"}

CHUNK_MIN, CHUNK_MAX = 40, 360   # 1回に表示する文章の長さ（文字数）の目安

DEFAULT_CONFIG = {
    "sources": [],           # [{"path": ..., "type": "chatgpt" / "folder" / "file", "enabled": True}]
    "chat_roles": "user",    # ChatGPT の発言 "user"=自分 / "assistant"=AI / "both"
    "interval_sec": 20,
    "slow_long": True,       # 長い文章は表示時間を延ばす
    "clean_marks": True,     # 「###」「---」「**」などの記号を外して表示
    "skin": "notepad",       # "notepad" / "sns"
    "width": 480,
    "topmost": True,
    "x": 180,
    "y": 180,
    "radio_rate": 0,         # 読み上げの速さ（-10〜10）
    "radio_volume": 100,     # 読み上げの音量（0〜100）
    "type_speed": 4,         # 1文字ずつ打ち込む速さ（0=演出なし、1〜10）
}
RADIO_RATES = [("ゆっくり", -2), ("ふつう", 0), ("はやめ", 2), ("かなりはやめ", 4)]
INTERVALS = [("10秒", 10), ("20秒", 20), ("30秒", 30), ("1分", 60), ("3分", 180), ("10分", 600)]
SIZES = [("ミニ", 240), ("小", 320), ("中", 480), ("大", 640)]
SKIN_NAMES = [("ドットメモ帳", "notepad"), ("ドットSNS", "sns")]
ROLE_NAMES = [("自分の発言だけ", "user"), ("AIの発言だけ", "assistant"), ("両方", "both")]


# ---------- ドット絵 ----------

_ICONS = {
    "play": "#...|##..|###.|##..|#...",
    "pause": "#.#|#.#|#.#|#.#|#.#",
    "next": "#..#..|##.##.|######|##.##.|#..#..",
    "copy": "####..|#..###|#..#.#|####.#|..#..#|..####",
    "radio": "....#..|...#...|#######|#.#.#.#|#..#..#|#.#.#.#|#######",
    "pencil": ".....##|....#.#|...#.#.|..#.#..|.#.#...|##.....|#......",
    "min": ".....|.....|.....|.....|#####",
    "max": "#####|#...#|#...#|#...#|#####",
    "close": "#...#|.#.#.|..#..|.#.#.|#...#",
    "heart": ".##.##.|#######|#######|.#####.|..###..|...#...",
    "bubble": ".#####.|#.....#|#.....#|.#####.|.#.....|#......",
    "repost": "..#....|.#####.|..#..#.|.#..#..|.#####.|....#..",
}

SKINS = {
    "notepad": dict(
        face=(250, 244, 232), out=(76, 58, 50), light=(255, 255, 255), shade=(214, 200, 182),
        title=(255, 190, 120), title2=(255, 216, 168), accent=(226, 92, 70), hover=(255, 224, 198),
        paper=(255, 252, 240), rule=(214, 228, 240), margin=(240, 176, 176),
        meta=(160, 136, 124), text=(62, 48, 44), font="BIZ UDGothic", pad_left=13),
    "sns": dict(
        face=(255, 252, 246), out=(70, 60, 90), light=(255, 255, 255), shade=(140, 186, 206),
        title=(186, 226, 240), title2=(206, 238, 248), accent=(240, 96, 140), hover=(255, 222, 232),
        paper=(255, 252, 246), rule=None, margin=None,
        meta=(150, 140, 168), text=(58, 50, 78), font="Yu Gothic UI", pad_left=4),
}

TEXT_X, TEXT_Y, TEXT_W, TEXT_H = 3, 22, 160, 100
WIN_W, WIN_H = 166, 148
STATUS_Y, BTN_Y = 124, 135
BUTTONS = {"play": (3, 27), "next": (31, 29), "copy": (61, 29), "radio": (91, 34)}
SPD_X, SPD_W = 127, 35
TYPE_CPS = [0, 8, 12, 18, 25, 35, 50, 70, 100, 150, 250]   # つまみの段階ごとの、1秒に打ち込む文字数
TYPE_TICK = 33


def short_count(n):
    return str(n) if n < 1000 else f"{n / 1000:.1f}K"


def draw_avatar(d, role, k):
    out = k["out"]
    if role == "assistant":     # ロボット
        d.line([(11, 2), (11, 4)], fill=out)
        d.point((11, 2), fill=k["accent"])
        d.rectangle([4, 5, 18, 18], fill=(150, 214, 196), outline=out)
        d.line([(5, 6), (17, 6)], fill=(196, 240, 226))   # つや
        d.rectangle([7, 9, 9, 11], fill=out)
        d.rectangle([13, 9, 15, 11], fill=out)
        d.point((7, 9), fill=(196, 240, 226))
        d.point((13, 9), fill=(196, 240, 226))
        d.point((6, 13), fill=(246, 140, 150))
        d.point((16, 13), fill=(246, 140, 150))
        d.line([(8, 15), (14, 15)], fill=out)
    elif role == "memo":        # ノート
        d.rectangle([5, 4, 17, 18], fill=(255, 214, 110), outline=out)
        for y in (8, 11, 14):
            d.line([(8, y), (15, y)], fill=out)
        for y in range(5, 18, 3):
            d.point((5, y), fill=k["light"])
    else:                       # 自分：空色の丸に、前髪の女の子
        skin, hair = (255, 214, 184), (74, 56, 82)   # 髪はカラーや夜で塗り替えない色
        d.ellipse([4, 4, 18, 18], fill=k["title"], outline=out)
        d.pieslice([6, 6, 16, 19], 180, 360, fill=hair)
        d.ellipse([7, 9, 15, 17], fill=skin)
        d.line([(7, 9), (15, 9)], fill=hair)
        d.point((9, 10), fill=hair)
        d.point((12, 10), fill=hair)
        d.point((9, 12), fill=out)
        d.point((13, 12), fill=out)
        d.point((8, 14), fill=(246, 140, 150))
        d.point((14, 14), fill=(246, 140, 150))
        d.point((11, 15), fill=out)


def _color_base(key):
    """skin の色 → カラーの役割（同じ色が重なるときは、後ろに書いた役割が勝つ）。"""
    k = SKINS[key]
    roles = ("rule", "margin", "paper", "meta", "text", "shade", "hover", "title2", "title", "accent", "out", "face")
    return {k[r]: r for r in roles if k.get(r)}


COLOR_BASE = {key: _color_base(key) for key in ("notepad", "sns")}


def render_window(p, key, info, cmap=None):
    return recolor(_render_window(p, key, info), cmap)


def _render_window(p, key, info):
    k = SKINS[key]
    W, H = WIN_W, WIN_H
    im = Image.new("RGB", (W, H), k["face"])
    d = ImageDraw.Draw(im)
    out = k["out"]
    if key == "notepad":
        d.rectangle([0, 0, W - 1, H - 1], outline=out)
        d.line([(1, 1), (W - 2, 1)], fill=k["light"])
        d.line([(1, 1), (1, H - 2)], fill=k["light"])
        dither_bar(d, 2, 2, W - 3, 11, k["title2"], k["title"])   # 左の明るい色から、右へ網点でなめらかに
        px_pattern(d, 5, 4, _ICONS["pencil"], k["light"])
        px_pattern(d, 4, 3, _ICONS["pencil"], out)
        px_text(d, 15, 6, "NOTEPIX.EXE", k["light"])
        px_text(d, 14, 5, "NOTEPIX.EXE", out)
        bx0 = W - 3 - 3 * 9
        for i, icon in enumerate(("min", "max", "close")):
            x0 = bx0 + i * 9
            d.rectangle([x0, 3, x0 + 7, 10], fill=k["hover"] if icon == "close" else k["face"], outline=out)
            px_pattern(d, x0 + 1, 4, _ICONS[icon], out)
        d.line([(1, 12), (W - 2, 12)], fill=out)
        for x, word in ((5, "FILE"), (23, "EDIT"), (41, "FORMAT"), (67, "VIEW")):
            px_text(d, x, 14, word, out)
            d.line([(x, 20), (x + 2, 20)], fill=out)   # 頭文字の下線（ショートカットの印）
        # 便箋をとめるクリップ（上のはしだけ見える）
        cx = TEXT_X + TEXT_W - 14
        d.rectangle([cx, 15, cx + 4, 21], outline=k["meta"])
        d.line([(cx + 2, 17), (cx + 2, 21)], fill=k["meta"])
        # 便箋
        d.rectangle([TEXT_X - 1, TEXT_Y - 1, TEXT_X + TEXT_W, TEXT_Y + TEXT_H], fill=k["paper"], outline=out)
        for y in range(TEXT_Y + 9, TEXT_Y + TEXT_H, 6):
            d.line([(TEXT_X, y), (TEXT_X + TEXT_W - 1, y)], fill=k["rule"])
        d.line([(TEXT_X + 10, TEXT_Y), (TEXT_X + 10, TEXT_Y + TEXT_H - 1)], fill=k["margin"])
        # ステータスバー
        d.rectangle([TEXT_X - 1, STATUS_Y - 1, TEXT_X + TEXT_W, STATUS_Y + 7], fill=k["face"], outline=k["shade"])
        px_text(d, TEXT_X + 2, STATUS_Y + 1, f"NOTES {info.get('count', 0):,}", out)
        right = "PAUSED" if info.get("paused") else "ON AIR" if info.get("radio") else "UTF-8"
        px_text(d, TEXT_X + TEXT_W - 2 - px_text_w(right), STATUS_Y + 1, right, out)
    else:
        d.rectangle([0, 0, W - 1, H - 1], fill=k["title"])
        for y in range(0, H, 4):
            for x in range((y // 4) % 2 * 4, W, 8):
                d.point((x, y), fill=k["title2"])
        d.rectangle([1, 1, W - 3, H - 3], fill=k["face"], outline=out)
        d.line([(W - 2, 3), (W - 2, H - 2)], fill=k["shade"])
        d.line([(3, H - 2), (W - 2, H - 2)], fill=k["shade"])
        role = info.get("role", "user")
        draw_avatar(d, role, k)
        name = {"user": "ME", "assistant": "AI", "memo": "MEMO"}.get(role, "ME")
        handle = "@CHATGPT_LOG" if info.get("kind") == "chatgpt" else "@MY_NOTES"
        px_text(d, 22, 6, name, out)
        bx = 22 + px_text_w(name) + 2   # 認証バッジ
        px_pattern(d, bx, 5, ".#.#.|#####|.###.|#####|.#.#.", k["accent"])
        d.point((bx + 2, 7), fill=k["face"])
        px_text(d, 22, 13, f"{handle} - {info.get('time', '1M')}", k["meta"], max_w=W - 34)
        for i in range(3):
            d.point((W - 10 + i * 2, 8), fill=k["meta"])
        for x in range(TEXT_X + 1, W - 6, 2):   # 名前と本文のあいだ、リアクション欄の上の点線
            d.point((x, 20), fill=k["title"])
            d.point((x, STATUS_Y - 2), fill=k["title"])
        # リアクション
        y = STATUS_Y + 1
        slot = 30
        for i, (icon, n, col) in enumerate((("bubble", info.get("replies", 0), k["meta"]),
                                            ("repost", info.get("reposts", 0), k["meta"]),
                                            ("heart", info.get("likes", 0), k["accent"]))):
            x = TEXT_X + 2 + i * slot
            px_pattern(d, x, y, _ICONS[icon], col)
            px_text(d, x + 9, y + 1, short_count(n), col, max_w=slot - 11)
        state = "PAUSED" if info.get("paused") else "ON AIR" if info.get("radio") else ""
        if state:
            px_text(d, TEXT_X + TEXT_W - px_text_w(state) - 1, y + 1, state,
                    k["meta"] if info.get("paused") else k["accent"])
    return im.resize((W * p, H * p), Image.NEAREST)


def render_button(p, key, icon, text, width, hover=False, lit=False, cmap=None):
    return recolor(_render_button(p, key, icon, text, width, hover, lit), cmap)


def _render_button(p, key, icon, text, width, hover=False, lit=False):
    k = SKINS[key]
    iw = len(_ICONS[icon].split("|")[0])
    w, h = width, 11
    fill = k["hover"] if (hover or lit) else k["face"]
    im = Image.new("RGB", (w, h), fill)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], fill=fill, outline=k["out"])
    d.line([(1, 1), (w - 2, 1)], fill=k["light"])
    d.line([(1, h - 2), (w - 2, h - 2)], fill=tuple(round(v * 0.88) for v in fill))
    iy = (h - len(_ICONS[icon].split("|"))) // 2
    px_pattern(d, 3, iy, _ICONS[icon], k["out"] if hover else k["accent"])
    px_text(d, 3 + iw + 2, 3, text, k["out"])
    return im.resize((w * p, h * p), Image.NEAREST)


# ---------- 文章の読み込み ----------

def decode_bytes(b):
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return b.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8-sig", "cp932"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def fmt_date(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y/%m/%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def split_chunks(text):
    """空行で区切った段落をまとめて、CHUNK_MIN〜CHUNK_MAX 文字くらいの塊に分ける。(start, end) のリスト。"""
    spans = [m.span() for m in re.finditer(r"(?:[^\n]*\S[^\n]*(?:\n|$))+", text)]
    pieces = []
    for s, e in spans:            # 長すぎる段落は文の切れ目で分ける
        while e - s > CHUNK_MAX:
            cut = -1
            for m in re.finditer(r"[。！？!?\n]", text[s + CHUNK_MIN:s + CHUNK_MAX]):
                cut = s + CHUNK_MIN + m.end()
            if cut <= s:
                cut = s + CHUNK_MAX
            pieces.append((s, cut))
            s = cut
        if e > s:
            pieces.append((s, e))
    chunks, cur = [], None
    for s, e in pieces:
        if cur is None:
            cur = [s, e]
        elif cur[1] - cur[0] < CHUNK_MIN and e - cur[0] <= CHUNK_MAX:
            cur[1] = e
        else:
            chunks.append(tuple(cur))
            cur = [s, e]
    if cur:
        chunks.append(tuple(cur))
    out = []
    for s, e in chunks:
        seg = text[s:e]
        lead = len(seg) - len(seg.lstrip())
        trail = len(seg.rstrip())
        if trail - lead >= 8:
            out.append((s + lead, s + trail))
    return out


def chatgpt_docs(data, src):
    docs = []
    if isinstance(data, dict):
        data = data.get("conversations") or [data]
    for conv in data if isinstance(data, list) else []:
        if not isinstance(conv, dict):
            continue
        title = conv.get("title") or "無題の会話"
        nodes = list((conv.get("mapping") or {}).values())
        msgs = []
        for node in nodes:
            msg = (node or {}).get("message") or {}
            role = (msg.get("author") or {}).get("role")
            if role not in ("user", "assistant"):
                continue
            content = msg.get("content") or {}
            parts = content.get("parts") or []
            text = "\n".join(x for x in parts if isinstance(x, str)).strip()
            if not text and isinstance(content.get("text"), str):
                text = content["text"].strip()
            if not text:
                continue
            ts = msg.get("create_time") or conv.get("create_time") or 0
            msgs.append((ts or 0, role, text))
        msgs.sort(key=lambda m: m[0])
        for ts, role, text in msgs:
            docs.append([src, "chatgpt", title, fmt_date(ts), role, text, ""])
    return docs


def unescape_newlines(text):
    """改行が「\\n」という文字で書かれているファイル（ストーリープロッターなど）を本物の改行に直す。"""
    if text.count("\\n") > text.count("\n"):
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    return text


def text_doc(src, label, raw, mtime, path):
    text = unescape_newlines(decode_bytes(raw).replace("\r\n", "\n"))
    return [src, "text", label, fmt_date(mtime), "memo", text, path]


def load_source(source):
    """1つのソースから docs を作る。"""
    path, typ = source["path"], source["type"]
    docs = []
    if typ == "chatgpt":
        if path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                name = next((n for n in z.namelist() if n.endswith("conversations.json")), None)
                if name:
                    docs += chatgpt_docs(json.loads(decode_bytes(z.read(name))), path)
        else:
            with open(path, "rb") as f:
                docs += chatgpt_docs(json.loads(decode_bytes(f.read())), path)
    elif typ == "folder":
        for dirpath, _, files in os.walk(path):
            for fn in sorted(files):
                if fn.lower().rsplit(".", 1)[-1] in TEXT_EXTS:
                    fp = os.path.join(dirpath, fn)
                    try:
                        with open(fp, "rb") as f:
                            docs.append(text_doc(path, os.path.splitext(fn)[0], f.read(),
                                                 os.path.getmtime(fp), fp))
                    except OSError:
                        continue
    else:   # "file"（1つ）または "files"（まとめて選んだ複数）
        for fp in source.get("paths") or [path]:
            try:
                with open(fp, "rb") as f:
                    docs.append(text_doc(path, os.path.splitext(os.path.basename(fp))[0], f.read(),
                                         os.path.getmtime(fp), fp))
            except OSError:
                continue
    return docs


def source_signature(source):
    path = source["path"]
    try:
        if source["type"] == "folder":
            n, latest = 0, 0.0
            for dirpath, _, files in os.walk(path):
                for fn in files:
                    if fn.lower().rsplit(".", 1)[-1] in TEXT_EXTS:
                        n += 1
                        latest = max(latest, os.path.getmtime(os.path.join(dirpath, fn)))
            return [path, n, latest]
        if source.get("paths"):
            return [path] + [[os.path.getsize(fp), os.path.getmtime(fp)] if os.path.exists(fp) else -1
                             for fp in source["paths"]]
        return [path, os.path.getsize(path), os.path.getmtime(path)]
    except OSError:
        return [path, -1, -1]


def source_label(source):
    path, typ = source["path"], source["type"]
    base = os.path.basename(path.rstrip("\\/")) or path
    if typ == "chatgpt":
        return f"ChatGPT（{base}）"
    if typ == "folder":
        return f"フォルダ：{base}"
    paths = source.get("paths") or []
    if len(paths) > 1:
        return f"ファイル：{os.path.basename(paths[0])} ほか{len(paths) - 1}件"
    return f"ファイル：{base}"


# ---------- 読み上げ ----------

def clean_for_display(text):
    """見出しや強調などの記号（マークダウン）を外して、読みやすくする。改行はそのまま。"""
    out = []
    for line in text.split("\n"):
        st = line.strip()
        if re.fullmatch(r"[-=*_~]{3,}", st):      # 区切り線は行ごと消す
            continue
        line = re.sub(r"^(\s*)#{1,6}\s+", r"\1", line)
        line = re.sub(r"^(\s*)>\s?", r"\1", line)
        line = re.sub(r"^(\s*)[-*]\s+", r"\1・", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        out.append(line)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def strip_for_speech(text):
    """記号やURLなど、読み上げると耳ざわりなものを外す。"""
    text = re.sub(r"```.*?```", "（コードは省略）", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "（URL）", text)
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if re.fullmatch(r"[-=*_~]{3,}", line):
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^>\s*", "", line)
        line = re.sub(r"^[-*・]\s+", "", line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        if line:
            lines.append(line)
    return "。\n".join(l.rstrip("。") for l in lines) + "。"


def greeting():
    h = datetime.now().hour
    if 5 <= h < 11:
        return "おはようございます"
    if 11 <= h < 18:
        return "こんにちは"
    return "こんばんは"


def spoken_date(date):
    m = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2})", date or "")
    return f"{m.group(1)}年{int(m.group(2))}月{int(m.group(3))}日" if m else ""


def host_line(doc):
    """MC の紹介文。"""
    when = spoken_date(doc[3])
    when = f"{when}の、" if when else ""
    if doc[1] == "chatgpt":
        if doc[4] == "user":
            pool = [f"続いては、{when}あなたの言葉です。話題は、{doc[2]}。",
                    f"お次は、{doc[2]}、という会話から。{when}あなたの発言です。",
                    f"{when}あなたが、こんなことを話していました。"]
        else:
            pool = [f"次は、{when}AIが話していたことです。話題は、{doc[2]}。",
                    f"続いて、{doc[2]}、という会話から、AIの返事です。"]
    else:
        pool = [f"続いて、{doc[2]}、というメモから。",
                f"お次は、{when}書かれたメモ、{doc[2]}です。",
                f"{doc[2]}、から、ひとつ読んでみます。"]
    return random.choice(pool)


CORNER_TALK = ["資料ことのはラジオ、引き続きお楽しみください。",
               "懐かしい言葉が出てきたら、コピーしてネタ帳へどうぞ。",
               "このあとも、しまってあった言葉を虫干ししていきます。"]


class Speaker:
    """Windows の音声読み上げ（SAPI）を、止めたり再開したりできるように包んだもの。"""
    def __init__(self):
        import win32com.client   # pip install pywin32
        self.sp = win32com.client.Dispatch("SAPI.SpVoice")
        voices = [self.sp.GetVoices().Item(i) for i in range(self.sp.GetVoices().Count)]
        ja = [v for v in voices if "japan" in v.GetDescription().lower() or "日本" in v.GetDescription()
              or v.GetAttribute("Language") in ("411", "0411")]
        if not ja:
            raise RuntimeError("日本語の音声が見つからないよ")
        self.reader = ja[0].GetAttribute("Name")
        self.host = ja[1].GetAttribute("Name") if len(ja) > 1 else self.reader
        self.paused = False

    def set_volume(self, v):
        try:
            self.sp.Volume = max(0, min(100, int(v)))
        except Exception:
            pass

    def speak(self, host_text, body_text, rate=0, volume=100):
        host_pitch = 3 if self.host == self.reader else 0
        xml = (f'<voice required="Name={xml_escape(self.host)}"><rate speed="1"><pitch middle="{host_pitch}">'
               f"{xml_escape(host_text)}</pitch></rate></voice>"
               f'<silence msec="600"/>'
               f'<voice required="Name={xml_escape(self.reader)}">{xml_escape(body_text)}</voice>')
        self.sp.Rate = max(-10, min(10, rate))
        self.set_volume(volume)
        self.resume()
        self.sp.Speak(xml, 1 | 2 | 8)   # 非同期 / 前の読み上げを打ち切る / XML

    def done(self):
        return self.sp.Status.RunningState == 1

    def stop(self):
        self.resume()
        self.sp.Speak("", 1 | 2)

    def pause(self):
        if not self.paused:
            self.sp.Pause()
            self.paused = True

    def resume(self):
        if self.paused:
            self.sp.Resume()
            self.paused = False


# ---------- 設定 ----------

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_PATH, {}))
    if cfg["skin"] not in SKINS:
        cfg["skin"] = "notepad"
    return cfg


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


def format_interval(sec):
    if sec % 3600 == 0:
        return f"{sec // 3600}時間"
    if sec % 60 == 0:
        return f"{sec // 60}分"
    if sec > 60:
        return f"{sec // 60}分{sec % 60}秒"
    return f"{sec}秒"


def parse_interval(text):
    t = text.strip().replace(" ", "").replace("　", "")
    t = t.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if not t:
        return None
    if t.isdigit():
        return int(t)
    total, num = 0, ""
    for ch in t:
        if ch.isdigit():
            num += ch
        elif ch in "時分秒" and num:
            total += int(num) * {"時": 3600, "分": 60, "秒": 1}[ch]
            num = ""
        elif ch == "間":
            continue
        else:
            return None
    return None if num else (total or None)


# ---------- 本体 ----------

class Kotonoha:
    def __init__(self):
        self.cfg = load_config()
        self.p = Scale(self.cfg["width"] / TEXT_W)
        self.docs, self.chunks, self.pool = [], [], []
        self.recent = deque(maxlen=60)
        self.current = None
        self.timer = None
        self.loading = False
        self.q = queue.Queue()
        self.pimgs = {}
        self.info = {}
        self.radio = False      # ラジオモード中か
        self.speaker = None
        self.speaking = False
        self.aired = 0

        self.root = tk.Tk()
        log_errors(self.root, "kotonoha_error.txt")
        self.root.title(f"資料ことのは ver.{APP_VERSION}")
        self.root.overrideredirect(True)
        try:
            self.root.iconbitmap(default=os.path.join(APP_DIR, "kotonoha.ico"))
        except tk.TclError:
            pass
        self.root.attributes("-topmost", self.cfg["topmost"])

        self.var_paused = tk.BooleanVar(value=False)
        self.var_topmost = tk.BooleanVar(value=self.cfg["topmost"])
        self.var_interval = tk.IntVar(value=self.cfg["interval_sec"])
        self.var_slow = tk.BooleanVar(value=self.cfg["slow_long"])
        self.var_roles = tk.StringVar(value=self.cfg["chat_roles"])
        self.var_skin = tk.StringVar(value=self.cfg["skin"])
        self.var_width = tk.IntVar(value=self.cfg["width"])

        self.frame_label = tk.Label(self.root, bd=0, highlightthickness=0)
        self.cv = tk.Canvas(self.root, bd=0, highlightthickness=0)
        self.spd = tk.Canvas(self.root, bd=0, highlightthickness=0, cursor="hand2")
        self.spd.bind("<Button-1>", self.speed_at)
        self.spd.bind("<B1-Motion>", self.speed_at)
        self.spd.bind("<Button-3>", self.popup_menu)
        # 打ち込み演出の状態
        self.type_key = None
        self.type_n = 0.0
        self.type_job = None
        self.blink_job = None
        self.body_item = None
        self.body_full = ""
        for w in (self.root, self.frame_label, self.cv):
            self.bind_events(w)
        self.frame_label.bind("<Motion>", self.frame_hover, add="+")
        self.frame_label.bind("<ButtonRelease-1>", self.frame_click, add="+")
        self.buttons = {}
        for key, action in (("play", self.toggle_play), ("next", self.show_next), ("copy", self.copy_text),
                            ("radio", self.toggle_radio)):
            lb = tk.Label(self.root, bd=0, highlightthickness=0, cursor="hand2")
            lb.bind("<Button-1>", lambda e, a=action: a())
            lb.bind("<Enter>", lambda e, k=key: self.draw_button(k, True))
            lb.bind("<Leave>", lambda e, k=key: self.draw_button(k, False))
            lb.bind("<Button-3>", self.popup_menu)
            self.buttons[key] = lb

        self.var_rate = tk.IntVar(value=self.cfg["radio_rate"])
        self.colorway = load_colorway()
        self.look = (self.colorway, is_night_time())
        self.root.after(2000, self.watch_colorway)
        self.pmenu = PixelMenu(self.root, self.menu_theme, title="NOTEPIX - MENU")
        self.layout()
        self.root.after(150, self.poll)
        self.root.after(200, self.load_index)

    # --- 見た目 ---
    @property
    def sk(self):
        return recolor_dict(SKINS[self.cfg["skin"]], self.cmap())

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
        self.root.geometry(f"{WIN_W * p}x{WIN_H * p}+{self.cfg['x']}+{self.cfg['y']}")
        self.frame_label.place(x=0, y=0, width=WIN_W * p, height=WIN_H * p)
        self.cv.place(x=TEXT_X * p, y=TEXT_Y * p, width=TEXT_W * p, height=TEXT_H * p)
        for key, (x, w) in BUTTONS.items():
            self.draw_button(key)
            self.buttons[key].place(x=x * p, y=BTN_Y * p)
        self.spd.config(bg=hexc(self.sk["face"]))
        self.spd.place(x=SPD_X * p, y=BTN_Y * p, width=SPD_W * p, height=11 * p)
        self.draw_speed()
        self.redraw()

    def frame_info(self):
        doc = self.docs[self.current[0]] if self.current else None
        return {
            "count": len(self.pool), "paused": self.var_paused.get(), "radio": self.radio,
            "role": doc[4] if doc else "memo", "kind": doc[1] if doc else "text",
            "time": random.choice(["JUST NOW", "1M", "5M", "12M", "1H", "3H"]),
            "likes": int(random.paretovariate(1.2) * 8), "reposts": int(random.paretovariate(1.4) * 3),
            "replies": random.randint(0, 24),
        }

    def redraw(self, new_info=True):
        if new_info or not self.info:
            self.info = self.frame_info()
        else:
            self.info.update(count=len(self.pool), paused=self.var_paused.get(), radio=self.radio)
        img = render_window(self.p, self.cfg["skin"], self.info, self.cmap())
        self.frame_photo = ImageTk.PhotoImage(img)
        self.frame_label.config(image=self.frame_photo)
        p = self.p
        crop = img.crop((TEXT_X * p, TEXT_Y * p, (TEXT_X + TEXT_W) * p, (TEXT_Y + TEXT_H) * p))
        self.bg_photo = ImageTk.PhotoImage(crop)
        self.draw_text()

    def draw_text(self, meta=None, body=None):
        cv, p, k = self.cv, self.p, self.sk
        cv.delete("all")
        cv.create_image(0, 0, image=self.bg_photo, anchor="nw")
        if body is None:
            if not self.current:
                meta, body = "", getattr(self, "msg_text", "")
            else:
                doc = self.docs[self.current[0]]
                body = doc[5][self.current[1]:self.current[2]]
                if self.cfg["clean_marks"]:
                    body = clean_for_display(body)
                if doc[1] == "chatgpt":
                    who = "あなた" if doc[4] == "user" else "AI"
                    meta = f"{doc[2]}　{doc[3]}　{who}"
                else:
                    meta = f"{doc[2]}　{doc[3]}"
        left = k["pad_left"] * p
        width = TEXT_W * p - left - 4 * p
        y = 2 * p
        if meta:
            item = cv.create_text(left, y, anchor="nw", text=meta, fill=hexc(k["meta"]),
                                  font=(k["font"], -max(10, int(3.2 * p))), width=width)
            y = cv.bbox(item)[3] + 2 * p
        if not body:
            return
        limit = TEXT_H * p - 2 * p
        size = 7.0   # 大きいサイズから試して、枠に収まる一番大きいサイズを使う
        while True:
            px = max(10, int(size * p))
            item = cv.create_text(left, y, anchor="nw", text=body, fill=hexc(k["text"]),
                                  font=(k["font"], -px), width=width)
            if cv.bbox(item)[3] <= limit or px <= 10:
                break
            cv.delete(item)
            size -= 0.25
        while cv.bbox(item)[3] > limit and len(body) > 20:   # それでも入らなければ末尾を省略
            body = body[:int(len(body) * 0.9)].rstrip() + "…"
            cv.itemconfig(item, text=body)
        self.body_item, self.body_full = item, body
        if not self.current:
            return
        key = tuple(self.current)
        if key != self.type_key:          # 新しい文章になったら打ち込みをやり直す
            self.type_key = key
            self.type_n = 0.0 if self.cfg["type_speed"] > 0 else float(len(body))
            self._stop_typing()
            if self.type_n < len(body):
                self.type_job = self.root.after(TYPE_TICK, self._type_step)
            else:
                self._start_blink()
        self._show_typed()

    # --- 打ち込み演出 ---
    def _stop_typing(self):
        for job in (self.type_job, self.blink_job):
            if job:
                self.root.after_cancel(job)
        self.type_job = self.blink_job = None

    def _show_typed(self, cursor=True):
        if self.body_item is None:
            return
        n = int(self.type_n)
        text = self.body_full[:n] + ("_" if cursor else " ")
        try:
            self.cv.itemconfig(self.body_item, text=text)
        except tk.TclError:
            pass

    def _type_step(self):
        self.type_job = None
        cps = TYPE_CPS[max(0, min(10, self.cfg["type_speed"]))] or 10000
        self.type_n = min(len(self.body_full), self.type_n + cps * TYPE_TICK / 1000)
        self._show_typed()
        if self.type_n < len(self.body_full):
            self.type_job = self.root.after(TYPE_TICK, self._type_step)
        else:
            self._start_blink()

    def _start_blink(self, on=True):
        self._show_typed(cursor=on)
        self.blink_job = self.root.after(530, lambda: self._start_blink(not on))

    def typing_seconds(self):
        cps = TYPE_CPS[max(0, min(10, self.cfg["type_speed"]))]
        if not cps or not self.current:
            return 0
        return (self.current[2] - self.current[1]) / cps

    # --- 速さのつまみ ---
    def draw_speed(self):
        cv, p, k = self.spd, self.p, self.sk
        cv.delete("all")
        for i, ch in enumerate("VOL" if self.radio else "SPD"):
            for ry, row in enumerate(PX_FONT[ch].split("|")):
                for rx, c in enumerate(row):
                    if c == "#":
                        X, Y = (i * 4 + rx) * p, (3 + ry) * p
                        cv.create_rectangle(X, Y, X + p, Y + p, fill=hexc(k["out"]), width=0)
        x0, x1 = 13, SPD_W - 1
        cv.create_rectangle(x0 * p, 4 * p, x1 * p, 7 * p, fill=hexc(k["paper"]), outline=hexc(k["out"]),
                            width=max(1, p // 2))
        lv = round(self.cfg["radio_volume"] / 10) if self.radio else self.cfg["type_speed"]
        fw = int((x1 - x0 - 2) * lv / 10)
        if fw > 0:
            cv.create_rectangle((x0 + 1) * p, 5 * p, (x0 + 1 + fw) * p, 6 * p, fill=hexc(k["accent"]), width=0)
        kx = x0 + int((x1 - x0 - 3) * lv / 10)
        cv.create_rectangle(kx * p, 1 * p, (kx + 3) * p, 10 * p, fill=hexc(k["face"]), outline=hexc(k["out"]),
                            width=max(1, p // 2))

    def speed_at(self, e):
        x0, x1 = 13, SPD_W - 1
        lv = round(min(1, max(0, (e.x / self.p - x0) / (x1 - x0 - 2))) * 10)
        if self.radio:
            self.set_radio_volume(lv * 10)
            return
        if lv != self.cfg["type_speed"]:
            self.cfg["type_speed"] = lv
            save_config(self.cfg)
            self.draw_speed()
            if lv == 0 and self.type_job:      # 演出なしにしたら、すぐ全部見せる
                self.root.after_cancel(self.type_job)
                self.type_job = None
                self.type_n = float(len(self.body_full))
                self._start_blink()

    def show_message(self, text):
        self._stop_typing()
        self.type_key = None
        self.current = None
        self.msg_text = text
        self.redraw()

    def canvas_flash(self, text):
        p, k = self.p, self.sk
        tag = "flash"
        self.cv.delete(tag)
        w = px_text_w(text) + 4
        x0 = TEXT_W - w - 2
        self.cv.create_rectangle(x0 * p, 2 * p, (x0 + w) * p, 9 * p, fill=hexc(k["accent"]), width=0, tags=tag)
        for i, ch in enumerate(text.upper()):
            for ry, row in enumerate(PX_FONT.get(ch, PX_FONT["?"]).split("|")):
                for rx, c in enumerate(row):
                    if c == "#":
                        X, Y = (x0 + 2 + i * 4 + rx) * p, (3 + ry) * p
                        self.cv.create_rectangle(X, Y, X + p, Y + p, fill="#ffffff", width=0, tags=tag)
        self.root.after(1200, lambda: self.cv.delete(tag))

    def draw_button(self, key, hover=False):
        x, w = BUTTONS[key]
        if key == "play":
            icon, text = ("play", "PLAY") if self.var_paused.get() else ("pause", "STOP")
        elif key == "next":
            icon, text = "next", "NEXT"
        elif key == "copy":
            icon, text = "copy", "COPY"
        else:
            icon, text = "radio", "RADIO"
        lit = key == "radio" and self.radio
        img = ImageTk.PhotoImage(render_button(self.p, self.cfg["skin"], icon, text, w, hover, lit,
                                                   self.cmap()))
        self.pimgs[key] = img
        self.buttons[key].config(image=img)

    # --- メニュー ---
    def menu_items(self):
        c = self.cfg

        def pick(var, value, fn):
            return lambda: (var.set(value), fn())

        src_items = [{"type": "check", "label": source_label(s), "checked": s.get("enabled", True),
                      "cmd": lambda i=i: self.toggle_source(i)} for i, s in enumerate(c["sources"])]
        if src_items:
            src_items.append({"type": "sep"})
        src_items += [
            {"type": "cmd", "label": "ChatGPT のエクスポートを追加…", "right": ".json / .zip", "cmd": self.add_chatgpt},
            {"type": "cmd", "label": "テキストのフォルダを追加…", "right": "Simplenote など", "cmd": self.add_folder},
            {"type": "cmd", "label": "テキストファイルを追加…", "right": "複数OK", "cmd": self.add_file},
        ]
        if c["sources"]:
            src_items.append({"type": "sub", "label": "ソースを外す",
                              "items": [{"type": "cmd", "label": source_label(s), "cmd": lambda i=i: self.remove_source(i)}
                                        for i, s in enumerate(c["sources"])]})
        role_items = [{"type": "radio", "label": n, "checked": c["chat_roles"] == k,
                       "cmd": pick(self.var_roles, k, self.set_roles)} for n, k in ROLE_NAMES]
        interval_items = [{"type": "radio", "label": n, "checked": c["interval_sec"] == v,
                           "cmd": pick(self.var_interval, v, self.set_interval)} for n, v in INTERVALS]
        interval_items += [{"type": "sep"}, {"type": "cmd", "label": "自由に設定…", "cmd": self.ask_interval}]
        rate_items = [{"type": "radio", "label": n, "checked": c["radio_rate"] == v,
                       "cmd": pick(self.var_rate, v, self.set_rate)} for n, v in RADIO_RATES]
        look_items = [{"type": "radio", "label": n, "checked": c["skin"] == k,
                       "cmd": pick(self.var_skin, k, self.set_skin)} for n, k in SKIN_NAMES]
        size_items = [{"type": "radio", "label": f"{n}（幅 {w}px）", "checked": c["width"] == w,
                       "cmd": pick(self.var_width, w, self.set_width)} for n, w in SIZES]
        settings = [
            {"type": "sub", "label": "切り替え間隔", "items": interval_items,
             "right": format_interval(c["interval_sec"])},
            {"type": "check", "label": "長い文章はゆっくり", "checked": c["slow_long"],
             "cmd": pick(self.var_slow, not c["slow_long"], self.set_slow)},
            {"type": "check", "label": "記号（### や ** など）を外して表示", "checked": c["clean_marks"],
             "cmd": self.toggle_clean},
            {"type": "sub", "label": "打ち込みの速さ", "right": "なし" if not c["type_speed"] else f"{c['type_speed']}",
             "items": [{"type": "radio", "label": n, "checked": c["type_speed"] == v,
                        "cmd": lambda v=v: self.set_type_speed(v)}
                       for n, v in (("なし（一瞬で表示）", 0), ("ゆっくり", 2), ("ふつう", 4), ("はやめ", 7), ("かなりはやめ", 10))]},
            {"type": "sub", "label": "読み上げの速さ", "items": rate_items,
             "right": next((n for n, v in RADIO_RATES if v == c["radio_rate"]), "")},
            {"type": "sub", "label": "読み上げの音量", "right": f"{c['radio_volume']}%",
             "items": [{"type": "radio", "label": f"{v}%", "checked": c["radio_volume"] == v,
                        "cmd": lambda v=v: self.set_radio_volume(v)} for v in (25, 50, 75, 100)]},
            {"type": "sep"},
            {"type": "sub", "label": "カラー", "items": lambda: colorway_menu(
                self.colorway, self.set_colorway, self.cfg["skin"] in COLOR_BASE),
             "right": next(n for n, k in COLORWAY_NAMES if k == self.colorway)},
            {"type": "sub", "label": "見た目", "items": look_items,
             "right": next((n for n, k in SKIN_NAMES if k == c["skin"]), "")},
            {"type": "sub", "label": "サイズ", "items": size_items,
             "right": next((n for n, w in SIZES if w == c["width"]), "")},
            {"type": "check", "label": "最前面に表示", "checked": c["topmost"],
             "cmd": pick(self.var_topmost, not c["topmost"], self.set_topmost)},
        ]
        on = sum(1 for s in c["sources"] if s.get("enabled", True))
        paused = self.var_paused.get()
        return [
            {"type": "cmd", "label": "次へ", "cmd": self.show_next},
            {"type": "cmd", "label": "再開する" if paused else "一時停止", "cmd": self.toggle_play},
            {"type": "cmd", "label": "元の文章をまるごと見る", "cmd": self.open_viewer, "enabled": bool(self.current)},
            {"type": "cmd", "label": "コピー", "cmd": self.copy_text, "enabled": bool(self.current)},
            {"type": "cmd", "label": "ラジオを終える" if self.radio else "ラジオを始める", "cmd": self.toggle_radio,
             "right": "ON AIR" if self.radio else ""},
            {"type": "sep"},
            {"type": "head", "label": "流す文章"},
            {"type": "sub", "label": "ソース", "items": src_items, "right": f"{on}件" if c["sources"] else "未設定"},
            {"type": "sub", "label": "ChatGPTの発言", "items": role_items,
             "right": next((n.replace("の発言だけ", "だけ") for n, k in ROLE_NAMES if k == c["chat_roles"]), "")},
            {"type": "sep"},
            {"type": "sub", "label": "設定", "items": settings},
            {"type": "cmd", "label": "読み込み直す", "cmd": lambda: self.load_index(force=True)},
            {"type": "sep"},
            {"type": "cmd", "label": "終了", "cmd": self.quit},
            {"type": "head", "label": f"資料ことのは ver.{APP_VERSION}"},
        ]

    def popup_menu(self, e):
        self.pmenu.title = "NOTEPIX - MENU" if self.cfg["skin"] == "notepad" else "MY NOTES - MENU"
        self.pmenu.popup(self.menu_items, e.x_root, e.y_root)

    # フチに描いてあるボタン
    def frame_hotspots(self):
        if self.cfg["skin"] == "notepad":
            bx0 = WIN_W - 3 - 3 * 9
            return {"min": (bx0, 3, bx0 + 7, 10), "close": (bx0 + 18, 3, bx0 + 25, 10)}
        return {"menu": (WIN_W - 13, 3, WIN_W - 3, 13)}

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
        w.bind("<Double-Button-1>", lambda e: self.open_viewer())
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

    # --- ソース ---
    def ask_paths(self, func, **kw):
        self.root.attributes("-topmost", False)
        got = func(parent=self.root, **kw)
        self.root.attributes("-topmost", self.cfg["topmost"])
        if not got:
            return []
        if isinstance(got, str):
            got = [got]
        return [os.path.normpath(x) for x in got]

    def add_sources(self, new):
        """new: 追加するソースの dict のリスト。まとめて追加してから1回だけ読み込む。"""
        have = {s["path"] for s in self.cfg["sources"]}
        added = [n for n in new if n["path"] not in have]
        if not added:
            if new:
                self.canvas_flash("ALREADY ADDED")
            return
        self.cfg["sources"] += added
        save_config(self.cfg)
        self.load_index(force=True)

    def add_chatgpt(self):
        paths = self.ask_paths(filedialog.askopenfilenames, title="ChatGPT のエクスポートを選択（複数OK）",
                               filetypes=[("ChatGPT エクスポート", "*.json *.zip"), ("すべて", "*.*")])
        self.add_sources([{"path": p, "type": "chatgpt", "enabled": True} for p in paths])

    def add_folder(self):
        paths = self.ask_paths(filedialog.askdirectory, title="テキストの入ったフォルダを選択")
        self.add_sources([{"path": p, "type": "folder", "enabled": True} for p in paths])

    def add_file(self):
        paths = self.ask_paths(filedialog.askopenfilenames, title="テキストファイルを選択（複数OK）",
                               filetypes=[("テキスト", "*.txt *.md"), ("すべて", "*.*")])
        if len(paths) == 1:
            self.add_sources([{"path": paths[0], "type": "file", "enabled": True}])
        elif paths:   # まとめて選んだファイルは1つのソースにする（メニューが長くならないように）
            key = "files:" + "|".join(sorted(paths))
            self.add_sources([{"path": key, "type": "files", "paths": paths, "enabled": True}])

    def toggle_source(self, i):
        self.cfg["sources"][i]["enabled"] = not self.cfg["sources"][i].get("enabled", True)
        save_config(self.cfg)
        self.apply_filter(restart=True)

    def remove_source(self, i):
        del self.cfg["sources"][i]
        save_config(self.cfg)
        self.load_index(force=True)

    # --- 読み込み ---
    def load_index(self, force=False):
        sources = list(self.cfg["sources"])
        if not sources:
            self.docs, self.chunks = [], []
            self.apply_filter(restart=True)
            return
        if self.loading:
            return
        self.loading = True
        self.show_message("文章を読み込んでいます…")

        def work():
            sigs = [source_signature(s) for s in sources]
            if not force:
                try:
                    with open(INDEX_PATH, encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("version") == INDEX_VERSION and data.get("sigs") == sigs:
                        self.q.put(("loaded", data["docs"], data["chunks"], []))
                        return
                except (OSError, ValueError, KeyError):
                    pass
            docs, chunks, errors = [], [], []
            for s in sources:
                try:
                    docs += load_source(s)
                except Exception as ex:
                    errors.append(f"{source_label(s)}：{ex}")
                self.q.put(("progress", len(docs)))
            for i, doc in enumerate(docs):
                for a, b in split_chunks(doc[5]):
                    chunks.append([i, a, b])
            save_json(INDEX_PATH, {"version": INDEX_VERSION, "sigs": sigs, "docs": docs, "chunks": chunks},
                      pretty=False)
            self.q.put(("loaded", docs, chunks, errors))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "progress":
                    self.show_message(f"文章を読み込んでいます…（{msg[1]:,} 件）")
                elif msg[0] == "loaded":
                    self.loading = False
                    self.docs, self.chunks = msg[1], msg[2]
                    self.apply_filter(restart=True)
                    if msg[3]:
                        self.show_message("読み込めなかったソースがあるよ\n\n" + "\n".join(msg[3]))
        except queue.Empty:
            pass
        if self.radio and self.speaking and not self.var_paused.get():
            try:
                finished = self.speaker.done()
            except Exception:
                finished = True
            if finished:
                self.speaking = False
                self.timer = self.root.after(1500, self.show_next)
        self.root.after(150, self.poll)

    def apply_filter(self, restart=False):
        enabled = {s["path"] for s in self.cfg["sources"] if s.get("enabled", True)}
        roles = self.cfg["chat_roles"]
        self.pool = [c for c in self.chunks
                     if self.docs[c[0]][0] in enabled
                     and (self.docs[c[0]][1] != "chatgpt" or roles == "both" or self.docs[c[0]][4] == roles)]
        if not self.cfg["sources"]:
            self.cancel_timer()
            self.show_message("右クリック →「ソース」から、\nChatGPT のエクスポートや\nテキストのフォルダを追加してね")
            return
        if not self.pool:
            self.cancel_timer()
            self.show_message("表示できる文章が見つからなかったよ。\n右クリック →「ソース」や「ChatGPTの発言」を確かめてね")
            return
        if restart or not self.current:
            self.show_next()

    # --- 表示の切り替え ---
    def show_next(self):
        if not self.pool:
            return
        if self.radio and self.var_paused.get():   # 一時停止中に NEXT を押したら再開する
            self.var_paused.set(False)
            self.draw_button("play")
        c = random.choice(self.pool)
        for _ in range(20):
            if tuple(c) not in self.recent:
                break
            c = random.choice(self.pool)
        self.recent.append(tuple(c))
        self.current = c
        self.redraw()
        if self.radio:
            self.cancel_timer()
            self.speak_current()
        else:
            self.schedule()

    def cancel_timer(self):
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None

    def schedule(self):
        self.cancel_timer()
        if self.var_paused.get() or not self.pool or self.radio:
            return
        sec = self.cfg["interval_sec"]
        if self.cfg["slow_long"] and self.current:
            sec = max(sec, 3 + (self.current[2] - self.current[1]) / 8)   # 1秒に8文字くらい
        sec += self.typing_seconds()
        self.timer = self.root.after(int(sec * 1000), self.show_next)

    def toggle_play(self):
        self.var_paused.set(not self.var_paused.get())
        if self.radio and self.speaker:
            if self.var_paused.get():
                self.cancel_timer()
                self.speaker.pause()
            else:
                self.speaker.resume()
                if not self.speaking:
                    self.show_next()
        self.schedule()
        self.draw_button("play", True)
        self.redraw(new_info=False)

    # --- ラジオ ---
    def toggle_radio(self):
        if self.radio:
            self.radio = False
            self.speaking = False
            if self.speaker:
                self.speaker.stop()
            self.canvas_flash("RADIO OFF")
            self.draw_button("radio", True)
            self.draw_speed()
            self.redraw(new_info=False)
            self.schedule()
            return
        if not self.speaker:
            try:
                self.speaker = Speaker()
            except ImportError:
                self.show_message("読み上げには部品が必要だよ。\nコマンドプロンプトで\npip install pywin32\nを実行してね")
                return
            except Exception as ex:
                self.show_message(f"読み上げの準備に失敗したよ\n{ex}")
                return
        if not self.pool:
            return
        self.radio = True
        self.aired = 0
        self.draw_speed()
        self.var_paused.set(False)
        self.draw_button("play")
        self.draw_button("radio", True)
        self.cancel_timer()
        if not self.current:
            self.show_next()
        else:
            self.redraw(new_info=False)
            self.speak_current(opening=True)

    def speak_current(self, opening=False):
        if not (self.radio and self.speaker and self.current):
            return
        doc = self.docs[self.current[0]]
        body = strip_for_speech(doc[5][self.current[1]:self.current[2]])
        intro = host_line(doc)
        if opening or self.aired == 0:
            intro = f"{greeting()}。資料ことのはラジオの時間です。今日も、しまってあった言葉を虫干ししていきます。" + intro
        elif self.aired % 6 == 0:
            intro = random.choice(CORNER_TALK) + intro
        self.aired += 1
        try:
            self.speaker.speak(intro, body, self.cfg["radio_rate"], self.cfg["radio_volume"])
            self.speaking = True
        except Exception as ex:
            self.radio = False
            self.show_message(f"読み上げに失敗したよ\n{ex}")

    def set_radio_volume(self, v):
        self.cfg["radio_volume"] = v
        save_config(self.cfg)
        if self.speaker:
            self.speaker.set_volume(v)
        self.draw_speed()

    def toggle_clean(self):
        self.cfg["clean_marks"] = not self.cfg["clean_marks"]
        save_config(self.cfg)
        self.type_key = None
        self.redraw(new_info=False)

    def set_type_speed(self, v):
        self.cfg["type_speed"] = v
        save_config(self.cfg)
        self.draw_speed()

    def set_rate(self):
        self.cfg["radio_rate"] = self.var_rate.get()
        save_config(self.cfg)

    def copy_text(self):
        if not self.current:
            return
        doc = self.docs[self.current[0]]
        self.root.clipboard_clear()
        self.root.clipboard_append(doc[5][self.current[1]:self.current[2]])
        self.canvas_flash("COPIED!")

    def open_viewer(self):
        if not self.current:
            return
        doc = self.docs[self.current[0]]
        s, e = self.current[1], self.current[2]
        t = self.menu_theme()
        head = f"{doc[3]}"
        if doc[1] == "chatgpt":
            head += "　" + ("あなた" if doc[4] == "user" else "AI")
        dlg = PixelDialog(self.root, t, doc[2], near=self.root)
        dlg.label(head, sub=True)
        txt = dlg.text(height=20, width=48)
        txt.insert("1.0", doc[5])
        txt.tag_add("hit", f"1.0 + {s} chars", f"1.0 + {e} chars")
        txt.tag_config("hit", background="#%02x%02x%02x" % t["title2"])
        txt.see(f"1.0 + {s} chars")
        txt.config(state="disabled")
        dlg.add_button("閉じる", dlg.close, primary=True)
        if doc[6] and os.path.exists(doc[6]):
            def open_file():
                try:
                    os.startfile(doc[6])
                except (AttributeError, OSError):
                    pass
            dlg.add_button("元のファイルを開く", open_file)
        dlg.show()

    # --- メニュー操作 ---
    def set_roles(self):
        self.cfg["chat_roles"] = self.var_roles.get()
        save_config(self.cfg)
        self.apply_filter(restart=True)

    def set_interval(self):
        self.cfg["interval_sec"] = self.var_interval.get()
        save_config(self.cfg)
        self.schedule()

    def ask_interval(self):
        text = ask_text(self.root, self.menu_theme(), "切り替え間隔",
                        "何秒ごとに切り替える？\n例：45 / 45秒 / 2分 / 1分30秒",
                        initial=format_interval(self.cfg["interval_sec"]), near=self.root)
        sec = parse_interval(text or "")
        if sec and sec >= 3:
            self.var_interval.set(sec)
            self.set_interval()

    def set_slow(self):
        self.cfg["slow_long"] = self.var_slow.get()
        save_config(self.cfg)
        self.schedule()

    def set_skin(self):
        self.cfg["skin"] = self.var_skin.get()
        save_config(self.cfg)
        self.layout()

    def set_width(self):
        self.cfg["width"] = self.var_width.get()
        self.p = Scale(self.cfg["width"] / TEXT_W)
        save_config(self.cfg)
        self.layout()

    def set_topmost(self):
        self.cfg["topmost"] = self.var_topmost.get()
        save_config(self.cfg)
        self.root.attributes("-topmost", self.cfg["topmost"])

    def quit(self):
        save_config(self.cfg)
        if self.speaker:
            try:
                self.speaker.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


LOG_PATH = os.path.join(APP_DIR, "kotonoha_error.txt")

if __name__ == "__main__":
    try:
        Kotonoha().run()
    except Exception:
        import traceback
        detail = traceback.format_exc()
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(detail + "\n")
        except OSError:
            pass
        try:
            from tkinter import messagebox
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("資料ことのは", "起動中にエラーが起きたよ。\n\n" + detail[-800:]
                                 + "\n\n（kotonoha_error.txt にも保存したよ）")
            r.destroy()
        except Exception:
            pass
