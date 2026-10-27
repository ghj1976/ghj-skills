# -*- coding: utf-8 -*-
"""量一量配音到底像不像选定的音色，避免“听不出来但观众觉得不对”。

检查三件事：
  1. 每段基频中位数是否落在参考音 ±18% 的区域内（同性别、同音区），段间极差 ≤30Hz；
  2. 每段与参考音的长时平均频谱（LTAS）相关系数 ≥ 0.90；
  3. 语速：字/秒（含停顿）落在 4.0–7.5；同时打印停顿占比，方便判断是不是被“压停顿”压太快。

不硬套“85–115Hz”：那是低沉男声的经验值，q1 这类女声正常就在 225–251Hz。

用法：python check_voice.py [参考音频]（默认 audio/prompt_ref.wav，其次 voices/<VOICE>/prompt_ref.wav）
      配合 script_data.py 统计字/秒；任一段不达标则退出码 1。
"""
import json
import os
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

import script_data

BASE = Path(__file__).resolve().parent
AUD = BASE / "audio"
VOICE = os.environ.get("VOICE", "q1")


def ltas(path):
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    m = (freqs >= 80) & (freqs <= 7500)
    spec = S[m].mean(1)
    spec = spec / (spec.sum() + 1e-12)
    bins = np.floor(np.log2(freqs[m]) * 3).astype(int)
    out = np.array([spec[bins == b].mean() for b in np.unique(bins)])
    return out / out.sum()


def corr(a, b):
    n = min(len(a), len(b))
    return float(np.corrcoef(np.log(a[:n] + 1e-12), np.log(b[:n] + 1e-12))[0, 1])


def f0_median(path):
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    f = librosa.pyin(y[:min(len(y), sr * 20)], fmin=60, fmax=400, sr=sr, frame_length=2048)[0]
    f = f[~np.isnan(f)]
    return float(np.median(f)) if len(f) else float("nan"), len(y) / sr


def main():
    ref = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if ref is None:
        local = AUD / "prompt_ref.wav"
        ref = local if local.exists() else BASE / "voices" / VOICE / "prompt_ref.wav"
    if not ref.exists():
        raise SystemExit(f"找不到参考音频：{ref}")
    ref_l = ltas(ref)
    ref_f0, _ = f0_median(ref)
    print(f"参考音 {ref}  f0={ref_f0:.1f}Hz")

    beats = script_data.flatten()
    chunks = sorted(AUD.glob("chunk_*.wav"))
    chunks = [c for c in chunks if not c.stem.endswith("_raw")]
    if not chunks:
        raise SystemExit("没有 audio/chunk_*.wav，先跑 tts_chunks.py")

    rows, f0s, ok = [], [], True
    lo, hi = ref_f0 * 0.82, ref_f0 * 1.18
    per = 2  # 每段 2 个场景，与 build_audio_cont 的 GROUPS 一致
    for i, c in enumerate(chunks):
        f0, dur = f0_median(c)
        n = sum(len(b["text"]) for b in beats if i * per <= b["scene"] <= i * per + per - 1)
        cps = n / dur if dur else 0
        r = corr(ltas(c), ref_l)
        f0s.append(f0)
        bad = []
        if not (4.0 <= cps <= 7.5):
            bad.append("语速")
        if r < 0.90:
            bad.append("音色")
        if not (lo <= f0 <= hi):
            bad.append("音区")
        y, _sr = sf.read(str(c), dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        w = max(1, int(_sr * 0.02))
        nwin = len(y) // w
        db = 20 * np.log10(np.sqrt(np.mean(y[:nwin * w].reshape(nwin, w) ** 2, 1) + 1e-12))
        sil = float((db < -45).mean())
        print(f"chunk {i}: {dur:6.2f}s  cps={cps:4.2f}  silence={sil:.0%}  f0={f0:6.1f}Hz  LTAS={r:.3f}"
              + (f"  << FAIL: {'/'.join(bad)}" if bad else "  ok"))
        if bad:
            ok = False
        rows.append((c.name, dur, cps, f0, r))

    spread = max(f0s) - min(f0s)
    print(f"参考音区 {lo:.0f}–{hi:.0f}Hz；段间基频极差 {spread:.1f}Hz（阈值 ≤30）")
    if spread > 30:
        ok = False
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
