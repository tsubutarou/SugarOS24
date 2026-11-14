# -*- coding: utf-8 -*-
"""
SugarOS 24（フォトフレーム・シアター・ことのは・レコード・水槽・温室・一方その頃・のぞき窓・エレクトロガール・マインスイーパ・ソリティア・シュガーフォール・お天気・カレンダー・ランチャー・メニュー）の、かわいいアイコン付きショートカットをデスクトップに作る。
このファイルを、ツールとアイコン（.ico）と同じフォルダに置いてダブルクリックしてね。
"""
import base64
import os
import subprocess
import tkinter as tk
from tkinter import messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = [
    ("資料フォトフレーム", "photo_frame.pyw", "photo_frame.ico"),
    ("資料シアター", "video_theater.pyw", "video_theater.ico"),
    ("資料ことのは", "kotonoha.pyw", "kotonoha.ico"),
    ("資料レコード", "record_player.pyw", "record_player.ico"),
    ("ドット水槽", "aquarium.pyw", "aquarium.ico"),
    ("ドット温室", "greenhouse.pyw", "greenhouse.ico"),
    ("一方その頃", "meanwhile.pyw", "meanwhile.ico"),
    ("のぞき窓", "nozokimado.pyw", "nozokimado.ico"),
    ("エレクトロガール", "electro_girl.pyw", "electro_girl.ico"),
    ("ドットマインスイーパ", "minesweeper.pyw", "minesweeper.ico"),
    ("ドットソリティア", "solitaire.pyw", "solitaire.ico"),
    ("ドットシュガーフォール", "sugarfall.pyw", "sugarfall.ico"),
    ("ドットお天気", "weather.pyw", "weather.ico"),
    ("ドットカレンダー", "dot_calendar.pyw", "calendar.ico"),
    ("SugarOS 24", "mushiboshi_start.pyw", "mushiboshi_start.ico"),
    ("SugarOS メニュー", "sugar_menu.pyw", "sugar_menu.ico"),
]


def ps_quote(text):
    return "'" + text.replace("'", "''") + "'"


def main():
    root = tk.Tk()
    root.withdraw()
    lines = ["$desk = [Environment]::GetFolderPath('Desktop')",
             "$sh = New-Object -ComObject WScript.Shell"]
    made, missing = [], []
    for name, script, icon in TOOLS:
        sp, ip = os.path.join(HERE, script), os.path.join(HERE, icon)
        if not os.path.exists(sp):
            missing.append(script)
            continue
        lines += [
            f"$s = $sh.CreateShortcut((Join-Path $desk {ps_quote(name + '.lnk')}))",
            f"$s.TargetPath = {ps_quote(sp)}",
            f"$s.WorkingDirectory = {ps_quote(HERE)}",
            f"$s.Description = {ps_quote(name)}",
        ]
        if os.path.exists(ip):
            lines.append(f"$s.IconLocation = {ps_quote(ip + ',0')}")
        lines.append("$s.Save()")
        made.append(name)
    if not made:
        messagebox.showerror("ショートカット作成", "同じフォルダにツールが見つからなかったよ。")
        return
    encoded = base64.b64encode("\n".join(lines).encode("utf-16-le")).decode("ascii")
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-EncodedCommand", encoded],
                            capture_output=True, text=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode != 0:
        messagebox.showerror("ショートカット作成", "うまく作れなかったよ。\n\n" + (result.stderr or "")[-600:])
        return
    msg = "デスクトップにショートカットを作ったよ！\n\n" + "\n".join("・" + m for m in made)
    if missing:
        msg += "\n\n見つからなかったファイル：\n" + "\n".join("・" + m for m in missing)
    messagebox.showinfo("ショートカット作成", msg)


if __name__ == "__main__":
    main()
