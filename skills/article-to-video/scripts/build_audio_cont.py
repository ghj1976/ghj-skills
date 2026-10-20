# -*- coding: utf-8 -*-
"""Continuous long-form narration + timeline.

Never cuts the voice per beat. Chunks are concatenated with short gaps and the
visual/caption boundaries come from asr_times.json (produced by align_asr.py).
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import script_data  # noqa: E402
import build_audio_utils as ba  # noqa: E402

AUD = BASE / "audio"
OUT = BASE / "out"
OUT.mkdir(exist_ok=True)
SR = 48000
LEAD = 1.0          # silence before the first word
CHUNK_GAP = 0.65    # silence between long chunks
TAIL = 2.2          # end-card hold
GROUPS = [(i, min(i + 1, len(script_data.SCENES) - 1))
          for i in range(0, len(script_data.SCENES), 2)]   # 2 scenes per chunk
try:
    from project_config import EXCLUDE
except ImportError:
    EXCLUDE = set()


def trim(y, sr, th=-45.0, pad=0.08):
    win = max(1, int(sr * 0.02))
    n = len(y) // win
    if n < 3:
        return y
    rms = np.sqrt(np.mean(y[:n * win].reshape(n, win) ** 2, 1) + 1e-12)
    db = 20 * np.log10(rms + 1e-12)
    idx = np.where(db > th)[0]
    if not len(idx):
        return y
    return y[max(0, int(idx[0] * win - pad * sr)):min(len(y), int((idx[-1] + 1) * win + pad * sr))]


def fallback_boundaries(y, sr, beats):
    """Character-proportional boundaries biased late; only used if ASR is absent."""
    n = len(y)
    dur = n / sr
    total = sum(len(b["text"]) for b in beats)
    cum = 0
    times = [0.0]
    for b in beats[:-1]:
        cum += len(b["text"])
        t = cum / total * dur
        t = max(times[-1] + 0.4, min(dur - 0.2, t))
        times.append(t)
    times.append(dur)
    return times


def main():
    asr_path = AUD / "asr_times.json"
    asr = json.loads(asr_path.read_text(encoding="utf-8")) if asr_path.exists() else None

    pieces, offsets = [], []
    t = LEAD
    for gi in range(len(GROUPS)):
        y, sr = sf.read(str(AUD / f"chunk_{gi}.wav"), dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = trim(y, sr)
        offsets.append(t)
        pieces.append(y)
        t += len(y) / sr + CHUNK_GAP
    total = t + TAIL

    n = int(total * SR)
    buf = np.zeros(n, dtype=np.float32)
    for y, off in zip(pieces, offsets):
        s = int(off * SR)
        buf[s:s + len(y)] += y
    buf *= 0.89 / (float(np.max(np.abs(buf))) or 1.0)
    sf.write(str(OUT / "narration.wav"), buf, SR, subtype="PCM_16")

    beats = []
    for gi in range(len(GROUPS)):
        y = pieces[gi]
        dur = len(y) / SR
        bs = [b for b in script_data.flatten()
              if GROUPS[gi][0] <= b["scene"] <= GROUPS[gi][1] and b["id"] not in EXCLUDE]
        if asr and str(gi) in asr:
            ts = asr[str(gi)]["times"]
        else:
            ts = fallback_boundaries(y, SR, bs)
        assert len(ts) == len(bs) + 1, (gi, len(ts), len(bs))
        for i, b in enumerate(bs):
            st, en = offsets[gi] + ts[i], offsets[gi] + ts[i + 1]
            beats.append({
                "id": b["id"], "scene": b["scene"], "text": b["text"], "sub": b["sub"],
                "big": b["big"], "layout": b["layout"], "accent": b["accent"],
                "eyebrow": b["eyebrow"], "img": b["img"],
                "start": round(st, 4), "end": round(en, 4), "duration": round(en - st, 4),
            })

    scenes = []
    for si, sc in enumerate(script_data.SCENES):
        sb = [x for x in beats if x["scene"] == si]
        if not sb:
            continue
        scenes.append({
            "index": si, "id": sc["id"], "label": sc["label"], "kind": sc["kind"],
            "start": round(sb[0]["start"] - 0.25, 4), "end": round(sb[-1]["end"] + 0.25, 4),
        })
    scenes[0]["start"] = 0.0
    for i in range(1, len(scenes)):
        mid = (scenes[i - 1]["end"] + scenes[i]["start"]) / 2
        scenes[i - 1]["end"] = round(mid, 4)
        scenes[i]["start"] = round(mid, 4)
    scenes[-1]["end"] = round(total, 4)

    tl = {"sr": SR, "duration": round(total, 4), "speech_end": round(t, 4),
          "beats": beats, "scenes": scenes}
    ba.music(tl["duration"])
    ba.sfx_track(tl)
    ba.mix()
    ba.write_srt(tl)
    ba.write_script(tl)
    (OUT / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"duration": tl["duration"], "beats": len(beats), "scenes": len(scenes)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
