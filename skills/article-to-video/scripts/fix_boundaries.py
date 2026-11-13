# -*- coding: utf-8 -*-
"""ASR 切点后处理（只用声学判据）：把落在“说话中间”的切点挪到最近的开口。

为什么需要：正文里的中文数字（六千零七 / 五千五百八十九）会被 Whisper 转成
6007 / 5589，字符匹配跳过整段，切点被对到后面的英文词上——实测 02_02 的切点
落到 “Claude”，画面晚 1.3 秒、上一句字幕停在画面上，观众感知为“卡一下”。

为什么不按字数估：`14 万行 Fortran`、`±10⁻¹⁰ K` 这种英数混排，字数与音节数差
得远，按字数估会把本来正确的切点推歪（实测把 00_01 推后 1.7 秒）。

做法：只问一件事——这个切点是不是落在静音里？
  - 在静音段内（±0.12s）或紧贴静音起点 → 已经在开口附近，不动；
  - 落在语音里 → 往后找最近的静音结束点（≤1.5s），作为新的开口。

用法：
  python fix_boundaries.py --dry      # 只报告，不改
  python fix_boundaries.py            # 改 audio/asr_times.json

改完再跑 `python check_audio.py` 与人工抽查（上一句必须完整播完）。
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import script_data  # noqa: E402

ASR = BASE / "audio" / "asr_times.json"
try:                       # 项目可在 project_config.GROUPS 里自定义分段（本片 4 段）
    from project_config import GROUPS as _GROUPS
except ImportError:
    _GROUPS = None
GROUPS = _GROUPS or [(i, min(i + 1, len(script_data.SCENES) - 1))
                     for i in range(0, len(script_data.SCENES), 2)]


def silences(gi, th=-42.0, min_len=0.10):
    y, sr = sf.read(str(BASE / f"audio/chunk_{gi}.wav"), dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
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


def in_silence(t, sil, tol=0.12):
    return any(x - tol <= t <= y + tol for x, y in sil)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只报告，不写回")
    ap.add_argument("--max-ahead", type=float, default=1.5, help="往后找开口的最大距离（秒）")
    a = ap.parse_args()

    if not ASR.exists():
        raise SystemExit(f"没有 {ASR}，先跑 align_asr.py")
    data = json.loads(ASR.read_text(encoding="utf-8"))
    beats = script_data.flatten()
    changed = 0
    for gi, (lo, hi) in enumerate(GROUPS):
        bs = [x for x in beats if lo <= x["scene"] <= hi]
        T = list(data[str(gi)]["times"])
        sil = silences(gi)
        for i in range(1, len(bs)):
            t = T[i]
            if in_silence(t, sil):
                continue
            ends = [b for s, b in sil if 0.0 < b - t <= a.max_ahead and b < T[i + 1] - 0.3]
            if not ends:
                print(f"  chunk{gi} {bs[i]['id']} @{t:.2f} 落在语音里，但 {a.max_ahead}s 内没有静音结束，保留")
                continue
            pick = min(ends) + 0.03
            print(f"chunk{gi} {bs[i]['id']}: {t:.2f} -> {pick:.2f}（原切点在语音里）")
            T[i] = pick
            changed += 1
        for i in range(1, len(T) - 1):
            T[i] = max(T[i], T[i - 1] + 0.4)
            T[i] = min(T[i], T[i + 1] - 0.25)
        data[str(gi)]["times"] = [round(x, 3) for x in T]

    if a.dry:
        print(f"dry-run: {changed} 处会改（加 --dry 之外不加参数写入）")
        return 0
    ASR.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"fixed {changed} boundaries -> {ASR}")
    print("下一步：build_audio_cont.py → check_audio.py，并人工抽查这几处切点前一秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())
