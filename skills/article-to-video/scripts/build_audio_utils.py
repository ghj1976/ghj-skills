# -*- coding: utf-8 -*-
"""视频流程的垫乐、音效、混音、SRT 与解说稿导出。

相对项目目录：out/ 需已存在；FFMPEG 可用环境变量覆盖。
按当前故事修改 IMPACT_IDS / RISER_BEFORE。
"""
import os
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

from ffmpeg_path import ffmpeg as _ffmpeg

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"
OUT.mkdir(exist_ok=True)
SR = 48000
FFMPEG = _ffmpeg()
# 需要 impact 音效的 beat；按项目修改
IMPACT_IDS = ["00_01", "02_03", "04_01", "06_03"]
RISER_BEFORE = "06_03"


def music(duration):
    """Am–F–C–G 慢铺底 + 52Hz 轻脉冲，RMS ≈ -40 dBFS。"""
    n = int(duration * SR)
    chords = [[110.0, 164.81, 220.0, 261.63], [87.31, 130.81, 174.61, 220.0],
              [130.81, 196.0, 261.63, 329.63], [98.0, 146.83, 196.0, 246.94]]
    seg = 8.0
    left = np.zeros(n, dtype=np.float32)
    right = np.zeros(n, dtype=np.float32)
    for k in range(int(np.ceil(duration / seg))):
        ch = chords[k % 4]
        a = k * seg
        b = min(duration, a + seg + 1.0)
        s0, s1 = int(a * SR), int(b * SR)
        tt = np.arange(s1 - s0, dtype=np.float32) / SR
        env = np.minimum(1, tt / 2.0) * np.minimum(1, np.maximum(0, (b - (a + tt)) / 2.0))
        for j, f in enumerate(ch):
            amp = 0.14 / (j + 2)
            for det, side in ((-0.1, left), (0.1, right)):
                ph = 2 * np.pi * (f + det) * tt + j * 0.6
                side[s0:s1] += (amp * env * (np.sin(ph) + 0.22 * np.sin(2 * ph))).astype(np.float32)
    for k in range(int(duration / 2)):
        s = int(k * 2 * SR)
        ln = int(0.28 * SR)
        tt = np.arange(ln) / SR
        pulse = (0.10 * np.exp(-tt * 11) * np.sin(2 * np.pi * 52 * tt)).astype(np.float32)
        left[s:s + ln] += pulse
        right[s:s + ln] += pulse
    fade = np.ones(n, dtype=np.float32)
    fi, fo = int(2.5 * SR), int(4 * SR)
    fade[:fi] = np.linspace(0, 1, fi) ** 2
    fade[-fo:] = np.linspace(1, 0, fo) ** 2
    left *= fade
    right *= fade
    stereo = np.stack([left, right], 1)
    rms = float(np.sqrt(np.mean(stereo ** 2))) or 1.0
    stereo *= 0.010 / rms
    sf.write(str(OUT / "music.wav"), stereo.astype(np.float32), SR, subtype="PCM_16")


def whoosh(dur=0.5):
    n = int(dur * SR)
    rng = np.random.default_rng(11)
    x = rng.standard_normal(n).astype(np.float32)
    sos = butter(2, [400, 3200], btype="band", fs=SR, output="sos")
    x = sosfilt(sos, x).astype(np.float32)
    t = np.arange(n) / SR
    e = np.minimum(1, t / 0.12) * np.exp(-np.maximum(0, t - 0.1) * 7)
    return (x * e * 0.5).astype(np.float32)


def impact():
    n = int(0.55 * SR)
    t = np.arange(n) / SR
    x = (0.8 * np.sin(2 * np.pi * 58 * t) * np.exp(-t * 8)
         + 0.25 * np.sin(2 * np.pi * 120 * t) * np.exp(-t * 16)).astype(np.float32)
    rng = np.random.default_rng(5)
    x[:int(0.03 * SR)] += rng.standard_normal(int(0.03 * SR)).astype(np.float32) * 0.15
    return x


def tick():
    n = int(0.04 * SR)
    t = np.arange(n) / SR
    return (0.6 * np.sin(2 * np.pi * 1600 * t) * np.exp(-t * 90)).astype(np.float32)


def riser(dur=1.6):
    n = int(dur * SR)
    rng = np.random.default_rng(9)
    x = rng.standard_normal(n).astype(np.float32)
    sos = butter(2, 1200, btype="high", fs=SR, output="sos")
    x = sosfilt(sos, x).astype(np.float32)
    t = np.arange(n) / SR
    return (x * (t / dur) ** 2 * 0.35).astype(np.float32)


def sfx_track(tl, impacts=None, riser_before=None):
    """按时间轴放置 whoosh、impact、tick 和 riser。"""
    impacts = IMPACT_IDS if impacts is None else impacts
    riser_before = RISER_BEFORE if riser_before is None else riser_before
    n = int(tl["duration"] * SR)
    buf = np.zeros(n, dtype=np.float32)

    def add(sig, at, gain):
        s = int(at * SR)
        if s < 0:
            sig = sig[-s:]
            s = 0
        e = min(n, s + len(sig))
        if e > s:
            buf[s:e] += sig[:e - s] * gain

    # 开头不再放 impact / whoosh：噪声冲击叠在音乐淡入上会像“刺啦”一声
    # （镜头 1.0 秒进第一句，留白比音效干净）
    for sc in tl["scenes"][1:]:
        add(whoosh(), sc["start"] - 0.18, 0.45)
    for bid in impacts:
        b = next((x for x in tl["beats"] if x["id"] == bid), None)
        if b:
            add(impact(), b["start"] - 0.05, 0.8)
    data = next((x for x in tl["beats"] if x["layout"] == "data"), None)
    if data:
        for k in range(8):
            add(tick(), data["start"] + 0.3 + k * 0.22, 0.25)
    end = next((x for x in tl["beats"] if x["id"] == riser_before), None)
    if end:
        add(riser(), end["start"] - 1.5, 0.5)
    peak = float(np.max(np.abs(buf))) or 1.0
    if peak > 0.30:
        buf *= 0.30 / peak
    sf.write(str(OUT / "sfx.wav"), np.stack([buf, buf], 1), SR, subtype="PCM_16")


def mix():
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(OUT / "narration.wav"), "-i", str(OUT / "music.wav"), "-i", str(OUT / "sfx.wav"),
           "-filter_complex",
           "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[n];"
           "[n][1:a][2:a]amix=inputs=3:duration=longest:normalize=0,"
           "alimiter=limit=0.95:level=false[out]",
           "-map", "[out]", "-ar", str(SR), "-ac", "2", str(OUT / "audio_mix.wav")]
    subprocess.run(cmd, check=True)


def write_srt(tl):
    def ts(x):
        h = int(x // 3600); m = int(x % 3600 // 60); s = int(x % 60); ms = int((x % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, b in enumerate(tl["beats"], 1):
        lines += [str(i), f"{ts(b['start'])} --> {ts(b['end'])}", b["sub"], ""]
    (OUT / "subtitles.srt").write_text("\n".join(lines), encoding="utf-8")


def write_script(tl):
    lines = ["# 解说稿（含时间码）", ""]
    for sc in tl["scenes"]:
        lines.append(f"## {sc['label']}")
        for b in tl["beats"]:
            if b["scene"] == sc["index"]:
                lines.append(f"- `{int(b['start']//60):02d}:{int(b['start']%60):02d}` {b['text']}")
        lines.append("")
    (OUT / "解说稿.md").write_text("\n".join(lines), encoding="utf-8")
