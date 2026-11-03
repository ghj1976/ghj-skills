# -*- coding: utf-8 -*-
"""量一量配音到底像不像选定的音色，避免“听不出来但观众觉得不对”。

检查五件事：
  1. 每段基频中位数是否落在参考音 ±8% 的区域内（默认；不是 ±18%——实测
     262Hz vs 参考 239Hz 只差 10%，但听感已经是“换了个人的开头”）；
  2. 段间基频极差 ≤18Hz（默认；超过就是章与章之间换人）；
  3. 每段与参考音的长时平均频谱（LTAS）相关 ≥0.90；
  4. 每段与参考音的 MFCC 说话人相似度 ≥0.985（同一个人，不看音区）；
  5. 语速：字/秒（含停顿）落在 4.0–7.5；同时打印静音占比。

另外两件事（不达标只是警告，FAIL 仍由上面五条决定）：
  - 项目 TEMPO / TEMPO_MAP 里任何一段 <0.80：减速超过 20% 会明显改变音色，
    听起来“闷、拖、不像”；优先重生成更慢的段落，而不是继续慢放。
  - 传了 `--baseline <目录>`（上一版项目的 audio/）：打印与上一版 chunk_N.wav 的
    基频差与 MFCC 相似度。**MFCC ≥0.99 是硬门槛**；Δf0 只做参考（≤15Hz 为宜）——
    不同文稿的语调本来就会差 10–20Hz，用 MFCC 判“是不是同一个人”更稳。

用法：
  python check_voice.py                        # 默认参考 audio/prompt_ref.wav → voices/<VOICE>/
  python check_voice.py --baseline ../../work/soml/audio
  python check_voice.py --f0-tol 0.10 --spread 22     # 放宽（不推荐）
"""
import argparse
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


def f0_median(path, sec=20):
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    f = librosa.pyin(y[:min(len(y), sr * sec)], fmin=60, fmax=400, sr=sr, frame_length=2048)[0]
    f = f[~np.isnan(f)]
    return float(np.median(f)) if len(f) else float("nan"), len(y) / sr


def mfcc_emb(path):
    """20 维 MFCC 的均值/标准差 + delta 标准差，说话人层面够用（无需额外模型）。"""
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y = librosa.resample(y.astype("float32"), orig_sr=sr, target_sr=16000)
    m = librosa.feature.mfcc(y=y, sr=16000, n_mfcc=20)
    return np.concatenate([m.mean(1), m.std(1), librosa.feature.delta(m).std(1)])


def cos(a, b):
    a = a - a.mean()
    b = b - b.mean()
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def tempo_warnings():
    try:
        import project_config as pc
    except ImportError:
        return []
    out = []
    t = getattr(pc, "TEMPO", None)
    if t is not None and t < 0.80:
        out.append(f"TEMPO={t}（减速超过 20%，音色会变闷）")
    for k, v in (getattr(pc, "TEMPO_MAP", None) or {}).items():
        if v < 0.80:
            out.append(f"TEMPO_MAP[{k}]={v}（减速超过 20%，音色会变闷）")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref", nargs="?", help="参考音频（默认 audio/prompt_ref.wav → voices/<VOICE>/prompt_ref.wav）")
    ap.add_argument("--baseline", default=None, help="上一版项目的 audio/ 目录，用来比“跟上一版像不像”")
    ap.add_argument("--f0-tol", type=float, default=0.08, help="基频允许偏离参考的百分比（默认 0.08）")
    ap.add_argument("--spread", type=float, default=18.0, help="段间基频极差上限 Hz（默认 18）")
    ap.add_argument("--mfcc-min", type=float, default=0.985, help="与参考的 MFCC 相似度下限（默认 0.985）")
    a = ap.parse_args()

    ref = Path(a.ref) if a.ref else None
    if ref is None:
        local = AUD / "prompt_ref.wav"
        ref = local if local.exists() else BASE / "voices" / VOICE / "prompt_ref.wav"
    if not ref.exists():
        raise SystemExit(f"找不到参考音频：{ref}")
    ref_l = ltas(ref)
    ref_f0, _ = f0_median(ref)
    ref_m = mfcc_emb(ref)
    print(f"参考音 {ref}  f0={ref_f0:.1f}Hz")

    beats = script_data.flatten()
    chunks = sorted(AUD.glob("chunk_*.wav"))
    chunks = [c for c in chunks if not c.stem.endswith("_raw")]
    chunks = [c for c in chunks if not c.stem.startswith("_")]
    if not chunks:
        raise SystemExit("没有 audio/chunk_*.wav，先跑 tts_chunks.py")

    base_dir = Path(a.baseline) if a.baseline else None
    if base_dir and not base_dir.exists():
        raise SystemExit(f"--baseline 目录不存在：{base_dir}")

    rows, f0s, ok = [], [], True
    lo, hi = ref_f0 * (1 - a.f0_tol), ref_f0 * (1 + a.f0_tol)
    per = 2  # 每段 2 个场景，与 build_audio_cont 的 GROUPS 一致
    for i, c in enumerate(chunks):
        f0, dur = f0_median(c)
        n = sum(len(b["text"]) for b in beats if i * per <= b["scene"] <= i * per + per - 1)
        cps = n / dur if dur else 0
        r = corr(ltas(c), ref_l)
        sim = cos(ref_m, mfcc_emb(c))
        f0s.append(f0)

        bad, warn = [], []
        if not (4.0 <= cps <= 7.5):
            bad.append("语速")
        if r < 0.90:
            bad.append("音色")
        if sim < a.mfcc_min:
            bad.append("说话人")
        if not (lo <= f0 <= hi):
            bad.append("音区")

        y, _sr = sf.read(str(c), dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        w = max(1, int(_sr * 0.02))
        nwin = len(y) // w
        db = 20 * np.log10(np.sqrt(np.mean(y[:nwin * w].reshape(nwin, w) ** 2, 1) + 1e-12))
        sil = float((db < -45).mean())

        line = (f"chunk {i}: {dur:6.2f}s  cps={cps:4.2f}  silence={sil:.0%}  "
                f"f0={f0:6.1f}Hz  LTAS={r:.3f}  MFCC={sim:.3f}")
        if base_dir:
            b = base_dir / c.name
            if b.exists():
                bf0, _ = f0_median(b)
                bsim = cos(mfcc_emb(b), mfcc_emb(c))
                line += f"  | 上一版 f0={bf0:6.1f}Hz Δ={f0 - bf0:+5.1f}Hz 相似={bsim:.3f}"
                if bsim < 0.99:
                    bad.append("跟上一版不像")
                elif abs(f0 - bf0) > 15.0:
                    warn.append(f"chunk{i} 与上一版 f0 差 {f0 - bf0:+.1f}Hz（>15Hz，听一下是否换了语气）")
        line += f"  << FAIL: {'/'.join(bad)}" if bad else ("  << WARN" if warn else "  ok")
        print(line)
        for w in warn:
            print(f"      WARN {w}")
        if bad:
            ok = False
        rows.append((c.name, dur, cps, f0, r, sim))

    spread = max(f0s) - min(f0s)
    print(f"参考音区 {lo:.0f}–{hi:.0f}Hz（±{a.f0_tol:.0%}）；段间基频极差 {spread:.1f}Hz（阈值 ≤{a.spread:.0f}）")
    if spread > a.spread:
        ok = False
    for w in tempo_warnings():
        print(f"WARN  {w}：优先 regen_chunk2.py 换种子/重写句子，别继续 atempo")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
