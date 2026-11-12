# -*- coding: utf-8 -*-
"""词级对齐（拼音版）：修“中文同音字把切点带偏”。

为什么不用 align_asr.py 的字符匹配：Whisper 会把“每俯冲一次”写成“没辅充一次”，
`difflib` 找不到“每/俯/冲”，于是把这个 beat 的第一个匹配字落到后面的“一次”上，
切点晚 0.8 秒——上一句画面多停一拍、这一句只剩 1.2 秒（实测 00_04 只有 1.63s，
算出来 8 字/秒，不可能是真语速）。

改法：两边都先转拼音（不带声调）再匹配。同音字对上，“每”=“没”=mei，
边界就落在真正的开口上。数字先转成中文读法（“0.3”→ “零点三”）。

输出 audio/asr_times.json，格式与 align_asr.py 相同，build_audio_cont.py 直接吃。
"""
import json
import re
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from pypinyin import lazy_pinyin

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import script_data  # noqa: E402

AUD = BASE / "audio"
MODEL_SIZE = sys.argv[1] if len(sys.argv) > 1 else "small"
GROUPS = [(i, min(i + 1, len(script_data.SCENES) - 1))
          for i in range(0, len(script_data.SCENES), 2)]
try:
    from project_config import EXCLUDE
    EXCLUDE = getattr(__import__("project_config"), "EXCLUDE", set())
except ImportError:
    EXCLUDE = set()

DIG = "零一二三四五六七八九"


def num_cn(s):
    """0–9999 的阿拉伯数字转中文读法；小数按“点”读。"""
    if "." in s:
        a, b = s.split(".", 1)
        return num_cn(a) + "点" + "".join(DIG[int(c)] for c in b)
    n = int(s)
    if n < 10:
        return DIG[n]
    if n < 20:
        return "十" + (DIG[n % 10] if n % 10 else "")
    if n < 100:
        return DIG[n // 10] + "十" + (DIG[n % 10] if n % 10 else "")
    if n < 1000:
        out = DIG[n // 100] + "百"
        r = n % 100
        if r:
            out += ("零" if r < 10 else "") + num_cn(str(r))
        return out
    out = DIG[n // 1000] + "千"
    r = n % 1000
    if r:
        out += ("零" if r < 100 else "") + num_cn(str(r))
    return out


def spoken(text):
    """把一句口播拆成“会被念出来的字”，数字转中文，标点/空格丢掉。"""
    text = re.sub(r"\d+(?:\.\d+)?", lambda m: num_cn(m.group(0)), text)
    return [c for c in text if re.match(r"[\u4e00-\u9fffA-Za-z]", c)]


def pys(text):
    return [p.lower() for p in lazy_pinyin(text)]


def heard_units(words):
    """把 Whisper 的词拆成逐字单元：(拼音, 起, 止)。多字词按字数均分时长。"""
    units = []
    for w in words:
        cs = [c for c in w.word if re.match(r"[\u4e00-\u9fffA-Za-z]", c)]
        if not cs:
            continue
        # 逐字取拼音并小写：整词取拼音会把 "Scout" 变成一个音节 "Scout"，
        # 与期望序列里逐字的 s/c/o/u/t 永远对不上，那一句的切点就整体后跳（实测 1 秒）。
        py = [(lazy_pinyin(c)[0] if lazy_pinyin(c) else c).lower() for c in cs]
        d = (w.end - w.start) / len(cs)
        for i, p in enumerate(py):
            units.append((p, w.start + i * d, w.start + (i + 1) * d))
    return units


def transcribe(y16):
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(y16, language="zh", word_timestamps=True, vad_filter=False)
    words = []
    for s in segs:
        for w in (s.words or []):
            words.append(w)
    return words


def trim(y, sr):
    win = int(sr * 0.02)
    n = len(y) // win
    db = 20 * np.log10(np.sqrt(np.mean(y[:n * win].reshape(n, win) ** 2, 1)) + 1e-12)
    idx = np.where(db > -45)[0]
    if not len(idx):
        return y
    return y[max(0, int(idx[0] * win - 0.08 * sr)):min(len(y), int((idx[-1] + 1) * win + 0.08 * sr))]


def main():
    import difflib
    out = {}
    for gi in range(len(GROUPS)):
        p = AUD / f"chunk_{gi}.wav"
        y, sr = sf.read(str(p), dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = trim(y, sr)
        y16 = librosa.resample(y.astype(np.float32), orig_sr=sr, target_sr=16000)
        beats = [b for b in script_data.flatten()
                 if GROUPS[gi][0] <= b["scene"] <= GROUPS[gi][1] and b["id"] not in EXCLUDE]

        units = heard_units(transcribe(y16))
        # 期望序列：每个字 + 它属于第几个 beat
        exp, owner = [], []
        for bi, b in enumerate(beats):
            for ch in spoken(b["text"]):
                exp.extend(pys(ch))
                owner.append(bi)
        got = [u[0] for u in units]
        sm = difflib.SequenceMatcher(None, exp, got, autojunk=False)

        # 每个 beat 在期望序列里的第一个下标
        first = {}
        bi = 0
        for k, o in enumerate(owner):
            if o not in first:
                first[o] = k

        # exp 下标 -> got 下标（只覆盖匹配块内部）
        pos_of = {}
        for blk in sm.get_matching_blocks():
            for j in range(blk.size):
                pos_of[blk.a + j] = blk.b + j

        starts = []
        for bi in range(len(beats)):
            k0 = first.get(bi)
            if k0 is None:
                starts.append(None)
                continue
            k1 = first.get(bi + 1, len(exp))
            # 只认“第一个字”会在块边界处失败（同音字/漏字），然后被当成缺失、退回
            # +0.45s 等距估计——实测 4 个 beat 被压成 0.45 秒，下一镜吃掉 7–8 秒。
            # 改成在**本 beat 的字范围内**找第一个真正匹配上的字。
            pos = None
            for k in range(k0, k1):
                if k in pos_of:
                    pos = pos_of[k]
                    break
            starts.append(units[pos][1] if pos is not None and pos < len(units) else None)
        # 缺失/倒序的边界用等距估计补，并加单调约束
        dur = len(y) / sr
        for i in range(1, len(starts)):
            lo = (starts[i - 1] if starts[i - 1] is not None else 0.0) + 0.45
            hi = dur - 0.15
            if starts[i] is None or starts[i] < lo:
                starts[i] = min(lo, hi)
            starts[i] = min(starts[i], hi)
        starts = [0.0] + [s if s is not None else 0.0 for s in starts[1:]] + [dur]
        out[str(gi)] = {"times": [round(t, 3) for t in starts]}
        rates = []
        for i, b in enumerate(beats):
            c = len(spoken(b["text"]))
            d = starts[i + 1] - starts[i]
            rates.append(f"{c / d:.1f}" if d > 0.05 else "-")
        print(f"chunk {gi}: {len(beats)} beats  c/s " + " ".join(rates), flush=True)

    (AUD / "asr_times.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    print("->", AUD / "asr_times.json")


if __name__ == "__main__":
    main()
