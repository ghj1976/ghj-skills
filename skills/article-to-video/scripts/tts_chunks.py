# -*- coding: utf-8 -*-
"""用 VoxCPM2 生成 2–4 个长段，并统一音色与语速。

为什么用长段：逐句克隆会让说话人漂移（实测各 beat 基频 71–154Hz）；
同一 prompt/reference 的 4 个长段稳定在 98–103Hz（男声）或 225–251Hz（q1 女声）。

音色来源（按优先级）：
  1. 环境变量 PROMPT_WAV / REFERENCE_WAV / PROMPT_TEXT
  2. 项目里的 audio/prompt_ref.wav（自定义音色，可配 audio/reference_ref.wav）
  3. 技能自带的 voices/<VOICE>/（默认 VOICE=q1，见 voices/q1/voice.json）

语速：voice.json 里的 atempo 会在每段生成后统一应用（不变调，原始段存 *_raw.wav）；
      项目的 project_config.py 里写 TEMPO 可以覆盖。
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import soundfile as sf
import torch

from voxcpm import VoxCPM

from ffmpeg_path import ffmpeg

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import script_data  # noqa: E402

AUD = BASE / "audio"
AUD.mkdir(exist_ok=True)
MODEL = os.environ.get("VOX_MODEL", "openbmb/VoxCPM2")
STEPS = int(os.environ.get("VOX_STEPS", "10"))
SEED = int(os.environ.get("VOX_SEED", "20"))
CFG = float(os.environ.get("VOX_CFG", "2.0"))
VOICE = os.environ.get("VOICE", "q1")
VOICE_DIR = BASE / "voices" / VOICE
GROUPS = [(i, min(i + 1, len(script_data.SCENES) - 1))
          for i in range(0, len(script_data.SCENES), 2)]   # 每段 2 个场景
try:
    import project_config as _pc
    EXCLUDE = getattr(_pc, "EXCLUDE", set())
    _CFG_TEMPO = getattr(_pc, "TEMPO", None)
except ImportError:
    EXCLUDE = set()
    _CFG_TEMPO = None


def voice_meta():
    p = VOICE_DIR / "voice.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


META = voice_meta()
_local_prompt = AUD / "prompt_ref.wav"
_local_ref = AUD / "reference_ref.wav"
PROMPT = os.environ.get("PROMPT_WAV") or str(
    _local_prompt if _local_prompt.exists() else VOICE_DIR / "prompt_ref.wav")
REFERENCE = os.environ.get("REFERENCE_WAV") or str(
    _local_ref if _local_ref.exists() else VOICE_DIR / "reference_ref.wav")
# prompt_ref 的准确文本，prompt/续写模式必需
PROMPT_TEXT = os.environ.get("PROMPT_TEXT") or META.get("prompt_text", "")
TEMPO = float(os.environ.get("TEMPO")
              if os.environ.get("TEMPO")
              else (_CFG_TEMPO if _CFG_TEMPO is not None else META.get("atempo", 1.0)))


def chunk_text(gi):
    a, b = GROUPS[gi]
    parts = [x["text"] for x in script_data.flatten()
             if a <= x["scene"] <= b and x["id"] not in EXCLUDE]
    return " ".join(parts)


def apply_tempo(path):
    """统一语速：原始长段另存 *_raw.wav，再 atempo（不变调）。"""
    raw = path.with_name(path.stem + "_raw.wav")
    if raw.exists():
        return
    path.replace(raw)
    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(raw), "-filter:a", f"atempo={TEMPO}",
                    "-ar", "48000", "-ac", "1", str(path)], check=True)
    print(f"  tempo {TEMPO} 已应用（原始存 {raw.name}）", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, default=0)
    ap.add_argument("--of", type=int, default=2)
    a = ap.parse_args()
    if not Path(PROMPT).exists():
        raise SystemExit(
            f"缺少音色参考 {PROMPT}：用 make_voice_ref.py 生成，或拷一份 4–8 秒、文本已知的音频到 audio/prompt_ref.wav")
    if not PROMPT_TEXT:
        raise SystemExit("缺少 PROMPT_TEXT：voice.json 没有 prompt_text，也没设环境变量")
    print(f"voice={VOICE} tempo={TEMPO}\n  prompt={PROMPT}\n  reference={REFERENCE}", flush=True)

    model = VoxCPM.from_pretrained(MODEL, load_denoiser=False, optimize=False, device="cuda")
    cache = model.tts_model.build_prompt_cache(
        prompt_text=PROMPT_TEXT, prompt_wav_path=PROMPT, reference_wav_path=REFERENCE)
    print("模型已加载", flush=True)

    for gi in range(len(GROUPS)):
        if gi % a.of != a.part:
            continue
        out = AUD / f"chunk_{gi}.wav"
        if out.exists():
            print("跳过", gi, flush=True)
            continue
        text = chunk_text(gi)
        t = time.time()
        torch.manual_seed(SEED)
        o, _, _ = model.tts_model.generate_with_prompt_cache(
            target_text=text, prompt_cache=cache,
            cfg_value=CFG, inference_timesteps=STEPS)
        w = o.detach().float().cpu().numpy().squeeze()
        sf.write(str(out), w, 48000)
        dur = len(w) / 48000
        print(f"chunk {gi} chars={len(text)} dur={dur:.2f}s cps={len(text)/dur:.2f} "
              f"gen={time.time()-t:.0f}s", flush=True)
        if abs(TEMPO - 1.0) > 1e-3:
            apply_tempo(out)


if __name__ == "__main__":
    main()
