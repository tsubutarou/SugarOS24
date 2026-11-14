# -*- coding: utf-8 -*-
"""
キャラ取り込み ver.1.1（CHARA IMPORT）
自分で描いた絵や、ほかのAIに描いてもらった絵を、エレクトロガールのキャラとして取り込む道具。SugarOS 24 の仲間。

使い方:
  1. 「絵を選ぶ」でポーズごとの絵を何枚でも選ぶ（ファイル名に idle / walk_1 / たち / ねる などが入っていれば自動で割り当てる）
     または「1枚にまとめた絵を選ぶ」で、何体も並んだ絵（スプライトシート）を選ぶと、1体ずつに切り分ける
  2. ポーズごとの「どの絵を使う？」を確かめる。大きさ・色の数・輪郭線もここで
  3. 名前をつけて「保存する」。エレクトロガールの右クリック →「だれといる？」から選べる

  絵は、どんな大きさ・背景でもOK。背景は自動で消して、64×64 のドット絵に縮める。

  「おへやの絵を取り込む…」では、キャラごとのおへや（昼・夜）の絵を取り込める。
  キャラが交代すると、おへやもその子の部屋になる。絵は 100×80 のドット絵に切り抜いて縮める。
  くわしくは electro_girl_data の「キャラの描き方.txt」を見てね。

必要なもの: pip install pillow
"""
import os
import re
import shutil
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageDraw, ImageTk

from mushiboshi_ui import log_errors, ui_font, hexc, mix, load_json, save_json

APP_VERSION = "1.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
T = 64                 # 1マス（エレクトロガールの絵の大きさ）
FEET_Y = 62            # 足の位置（マスの中）
ROOM_W, ROOM_H = 100, 80   # エレクトロガールのおへやの大きさ
ROOM_FLOOR = 77            # おへやの中で、キャラの足が来る高さ

# (ポーズ, 表示名, ファイル名で見分けることば)
POSES = [
    ("idle", "たち（必須）", ["idle", "stand", "たち", "立ち", "基本"]),
    ("blink", "まばたき", ["blink", "まばたき", "目とじ", "目閉じ"]),
    ("talk", "おしゃべり", ["talk", "しゃべ", "話", "口あけ"]),
    ("walk_0", "あるく 1", ["walk_0", "walk0", "walk_1", "walk1", "あるく1", "歩き1", "歩く1"]),
    ("walk_1", "あるく 2", ["walk_2", "walk2", "あるく2", "歩き2", "歩く2"]),
    ("walk_2", "あるく 3", ["walk_3", "walk3", "あるく3", "歩き3", "歩く3"]),
    ("happy", "ごきげん", ["happy", "ごきげん", "喜", "うれし", "嬉"]),
    ("eat", "おやつ", ["eat", "たべ", "食"]),
    ("drowsy", "ねむい", ["drowsy", "ねむ", "眠"]),
    ("sleep", "ねる", ["sleep", "ねる", "寝"]),
    ("game", "ゲーム", ["game", "ゲーム"]),
    ("groove_0", "ノる 1", ["groove_0", "groove0", "groove_1", "groove1", "dance1", "ノる1", "踊り1", "おどる1"]),
    ("groove_1", "ノる 2", ["groove_2", "groove2", "dance2", "ノる2", "踊り2", "おどる2"]),
]
SIZES = [("小", 40), ("中", 48), ("大", 56), ("特大", 62)]
COLOR_COUNTS = [("16色", 16), ("32色", 32), ("64色", 64), ("へらさない", 0)]
NONE = "（なし）"
INK = (40, 30, 56)
BG = (204, 190, 228)   # プレビューの壁の色（おへやと同じ）


def find_data_dir():
    """electro_girl_data を探す（エレクトロガールと同じ探し方）。"""
    cand = os.path.join(APP_DIR, "electro_girl_data")
    if os.path.isdir(cand):
        return cand
    for root, dirs, files in os.walk(APP_DIR):
        if os.path.basename(root) == "electro_girl_data" and os.path.isdir(os.path.join(root, "chara")):
            return root
    os.makedirs(os.path.join(cand, "chara"), exist_ok=True)
    return cand


# ---------- 絵の下ごしらえ ----------

def shrink(im, max_side):
    """大きすぎる絵は、作業しやすい大きさに縮める（最後は 64×64 なので、細かすぎても意味がない）。"""
    w, h = im.size
    k = max_side / max(w, h)
    return im.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS) if k < 1 else im


def remove_background(im, tol=60):
    """ふちから続いている「背景の色」を透明にする。すでに背景が透明な絵は、そのまま。"""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    if sum(c[3] < 128 for c in corners) >= 2:   # もう透けている
        return im
    bg = max(set(c[:3] for c in corners), key=lambda c: sum(1 for k in corners if k[:3] == c))

    def near(c):
        return abs(c[0] - bg[0]) + abs(c[1] - bg[1]) + abs(c[2] - bg[2]) <= tol
    seen = bytearray(w * h)
    stack = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    while stack:
        x, y = stack.pop()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        c = px[x, y]
        if c[3] < 128 or near(c):
            px[x, y] = (0, 0, 0, 0)
            if x > 0:
                stack.append((x - 1, y))
            if x < w - 1:
                stack.append((x + 1, y))
            if y > 0:
                stack.append((x, y - 1))
            if y < h - 1:
                stack.append((x, y + 1))
    remove_enclosed(im, bg)
    return im


