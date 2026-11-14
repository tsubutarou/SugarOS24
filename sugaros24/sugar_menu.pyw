# -*- coding: utf-8 -*-
"""
SugarOS メニュー（デスクトップの入口）
ダブルクリックすると、ランチャーの「メニュー画面」（大きなアイコンが並ぶ画面）が開く。
ランチャーが動いていれば、そのメニュー画面を開く。動いていなければ、ランチャーごと起動して開く。
このファイルを、ツールと同じフォルダに置いてね。
"""
import json
import os
import subprocess
import sys
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DOCK_PATH = os.path.join(APP_DIR, "mushiboshi_dock.json")              # ランチャーが2秒ごとに書くファイル
MENU_REQUEST = os.path.join(APP_DIR, "mushiboshi_menu_request.json")   # 「メニューを開いて」の合図


def launcher_running():
    """ランチャーが最近バーの位置を書いていれば、動いていると考える。"""
    try:
        with open(DOCK_PATH, encoding="utf-8") as f:
            info = json.load(f)
        return time.time() - float(info.get("ts", 0)) < 8
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def pythonw():
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def main():
    if launcher_running():
        with open(MENU_REQUEST, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time()}, f)
    else:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([pythonw(), os.path.join(APP_DIR, "mushiboshi_start.pyw"), "--menu"],
                         cwd=APP_DIR, creationflags=flags)


if __name__ == "__main__":
    main()
