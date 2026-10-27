# -*- coding: utf-8 -*-
"""从任意视频/音频里抽一段音色，做成 VoxCPM2 可用的 prompt + reference。

为什么需要这步：直接拿带背景音乐的原片当参考，克隆会连底噪和 BGM 一起学走。
流程：抽音轨 → 按词边界切片 → ZIP-Enhancer 去伴奏 → 峰值归一 → 写 voice.json。

用法（在项目目录里跑）：
  python make_voice_ref.py --src ../../02/q1.mp4 --prompt 8.66,14.32 --ref 8.66,22.72 --transcribe
  python make_voice_ref.py --src ../../02/q1.mp4 --prompt 8.66,14.32 --ref 8.66,22.72 --text "目前项目已经完全开源，……"

  --transcribe  先打印词级时间戳，方便挑切片边界（不切在字中间）
  --text        不给就自动对 prompt 片段做一次 ASR 当草稿；**务必人工核对**
                （实测短片段容易把“电视”听成“电源”，错字会影响 prompt 对齐）
  --name        音色名，默认取源文件名；输出到 voices/<name>/
  --outdir      直接指定输出目录（默认 voices/<name>）
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch
import torchaudio

from ffmpeg_path import ffmpeg

BASE = Path(__file__).resolve().parent


def _load(path, **kw):
    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return torch.from_numpy(y.T.copy()), sr


def _save(path, wav, sr, **kw):
    a = wav.detach().cpu().numpy()
    sf.write(str(path), a.T if a.ndim > 1 else a, int(sr))


# torchaudio 2.11 走 torchcodec，缺 shared FFmpeg DLL 会直接崩；换成 soundfile
torchaudio.load = _load
torchaudio.save = _save


def extract(src, dst):
    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(src), "-vn", "-ac", "1", "-ar", "48000", str(dst)], check=True)


def cut(src, a, b, dst):
    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(a), "-to", str(b), "-i", str(src),
                    "-af", "highpass=f=70", "-ar", "48000", "-ac", "1", str(dst)], check=True)


def words_of(path):
    from faster_whisper import WhisperModel
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y16 = librosa.resample(y, orig_sr=sr, target_sr=16000)
    m = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(y16, language="zh", word_timestamps=True, beam_size=5, vad_filter=False)
    out = []
    for s in segs:
        for w in (s.words or []):
            if w.word.strip():
                out.append({"w": w.word, "s": round(float(w.start), 2), "e": round(float(w.end), 2)})
    return out


def f0_median(y, sr):
    f = librosa.pyin(y[:min(len(y), sr * 20)], fmin=60, fmax=400, sr=sr, frame_length=2048)[0]
    f = f[~np.isnan(f)]
    return round(float(np.median(f)), 1) if len(f) else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="源视频/音频")
    ap.add_argument("--name", default=None, help="音色名，默认取源文件名")
    ap.add_argument("--outdir", default=None, help="输出目录，默认 voices/<name>")
    ap.add_argument("--prompt", required=True, help="prompt 片段，秒范围如 8.66,14.32（4–8 秒）")
    ap.add_argument("--ref", default=None, help="reference 片段，默认与 prompt 相同")
    ap.add_argument("--text", default=None, help="prompt 的准确文本；不给就自动 ASR")
    ap.add_argument("--transcribe", action="store_true", help="打印词级时间戳后退出")
    a = ap.parse_args()

    src = Path(a.src).resolve()
    name = a.name or src.stem
    outdir = Path(a.outdir) if a.outdir else BASE / "voices" / name
    outdir.mkdir(parents=True, exist_ok=True)
    work = outdir / f"_{name}_full.wav"   # 抽出来的整轨，处理完就删
    extract(src, work)

    if a.transcribe:
        try:
            for w in words_of(work):
                print(f"{w['s']:6.2f} {w['e']:6.2f} {w['w']}")
        finally:
            work.unlink(missing_ok=True)
        print("\n挑边界后重跑：--prompt a,b --ref a,c（边界落在词的起止处）")
        return

    pa, pb = [float(x) for x in a.prompt.split(",")]
    ra, rb = [float(x) for x in (a.ref or a.prompt).split(",")]
    prompt = outdir / "prompt_ref.wav"
    reference = outdir / "reference_ref.wav"

    from voxcpm.zipenhancer import ZipEnhancer
    z = ZipEnhancer()
    for (x, y), dst in (((pa, pb), prompt), ((ra, rb), reference)):
        tmp = outdir / f"_{dst.stem}_raw.wav"
        cut(work, x, y, tmp)
        z.enhance(str(tmp), output_path=str(dst), normalize_loudness=False)
        w, sr = sf.read(str(dst), dtype="float32")
        w = w / (np.max(np.abs(w)) + 1e-9) * 0.9
        sf.write(str(dst), w, sr, subtype="PCM_16")
        tmp.unlink(missing_ok=True)
        print(f"{dst.name}: {x}–{y}s, {len(w)/sr:.2f}s, {sr}Hz, f0={f0_median(w, sr)}Hz")

    text = a.text
    if not text:
        seg = outdir / "_prompt_asr.wav"
        cut(work, pa, pb, seg)
        text = "".join(w["w"] for w in words_of(seg))
        seg.unlink(missing_ok=True)
        print("!! PROMPT_TEXT 是自动转写的草稿，请对照音频核对后改进 voice.json")
    print("PROMPT_TEXT =", text)

    y, sr = sf.read(str(prompt), dtype="float32")
    natural_cps = round(len(text) / (len(y) / sr), 2)
    # 目标 5.9 字/秒（参考节奏），只在源音偏快时降速，不快于 1.0
    tempo = max(0.85, min(1.0, round(5.9 / natural_cps, 2))) if natural_cps > 0 else 1.0
    meta = {
        "id": name,
        "label": f"{name}（来自 {src.name}）",
        "prompt_text": text,
        "prompt_wav": "prompt_ref.wav",
        "reference_wav": "reference_ref.wav",
        "source": str(src),
        "prompt_span_s": [pa, pb],
        "reference_span_s": [ra, rb],
        "preprocess": "highpass 70Hz → VoxCPM2 ZIP-Enhancer 去伴奏 → 峰值归一 0.9",
        "sample_rate": sr,
        "prompt_duration_s": round(len(y) / sr, 2),
        "f0_median_hz": f0_median(y, sr),
        "natural_cps": natural_cps,
        "atempo": tempo,
        "cps_after_tempo": round(natural_cps * tempo, 2),
        "notes": "自动生成；如音色/语速不合适，改 prompt 片段或 audio/prompt_ref.wav 后重跑 tts_chunks.py",
    }
    (outdir / "voice.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    work.unlink(missing_ok=True)
    print(f"写入 {outdir/'voice.json'}；脚手架时把 {outdir.name}/ 放到项目 voices/ 下即可用 VOICE={name}")


if __name__ == "__main__":
    sys.exit(main())
