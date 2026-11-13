# -*- coding: utf-8 -*-
"""连续长段口播 + 时间轴。

不按 beat 切音频。长段之间只留短空隙，画面/字幕边界来自
asr_times.json（由 align_asr.py 生成）。
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
LEAD = 1.0          # 开头留白
CHUNK_GAP = 0.45    # 长段之间的空白：trim 两端各留 0.08s pad，0.65 实测成 0.68–0.78s，
                    # 会被 check_audio 的“最长停顿 ≤0.65s”判 FAIL；0.45 落到约 0.58s
TAIL = 2.2          # 结尾卡停留
try:                       # 项目可在 project_config.GROUPS 里自定义分段（本片 4 段）
    from project_config import GROUPS as _GROUPS
except ImportError:
    _GROUPS = None
GROUPS = _GROUPS or [(i, min(i + 1, len(script_data.SCENES) - 1))
                     for i in range(0, len(script_data.SCENES), 2)]   # 每段 2 个场景
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
    """按字数比例估算、偏晚的边界；只在 ASR 结果缺失时使用。"""
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


def onsets_of(y, sr, quiet_db=-38.0, voiced_db=-36.0, sustain=4):
    """返回语音起点（20ms 窗，从静音跳过阈值且持续 100ms）。"""
    win = int(0.02 * sr)
    n = len(y) // win
    db = 20 * np.log10(np.sqrt(np.mean(y[:n * win].reshape(n, win) ** 2, 1)) + 1e-12)
    out = []
    for i in range(1, n - sustain):
        if db[i] > voiced_db and db[i - 1] <= quiet_db and (db[i:i + sustain] > voiced_db).all():
            out.append(i * 0.02)
    return out, db


def silence_spans(y, sr, th=-45.0, min_len=0.12):
    """全片静音段（起点, 终点）；只用来找“下一句开口前的停顿”。"""
    win = int(0.02 * sr)
    n = len(y) // win
    db = 20 * np.log10(np.sqrt(np.mean(y[:n * win].reshape(n, win) ** 2, 1)) + 1e-12)
    q = db < th
    spans, i = [], 0
    while i < n:
        if q[i]:
            j = i
            while j < n and q[j]:
                j += 1
            if (j - i) * 0.02 >= min_len:
                spans.append((i * 0.02, j * 0.02))
            i = j
        else:
            i += 1
    return spans


def snap_forward_to_pause(times, y, sr, max_ahead=1.0, min_gap=0.35):
    """whisper 的词起点常常偏早，切点会落进上一句的尾音里（“话没说完就切”）。

    规则：如果切点之后紧跟一段停顿（停顿结束在 1 秒内），就把切点放到停顿结束——
    也就是下一句真正开口的地方。只往后挪、不动已经落在开口上的切点。
    """
    spans = silence_spans(y, sr)
    out = list(times)
    for k in range(1, len(out) - 1):
        t = out[k]
        for a, b in spans:
            if t - 0.06 <= a < b and 0.0 < b - t <= max_ahead:
                out[k] = b + 0.03
                break
        out[k] = max(out[k], out[k - 1] + min_gap)
        if k + 1 < len(out):
            out[k] = min(out[k], times[k + 1] - 0.25)
    return out


def snap_to_onsets(times, y, sr, tol=0.55):
    """把每个切点吸附到最近的语音起点，避免“画面先跳、声音没到”。

    whisper 的词起点会有 ±0.3s 误差，长段之间还有空白；不吸附就会出现
    章节切点比开口早/晚 0.2–0.5s，观众感知为“卡一下”。
    """
    ons, _ = onsets_of(y, sr)
    out = list(times)
    for k in range(1, len(times) - 1):
        t = times[k]
        cand = [o for o in ons if abs(o - t) <= tol]
        if cand:
            out[k] = min(cand, key=lambda x: abs(x - t))
    for k in range(1, len(out)):
        out[k] = max(out[k], out[k - 1] + 0.4)
    return out


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
                "note": b.get("note", ""), "clip": b.get("clip", ""),
                "extras": b.get("extras") or {},
                "start": round(st, 4), "end": round(en, 4), "duration": round(en - st, 4),
            })

    # 切点吸附到真实开口（在拼接好的 narration 上做，不含音乐）
    starts = [b["start"] for b in beats] + [round(total, 4)]
    snapped = snap_to_onsets(starts, buf, SR)
    snapped = snap_forward_to_pause(snapped, buf, SR)
    for i, b in enumerate(beats):
        b["start"] = round(snapped[i], 4)
        b["end"] = round(snapped[i + 1], 4)
        b["duration"] = round(b["end"] - b["start"], 4)

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
        # 章节边界落在“新章节第一句的开口”，不是两段中间：长段之间还有 0.65s 空白，
        # 取中点会让进度条/章节标签在开口前 0.3–0.4s 就跳（check_audio 会判偏差过大）。
        cut = scenes[i]["start"] + 0.25
        scenes[i - 1]["end"] = round(cut, 4)
        scenes[i]["start"] = round(cut, 4)
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
