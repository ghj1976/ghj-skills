# -*- coding: utf-8 -*-
"""统一语速 + 清理配音长段：去掉段首咔哒、压缩过长停顿。

为什么需要：VoxCPM2 每段开头约 40ms 有一个 −11dB 的瞬态，随后还有 0.3–0.4s 静音；
build_audio_cont 按 −45dB 裁首尾静音时会把这段咔哒留下。段落拼接点正好落在
章节开头，于是每一节开头听起来都是“咔一下、停半拍、再正常说”。

处理只碰首尾和静音，不切任何语音；所有拼接点加 10ms 淡入淡出。

用法：
  python clean_audio.py                # 用 project_config.TEMPO（没有就用 1.0）
  python clean_audio.py --atempo 0.92 --max-pause 0.55
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from ffmpeg_path import ffmpeg

BASE = Path(__file__).resolve().parent
AUD = BASE / "audio"
SR = 48000

WIN = int(0.02 * SR)          # 20ms 分析窗
VOICED_DB = -38.0             # “在说话”的阈值
SUSTAIN = 10                  # 连续 10 窗（200ms）才算真的开口（段首咔哒只有 60–80ms）
EDGE_PAD_HEAD = 0.05
EDGE_PAD_TAIL = 0.12
FADE = int(0.01 * SR)


def db_of(y):
    n = len(y) // WIN
    rms = np.sqrt(np.mean(y[:n * WIN].reshape(n, WIN) ** 2, 1) + 1e-12)
    return 20 * np.log10(rms + 1e-12)


def speech_edges(y):
    db = db_of(y)
    voiced = db > VOICED_DB
    start = end = None
    for i in range(len(voiced) - SUSTAIN):
        if voiced[i:i + SUSTAIN].all():
            start = i
            break
    for i in range(len(voiced) - SUSTAIN, -1, -1):
        if voiced[i:i + SUSTAIN].all():
            end = i + SUSTAIN
            break
    if start is None or end is None:
        return 0, len(y)
    return (max(0, start * WIN - int(EDGE_PAD_HEAD * SR)),
            min(len(y), end * WIN + int(EDGE_PAD_TAIL * SR)))


def squash_pauses(y, max_pause, keep_pause):
    """把 >= max_pause 的静音压到 keep_pause，拼接点做 10ms 淡入淡出。

    阈值放到 −50dB，并合并间隔 <80ms 的静音段——否则长停顿会被一两个短促音节
    切碎，检测不到（实测有 1.0s 的停顿被 60ms 的气口分成两段，结果漏掉）。
    """
    db = db_of(y)
    quiet = db < -50.0
    raw = []
    i, n = 0, len(quiet)
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            raw.append([i * WIN, j * WIN])
            i = j
        else:
            i += 1
    spans = []
    for a, b in raw:
        if spans and a - spans[-1][1] <= int(0.08 * SR):
            spans[-1][1] = b
        else:
            spans.append([a, b])
    spans = [(a, b) for a, b in spans if (b - a) / SR >= max_pause]
    if not spans:
        return y, 0

    pieces, pos = [], 0
    keep_len = int(keep_pause * SR)
    for a, b in spans:
        pieces.append(y[pos:a])
        sil = y[a:b]
        mid = max(0, (len(sil) - keep_len) // 2)
        keep = sil[mid:mid + keep_len].copy()
        if len(keep) > 2 * FADE:
            keep[:FADE] *= np.linspace(0, 1, FADE)
            keep[-FADE:] *= np.linspace(1, 0, FADE)
        pieces.append(keep)
        pos = b
    pieces.append(y[pos:])
    return np.concatenate(pieces), len(spans)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--atempo", type=float, default=None, help="统一语速（不变调），默认取 project_config.TEMPO")
    ap.add_argument("--max-pause", type=float, default=0.55)
    ap.add_argument("--keep-pause", type=float, default=0.45)
    a = ap.parse_args()

    tempo = a.atempo
    if tempo is None:
        try:
            import project_config
            tempo = getattr(project_config, "TEMPO", 1.0)
        except ImportError:
            tempo = 1.0

    chunks = sorted(p for p in AUD.glob("chunk_*.wav") if not p.stem.endswith("_raw"))
    if not chunks:
        raise SystemExit("没有 audio/chunk_*.wav，先跑 tts_chunks.py")

    for p in chunks:
        raw = p.with_name(p.stem + "_raw.wav")
        src = raw if raw.exists() else p
        tmp = AUD / f"_{p.stem}_tempo.wav"
        if abs(tempo - 1.0) > 1e-3:
            subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                            "-filter:a", f"atempo={tempo}", "-ar", str(SR), "-ac", "1", str(tmp)],
                           check=True)
            work = tmp
        else:
            work = src
        y, sr = sf.read(str(work), dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        if sr != SR:
            raise SystemExit(f"{work} 采样率 {sr}，需要 {SR}")
        d0 = len(y) / sr
        a0, b0 = speech_edges(y)
        y = y[a0:b0]
        y, ncut = squash_pauses(y, a.max_pause, a.keep_pause)
        sf.write(str(p), y, sr, subtype="PCM_16")
        if work == tmp:
            tmp.unlink(missing_ok=True)
        print(f"{p.name}: {d0:.2f}s -> {len(y)/sr:.2f}s  裁首尾 {a0/sr:.2f}s  压缩停顿 {ncut} 处")


if __name__ == "__main__":
    main()
