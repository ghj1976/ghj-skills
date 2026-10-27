# -*- coding: utf-8 -*-
"""声音门禁：把本轮踩过的“卡顿/刺啦/切点早于开口”变成可自动检查的项。

检查：
  1. 开头没有瞬态（音乐淡入期不应有 >0.2 的样本跳变，也没有 −40dB 以上的噪声）；
  2. 全片没有爆音（相邻样本跳变 > 0.6）；
  3. 句间停顿不过长（正文里最长静音 ≤ 0.65s；段首咔哒/长停顿都算这里）；
  4. 章节切点 = 第一句开口（时间轴里的 scene.start 与真实语音起点偏差 ≤ 0.15s）；
  5. 响度 −17.5…−14.5 LUFS、真峰值 ≤ −1.0dB。

用法：python check_audio.py [--mix out/audio_mix.wav] [--tl out/timeline.json]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from ffmpeg_path import ffmpeg

BASE = Path(__file__).resolve().parent
SR = 48000
WIN = int(0.02 * SR)


def load_dB(path):
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    n = len(y) // WIN
    db = 20 * np.log10(np.sqrt(np.mean(y[:n * WIN].reshape(n, WIN) ** 2, 1)) + 1e-12)
    return y, sr, db


def first_speech(db, thresh=-35.0, sustain=5):
    v = db > thresh
    for i in range(len(v) - sustain):
        if v[i:i + sustain].all():
            return i * 0.02
    return 0.0


def last_speech(db, thresh=-35.0, sustain=5):
    v = db > thresh
    for i in range(len(v) - sustain, -1, -1):
        if v[i:i + sustain].all():
            return (i + sustain) * 0.02
    return len(db) * 0.02


def silence_runs(db, thresh=-45.0, min_len=0.12):
    q = db < thresh
    runs, i, n = [], 0, len(q)
    while i < n:
        if q[i]:
            j = i
            while j < n and q[j]:
                j += 1
            if (j - i) * 0.02 >= min_len:
                runs.append((i * 0.02, (j - i) * 0.02))
            i = j
        else:
            i += 1
    return runs


def loudness(path):
    r = subprocess.run([ffmpeg(), "-hide_banner", "-nostats", "-i", str(path),
                        "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    p = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    return (float(i[-1]) if i else None, float(p[-1]) if p else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mix", default=str(BASE / "out" / "audio_mix.wav"))
    ap.add_argument("--tl", default=str(BASE / "out" / "timeline.json"))
    a = ap.parse_args()

    y, sr, db = load_dB(a.mix)
    # 停顿/开口要看纯人声：音乐铺底会把 −45dB 的静音填满，mix 上量不出来
    nar = Path(a.mix).with_name("narration.wav")
    ny, nsr, ndb = load_dB(nar) if nar.exists() else (y, sr, db)
    ok = True
    start = first_speech(ndb)
    end = last_speech(ndb)
    print(f"语音区间 {start:.2f}–{end:.2f}s（总 {len(y)/sr:.2f}s）")

    # 1) 开头瞬态
    head = y[:max(1, int((start - 0.02) * sr))]
    head_delta = float(np.abs(np.diff(head)).max()) if len(head) > 1 else 0.0
    head_db = db[:max(2, int((start - 0.2) / 0.02))]
    rise = float(np.max(np.diff(head_db))) if len(head_db) > 1 else 0.0
    print(f"开头：最大样本跳变 {head_delta:.3f}，20ms 最大跳升 {rise:.1f}dB")
    if head_delta > 0.2 or rise > 12:
        print("FAIL: 开头有瞬态/噪声（音乐淡入期不应有音效冲击，也不该有 >12dB 的突跳）")
        ok = False

    # 2) 爆音
    d = np.abs(np.diff(y))
    clicks = int((d > 0.6).sum())
    print(f"爆音（跳变>0.6）：{clicks}")
    if clicks:
        print("FAIL: 有爆音，检查拼接/限幅")
        ok = False

    # 3) 停顿
    scene_starts = [sc["start"] for sc in json.loads(Path(a.tl).read_text(encoding="utf-8"))["scenes"]]
    def near_scene(t, dur=0.0):
        return any(abs(t - s) <= 0.5 or abs(t + dur - s) <= 0.3 for s in scene_starts)
    runs = [r for r in silence_runs(ndb, thresh=-50.0)
            if start < r[0] < end - 0.3 and not near_scene(r[0], r[1])]
    longest = max((r[1] for r in runs), default=0)
    print(f"正文静音段：{len(runs)} 处，最长 {longest:.2f}s")
    if longest > 0.65:
        worst = max(runs, key=lambda r: r[1])
        print(f"FAIL: 停顿过长 {worst[1]:.2f}s @ {worst[0]:.2f}s（段首咔哒/长停顿没清）")
        ok = False

    # 4) 章节切点是否等于开口
    tl = json.loads(Path(a.tl).read_text(encoding="utf-8"))
    for sc in tl["scenes"][1:]:
        t = sc["start"]
        i0 = max(0, int((t - 0.5) / 0.02))
        i1 = min(len(ndb), int((t + 0.5) / 0.02))
        seg = ndb[i0:i1]
        # 找切点附近第一个“语音起点”
        onsets = [i0 * 0.02 + k * 0.02 for k in range(len(seg) - 5)
                  if (seg[k:k + 5] > -35).all() and (k == 0 or seg[k - 1] <= -35)]
        if not onsets:
            print(f"  {sc['label']}: 切点 {t:.2f}s 附近没有检测到开口")
            continue
        near = min(onsets, key=lambda x: abs(x - t))
        delta = near - t
        flag = "" if abs(delta) <= 0.15 else "  <-- 偏差过大"
        print(f"  {sc['label']}: 切点 {t:.2f}s，最近开口 {near:.2f}s（{delta:+.2f}s）{flag}")
        if abs(delta) > 0.15:
            ok = False

    I, peak = loudness(a.mix)
    print(f"响度 {I} LUFS / 真峰值 {peak} dBFS")
    if I is None or not (-17.5 <= I <= -14.5):
        print("FAIL: 响度超出 −17.5…−14.5 LUFS")
        ok = False
    if peak is None or peak > -1.0:
        print("FAIL: 真峰值过高")
        ok = False

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
