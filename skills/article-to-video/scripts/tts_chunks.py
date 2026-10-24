# -*- coding: utf-8 -*-
"""用 VoxCPM2 生成 2–4 个长段。

为什么用长段：逐句克隆会让说话人漂移（实测各 beat 基频 71–154Hz）；
同一 prompt/reference 的 4 个长段稳定在 98–103Hz。
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from voxcpm import VoxCPM

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import script_data  # noqa: E402

AUD = BASE / "audio"
AUD.mkdir(exist_ok=True)
MODEL = os.environ.get("VOX_MODEL", "openbmb/VoxCPM2")
STEPS = int(os.environ.get("VOX_STEPS", "10"))
SEED = int(os.environ.get("VOX_SEED", "20"))
CFG = float(os.environ.get("VOX_CFG", "2.0"))
GROUPS = [(i, min(i + 1, len(script_data.SCENES) - 1))
          for i in range(0, len(script_data.SCENES), 2)]   # 每段 2 个场景
try:
    from project_config import EXCLUDE
except ImportError:
    EXCLUDE = set()

PROMPT = str(AUD / "prompt_ref.wav")
# prompt_ref.wav 的准确文本，prompt/续写模式必需。
PROMPT_TEXT = "这不是段子。是一份 AI 安全报告里的真事。"


def chunk_text(gi):
    a, b = GROUPS[gi]
    parts = [x["text"] for x in script_data.flatten()
             if a <= x["scene"] <= b and x["id"] not in EXCLUDE]
    return " ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, default=0)
    ap.add_argument("--of", type=int, default=2)
    a = ap.parse_args()
    if not Path(PROMPT).exists():
        raise SystemExit(f"缺少 {PROMPT}：请提供 4–8 秒、文本已知的音色样本")

    model = VoxCPM.from_pretrained(MODEL, load_denoiser=False, optimize=False, device="cuda")
    cache = model.tts_model.build_prompt_cache(
        prompt_text=PROMPT_TEXT, prompt_wav_path=PROMPT, reference_wav_path=PROMPT)
    print("模型已加载", flush=True)

    for gi in range(len(GROUPS)):
        if gi % a.of != a.part:
            continue
        text = chunk_text(gi)
        out = AUD / f"chunk_{gi}.wav"
        if out.exists():
            print("跳过", gi, flush=True)
            continue
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


if __name__ == "__main__":
    main()
