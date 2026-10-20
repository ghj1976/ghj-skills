# -*- coding: utf-8 -*-
"""Locate ffmpeg/ffprobe without relying on %USERNAME% (mojibake under WSL)."""
import glob
import os
import shutil
from pathlib import Path


def ffmpeg():
    env = os.environ.get("FFMPEG")
    if env and Path(env).exists():
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    patterns = [
        r"C:\Users\*\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg*\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ]
    for pat in patterns:
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return "ffmpeg"


def ffprobe():
    env = os.environ.get("FFPROBE")
    if env and Path(env).exists():
        return env
    exe = ffmpeg()
    if exe != "ffmpeg":
        p = Path(exe).with_name("ffprobe.exe")
        if p.exists():
            return str(p)
    found = shutil.which("ffprobe")
    return found or "ffprobe"
