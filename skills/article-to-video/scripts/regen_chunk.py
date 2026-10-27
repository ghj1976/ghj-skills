# -*- coding: utf-8 -*-
"""音色漂移时，按随机种子重生成某一段，挑基频/频谱最像参考的那次。

为什么需要：同一 prompt cache 生成多段，段间基频偶尔会拉开（实测 263/248/224Hz，
极差 39Hz，超过 30Hz 门限，听感就是“换了个人的一部分”）。换 seed 重生成偏差段即可。

用法：
  python regen_chunk.py 0,2 --seeds 20,21,22 [--target 243]
  生成结果写到 audio/chunk_<i>_raw.wav，之后照常跑 clean_audio.py / check_voice.py。
"""
import argparse
import sys

import librosa
import numpy as np
import soundfile as sf
import torch

from voxcpm import VoxCPM

import tts_chunks as base   # 复用 prompt/文本/GROUPS 的解析逻辑
import script_data


def f0_median(y, sr):
    f = librosa.pyin(y[:min(len(y), sr * 20)], fmin=60, fmax=400, sr=sr, frame_length=2048)[0]
    f = f[~np.isnan(f)]
    return float(np.median(f)) if len(f) else float("nan")


def ltas(y, sr):
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512)) ** 2
    fr = librosa.fft_frequencies(sr=sr, n_fft=2048)
    m = (fr >= 80) & (fr <= 7500)
    s = S[m].mean(1)
    s = s / (s.sum() + 1e-12)
    b = np.floor(np.log2(fr[m]) * 3).astype(int)
    o = np.array([s[b == k].mean() for k in np.unique(b)])
    return o / o.sum()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks", help="逗号分隔，如 0,2")
    ap.add_argument("--seeds", default="20,21,22,23")
    ap.add_argument("--target", type=float, default=243.0, help="目标基频（参考音的基频中位数）")
    a = ap.parse_args()

    ref, rsr = sf.read(base.PROMPT, dtype="float32")
    ref_l = ltas(ref, rsr)
    model = VoxCPM.from_pretrained(base.MODEL, load_denoiser=False, optimize=False, device="cuda")
    cache = model.tts_model.build_prompt_cache(
        prompt_text=base.PROMPT_TEXT, prompt_wav_path=base.PROMPT,
        reference_wav_path=base.REFERENCE)
    print("model ready", flush=True)

    for gi in [int(x) for x in a.chunks.split(",")]:
        text = base.chunk_text(gi)
        best = None
        for seed in [int(x) for x in a.seeds.split(",")]:
            torch.manual_seed(seed)
            o, _, _ = model.tts_model.generate_with_prompt_cache(
                target_text=text, prompt_cache=cache,
                cfg_value=base.CFG, inference_timesteps=base.STEPS)
            y = o.detach().float().cpu().numpy().squeeze()
            f = f0_median(y, 48000)
            c = float(np.corrcoef(np.log(ltas(y, 48000) + 1e-12), np.log(ref_l + 1e-12))[0, 1])
            score = abs(f - a.target) - 20 * (c - 0.98)
            print(f"  chunk{gi} seed={seed} f0={f:.1f} ltas={c:.3f} score={score:.2f}", flush=True)
            if best is None or score < best[0]:
                best = (score, seed, y, f, c)
        _, seed, y, f, c = best
        out = base.AUD / f"chunk_{gi}_raw.wav"
        sf.write(str(out), y, 48000, subtype="PCM_16")
        print(f"chunk{gi}: 选 seed={seed} f0={f:.1f} ltas={c:.3f} -> {out}")


if __name__ == "__main__":
    sys.exit(main())