def remove_enclosed(im, bg, tol=12, min_share=0.002):
    """キャラに囲まれたすきま（足のあいだ・腕と体のあいだ）に残った背景の色も消す。
    背景とほぼ同じ色で、ある程度の広さがあるところだけ（目の光のような小さな白は残す）。"""
    w, h = im.size
    px = im.load()

    def same(c):
        return c[3] >= 128 and abs(c[0] - bg[0]) + abs(c[1] - bg[1]) + abs(c[2] - bg[2]) <= tol
    seen = bytearray(w * h)
    for sy in range(h):
        for sx in range(w):
            if seen[sy * w + sx] or not same(px[sx, sy]):
                continue
            region, stack = [], [(sx, sy)]
            seen[sy * w + sx] = 1
            while stack:
                x, y = stack.pop()
                region.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] and same(px[nx, ny]):
                        seen[ny * w + nx] = 1
                        stack.append((nx, ny))
            if len(region) >= w * h * min_share:
                for x, y in region:
                    px[x, y] = (0, 0, 0, 0)


def find_figures(im):
    """1枚にまとめた絵から、1体ずつの絵を切り出す。読む順（上の段の左から）に並べる。"""
    w, h = im.size
    step = 3
    sw, sh = w // step + 1, h // step + 1
    a = im.getchannel("A").load()
    mask = [[False] * sw for _ in range(sh)]
    for y in range(0, h, step):
        for x in range(0, w, step):
            if a[x, y] >= 128:
                mask[y // step][x // step] = True
    seen = [[False] * sw for _ in range(sh)]
    boxes = []
    for sy in range(sh):
        for sx in range(sw):
            if not mask[sy][sx] or seen[sy][sx]:
                continue
            stack, cells = [(sx, sy)], 0
            x0, y0, x1, y1 = sx, sy, sx, sy
            seen[sy][sx] = True
            while stack:
                cx, cy = stack.pop()
                cells += 1
                x0, y0, x1, y1 = min(x0, cx), min(y0, cy), max(x1, cx), max(y1, cy)
                for dx in (-2, -1, 0, 1, 2):   # 少しはなれた部分（髪の毛先など）も、同じ1体にまとめる
                    for dy in (-2, -1, 0, 1, 2):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < sw and 0 <= ny < sh and mask[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
            boxes.append((cells, (x0 * step, y0 * step, min(w, (x1 + 1) * step), min(h, (y1 + 1) * step))))
    if not boxes:
        return []
    biggest = max(c for c, _ in boxes)
    boxes = [b for c, b in boxes if c >= biggest * 0.15]   # 小さなごみは捨てる
    avg_h = sum(b[3] - b[1] for b in boxes) / len(boxes)
    rows = []
    for b in sorted(boxes, key=lambda b: (b[1] + b[3]) / 2):
        cy = (b[1] + b[3]) / 2
        for row in rows:
            if abs(row[0] - cy) < avg_h * 0.5:
                row[1].append(b)
                break
        else:
            rows.append([cy, [b]])
    ordered = [b for _, row in rows for b in sorted(row, key=lambda b: b[0])]
    return [drop_small_parts(im.crop(b)) for b in ordered]


def drop_small_parts(im, share=0.06):
    """本体から離れた小さな飾り（Zzz や ♪ など）を消す。エレクトロガールが自分で出すので、二重にならないように。
    細い線でつながっているだけの飾りも外せるよう、いったん1ドットやせさせてから、かたまりを数える。"""
    w, h = im.size
    a = im.getchannel("A").load()
    solid = [[a[x, y] >= 128 for x in range(w)] for y in range(h)]
    core = [[solid[y][x] and all(0 <= x + dx < w and 0 <= y + dy < h and solid[y + dy][x + dx]
                                 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
             for x in range(w)] for y in range(h)]
    label = [[-1] * w for _ in range(h)]
    sizes = []
    for sy in range(h):
        for sx in range(w):
            if not core[sy][sx] or label[sy][sx] >= 0:
                continue
            n = len(sizes)
            stack, count = [(sx, sy)], 0
            label[sy][sx] = n
            while stack:
                x, y = stack.pop()
                count += 1
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and core[ny][nx] and label[ny][nx] < 0:
                        label[ny][nx] = n
                        stack.append((nx, ny))
            sizes.append(count)
    if len(sizes) < 2:
        return im
    keep = {i for i, c in enumerate(sizes) if c >= max(sizes) * share}
    px = im.load()
    for y in range(h):   # 残すかたまりの近く（2ドット以内）にない点は消す
        for x in range(w):
            if not solid[y][x]:
                continue
            near = any(0 <= x + dx < w and 0 <= y + dy < h and label[y + dy][x + dx] in keep
                       for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2))
            if not near:
                px[x, y] = (0, 0, 0, 0)
    box = im.getbbox()
    return im.crop(box) if box else im


def to_tile(src, height, colors, outline, ref_h=None):
    """下ごしらえした絵 → 64×64 のドット絵（足はマスの下、横はまんなか）。
    ref_h：この高さを height に合わせる（同じシートの絵は同じ縮め方にして、ポーズで大きさが変わらないように）。"""
    box = src.getbbox()
    if not box:
        return Image.new("RGBA", (T, T), (0, 0, 0, 0))
    im = src.crop(box)
    w, h = im.size
    k = min(height / (ref_h or h), (T - 2) / w, (T - 2) / h)
    nw, nh = max(1, round(w * k)), max(1, round(h * k))
    small_already = w <= nw * 1.5   # もともとドット絵なら、にじませずにそのまま
    im = im.resize((nw, nh), Image.NEAREST if small_already else Image.BOX)
    r, g, b, a = im.split()
    a = a.point(lambda v: 255 if v >= 128 else 0)    # ふちのにじみを、くっきりに
    rgb = Image.merge("RGB", (r, g, b))
    if colors:
        rgb = rgb.quantize(colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
    im = Image.merge("RGBA", (*rgb.split(), a))
    tile = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    tile.paste(im, ((T - nw) // 2, FEET_Y - nh + 1), im)
    if outline:   # まわりに、うすく暗いフチ
        px = tile.load()
        add = []
        for y in range(T):
            for x in range(T):
                if px[x, y][3]:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < T and 0 <= ny < T and px[nx, ny][3]:
                        add.append((x, y, px[nx, ny][:3]))
                        break
        for x, y, c in add:
            px[x, y] = mix(c, INK, 0.7) + (255,)
    return tile


# ---------- 「たち」の絵から、ほかのポーズを作る ----------

def _lum(c):
    return c[0] * 0.3 + c[1] * 0.59 + c[2] * 0.11


def find_face(tile):
    """目（まつげの濃い線）と口の場所を探す。見つからなければ None。
    頭のあたり（輪郭線から離れたところ）で、左右それぞれいちばん暗いところを目とみなす。"""
    box = tile.getbbox()
    if not box:
        return None
    px = tile.load()
    x0, top, x1, bottom = box
    cx = (x0 + x1) / 2
    head_bottom = top + int((bottom - top) * 0.42)

    def inner(x, y):   # まわり2ドットが全部うまっている（＝フチの線ではない）
        return all(0 <= x + dx < T and 0 <= y + dy < T and px[x + dx, y + dy][3]
                   for dx in (-2, 0, 2) for dy in (-2, 0, 2))
    band = [(x, y) for y in range(top + int((bottom - top) * 0.12), head_bottom)
            for x in range(int(cx) - 11, int(cx) + 12) if 0 <= x < T and px[x, y][3] and inner(x, y)]
    eyes = []
    for side in (-1, 1):
        mine = [p for p in band if (p[0] - cx) * side > 1]
        strong = [p for p in mine if _lum(px[p]) < 60]   # 黒いまつげがあれば、それ
        if len(strong) >= 2:
            lash = min(y for _, y in strong)
            row = [x for x, y in strong if y <= lash + 1]
            pts = [(min(row) - 1, lash), (max(row) + 1, lash)]   # まつげの両はしを1ドットずつ広げる
        else:                                             # なければ、いちばん暗い6点
            pts = sorted(mine, key=lambda p: _lum(px[p]))[:6]
        if len(pts) < 2:
            return None
        lash = min(y for _, y in pts)
        ex0, ex1 = min(x for x, _ in pts), max(x for x, _ in pts)
        while ex1 - ex0 < 3:   # 目の幅は4ドット以上に
            ex0, ex1 = ex0 - (ex1 - ex0) % 2, ex1 + 1 - (ex1 - ex0) % 2
        eyes.append((ex0, ex1, lash))
    eyes.sort()
    mouth_y = max(e[2] for e in eyes) + 6
    return {"eyes": eyes, "mouth": (round(cx), mouth_y), "top": top, "bottom": bottom, "cx": cx}


def _skin(tile, eyes):
    """ほっぺのあたりの色（まぶたを閉じた絵にぬる色）。"""
    from collections import Counter
    px = tile.load()
    cols = Counter()
    for ex0, ex1, lash in eyes:
        for y in range(lash + 5, lash + 8):
            for x in range(ex0, ex1 + 1):
                if 0 <= y < T and px[x, y][3] and _lum(px[x, y]) > 120:
                    cols[px[x, y][:3]] += 1
    return cols.most_common(1)[0][0] if cols else (236, 200, 190)


def _shift(tile, dy):
    out = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    out.alpha_composite(tile, (0, dy)) if dy >= 0 else out.alpha_composite(tile.crop((0, -dy, T, T)), (0, 0))
    return out


def make_auto_poses(idle):
    """「たち」の絵から、まばたき・おしゃべり・ねむい・ごきげん・ねる・あるく・ノるを作る。
    目と口が見つからないときは、あるく・ノるだけ作る。"""
    face = find_face(idle)
    out = {}
    lash_c = (40, 28, 44)
    if face:
        skin = _skin(idle, face["eyes"])

        def eyes_variant(kind):
            t = idle.copy()
            d = ImageDraw.Draw(t)
            for ex0, ex1, lash in face["eyes"]:
                lid = {"closed": 4, "half": 2, "happy": 4}[kind]
                d.rectangle([ex0, lash + 1, ex1, lash + lid], fill=skin)    # まぶたをおろす
                if kind == "closed":     # ‿ の形に閉じた目
                    d.line([(ex0, lash + 2), (ex1, lash + 2)], fill=lash_c)
                    d.point((ex0, lash + 1), fill=lash_c)
                    d.point((ex1, lash + 1), fill=lash_c)
                elif kind == "half":     # 半分ねむい：まつげを2ドット下に
                    d.rectangle([ex0, lash, ex1, lash], fill=skin)
                    d.line([(ex0, lash + 2), (ex1, lash + 2)], fill=lash_c)
                else:                    # ^ の形のごきげんな目
                    mid = (ex0 + ex1) / 2
                    d.line([(ex0, lash + 3), (mid, lash + 1), (ex1, lash + 3)], fill=lash_c)
            return t
        out["blink"] = eyes_variant("closed")
        out["drowsy"] = eyes_variant("half")
        out["sleep"] = eyes_variant("closed")
        out["happy"] = _shift(eyes_variant("happy"), -1)
        talk = idle.copy()
        mx, my = face["mouth"]
        ImageDraw.Draw(talk).rectangle([mx - 1, my, mx, my + 1], fill=(150, 56, 80))   # 口をあける
        out["talk"] = talk
    # あるく：片足ずつ1ドット上げて、体も少しはずむ
    box = idle.getbbox()
    if box:
        legs_y = box[1] + int((box[3] - box[1]) * 0.78)
        cx = (box[0] + box[2]) // 2
        for name, side in (("walk_0", 0), ("walk_2", 1)):
            t = idle.copy()
            region = (cx, legs_y, box[2], T) if side else (box[0], legs_y, cx, T)
            leg = idle.crop(region)
            t.paste((0, 0, 0, 0), region)
            t.alpha_composite(leg, (region[0], region[1] - 1))
            out[name] = t
        out["walk_1"] = idle.copy()
        out["groove_0"] = out.get("happy", _shift(idle, -1))
        out["groove_1"] = idle.copy()
    return out


def save_chara(data_dir, name, credit, tiles, source_paths=(), colorway=None, cid_hint=None):
    """キャラを electro_girl_data/chara/<id> に保存する。同じ名前のフォルダがあれば、上書きせず別の名前で。
    tiles：{ポーズ: 64×64 の絵}（"idle" は必須）。保存したフォルダを返す。"""
    chara_dir = os.path.join(data_dir, "chara")
    cid = safe_id(cid_hint or name, chara_dir)
    base = os.path.join(chara_dir, cid)
    os.makedirs(os.path.join(base, "source"), exist_ok=True)
    poses = [p for p, _, _ in POSES if p in tiles]
    cols = 8
    atlas = Image.new("RGBA", (T * cols, T * (len(poses) // cols + 1)), (0, 0, 0, 0))
    slots = {}
    for i, pose in enumerate(poses):
        col, row = i % cols, i // cols
        atlas.paste(tiles[pose], (col * T, row * T))
        slots["body_" + pose] = {"col": col, "row": row}
    atlas.save(os.path.join(base, "atlas.png"))
    save_json(os.path.join(base, "atlas_map.json"),
              {"asset_spec": "full_pose_v1", "tile_size": [T, T], "atlas_tiles": [cols, atlas.height // T], "slots": slots})
    top = tiles["idle"].getbbox() or (0, 0, T, T)
    save_json(os.path.join(base, "meta.json"),
              {"id": cid, "name": name, "credit": credit, "full_pose": True,
               "snack_hand": [44, int(top[1] + (FEET_Y - top[1]) * 0.55)], "colorway": colorway,
               "imported": time.strftime("%Y-%m-%d %H:%M:%S"),
               "notes": "キャラ取り込みで作ったキャラ。ポーズごとの1枚絵（body_<ポーズ>）だけで描く。"
                        "source フォルダに、取り込んだもとの絵のコピーがある。"})
    for path in source_paths:   # もとの絵は、コピーをとっておく（あとで取り込み直せるように）
        if path and os.path.exists(path):
            try:
                shutil.copy2(path, os.path.join(base, "source", os.path.basename(path)))
            except OSError:
                pass
    return base


def prepare_room(im, valign="middle", colors=64):
    """おへやの絵 → 100×80 のドット絵。横5：縦4 に切り抜いてから縮める。valign：縦長の絵のどこを残すか。"""
    im = im.convert("RGB")
    w, h = im.size
    if w / h > ROOM_W / ROOM_H:   # 横に長い：左右を切る
        nw = round(h * ROOM_W / ROOM_H)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:                          # 縦に長い：上下を切る
        nh = round(w * ROOM_H / ROOM_W)
        y0 = {"top": 0, "middle": (h - nh) // 2, "bottom": h - nh}[valign]
        im = im.crop((0, y0, w, y0 + nh))
    im = im.resize((ROOM_W, ROOM_H), Image.BOX)
    if colors:
        im = im.quantize(colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
    return im


def list_charas(data_dir):
    """取り込んだキャラ [(名前, フォルダ)]"""
    root = os.path.join(data_dir, "chara")
    out = []
    try:
        for k in sorted(os.listdir(root)):
            if os.path.isfile(os.path.join(root, k, "atlas.png")):
                meta = load_json(os.path.join(root, k, "meta.json"), {})
                out.append((meta.get("name", k), os.path.join(root, k)))
    except OSError:
        pass
    return out


def save_room(chara_path, day, night=None):
    """おへやの絵をキャラのフォルダに保存。前の絵は消さずに room_old_日時.png に名前を変えて残す。"""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for name, im in (("room.png", day), ("room_night.png", night)):
        path = os.path.join(chara_path, name)
        if os.path.exists(path):
            os.replace(path, os.path.join(chara_path, f"{name[:-4]}_old_{stamp}.png"))
        if im is not None:
            im.save(path)


class RoomDialog:
    """おへやの絵を取り込む小窓。"""

    def __init__(self, master, data_dir):
        self.data_dir = data_dir
        self.charas = list_charas(data_dir)
        self.src = {"day": None, "night": None}   # もとの絵
        self.win = tk.Toplevel(master)
        self.win.title("おへやの絵を取り込む")
        self.win.configure(bg="#f4eefa")
        f, fb = ui_font(self.win, 13), ui_font(self.win, 13, bold=True)
        if not self.charas:
            tk.Label(self.win, text="先にキャラを取り込んでね", font=f, bg="#f4eefa").pack(padx=20, pady=20)
            return
        row = tk.Frame(self.win, bg="#f4eefa")
        row.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(row, text="だれのおへや？", font=fb, bg="#f4eefa").pack(side="left")
        self.chara_var = tk.StringVar(value=self.charas[0][0])
        menu = tk.OptionMenu(row, self.chara_var, *[n for n, _ in self.charas], command=lambda _: self.redraw())
        menu.config(font=f)
        menu.pack(side="left", padx=6)
        row2 = tk.Frame(self.win, bg="#f4eefa")
        row2.pack(fill="x", padx=10, pady=4)
        tk.Button(row2, text="昼の絵を選ぶ", font=f, command=lambda: self.pick("day")).pack(side="left")
        tk.Button(row2, text="夜の絵を選ぶ（なくてもOK）", font=f,
                  command=lambda: self.pick("night")).pack(side="left", padx=6)
        tk.Button(row2, text="夜の絵をはずす", font=f, command=self.drop_night).pack(side="left")
        row3 = tk.Frame(self.win, bg="#f4eefa")
        row3.pack(fill="x", padx=10, pady=4)
        tk.Label(row3, text="縦長の絵は", font=fb, bg="#f4eefa").pack(side="left")
        self.valign = tk.StringVar(value="bottom")
        for n, v in (("上を残す", "top"), ("まんなか", "middle"), ("下（床）を残す", "bottom")):
            tk.Radiobutton(row3, text=n, value=v, variable=self.valign, font=f, bg="#f4eefa",
                           command=self.redraw).pack(side="left")
        tk.Label(row3, text="　色の数", font=fb, bg="#f4eefa").pack(side="left")
        self.colors = tk.IntVar(value=64)
        for n, v in (("32色", 32), ("64色", 64), ("へらさない", 0)):
            tk.Radiobutton(row3, text=n, value=v, variable=self.colors, font=f, bg="#f4eefa",
                           command=self.redraw).pack(side="left")
        prev = tk.Frame(self.win, bg="#f4eefa")
        prev.pack(padx=10, pady=4)
        self.day_lb = tk.Label(prev, bg="#f4eefa")
        self.day_lb.grid(row=0, column=0, padx=4)
        self.night_lb = tk.Label(prev, bg="#f4eefa")
        self.night_lb.grid(row=0, column=1, padx=4)
        tk.Label(prev, text="昼", font=f, bg="#f4eefa").grid(row=1, column=0)
        tk.Label(prev, text="夜（絵がなければ、自動で暗くするよ）", font=f, bg="#f4eefa").grid(row=1, column=1)
        tk.Button(self.win, text="このおへやにする", font=fb, command=self.save).pack(pady=8)
        self.status = tk.Label(self.win, text="AIや自分で描いたおへやの絵を選んでね。キャラが立ったところを見て確かめられるよ",
                               font=f, bg="#f4eefa")
        self.status.pack(padx=10, pady=(0, 10))
        self.redraw()

    def chara_path(self):
        return dict(self.charas)[self.chara_var.get()]

    def pick(self, which):
        path = filedialog.askopenfilename(parent=self.win, title="おへやの絵を選ぶ",
                                          filetypes=[("画像", "*.png *.jpg *.jpeg *.webp *.gif *.bmp")])
        if not path:
            return
        try:
            with Image.open(path) as im:
                self.src[which] = im.convert("RGB")
        except (OSError, ValueError) as ex:
            self.status.config(text=f"読めなかったよ：{ex}")
            return
        self.redraw()

    def drop_night(self):
        self.src["night"] = None
        self.redraw()

    def rooms(self):
        day = prepare_room(self.src["day"], self.valign.get(), self.colors.get()) if self.src["day"] else None
        night = prepare_room(self.src["night"], self.valign.get(), self.colors.get()) if self.src["night"] else None
        return day, night

    def redraw(self):
        day, night = self.rooms()
        try:
            with Image.open(os.path.join(self.chara_path(), "atlas.png")) as atlas:
                idle = atlas.convert("RGBA").crop((0, 0, T, T))   # 先頭のマス＝たち
        except OSError:
            idle = None
        if day is None:
            day = Image.new("RGB", (ROOM_W, ROOM_H), BG)
        if night is None:   # エレクトロガールと同じ暗くし方
            night = Image.blend(day, Image.new("RGB", day.size, (30, 26, 70)), 0.38)
        self.photos = []
        for im, lb in ((day, self.day_lb), (night, self.night_lb)):
            im = im.convert("RGBA")
            if idle is not None:   # キャラを、おへやのまんなかに立たせてみる
                im.alpha_composite(idle, (ROOM_W // 2 - T // 2, ROOM_FLOOR - FEET_Y))
            ph = ImageTk.PhotoImage(im.resize((ROOM_W * 3, ROOM_H * 3), Image.NEAREST))
            self.photos.append(ph)
            lb.config(image=ph)

    def save(self):
        day, night = self.rooms()
        if day is None:
            messagebox.showinfo("おへやの絵", "昼の絵を選んでね", parent=self.win)
            return
        save_room(self.chara_path(), day, night)
        name = self.chara_var.get()
        self.status.config(text=f"「{name}」のおへやにしたよ。エレクトロガールでその子にすると、おへやが変わるよ")
        messagebox.showinfo("おへやの絵", f"「{name}」のおへやにしたよ！\nエレクトロガールを開きなおすと反映されるよ",
                            parent=self.win)


def guess_pose(filename, taken):
    name = os.path.splitext(os.path.basename(filename))[0].lower()
    for pose, _, words in POSES:
        if pose not in taken and any(wd.lower() in name for wd in words):
            return pose
    return None


def safe_id(name, chara_dir):
    base = re.sub(r"[^0-9a-zA-Z_]+", "", name.lower()) or time.strftime("chara_%Y%m%d")   # 日本語の名前なら日付で
    cid, n = base, 2
    while os.path.exists(os.path.join(chara_dir, cid)):   # 同じ名前のキャラは上書きせず、別の名前で
        cid = f"{base}_{n}"
        n += 1
    return cid


# ---------- 画面 ----------

class Importer:
    def __init__(self):
        self.data_dir = find_data_dir()
        self.sources = []           # [(名前, 下ごしらえした絵, もとのファイル, なかま)]  なかま＝同じ縮め方にする絵の組
        self.batch = 0
        self.assign = {}            # ポーズ → sources の番号
        self.tiles = {}
        self.photos = {}
        self.frame_i = 0

        self.root = tk.Tk()
        log_errors(self.root, "chara_import_error.txt")
        self.root.title(f"キャラ取り込み ver.{APP_VERSION}")
        self.root.configure(bg="#f4eefa")
        f = ui_font(self.root, 13)
        fb = ui_font(self.root, 13, bold=True)
        top = tk.Frame(self.root, bg="#f4eefa")
        top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Button(top, text="絵を選ぶ（何枚でも）", font=f, command=self.pick_images).pack(side="left")
        tk.Button(top, text="1枚にまとめた絵を選ぶ", font=f, command=self.pick_sheet).pack(side="left", padx=6)
        tk.Button(top, text="ぜんぶ外す", font=f, command=self.clear).pack(side="left")
        tk.Button(top, text="おへやの絵を取り込む…", font=f,
                  command=lambda: RoomDialog(self.root, self.data_dir)).pack(side="right")

        opts = tk.Frame(self.root, bg="#f4eefa")
        opts.pack(fill="x", padx=10, pady=4)
        self.size_var = tk.IntVar(value=48)
        self.color_var = tk.IntVar(value=32)
        self.outline_var = tk.BooleanVar(value=True)
        self.bg_var = tk.BooleanVar(value=True)
        self.auto_var = tk.BooleanVar(value=True)
        tk.Label(opts, text="大きさ", font=fb, bg="#f4eefa").pack(side="left")
        for n, v in SIZES:
            tk.Radiobutton(opts, text=n, value=v, variable=self.size_var, font=f, bg="#f4eefa",
                           command=self.rebuild).pack(side="left")
        tk.Label(opts, text="　色の数", font=fb, bg="#f4eefa").pack(side="left")
        for n, v in COLOR_COUNTS:
            tk.Radiobutton(opts, text=n, value=v, variable=self.color_var, font=f, bg="#f4eefa",
                           command=self.rebuild).pack(side="left")
        tk.Checkbutton(opts, text="輪郭線", variable=self.outline_var, font=f, bg="#f4eefa",
                       command=self.rebuild).pack(side="left", padx=(12, 0))
        tk.Checkbutton(opts, text="背景を消す（次に選ぶ絵から）", variable=self.bg_var, font=f,
                       bg="#f4eefa").pack(side="left", padx=(8, 0))
        tk.Checkbutton(opts, text="ないポーズは「たち」から自動で作る", variable=self.auto_var, font=f,
                       bg="#f4eefa", command=self.rebuild).pack(side="left", padx=(8, 0))

        body = tk.Frame(self.root, bg="#f4eefa")
        body.pack(fill="both", padx=10, pady=4)
        grid = tk.Frame(body, bg="#f4eefa")
        grid.pack(side="left")
        self.cells = {}
        for i, (pose, label, _) in enumerate(POSES):
            cell = tk.Frame(grid, bg="#ffffff", bd=1, relief="solid")
            cell.grid(row=i // 5, column=i % 5, padx=3, pady=3)
            tk.Label(cell, text=label, font=fb, bg="#ffffff").pack()
            img = tk.Label(cell, bg=hexc(BG), width=128, height=128)
            img.pack(padx=4)
            var = tk.StringVar(value=NONE)
            menu = tk.OptionMenu(cell, var, NONE)
            menu.config(font=f, width=12)
            menu.pack(pady=2)
            self.cells[pose] = (img, var, menu)
        side = tk.Frame(body, bg="#f4eefa")
        side.pack(side="left", fill="y", padx=(12, 0))
        tk.Label(side, text="うごきの確認", font=fb, bg="#f4eefa").pack(anchor="w")
        self.preview = tk.Label(side, bg=hexc(BG), width=T * 4, height=T * 4)
        self.preview.pack(pady=4)
        tk.Label(side, text="キャラの名前", font=fb, bg="#f4eefa").pack(anchor="w", pady=(10, 0))
        self.name_var = tk.StringVar(value="")
        tk.Entry(side, textvariable=self.name_var, font=f, width=20).pack(anchor="w")
        tk.Label(side, text="描いた人（クレジット）", font=fb, bg="#f4eefa").pack(anchor="w", pady=(6, 0))
        self.credit_var = tk.StringVar(value="")
        tk.Entry(side, textvariable=self.credit_var, font=f, width=20).pack(anchor="w")
        tk.Button(side, text="保存する", font=fb, command=self.save).pack(anchor="w", pady=12)
        self.status = tk.Label(self.root, text="まずは「絵を選ぶ」から。ファイル名で、ポーズを自動で割り当てるよ",
                               font=f, bg="#f4eefa", anchor="w", justify="left")
        self.status.pack(fill="x", padx=10, pady=(0, 10))
        self.rebuild()
        self.root.after(250, self.animate)

    # --- 絵を読む ---
    def load_one(self, path, max_side=320):
        im = Image.open(path)
        im.load()
        im = shrink(im.convert("RGBA"), max_side)
        return remove_background(im) if self.bg_var.get() else im

    def pick_images(self):
        paths = filedialog.askopenfilenames(parent=self.root, title="ポーズごとの絵を選ぶ（何枚でも）",
                                            filetypes=[("画像", "*.png *.jpg *.jpeg *.webp *.gif *.bmp")])
        if not paths:
            return
        self.say("絵を読みこんでいるよ…")
        taken = set(self.assign)
        self.batch += 1
        for path in paths:
            try:
                with Image.open(path) as probe:   # 同じ大きさの絵どうしは、同じ縮め方に
                    group = (self.batch, probe.size)
                im = self.load_one(path)
            except (OSError, ValueError) as ex:
                self.say(f"{os.path.basename(path)} が読めなかったよ：{ex}")
                continue
            self.sources.append((os.path.basename(path), im, path, group))
            pose = guess_pose(path, taken) or next((p for p, _, _ in POSES if p not in taken), None)
            if pose:
                self.assign[pose] = len(self.sources) - 1
                taken.add(pose)
        self.after_load(f"{len(paths)}枚 読みこんだよ。ポーズの割り当てを確かめてね")

    def pick_sheet(self):
        path = filedialog.askopenfilename(parent=self.root, title="何体も並んだ1枚の絵を選ぶ",
                                          filetypes=[("画像", "*.png *.jpg *.jpeg *.webp *.gif *.bmp")])
        if not path:
            return
        self.say("切り分けているよ…（大きな絵だと少しかかるよ）")
        self.root.update()
        try:
            sheet = self.load_one(path, max_side=900)
        except (OSError, ValueError) as ex:
            self.say(f"読めなかったよ：{ex}")
            return
        figures = find_figures(sheet)
        if not figures:
            self.say("キャラが見つからなかったよ。背景が1色の絵だと切り分けやすいよ")
            return
        # 「たち」がまだなら、シートは「まばたき」から順に入れて、「たち」には足をそろえた歩き（あるく 2）を使う
        no_idle = "idle" not in self.assign
        free = [p for p, _, _ in POSES if p not in self.assign and p != "idle"]
        base = os.path.splitext(os.path.basename(path))[0]
        self.batch += 1
        for i, im in enumerate(figures):
            self.sources.append((f"{base} #{i + 1}", im, path if i == 0 else None, (self.batch, "sheet")))
            if i < len(free):
                self.assign[free[i]] = len(self.sources) - 1
        if no_idle:
            self.assign["idle"] = self.assign.get("walk_1", len(self.sources) - len(figures))
        self.after_load(f"{len(figures)}体に切り分けたよ（上の段の左から、まばたき・おしゃべり…の順に割り当て。"
                        "「たち」は あるく 2 の絵）。ちがっていたら選び直してね")

    def clear(self):
        self.sources, self.assign = [], {}
        self.after_load("ぜんぶ外したよ")

    def after_load(self, msg):
        names = [NONE] + [f"{i + 1}. {n}" for i, (n, *_rest) in enumerate(self.sources)]
        for pose, (img, var, menu) in self.cells.items():
            m = menu["menu"]
            m.delete(0, "end")
            for k, label in enumerate(names):
                m.add_command(label=label, command=lambda p=pose, k=k: self.set_assign(p, k - 1))
            i = self.assign.get(pose)
            var.set(names[i + 1] if i is not None else NONE)
        self.rebuild()
        self.say(msg)

    def set_assign(self, pose, i):
        if i < 0:
            self.assign.pop(pose, None)
        else:
            self.assign[pose] = i
        self.after_load("割り当てを変えたよ")

    # --- 絵を作る ---
    def rebuild(self):
        h, colors, outline = self.size_var.get(), self.color_var.get(), self.outline_var.get()
        self.tiles = {}
        refs = self.group_heights()
        for pose in self.cells:
            i = self.assign.get(pose)
            if i is not None and i < len(self.sources):
                self.tiles[pose] = to_tile(self.sources[i][1], h, colors, outline, refs.get(self.sources[i][3]))
        auto = set()
        if self.auto_var.get() and "idle" in self.tiles:   # ないポーズは「たち」から作る
            for pose, tile in make_auto_poses(self.tiles["idle"]).items():
                if pose not in self.tiles:
                    self.tiles[pose] = tile
                    auto.add(pose)
        for pose, (img, var, menu) in self.cells.items():
            if pose in auto:
                var.set("（自動で作った）")
            shown = self.tiles.get(pose)
            if shown is None and pose != "idle" and "idle" in self.tiles:   # ないポーズは「たち」で代わり（うすく）
                shown = self.tiles["idle"].copy()
                shown.putalpha(shown.getchannel("A").point(lambda v: v // 3))
            canvas = Image.new("RGBA", (T, T), BG + (255,))
            if shown is not None:
                canvas.alpha_composite(shown)
            self.photos[pose] = ImageTk.PhotoImage(canvas.resize((T * 2, T * 2), Image.NEAREST))
            img.config(image=self.photos[pose], width=T * 2, height=T * 2)

    def group_heights(self):
        """なかまごとの「基準の高さ」：その組の「たち」の絵の高さ。なければ、組の中のまんなかの高さ。"""
        heights = {}
        for i, (_, im, _, group) in enumerate(self.sources):
            box = im.getbbox()
            if box:
                heights.setdefault(group, []).append((i, box[3] - box[1]))
        refs = {}
        idle = self.assign.get("idle")
        for group, items in heights.items():
            hs = sorted(hgt for _, hgt in items)
            refs[group] = next((hgt for i, hgt in items if i == idle), hs[len(hs) // 2])
        return refs

    def animate(self):
        """プレビュー：あるく → まばたき → ごきげん をくり返す。"""
        t = self.tiles
        seq = [p for p in ("walk_0", "walk_1", "walk_2", "walk_1") if p in t] or ["idle"]
        seq = seq * 2 + ["idle", "blink" if "blink" in t else "idle", "idle", "happy" if "happy" in t else "idle"]
        pose = seq[self.frame_i % len(seq)]
        self.frame_i += 1
        canvas = Image.new("RGBA", (T, T), BG + (255,))
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, FEET_Y + 1, T - 1, T - 1], fill=(222, 178, 170))
        if pose in t:
            canvas.alpha_composite(t[pose])
        self.prev_photo = ImageTk.PhotoImage(canvas.resize((T * 4, T * 4), Image.NEAREST))
        self.preview.config(image=self.prev_photo, width=T * 4, height=T * 4)
        self.root.after(220, self.animate)

    # --- 保存 ---
    def save(self):
        if "idle" not in self.tiles:
            messagebox.showinfo("キャラ取り込み", "「たち」の絵は必ず入れてね（ほかのポーズの代わりにも使うよ）", parent=self.root)
            return
        name = self.name_var.get().strip() or "あたらしい子"
        base = save_chara(self.data_dir, name, self.credit_var.get().strip(), self.tiles,
                          [path for _, _, path, _ in self.sources])
        self.say(f"「{name}」を保存したよ（{base}）。エレクトロガールの右クリック →「だれといる？」から選んでね")
        messagebox.showinfo("キャラ取り込み", f"「{name}」を保存したよ！\nエレクトロガールの右クリック →「だれといる？」から選べるよ",
                            parent=self.root)

    def say(self, text):
        self.status.config(text=text)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        Importer().run()
    except Exception:
        import traceback
        with open(os.path.join(APP_DIR, "chara_import_error.txt"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
