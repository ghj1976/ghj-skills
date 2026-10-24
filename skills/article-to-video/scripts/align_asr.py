# -*- coding: utf-8 -*-
"""用词级 ASR 对齐字幕/画面边界。

关键：Whisper 之前必须把 48kHz 重采样到 16kHz。直接喂 48kHz，
Whisper 会听到慢速音频，输出英文幻觉。

第 i 个 beat 的结束边界 = 第 i+1 个 beat 第一个词的开始时间。
这样能保证切换前上一句已经播完。
"""
import json
import re
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import script_data  # noqa: E402

AUD = BASE / "audio"
MODEL_SIZE = sys.argv[1] if len(sys.argv) > 1 else "small"
GROUPS = [(i, min(i + 1, len(script_data.SCENES) - 1))
          for i in range(0, len(script_data.SCENES), 2)]
try:
    from project_config import EXCLUDE
except ImportError:
    EXCLUDE = set()


def norm(s):
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s).lower()


def trim(y, sr):
    win = int(sr * 0.02)
    n = len(y) // win
    rms = np.sqrt(np.mean(y[:n * win].reshape(n, win) ** 2, 1) + 1e-12)
    db = 20 * np.log10(rms + 1e-12)
    idx = np.where(db > -45)[0]
    return y[max(0, int(idx[0] * win - 0.08 * sr)):min(len(y), int((idx[-1] + 1) * win + 0.08 * sr))] if len(idx) else y


def main():
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    out = {}
    for gi in range(len(GROUPS)):
        y, sr = sf.read(str(AUD / f"chunk_{gi}.wav"), dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = trim(y, sr)
        dur = len(y) / sr
        y16 = librosa.resample(y.astype(np.float32), orig_sr=sr, target_sr=16000)
        segs, _ = model.transcribe(y16, language="zh", word_timestamps=True,
                                   beam_size=5, vad_filter=False)
        words = []
        for s in segs:
            for w in (s.words or []):
                if w.word.strip():
                    words.append({"w": w.word, "s": float(w.start), "e": float(w.end)})

        bs = [b for b in script_data.flatten()
              if GROUPS[gi][0] <= b["scene"] <= GROUPS[gi][1] and b["id"] not in EXCLUDE]
        exp, owner = "", []
        for i, b in enumerate(bs):
            for ch in norm(b["text"]):
                exp += ch
                owner.append(i)
        tr, tmap = "", []
        for w in words:
            for ch in norm(w["w"]):
                tr += ch
                tmap.append((w["s"], w["e"]))

        sm = difflib_matcher(exp, tr)
        e2t = {}
        for a, b, size in sm.get_matching_blocks():
            for k in range(size):
                e2t[a + k] = b + k
        first, last = {}, {}
        for ei, bi in enumerate(owner):
            if ei in e2t:
                ti = e2t[ei]
                first.setdefault(bi, ti)
                last[bi] = ti

        times = [0.0]
        prev = 0.0
        for i in range(1, len(bs)):
            if i in first:
                t = tmap[first[i]][0]
            elif (i - 1) in last:
                t = tmap[last[i - 1]][1] + 0.12
            else:
                t = prev + len(bs[i - 1]["text"]) * 0.19
            t = max(prev + 0.4, min(dur - 0.15, t))
            times.append(t)
            prev = t
        times.append(dur)
        out[str(gi)] = {"dur": round(dur, 3), "times": [round(x, 3) for x in times]}
        print("分段", gi, "边界", [round(x, 2) for x in times], flush=True)
    (AUD / "asr_times.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def difflib_matcher(exp, tr):
    import difflib
    return difflib.SequenceMatcher(None, exp, tr, autojunk=False)


if __name__ == "__main__":
    main()
