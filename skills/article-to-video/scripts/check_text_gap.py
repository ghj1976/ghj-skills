# -*- coding: utf-8 -*-
"""大字有没有压到画面/面板上：按真实字形 bbox 逐 beat 量一遍。

为什么要单独做一个门禁：`card` 版式卡片从 y=540 起，而 200px 的中文字形下缘在
base+251、下划线再 +16 —— 写死「200px 大字」就会把下划线压进视频画面 19px。
肉眼在缩略图里很容易漏（白墙背景尤其看不出来），所以按数字判：

    下划线底 = textbbox[3] + 16
    卡片顶   = card/hook 540 · full/phone/diptych 470 · 结构版式 536 · text+窗口 470

判据：`卡片顶 - 下划线底 >= --min-gap`（默认 12px）。实测合格片是 29–30px。

用法（在项目目录里跑，依赖 render.py 的版式度量与 out/timeline.json）：
  python check_text_gap.py
  python check_text_gap.py --min-gap 20
退出码：全过 0，有不过 1。
"""
import argparse
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import render  # noqa: E402

# 文字下方的「障碍物」：卡片顶 / 舞台顶。数字是像素，改版式时一起改这里。
CARD_TOP = {"card": 540, "hook": 540, "full": 470, "phone": 470, "diptych": 470}


def obstacle(b):
    lay = b["layout"]
    if lay in CARD_TOP:
        return CARD_TOP[lay]
    if lay in render.STAGE_LAYOUTS:
        return render.STAGE_TOP
    if lay == "text":
        return render.WIN_Y if render.has_win(b) else 1180
    if lay == "data":
        return render.WIN_Y if render.has_win(b) else 1180
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", default=str(BASE / "out" / "timeline.json"))
    ap.add_argument("--min-gap", type=int, default=12)
    a = ap.parse_args()

    tl = render.TIMELINE
    rows, bad = [], []
    for b in tl["beats"]:
        big = b.get("big") or ""
        if not big:
            continue
        top = obstacle(b)
        if top is None:
            continue
        start, base, lim = render.layout_text_box(b)
        f, size = render.fit_text_in_box(big, start, base, lim)
        if b["layout"] == "data":
            # 数据卡：主数字画在 top+eye_h+18 处，量它的下缘
            oy = 140 if render.has_win(b) else 260
            bb = render._MEASURE.textbbox((62, oy + 60 + 18), big, font=f)
            bottom = bb[3]
        else:
            bottom = render._MEASURE.textbbox((60, base), big, font=f)[3] + 16
        gap = top - bottom
        rows.append((b["id"], b["layout"], size, bottom, top, gap))
        if gap < a.min_gap:
            bad.append(rows[-1])

    for r in rows:
        flag = "  <<<" if r[5] < a.min_gap else ""
        print(f"{r[0]} {r[1]:8s} 字号{r[2]:3d} 字底{r[3]:4d} 卡顶{r[4]:4d} 间距{r[5]:4d}{flag}")
    print(f"\n{len(rows)} 个镜头带大字，最小间距 {min([r[5] for r in rows], default=0)}px"
          f"（门槛 {a.min_gap}px）")
    if bad:
        print(f"RESULT: FAIL —— {len(bad)} 处会压字（按 SKILL.md「大字压到画面上」收字号）")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
