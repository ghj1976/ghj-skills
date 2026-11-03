# -*- coding: utf-8 -*-
"""按种子重生成长段，挑“最像参考音”的一次（音色漂移的主力工具）。

为什么需要：同一 prompt cache、同一文本，换 seed 生成 4 次，基频能差 15–25Hz、
频谱亮度能差 500Hz。实测一条片子的 4 段拿到 262/251/250/239Hz，第一段听着
就是“换了个人”；换种子挑到 240/237/246/240 之后才和参考音一致。

和 regen_chunk.py 的区别：
  - 目标基频默认取参考音实测值（不再写死 243Hz）；
  - 候选全部落盘到 audio/cand/，方便事后人工对比；
  - 打分只看“像不像参考”：|f0-目标| + 频谱项；谱心默认不参与（它随文本内容
    变化很大，同一段不同文本能差 800Hz，拿它当目标容易挑到错误的音色）。

用法：
  python regen_chunk2.py                      # 4 段 × seed 20–23
  python regen_chunk2.py --chunks 0 --seeds 20,21,22,23,24
  python regen_chunk2.py --target-f0 239 --target-centroid 3300   # 谱心确实要管时才用

生成结果写 audio/chunk_<i>_raw.wav（未做 atempo），之后照常跑
clean_audio.py（可用 TEMPO_MAP 逐段调速）/ check_voice.py。
"""
import argparse
import sys

import librosa
import numpy as np
import soundfile as sf
import torch

from voxcpm import VoxCPM

import tts_chunks as base


def feats(y, sr):
    y = y.astype("float32")
    f = librosa.pyin(y[:min(len(y), sr * 20)], fmin=60, fmax=400,
                     sr=sr, frame_length=2048)[0]
    f = f[~np.isnan(f)]
    c = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512)) ** 2
    fr = librosa.fft_frequencies(sr=sr, n_fft=2048)
    m = (fr >= 80) & (fr <= 7500)
    s = S[m].mean(1)
    s = s / (s.sum() + 1e-12)
    b = np.floor(np.log2(fr[m]) * 3).astype(int)
    o = np.array([s[b == k].mean() for k in np.unique(b)])
    return (float(np.median(f)) if len(f) else float("nan")), c, o / o.sum()


def ltas_corr(a, b):
    n = min(len(a), len(b))
    return float(np.corrcoef(np.log(a[:n] + 1e-12), np.log(b[:n] + 1e-12))[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", default=",".join(str(i) for i in range(8)))
    ap.add_argument("--seeds", default="20,21,22,23")
    ap.add_argument("--target-f0", type=float, default=None,
                    help="目标基频；默认用参考音实测值")
    ap.add_argument("--target-centroid", type=float, default=None,
                    help="目标谱心（默认不参与打分：它随文本变化太大）")
    ap.add_argument("--no-save", action="store_true", help="不把候选落盘到 audio/cand/")
    a = ap.parse_args()

    ref, rsr = sf.read(base.PROMPT, dtype="float32")
    ref_f0, ref_c, ref_l = feats(ref, rsr)
    target_f0 = a.target_f0 if a.target_f0 is not None else ref_f0
    print(f"参考音 f0={ref_f0:.1f} centroid={ref_c:.0f}  目标 f0={target_f0:.1f}", flush=True)

    n_groups = len(base.GROUPS)
    chunks = [int(x) for x in a.chunks.split(",") if int(x) < n_groups]
    cand_dir = base.AUD / "cand"
    if not a.no_save:
        cand_dir.mkdir(exist_ok=True)

    model = VoxCPM.from_pretrained(base.MODEL, load_denoiser=False, optimize=False, device="cuda")
    cache = model.tts_model.build_prompt_cache(
        prompt_text=base.PROMPT_TEXT, prompt_wav_path=base.PROMPT,
        reference_wav_path=base.REFERENCE)
    print("model ready", flush=True)

    for gi in chunks:
        text = base.chunk_text(gi)
        cands = []
        for seed in [int(x) for x in a.seeds.split(",")]:
            torch.manual_seed(seed)
            o, _, _ = model.tts_model.generate_with_prompt_cache(
                target_text=text, prompt_cache=cache,
                cfg_value=base.CFG, inference_timesteps=base.STEPS)
            y = o.detach().float().cpu().numpy().squeeze()
            f, c, L = feats(y, 48000)
            lc = ltas_corr(L, ref_l)
            score = abs(f - target_f0) - 30 * (min(lc, 0.98) - 0.98)
            if a.target_centroid is not None:
                score += abs(c - a.target_centroid) / 120.0
            print(f"  chunk{gi} seed={seed:2d} f0={f:6.1f} centroid={c:5.0f} "
                  f"ltas={lc:.3f} score={score:6.2f}", flush=True)
            if not a.no_save:
                sf.write(str(cand_dir / f"chunk_{gi}_seed{seed}.wav"), y, 48000, subtype="PCM_16")
            cands.append((score, seed, y, f, c, lc))
        best = min(cands, key=lambda x: x[0])
        _, seed, y, f, c, lc = best
        out = base.AUD / f"chunk_{gi}_raw.wav"
        sf.write(str(out), y, 48000, subtype="PCM_16")
        print(f"chunk{gi}: seed={seed} f0={f:.1f} centroid={c:.0f} ltas={lc:.3f} -> {out.name}",
              flush=True)

    print("下一步：clean_audio.py（可配 TEMPO_MAP）→ check_voice.py --baseline <上一版/audio>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
