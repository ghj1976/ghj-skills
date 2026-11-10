# -*- coding: utf-8 -*-
"""1080×1920 竖屏：动态大字、模糊底图、30fps。

图片镜头：
  - 静帧 card/hook/full：整图按比例进卡片，整帧慢推近 + 光扫；
  - 超宽横幅（gap > 0.28h）：深色卡底 + 上下细边，不用“同图放大模糊填空”（会成色块）；
  - poster：竖构图/近方形插画，卡片按图片比例收窄，让图铺满卡片（先裁掉原图空白边）；
  - cover：竖幅照片整屏铺满，上下渐变 scrim 给大字和字幕让位；
  - 动态 B-roll（clip）：读 clips/<beat_id>/ 的帧序列，按 beat 时长线性播放。
  - phone：竖屏/竖构图片段整帧进「设备卡」，**不裁高度**（手机录屏、竖构图资产卡用这个）；
  - diptych：左右两张对照图（从片段里抽的前后帧），讲「换装前 / 换装后」这类对比。

结构版式（不依赖图片，靠程序画，数据和文案写在 beat 的 extras 里）：
  - chat     群聊/消息流：左人右 AI，气泡逐条出现，可带“没人@它”之类的标签
  - layers   分层架构：上层调度 + 下层多工位 + 箭头，逐层点亮
  - flow     纵向流程：编号步骤 + 连接线，按顺序推进
  - compare  左右对比：两栏标题 + 要点 + 中间 VS
  - bars     条形对比：数值条生长 + 数值标注
  - kpi      多数字并排：2–3 个关键数字 + 说明
  - list     清单：序号 + 标题 + 一行说明，逐行点亮
  - terminal 终端/PR 卡：标题栏 + diff 行 + 状态徽章
  - quote    长引语：左侧竖条 + 出处

图片查找顺序：--assets 目录 → 项目 assets/ 目录（放裁切过的衍生图，不覆盖原始素材）。
"""
import bisect
import json
import math
import re
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from ffmpeg_path import ffmpeg as _ffmpeg

BASE = Path(__file__).resolve().parent
ASSET_DIR = Path(os.environ.get("ASSET_DIR", str(BASE.parent)))
ROOT = ASSET_DIR
OUT = BASE / "out"
OUT.mkdir(exist_ok=True)
TIMELINE = json.loads((OUT / "timeline.json").read_text(encoding="utf-8"))

W, H = 1080, 1920
FPS = 30
FFMPEG = _ffmpeg()
FONT_BOLD = os.environ.get("FONT_BOLD", r"C:\Windows\Fonts\Noto Sans SC Bold (TrueType).otf")
FONT_MED = os.environ.get("FONT_MED", r"C:\Windows\Fonts\Noto Sans SC Medium (TrueType).otf")

# --- 项目副本：每条视频改这里 ---
BRAND = os.environ.get("VIDEO_BRAND", "AI 失控 11 天")
TITLE_MAIN = os.environ.get("VIDEO_TITLE", "AI 失控 11 天")
TITLE_SUB = os.environ.get("VIDEO_SUBTITLE", "不毁灭世界，只想查清哪个门人多")
TITLE_KICKER = os.environ.get("VIDEO_KICKER", "真实事件 · 一份 AI 安全报告")
TITLE_GHOST = os.environ.get("VIDEO_TITLE_GHOST", "11")   # 标题卡右上角的装饰数字
TITLE_CREDIT = os.environ.get("VIDEO_CREDIT", "AI 配音：VoxCPM2")
END_L1 = os.environ.get("VIDEO_END_1", "有些事，人类早忘了")
END_L2 = os.environ.get("VIDEO_END_2", "AI 还在较真")
END_Q = os.environ.get("VIDEO_END_Q", "你猜，它下一个执念会是什么？")
END_CTA = os.environ.get("VIDEO_END_CTA", "你怎么看？评论区聊聊")
END_SOURCE = os.environ.get("VIDEO_SOURCE", "资料来源：Swarmcha.se 报告 / 腾讯方面回应")
DATA_SOURCE = os.environ.get("VIDEO_DATA_SOURCE", "数据来自公开资料")
# 开场第一句就是原声/钩子时，不要那 1 秒静态标题卡：VIDEO_NO_TITLE=1
NO_TITLE = os.environ.get("VIDEO_NO_TITLE", "0") == "1"
if not NO_TITLE:
    print("[warn] 标题卡开启：0–1 秒是一张静态标题卡。若开场第一句就是钩子，"
          "按「开场铁律」设 VIDEO_NO_TITLE=1。", flush=True)

WHITE = (247, 248, 250)
MUTED = (158, 167, 180)
ORANGE = (255, 138, 61)
CYAN = (58, 224, 240)
INK = (7, 10, 16)

_f = {}


def font(size, bold=True):
    k = (size, bold)
    if k not in _f:
        _f[k] = ImageFont.truetype(FONT_BOLD if bold else FONT_MED, size)
    return _f[k]


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 2


def make_bg():
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    top = np.array([12, 17, 28], np.float32)[None, None, :]
    bot = np.array([4, 6, 10], np.float32)[None, None, :]
    img = np.repeat(top + (bot - top) * yy, W, axis=1)
    gx, gy = np.meshgrid(np.linspace(0, 1, W, dtype=np.float32), np.linspace(0, 1, H, dtype=np.float32))
    for cx, cy, col, rad, amp in ((0.8, 0.1, (40, 120, 140), 0.5, 0.6), (0.1, 0.9, (150, 70, 30), 0.55, 0.5)):
        g = np.exp(-(((gx - cx) ** 2 + (gy - cy) ** 2) / rad ** 2)).astype(np.float32)
        for c in range(3):
            img[:, :, c] += g * col[c] * amp
    base = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(grid)
    for x in range(0, W, 90):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 5), width=1)
    for y in range(0, H, 90):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 5), width=1)
    return Image.alpha_composite(base.convert("RGBA"), grid).convert("RGB")


BG = make_bg()

SCENES = TIMELINE["scenes"]
BEATS = TIMELINE["beats"]
STARTS = [b["start"] for b in BEATS]

# caches
_BG = {}
_FG = {}
_CAP = {}


ASSETS = BASE / "assets"


def asset_path(img):
    """先找 --assets 目录，再回落到项目自己的 assets/。

    没有空白边的原图直接引用素材目录；量过墨迹 bbox、裁过空白边的衍生图放
    项目 assets/，这样既不覆盖用户素材，也不用把整份素材复制一遍。
    """
    p = ROOT / img
    if p.exists():
        return p
    q = ASSETS / img
    return q if q.exists() else p


def bg_for(img):
    if img not in _BG:
        src = Image.open(asset_path(img)).convert("RGB")
        sw, sh = src.size
        scale = max(W / sw, H / sh)
        big = src.resize((int(sw * scale) + 1, int(sh * scale) + 1), Image.LANCZOS)
        x0 = (big.width - W) // 2
        y0 = (big.height - H) // 2
        crop = big.crop((x0, y0, x0 + W, y0 + H)).filter(ImageFilter.GaussianBlur(26))
        # 按底图平均亮度加深：白底照片（如白背景蝴蝶）用 150 会糊成一片灰，字也没对比
        mean = float(np.asarray(crop.resize((90, 160), Image.BILINEAR), dtype=np.float32).mean())
        alpha = int(min(215, max(150, 150 + (mean - 55) * 1.15)))
        dark = Image.new("RGBA", (W, H), (4, 6, 10, alpha))
        _BG[img] = Image.alpha_composite(crop.convert("RGBA"), dark).convert("RGB")
    return _BG[img]


_BG_MEAN = {}


def bg_mean(img):
    key = img or "__gradient__"
    if key not in _BG_MEAN:
        src = bg_for(img) if img else BG
        small = src.resize((120, 213), Image.BILINEAR)
        arr = np.asarray(small, dtype=np.float32)
        _BG_MEAN[key] = float(arr.mean())
    return _BG_MEAN[key]


def fg_for(img):
    """只做尺寸上限，不强行拉成 16:9；竖图/方图交回 image_card 按比例摆放。"""
    if img not in _FG:
        src = Image.open(asset_path(img)).convert("RGB")
        scale = min(1.0, 1600 / max(1, src.width), 900 / max(1, src.height))
        if scale < 1.0:
            src = src.resize((max(1, int(src.width * scale)),
                              max(1, int(src.height * scale))), Image.LANCZOS)
        _FG[img] = src
    return _FG[img]


def wrap(text, f, maxw):
    lines = []
    for raw in text.split("\n"):
        cur = ""
        for ch in raw:
            if not cur or f.getlength(cur + ch) <= maxw:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


def cap_for(b):
    if b["id"] in _CAP:
        return _CAP[b["id"]]
    img = Image.new("RGBA", (W, 470), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 64
    f = font(size)
    lines = wrap(b["sub"], f, 930)
    while len(lines) > 3 and size > 50:
        size -= 4
        f = font(size)
        lines = wrap(b["sub"], f, 930)
    lh = int(size * 1.28)
    total = lh * len(lines)
    y = (470 - total) // 2 + lh // 2
    for ln in lines:
        d.text((W // 2 + 3, y + 4), ln, font=f, fill=(0, 0, 0, 220), anchor="mm",
               stroke_width=8, stroke_fill=(0, 0, 0, 220))
        d.text((W // 2, y), ln, font=f, fill=WHITE, anchor="mm",
               stroke_width=8, stroke_fill=(3, 5, 9, 240))
        y += lh
    _CAP[b["id"]] = (img.convert("RGB"), img.getchannel("A"))
    return _CAP[b["id"]]


def accent(b):
    return ORANGE if b["accent"] == "orange" else CYAN


def fit_big(text, start=170, min_size=62, maxw=960):
    size = start
    while size > min_size and font(size).getlength(text) > maxw:
        size -= 6
    return font(size), size


EYE_GAP = 13          # 小标签下划线与字形的间距（写死 top+42 时正好压在字底）
EYE_W, EYE_H_ = 36, 4


def draw_eyebrow(d, x, y, text, size, color, ac, gap=EYE_GAP, upper=False):
    """小标签 + 下划线。线按字形 bbox 下移 gap 像素画，不按字号估算。"""
    t = text.upper() if upper else text
    if not t:
        return None
    f = font(size, False)
    d.text((x, y), t, font=f, fill=color)
    bb = d.textbbox((x, y), t, font=f)
    ly = bb[3] + gap
    d.rectangle([x, ly, x + EYE_W, ly + EYE_H_], fill=ac)
    return ly


_MEASURE = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def layout_text_box(b):
    """大字在某个版式里的（字号起点, 基线, 下划线最低 y）。

    为什么单独抽出来：`card` 的卡片从 y=540 起，而 200px 的中文字形下缘在
    base+251、下划线再 +16——写死"200px"就会压进画面 19px。渲染和
    `check_text_gap.py` 必须用同一套算式，否则检查脚本和成片会各说各话。
    """
    lay = b["layout"]
    big = b.get("big") or ""
    if lay in ("phone", "diptych"):
        return 150, 232, 442
    if lay == "full":
        return 150, 236, 442
    if lay in STAGE_LAYOUTS:
        return 200, 262, STAGE_TOP - 28
    if lay == "text":
        if has_win(b):
            start = 200 if len(big) <= 4 else 172 if len(big) <= 6 else 146
            return start, 172, WIN_Y - 28
        return 200, 690, 1150
    return 200, 268, 512          # card / hook


def fit_text_in_box(text, start, base, lim, floor=72):
    """按宽度收完，再按真实字形 bbox 收，直到「下划线底」不越过 lim。"""
    f, size = fit_big(text, start=start)
    while size > floor and _MEASURE.textbbox((60, base), text, font=f)[3] + 16 > lim:
        size -= 4
        f = font(size)
    return f, size


def draw_big(frame, b, lt):
    if b["layout"] == "text":
        return draw_text_layout(frame, b, lt)
    d = ImageDraw.Draw(frame)
    ac = accent(b)
    draw_eyebrow(d, 60, 214, b.get("eyebrow") or "", 27, ac, ac, upper=True)
    big = b.get("big")
    if not big:
        return
    # phone / full / diptych 这几种版式的卡片从 y≈470 起，大字必须缩一号，
    # 否则 200px 的「换一身」会直接压到卡片和标签上（实测正好差 30px）
    start, base, lim = layout_text_box(b)
    f, size = fit_text_in_box(big, start, base, lim)
    y = base + int(10 * (1 - ease_out(lt / 0.28)))
    d.text((63, y + 4), big, font=f, fill=(0, 0, 0), stroke_width=5, stroke_fill=(0, 0, 0))
    d.text((60, y), big, font=f, fill=ac)
    # underline sweep, placed below the real glyph bbox
    bbox = d.textbbox((60, y), big, font=f)
    ly = bbox[3] + 16
    w = int(min(300, f.getlength(big) * 0.55) * ease_out(lt / 0.35))
    if w > 0:
        d.rectangle([60, ly, 60 + w, ly + 8], fill=ac)


def draw_text_layout(frame, b, lt):
    d = ImageDraw.Draw(frame)
    ac = accent(b)
    if has_win(b):
        # 下面有满幅原片窗口：大字整体上移，去掉装饰引号
        draw_eyebrow(d, 60, 118, b.get("eyebrow") or "", 28, ac, ac)
        big = b.get("big") or ""
        start, base, lim = layout_text_box(b)
        f, size = fit_text_in_box(big, start, base, lim)
        y = base + int(12 * (1 - ease_out(lt / 0.28)))
        d.text((63, y + 4), big, font=f, fill=(0, 0, 0))
        d.text((60, y), big, font=f, fill=ac)
        bbox = d.textbbox((60, y), big, font=f)
        ly = bbox[3] + 16
        w = int(min(320, f.getlength(big) * 0.55) * ease_out(lt / 0.35))
        if w:
            d.rectangle([60, ly, 60 + w, ly + 8], fill=ac)
        return
    d.text((44, 350), "“", font=font(240), fill=(ac[0] // 4, ac[1] // 4, ac[2] // 4))
    draw_eyebrow(d, 60, 600, b.get("eyebrow") or "", 28, ac, ac)
    big = b.get("big") or ""
    start = 200 if len(big) <= 4 else 172 if len(big) <= 6 else 140
    f, size = fit_big(big, start=start, min_size=64, maxw=960)
    y = 690 + int(12 * (1 - ease_out(lt / 0.28)))
    d.text((63, y + 4), big, font=f, fill=(0, 0, 0))
    d.text((60, y), big, font=f, fill=ac)
    bbox = d.textbbox((60, y), big, font=f)
    ly = bbox[3] + 18
    w = int(min(320, f.getlength(big) * 0.55) * ease_out(lt / 0.35))
    if w:
        d.rectangle([60, ly, 60 + w, ly + 8], fill=ac)


# ---------------------------------------------------------------- 结构版式
# 不依赖图片的“程序画”版式：数据/文案写在 beat 的 extras（元组第 10 位）里。
# 这些镜头一律用深色渐变底，不拿配图当背景——它们读起来是界面/图表，不是照片。
STAGE_LAYOUTS = ("chat", "layers", "flow", "compare", "bars", "kpi",
                 "list", "terminal", "quote")
STAGE_TOP = 536
STAGE_BOT = 1180

# 「视频 + 文字」的两种做法：
#  1) 文字类（text/quote/data）：大字在上，原片按**原始画幅**放在 y=470–1234 的满幅窗口里。
#     这批素材是 1.414:1，硬裁 9:16 只剩 40% 宽——实测鸽子被裁成一面白墙、猫只剩一截，
#     所以不做竖裁，宁可把文字挪到画面上方。
#  2) 图表类（list/compare/bars/chat/...）：面板要占住 536–1180，原片只能当模糊底，
#     否则图表和画面互相抢；压暗 + 高斯模糊后只保留运动感。
CLIP_WINDOW_LAYOUTS = {"text", "quote", "data"}
CLIP_BG_LAYOUTS = {"list", "compare", "bars", "kpi",
                   "chat", "flow", "layers", "terminal"}
WIN_Y, WIN_H = 470, 764          # 满幅原片窗口（1080 × 764 = 1.414:1，不裁不拉伸）


def clamp01(x):
    return max(0.0, min(1.0, x))


def ellip(text, f, maxw):
    """按像素宽度截断并加省略号，保证任何版式都不会把字顶出安全区。"""
    if f.getlength(text) <= maxw:
        return text
    s = ""
    for ch in text:
        if f.getlength(s + ch + "…") > maxw:
            break
        s += ch
    return s + "…"


NO_LINE_START = "，。！？、；：）》」』】·…,.!?;:)]}"


def _tokens(text):
    """把中英混排切成“字”和“整词”：Agent / macOS / 29.5% 不能被拆到两行。"""
    out, buf = [], ""
    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch in "+-_.%/'"):
            buf += ch
        else:
            if buf:
                out.append(buf)
                buf = ""
            out.append(ch)
    if buf:
        out.append(buf)
    return out


def wrap_cjk(text, f, maxw):
    """按像素换行，但不让行首落在标点上、也不拆英文词。"""
    lines = []
    for raw in text.split("\n"):
        cur = ""
        for tok in _tokens(raw):
            if not cur:
                cur = tok
            elif f.getlength(cur + tok) <= maxw:
                cur += tok
            elif tok in NO_LINE_START:
                cur += tok            # “，。”不许另起一行
            else:
                lines.append(cur)
                cur = tok
        if cur:
            lines.append(cur)
    return lines


def fit_lines(text, f, maxw, maxlines=2):
    lines = wrap_cjk(text, f, maxw)
    if len(lines) <= maxlines:
        return lines
    lines = lines[:maxlines]
    last = lines[-1]
    while last and f.getlength(last + "…") > maxw:
        last = last[:-1]
    lines[-1] = last + "…"
    return lines


def paste_alpha(frame, layer, xy, a):
    """按 alpha 把一层 RGBA 贴进 RGB 帧（气泡/卡片入场用）。"""
    if a <= 0.01:
        return
    if a >= 0.995:
        frame.paste(layer, xy, layer)
        return
    lay = layer.copy()
    lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a)))
    frame.paste(lay, xy, lay)


def draw_chat(frame, b, lt):
    """群聊消息流：左人右 AI，气泡逐条出现，最后一条带“正在输入”。

    extras = {"title","badge","msgs":[{"who","role","text","tag"}]}
    """
    ex = b.get("extras") or {}
    ac = accent(b)
    msgs = ex.get("msgs") or []
    d = ImageDraw.Draw(frame)
    y0 = STAGE_TOP
    d.rounded_rectangle([60, y0, 1020, y0 + 54], radius=14, fill=(19, 25, 35),
                        outline=(44, 54, 70), width=2)
    d.text((84, y0 + 14), ellip(ex.get("title", "工作群"), font(26, False), 700),
           font=font(26, False), fill=(176, 187, 202))
    d.text((998, y0 + 16), ex.get("badge", "群聊"), font=font(22, False),
           fill=(118, 130, 148), anchor="ra")

    size = 30
    maxw = 660
    # 每条消息上方还要放名字（34px），所以舞台从标题条下 34px 才开始算
    avail = STAGE_BOT - (y0 + 54) - 34

    def build(size):
        f = font(size, False)
        pad = max(12, int(size * 0.58))
        lh = int(size * 1.36)
        items = []
        for m in msgs:
            lines = fit_lines(m.get("text", ""), f, maxw, 3)
            bh = pad * 2 + lh * len(lines)
            items.append((m, lines, bh, pad, lh))
        total = sum(it[2] + 46 for it in items)
        return f, items, total

    f, items, total = build(size)
    while total > avail and size > 22:
        size -= 2
        f, items, total = build(size)
    gap = int(min(40, max(0, (avail - total) / max(1, len(items) - 1)))) if len(items) > 1 else 0
    dur = max(1.2, float(b.get("duration") or 2.0))
    step = min(0.5, dur * 0.55 / max(1, len(items)))
    yy = y0 + 54 + 40
    last_agent = bool(items) and items[-1][0].get("role") == "agent"
    for i, (m, lines, bh, pad, lh) in enumerate(items):
        appear = i * step
        a = clamp01((lt - appear) / 0.22)
        role = m.get("role", "user")
        if a <= 0:
            if i == len(items) - 1 and last_agent:
                # 还没发出来：先给“正在输入”的三点，别让画面空着
                for k in range(3):
                    cx = 940 - k * 30
                    rad = 6 + 2 * abs(math.sin(lt * 5 + k * 1.1))
                    d.ellipse([cx - rad, yy + 14 - rad, cx + rad, yy + 14 + rad],
                              fill=(96, 112, 132))
            continue
        layer = Image.new("RGBA", (W, bh + 40), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        name_f = font(23, False)
        if role == "agent":
            color = ac
            fill = (int(ac[0] * 0.14) + 12, int(ac[1] * 0.14) + 15, int(ac[2] * 0.14) + 20)
            outl = (int(ac[0] * 0.62), int(ac[1] * 0.62), int(ac[2] * 0.62))
            name_x, anchor = 978, "ra"
        else:
            color = (152, 164, 184)
            fill = (28, 34, 46)
            outl = (62, 74, 92)
            name_x, anchor = 102, "la"
        who = m.get("who", "")
        ld.text((name_x, 2), who, font=name_f, fill=color, anchor=anchor)
        tag = m.get("tag")
        if tag:
            cf = font(20, False)
            cw = cf.getlength(tag) + 20
            tw = name_f.getlength(who)
            cx = name_x + tw + 10 if anchor == "la" else name_x - tw - 10 - cw
            ld.rounded_rectangle([cx, 1, cx + cw, 29], radius=14,
                                 fill=(int(ac[0] * 0.28), int(ac[1] * 0.28), int(ac[2] * 0.28)))
            ld.text((cx + 10, 15), tag, font=cf, fill=ac, anchor="lm")
        textw = max((f.getlength(l) for l in lines), default=0)
        bw = min(maxw + 2 * pad, int(textw) + 2 * pad)
        bx0 = 978 - bw if role == "agent" else 102
        bx1 = bx0 + bw
        ld.rounded_rectangle([bx0, 34, bx1, 34 + bh], radius=18, fill=fill,
                             outline=outl, width=2)
        ty = 34 + pad
        for ln in lines:
            ld.text((bx0 + pad, ty), ln, font=f, fill=(238, 244, 250))
            ty += lh
        paste_alpha(frame, layer, (0, yy - 34 + int(10 * (1 - a))), a)
        yy += bh + 46 + gap


def draw_layers(frame, b, lt):
    """分层架构：上层调度 + 下层并列工位 + 分流箭头，逐层点亮。

    extras = {"top":{"label","sub","chips":[]}, "bottom":[{"label","lines":[]}], "note":""}
    """
    ex = b.get("extras") or {}
    ac = accent(b)
    d = ImageDraw.Draw(frame)
    top = ex.get("top") or {}
    p = ease_out(clamp01(lt / 0.45))
    dy = int(18 * (1 - p))
    x0, x1 = 60, 1020
    y0, y1 = STAGE_TOP, STAGE_TOP + 186
    d.rounded_rectangle([x0, y0 + dy, x1, y1 + dy], radius=22, fill=(18, 24, 34),
                        outline=(int(ac[0] * 0.55), int(ac[1] * 0.55), int(ac[2] * 0.55)),
                        width=2)
    d.text((x0 + 30, y0 + 18 + dy), top.get("label", "Router"), font=font(40), fill=ac)
    d.text((x0 + 30, y0 + 72 + dy), ellip(top.get("sub", ""), font(25, False), 880),
           font=font(25, False), fill=(168, 179, 196))
    cx = x0 + 30
    for i, c in enumerate(top.get("chips") or []):
        a = clamp01((lt - 0.22 - i * 0.1) / 0.2)
        if a <= 0:
            continue
        cf = font(23, False)
        cw = cf.getlength(c) + 26
        if cx + cw > x1 - 24:
            break
        d.rounded_rectangle([cx, y0 + 124 + dy, cx + cw, y0 + 158 + dy], radius=17,
                            fill=(int(ac[0] * 0.13 * a) + 14, int(ac[1] * 0.13 * a) + 18,
                                  int(ac[2] * 0.13 * a) + 24))
        d.text((cx + 13, y0 + 141 + dy), c, font=cf, fill=(222, 232, 244), anchor="lm")
        cx += cw + 12

    items = ex.get("bottom") or []
    n = max(1, len(items))
    gap = 14
    bw = (x1 - x0 - gap * (n - 1)) / n
    by0 = y1 + 92
    bh = ex.get("bottom_h", 196)
    bus_y = y1 + 46
    trunk = clamp01(lt / 0.3)
    d.line([(540, y1 + 2), (540, y1 + 2 + 44 * trunk)], fill=(72, 84, 104), width=3)
    if trunk >= 1:
        d.line([(x0 + bw / 2, bus_y), (x0 + (n - 1) * (bw + gap) + bw / 2, bus_y)],
               fill=(72, 84, 104), width=3)
    for i, it in enumerate(items):
        bx0 = x0 + i * (bw + gap)
        bx1 = bx0 + bw
        acx = bx0 + bw / 2
        a = clamp01((lt - 0.4 - i * 0.12) / 0.28)
        if a <= 0:
            continue
        off = int(14 * (1 - a))
        if trunk >= 1:
            d.line([(acx, bus_y), (acx, by0 - 12 + off)], fill=(72, 84, 104), width=3)
            d.polygon([(acx - 7, by0 - 18 + off), (acx + 7, by0 - 18 + off), (acx, by0 - 8 + off)],
                      fill=ac)
        last = i == n - 1
        fill = ((int(ac[0] * 0.20) + 10, int(ac[1] * 0.20) + 12, int(ac[2] * 0.20) + 16)
                if last else (20, 26, 37))
        d.rounded_rectangle([bx0, by0 + off, bx1, by0 + bh + off], radius=18, fill=fill,
                            outline=(int(ac[0] * 0.55), int(ac[1] * 0.55), int(ac[2] * 0.55))
                            if last else (56, 68, 86), width=2)
        d.text((bx0 + 20, by0 + 20 + off), ellip(it.get("label", ""), font(29), bw - 40),
               font=font(29), fill=(236, 241, 248))
        rows = it.get("lines") or ([it["sub"]] if it.get("sub") else [])
        for j, s in enumerate(rows[:4]):
            d.text((bx0 + 20, by0 + 66 + j * 34 + off),
                   ellip(s, font(22, False), bw - 40), font=font(22, False),
                   fill=(160, 172, 190))
    note = ex.get("note")
    if note:
        d.text((60, by0 + bh + 18), ellip(note, font(23, False), 940),
               font=font(23, False), fill=(140, 152, 170))


def draw_flow(frame, b, lt):
    """纵向流程：编号 + 连接线，按顺序推进，最后一步高亮。

    extras = {"steps":[{"t":"群聊吐槽","s":"Trigger · 没人 @"}], "note":""}
    """
    ex = b.get("extras") or {}
    ac = accent(b)
    steps = ex.get("steps") or []
    n = max(1, len(steps))
    d = ImageDraw.Draw(frame)
    top = STAGE_TOP
    avail = STAGE_BOT - top
    rh = min(124, int((avail - 8 * (n - 1)) / n))
    gap = max(4, int((avail - rh * n) / max(1, n - 1))) if n > 1 else 0
    for i, s in enumerate(steps):
        y = top + i * (rh + gap)
        a = clamp01((lt - i * 0.14) / 0.28)
        if a <= 0:
            continue
        off = int(12 * (1 - a))
        last = i == n - 1
        if i < n - 1:
            d.line([(104, y + rh // 2 + 24), (104, y + rh + gap + 20)],
                   fill=(58, 70, 88), width=3)
        cy = y + rh // 2 + off
        d.ellipse([104 - 24, cy - 24, 104 + 24, cy + 24],
                  fill=((int(ac[0] * 0.15) + 10, int(ac[1] * 0.15) + 12,
                         int(ac[2] * 0.15) + 16) if last else (28, 34, 46)),
                  outline=ac if last else (70, 82, 100), width=2)
        d.text((104, cy), f"{i + 1}", font=font(26),
               fill=ac if last else (170, 182, 198), anchor="mm")
        d.text((152, y + 16 + off), ellip(s.get("t", ""), font(34), 820), font=font(34),
               fill=(240, 244, 250) if last else (210, 218, 230))
        d.text((152, y + 64 + off), ellip(s.get("s", ""), font(23, False), 820),
               font=font(23, False), fill=(150, 162, 182))
    note = ex.get("note")
    if note:
        d.text((152, top + n * (rh + gap) + 4), ellip(note, font(23, False), 820),
               font=font(23, False), fill=(136, 148, 166))


def draw_compare(frame, b, lt):
    """左右对比：两栏标题 + 要点，中间 VS。

    extras = {"left":{"kicker","title","items":[]},
              "right":{...}, "vs":"VS"}
    """
    ex = b.get("extras") or {}
    ac = accent(b)
    d = ImageDraw.Draw(frame)
    cols = [(60, 500), (580, 1020)]
    for k, key in enumerate(("left", "right")):
        c = ex.get(key) or {}
        a = clamp01((lt - k * 0.18) / 0.3)
        if a <= 0:
            continue
        x0, x1 = cols[k]
        off = int(16 * (1 - a))
        y0, y1 = STAGE_TOP + 8 + off, STAGE_TOP + 500 + off
        strong = key == "right"
        col = ac if strong else (150, 162, 182)
        d.rounded_rectangle([x0, y0, x1, y1], radius=20,
                            fill=((int(ac[0] * 0.1) + 12, int(ac[1] * 0.1) + 14,
                                   int(ac[2] * 0.1) + 18) if strong else (22, 28, 40)),
                            outline=col if strong else (58, 70, 88), width=2)
        d.text((x0 + 26, y0 + 20), ellip(c.get("kicker", ""), font(23, False), 380),
               font=font(23, False), fill=col)
        d.text((x0 + 26, y0 + 54), ellip(c.get("title", ""), font(35), 380),
               font=font(35), fill=(240, 244, 250))
        yy = y0 + 130
        for j, it in enumerate(c.get("items") or []):
            ia = clamp01((lt - (0.3 + k * 0.15 + j * 0.08)) / 0.22)
            if ia <= 0:
                break
            d.ellipse([x0 + 28, yy + 12, x0 + 38, yy + 22], fill=col)
            d.text((x0 + 54, yy), ellip(it, font(27, False), x1 - x0 - 84),
                   font=font(27, False), fill=(206, 214, 228))
            yy += 62
    va = clamp01((lt - 0.55) / 0.22)
    if va > 0:
        cy = STAGE_TOP + 238
        r = int(30 * (0.6 + 0.4 * va))
        d.ellipse([540 - r, cy - r, 540 + r, cy + r], fill=(10, 13, 19), outline=ac, width=3)
        d.text((540, cy - 2), ex.get("vs", "VS"), font=font(24), fill=ac, anchor="mm")


def draw_bars(frame, b, lt):
    """条形对比：数值条生长 + 右侧数值。

    extras = {"rows":[{"label","value","text","strong"}], "max":30, "note":""}
    """
    ex = b.get("extras") or {}
    ac = accent(b)
    rows = ex.get("rows") or []
    d = ImageDraw.Draw(frame)
    n = max(1, len(rows))
    maxv = float(ex.get("max") or max([float(r.get("value", 0)) for r in rows] + [1]))
    top = STAGE_TOP + 16
    rh = min(152, int((STAGE_BOT - top - 30) / n))
    f_lab = font(27, False)
    f_val = font(42)
    for i, r in enumerate(rows):
        y = top + i * rh
        a = clamp01((lt - i * 0.12) / 0.7)
        if a <= 0:
            continue
        val = float(r.get("value", 0))
        strong = r.get("strong", i == n - 1)
        col = ac if strong else (118, 132, 152)
        d.text((60, y), ellip(r.get("label", ""), f_lab, 690), font=f_lab, fill=(196, 205, 220))
        d.text((1020, y - 8), r.get("text") or f"{val:g}", font=f_val,
               fill=ac if strong else (226, 233, 244), anchor="ra")
        d.rounded_rectangle([60, y + 44, 940, y + 84], radius=20, fill=(30, 36, 48))
        bw = int(880 * min(1.0, val / maxv) * ease_out(a))
        if bw > 4:
            d.rounded_rectangle([60, y + 44, 60 + bw, y + 84], radius=20, fill=col)
    note = ex.get("note")
    if note:
        d.text((60, min(STAGE_BOT - 4, top + n * rh + 8)), ellip(note, font(23, False), 930),
               font=font(23, False), fill=(140, 152, 170))


def draw_kpi(frame, b, lt):
    """2–3 个关键数字并排（可 count-up）。

    extras = {"items":[{"v":"300","u":"条消息","l":"模拟环境"}], "note":""}
    """
    ex = b.get("extras") or {}
    ac = accent(b)
    items = ex.get("items") or []
    d = ImageDraw.Draw(frame)
    n = max(1, len(items))
    gap = 16
    w = (960 - gap * (n - 1)) / n
    top, h = STAGE_TOP + 30, 336
    for i, it in enumerate(items):
        a = clamp01((lt - i * 0.14) / 0.4)
        if a <= 0:
            continue
        off = int(18 * (1 - a))
        x0 = 60 + i * (w + gap)
        d.rounded_rectangle([x0, top + off, x0 + w, top + h + off], radius=20,
                            fill=(20, 26, 37), outline=(60, 72, 90), width=2)
        v = str(it.get("v", ""))
        m = re.match(r"^([+-]?)([0-9]+(?:\.[0-9]+)?)(.*)$", v)
        if m:
            sign, num, suf = m.group(1), float(m.group(2)), m.group(3)
            pr = smooth(clamp01(a * 1.7))
            dec = len(m.group(2).split(".")[1]) if "." in m.group(2) else 0
            v = sign + (f"{num * pr:.{dec}f}" if dec else f"{int(round(num * pr))}") + suf
        f, _ = fit_big(v, start=86, min_size=38, maxw=w - 44)
        d.text((x0 + w / 2, top + 104 + off), v, font=f, fill=ac, anchor="mm")
        if it.get("u"):
            d.text((x0 + w / 2, top + 178 + off), it["u"], font=font(26, False),
                   fill=(168, 180, 198), anchor="mm")
        ly = top + 238 + off
        for ln in fit_lines(it.get("l", ""), font(25, False), w - 44, 2):
            d.text((x0 + w / 2, ly), ln, font=font(25, False), fill=(150, 162, 182), anchor="mm")
            ly += 34
    note = ex.get("note")
    if note:
        d.text((60, top + h + 26), ellip(note, font(23, False), 930),
               font=font(23, False), fill=(140, 152, 170))


def draw_list(frame, b, lt):
    """清单：序号 + 标题 + 一行说明，逐行点亮。

    extras = {"items":[{"k":"连续","d":"跨群聊和 PR 保持上下文"}], "note":""}
    """
    ex = b.get("extras") or {}
    ac = accent(b)
    items = ex.get("items") or []
    d = ImageDraw.Draw(frame)
    n = max(1, len(items))
    top = STAGE_TOP + 4
    rh = min(146, int((STAGE_BOT - top) / n))
    for i, it in enumerate(items):
        y = top + i * rh
        a = clamp01((lt - i * 0.13) / 0.3)
        if a <= 0:
            continue
        off = int(10 * (1 - a))
        d.line([(60, y + rh - 2), (1020, y + rh - 2)], fill=(40, 48, 62), width=1)
        d.text((60, y + 16 + off), f"{i + 1:02d}", font=font(30), fill=ac)
        d.text((140, y + 8 + off), ellip(it.get("k", ""), font(40), 840),
               font=font(40), fill=(238, 243, 250))
        if it.get("d"):
            d.text((140, y + 70 + off), ellip(it["d"], font(24, False), 840),
                   font=font(24, False), fill=(152, 164, 182))
    note = ex.get("note")
    if note:
        d.text((60, top + n * rh + 6), ellip(note, font(23, False), 930),
               font=font(23, False), fill=(136, 148, 166))


def draw_terminal(frame, b, lt):
    """终端 / PR 卡：窗口标题 + diff 行 + 状态徽章。

    extras = {"title","lines":[{"k":"add|del|ctx|meta","t":"..."}],
              "status":"已合并","note":""}
    """
    ex = b.get("extras") or {}
    ac = accent(b)
    d = ImageDraw.Draw(frame)
    x0, y0, x1 = 60, STAGE_TOP, 1020
    rows = (ex.get("lines") or [])[:9]
    lh = 40
    # 窗口高度跟着 diff 行数走：行少就不要留一大块空面板
    y1 = y0 + 82 + lh * max(3, len(rows)) + 84
    d.rounded_rectangle([x0, y0, x1, y1], radius=18, fill=(13, 17, 23),
                        outline=(54, 66, 84), width=2)
    d.rounded_rectangle([x0, y0, x1, y0 + 54], radius=18, fill=(24, 30, 38))
    d.rectangle([x0, y0 + 34, x1, y0 + 54], fill=(24, 30, 38))
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse([x0 + 20 + i * 24, y0 + 19, x0 + 32 + i * 24, y0 + 31], fill=c)
    d.text((x0 + 110, y0 + 15), ellip(ex.get("title", "Terminal"), font(24, False), 760),
           font=font(24, False), fill=(168, 180, 198))
    f = font(24, False)
    yy = y0 + 82
    for i, ln in enumerate(rows):
        a = clamp01((lt - 0.1 - i * 0.05) / 0.18)
        if a <= 0:
            break
        k = ln.get("k", "ctx")
        txt = ln.get("t", "")
        if k == "add":
            d.rectangle([x0 + 8, yy - 5, x1 - 8, yy + lh - 9], fill=(20, 44, 30))
            fill, prefix = (150, 232, 168), "+ "
        elif k == "del":
            d.rectangle([x0 + 8, yy - 5, x1 - 8, yy + lh - 9], fill=(52, 24, 28))
            fill, prefix = (255, 160, 160), "- "
        elif k == "meta":
            fill, prefix = (120, 205, 225), ""
        else:
            fill, prefix = (168, 178, 194), "  "
        d.text((x0 + 22, yy), ellip(prefix + txt, f, x1 - x0 - 52), font=f, fill=fill)
        yy += lh
    st = ex.get("status")
    if st:
        a = clamp01((lt - 0.6) / 0.25)
        if a > 0:
            sf = font(26)
            bw = sf.getlength(st) + 40
            bx, by = x1 - 30 - bw, y1 - 68
            d.rounded_rectangle([bx, by, bx + bw, by + 46], radius=23,
                                fill=(int(ac[0] * 0.18), int(ac[1] * 0.18), int(ac[2] * 0.18)),
                                outline=ac, width=2)
            d.text((bx + 20, by + 22), st, font=sf, fill=ac, anchor="lm")
    if ex.get("note"):
        d.text((x0 + 2, y1 + 14), ellip(ex["note"], font(23, False), 940),
               font=font(23, False), fill=(146, 158, 176))


def draw_quote(frame, b, lt):
    """长引语：左侧竖条 + 出处，适合官方原话/金句。

    extras = {"text":"...","by":"Super-agent 官方哲学"}
    """
    ex = b.get("extras") or {}
    ac = accent(b)
    d = ImageDraw.Draw(frame)
    text = ex.get("text") or b.get("big") or ""
    # 引语是整段话，不能按“单行塞进 860px”去缩字号（会缩到 44px 还把句号甩到下一行）。
    # 按最多 3 行反推字号，并保证最后一行不是孤零零的标点。
    size = 54 if has_win(b) else 72
    while size > 40:
        f = font(size)
        lines = wrap_cjk(text, f, 860)
        tail = lines[-1].strip("。！？，、；：") if lines else ""
        if len(lines) <= 3 and (len(lines) == 1 or len(tail) >= 3):
            break
        size -= 4
    f = font(size)
    lines = fit_lines(text, f, 860, 3 if has_win(b) else 4)
    lh = int(size * 1.44)
    total = lh * len(lines)
    # 没有 big 时整块引语占满大字区 + 舞台区，不要顶在 536 以下留一大片空
    if has_win(b):
        top = 150
    else:
        top = 420 if not b.get("big") else STAGE_TOP + 20
    y = top if has_win(b) else top + max(0, (STAGE_BOT - top - 120 - total) // 2)
    p = ease_out(clamp01(lt / 0.4))
    bar_h = int((total + 6) * p)
    d.rectangle([58, y - 8, 64, y - 8 + bar_h], fill=ac)
    for i, ln in enumerate(lines):
        la = clamp01((lt - i * 0.07) / 0.25)
        if la <= 0:
            break
        d.text((98, y), ln, font=f, fill=(240, 245, 252),
               stroke_width=3, stroke_fill=(4, 6, 10))
        y += lh
    by = ex.get("by")
    if by:
        ba = clamp01((lt - 0.5) / 0.3)
        if ba > 0:
            d.text((98, y + 22), "—— " + by, font=font(26, False),
                   fill=(150, 162, 182))


STAGE_DRAW = {
    "chat": draw_chat,
    "layers": draw_layers,
    "flow": draw_flow,
    "compare": draw_compare,
    "bars": draw_bars,
    "kpi": draw_kpi,
    "list": draw_list,
    "terminal": draw_terminal,
    "quote": draw_quote,
}


def cover_card(frame, b, lt):
    """竖幅照片整屏铺满（cover），上下渐变 scrim 给大字和字幕让位。

    近 9:16 的照片放进 16:9 卡片会在两侧留几百像素空；整屏 cover 只裁掉几个百分点。
    """
    src = fg_for(b["img"])
    img = ImageOps.fit(src, (W, H), method=Image.LANCZOS)
    arr = np.asarray(img.resize((90, 160), Image.BILINEAR), dtype=np.float32)
    mean = float(arr.mean())
    base = int(min(120, max(45, 30 + (mean - 60) * 0.55)))
    ys = np.arange(H, dtype=np.float32)
    top_a = (base + 175) * np.clip((700 - ys) / 700.0, 0, 1) ** 0.95
    bot_a = (base + 150) * np.clip((ys - 1150) / (H - 1150.0), 0, 1) ** 1.25
    alpha = np.clip(base + np.maximum(top_a, bot_a), 0, 232).astype(np.uint8)
    rows = Image.fromarray(np.repeat(alpha[:, None], W, axis=1), "L")
    frame.paste(Image.composite(Image.new("RGB", (W, H), (5, 5, 7)), img, rows), (0, 0))
    return frame


CLIPS = BASE / "clips"
_CLIP_META = {}


def clip_meta(cid):
    if cid not in _CLIP_META:
        _CLIP_META[cid] = json.loads(
            (CLIPS / cid / "meta.json").read_text(encoding="utf-8"))
    return _CLIP_META[cid]


def clip_card(frame, b, lt, y=540, h=608):
    """把原片镜头按 beat 时长线性铺进图片卡（静音 B-roll）。

    不做循环、不在结尾冻结：整段素材按 beat 时长映射，短素材自然放慢，
    每帧都在动。推近交给素材本身，所以这个镜头不再套整帧 slow_zoom。
    """
    cid = b["clip"]
    meta = clip_meta(cid)
    n = int(meta["frames"])
    dur = max(0.2, float(b.get("duration") or 1.0))
    idx = int(min(n - 1, max(0.0, lt / dur) * n)) + 1
    im = Image.open(CLIPS / cid / f"f_{idx:04d}.jpg").convert("RGB")
    if im.size != (W, h):
        im = im.resize((W, h), Image.LANCZOS)
    frame.paste(im, (0, y))
    d = ImageDraw.Draw(frame)
    d.rectangle([0, y, W, y + 3], fill=accent(b))
    return frame


_WIDE = {}


def clip_is_wide(cid):
    """片段的画幅决定「视频+文字」的做法：宽片段进窗口，竖片段只当模糊底。"""
    if cid not in _WIDE:
        try:
            _WIDE[cid] = Image.open(CLIPS / cid / "f_0001.jpg").width > 900
        except Exception:
            _WIDE[cid] = False
    return _WIDE[cid]


def has_win(b):
    cid = b.get("clip") or ""
    return bool(cid) and b["layout"] in (CLIP_WINDOW_LAYOUTS | CLIP_BG_LAYOUTS) \
        and clip_is_wide(cid)


def clip_bg_fill(b, lt, dim=0.62, stage=True):
    """图表版式的整屏底：9:16 铺满 + 高斯模糊 + 压暗，只保留「画面在动」。"""
    cid = b["clip"]
    meta = clip_meta(cid)
    n = int(meta["frames"])
    dur = max(0.2, float(b.get("duration") or 1.0))
    idx = int(min(n - 1, max(0.0, lt / dur) * n)) + 1
    im = Image.open(CLIPS / cid / f"f_{idx:04d}.jpg").convert("RGB")
    im = ImageOps.fit(im, (W, H), method=Image.LANCZOS).filter(
        ImageFilter.GaussianBlur(26))
    im = ImageEnhance.Brightness(im).enhance(dim)
    ys = np.arange(H, dtype=np.float32)
    a = 0.22 * (1 - np.clip(ys / 240.0, 0, 1))
    a += 0.55 * np.clip((ys - 1150) / 170.0, 0, 1)
    a += 0.30 * np.clip((ys - 470) / 120.0, 0, 1) * (1 - np.clip((ys - 1150) / 100.0, 0, 1))
    a = np.clip(a, 0, 0.86)
    rows = Image.fromarray(np.repeat((a * 255).astype(np.uint8)[:, None], W, axis=1), "L")
    return Image.composite(Image.new("RGB", (W, H), (4, 6, 10)), im, rows)


def clip_window(frame, b, lt):
    """文字类版式底下的「满幅原片窗口」：1080×764，按原始画幅贴，不裁不拉伸。

    画面上方留给大字（y≈130–420），下方留给字幕（y≈1400）。窗口本身自带
    逐帧推进，所以这些镜头不再套整帧推近。
    """
    cid = b["clip"]
    meta = clip_meta(cid)
    n = int(meta["frames"])
    dur = max(0.2, float(b.get("duration") or 1.0))
    idx = int(min(n - 1, max(0.0, lt / dur) * n)) + 1
    im = Image.open(CLIPS / cid / f"f_{idx:04d}.jpg").convert("RGB")
    if im.size != (W, WIN_H):
        im = ImageOps.fit(im, (W, WIN_H), method=Image.LANCZOS)
    frame.paste(im, (0, WIN_Y))
    d = ImageDraw.Draw(frame)
    d.rectangle([0, WIN_Y, W, WIN_Y + 3], fill=accent(b))
    d.rectangle([0, WIN_Y, 2, WIN_Y + WIN_H], fill=(30, 36, 48))
    d.rectangle([0, WIN_Y + WIN_H - 2, W, WIN_Y + WIN_H], fill=(18, 22, 30))
    return frame


def clip_phone_card(frame, b, lt, y=470):
    """竖屏/竖构图片段：整帧进「设备卡」，**不裁高度**。

    手机录屏（600×800）和从 16:9 里裁出来的竖构图资产卡（400×640）都走这里：
    片段帧按原比例摆放，圆角 + 描边 + 投影，看上去是一块屏幕，而不是被切掉一截的截图。
    片段帧的分辨率就是卡片尺寸（`make_clips.py` 的 `CLIP_SIZE` 决定），这里不再缩放。
    """
    cid = b["clip"]
    meta = clip_meta(cid)
    n = int(meta["frames"])
    dur = max(0.2, float(b.get("duration") or 1.0))
    idx = int(min(n - 1, max(0.0, lt / dur) * n)) + 1
    im = Image.open(CLIPS / cid / f"f_{idx:04d}.jpg").convert("RGB")
    w, h = im.size
    x = (W - w) // 2
    # 投影
    pad = 30
    mask = Image.new("L", (w + pad * 2, h + pad * 2), 0)
    ImageDraw.Draw(mask).rectangle([pad, pad, pad + w - 1, pad + h - 1], fill=105)
    mask = mask.filter(ImageFilter.GaussianBlur(16))
    frame.paste((0, 0, 0), (x - pad, y - pad + 10), mask)
    # 圆角 + 描边
    rad = 26
    rmask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(rmask).rounded_rectangle([0, 0, w - 1, h - 1], radius=rad, fill=255)
    frame.paste(im, (x, y), rmask)
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=rad,
                        outline=(84, 96, 116), width=2)
    d.rectangle([x, y, W - x, y + 3], fill=accent(b))
    return frame


def draw_diptych(frame, b, lt):
    """左右对照：两张图并排 + 各自标签，讲「换装前 / 换装后」。

    extras = {"left": {"img","label"},"right": {"img","label"},"note":""}
    两张图按同高摆放（等高更整齐），各自带 1px 描边和标签下划线。
    图从片段里抽：`ffmpeg -ss <t> -i src -frames:v 1 -vf crop=w:h:x:y -y assets/x.png`
    """
    ex = b.get("extras") or {}
    ac = accent(b)
    d = ImageDraw.Draw(frame)
    y0, h = 508, 650
    sides = []
    for key in ("left", "right"):
        c = ex.get(key) or {}
        src = fg_for(c["img"])
        nw = max(1, int(round(src.width * h / src.height)))
        sides.append((src.resize((nw, h), Image.LANCZOS), nw, c))
    total = sum(nw for _, nw, _ in sides) + ex.get("gap", 34)
    x = (W - total) // 2
    for i, (art, nw, c) in enumerate(sides):
        p = ease_out(clamp01((lt - i * 0.18) / 0.36))
        off = int(16 * (1 - p))
        lab = c.get("label") or ""
        if lab:
            draw_eyebrow(d, x, y0 - 46 + off, lab, 27, (208, 216, 228), ac)
        frame.paste(art, (x, y0 + off))
        d.rectangle([x, y0 + off, x + nw - 1, y0 + h + off - 1],
                    outline=(74, 84, 100), width=2)
        x += nw + ex.get("gap", 34)
    note = ex.get("note")
    if note:
        d.text((60, y0 + h + 26), ellip(note, font(23, False), 940),
               font=font(23, False), fill=(142, 154, 172))
    return frame


def poster_card(frame, b, lt, y=540, h=800):
    """竖构图插画（原图左右大片空白）：卡片按插画比例收窄，让图铺满卡片。

    宽卡片 contain 一张 0.73 比例的竖图，两侧会剩几百像素的空，观众看到的是
    “一张纸上画了个小人”。改成窄卡片后插画顶到卡片四边，留白交给深色背景；
    前提是先用 image_margins.py 把原图的空白边裁掉（比例已是内容比例）。
    """
    src = fg_for(b["img"])
    nw = max(1, int(round(src.width * h / src.height)))
    art = src.resize((nw, h), Image.LANCZOS)
    x = (W - nw) // 2
    pad = 26
    mask = Image.new("L", (nw + pad * 2, h + pad * 2), 0)
    ImageDraw.Draw(mask).rectangle([pad, pad, nw + pad, h + pad], fill=125)
    mask = mask.filter(ImageFilter.GaussianBlur(14))
    frame.paste((0, 0, 0), (x - pad, y - pad + 8), mask)
    frame.paste(art, (x, y))
    d = ImageDraw.Draw(frame)
    # 不加顶部强调条：它离大标题下划线只有十几像素，会看成“两条线”
    d.rectangle([x, y, x + nw - 1, y + h - 1], outline=(74, 84, 100), width=2)
    return frame


def image_card(frame, b, lt, y=540, h=608, zoom_max=0.10, duration=None):
    """整图按比例放进卡片：不裁切、不拉变形，保留图片自带说明文字。

    16:9 素材正好铺满；竖图/方图按 contain 摆中间，空白处用同一张图放大压暗填底。
    运动交给整帧 slow_zoom + 光扫，避免把图上文字切掉。
    """
    src = fg_for(b["img"])
    scale = min(W / src.width, h / src.height)
    nw, nh = max(1, int(round(src.width * scale))), max(1, int(round(src.height * scale)))
    if (nw, nh) != (W, h):
        gap = h - nh
        if gap > h * 0.28:
            # 3:1、4:1 这种超宽横幅：同图 cover 要放大 2 倍以上，模糊填充会被拉成
            # 一片刺眼色块，像渲染故障。改用深色卡底 + 上下两条细边，读起来是
            # “贴在深色卡纸上的一张图”，而不是坏掉的背景。
            mat = Image.new("RGB", (W, h), (13, 17, 25))
            md = ImageDraw.Draw(mat)
            md.rectangle([0, 0, W, 1], fill=(52, 62, 80))
            md.rectangle([0, h - 1, W, h], fill=(52, 62, 80))
            frame.paste(mat, (0, y))
        else:
            cover = ImageOps.fit(src, (W, h), method=Image.LANCZOS).filter(
                ImageFilter.GaussianBlur(max(16, int(h * 0.10))))
            shade = Image.new("RGBA", (W, h), (0, 0, 0, 150))
            frame.paste(Image.alpha_composite(cover.convert("RGBA"), shade).convert("RGB"), (0, y))
    frame.paste(src.resize((nw, nh), Image.LANCZOS), ((W - nw) // 2, y + (h - nh) // 2))
    d = ImageDraw.Draw(frame)
    d.rectangle([0, y, W, y + 3], fill=accent(b))
    return frame


def draw_caption(frame, b, t):
    if not (b["start"] - 0.05 <= t <= b["end"] + 0.12):
        return
    rgb, mask = cap_for(b)
    frame.paste(rgb, (0, 1255), mask)


def header(frame, label):
    d = ImageDraw.Draw(frame)
    d.rectangle([58, 76, 66, 108], fill=ORANGE)
    d.text((82, 76), label, font=font(28), fill=(255, 166, 104))
    d.text((W - 58, 80), BRAND, font=font(24, False), fill=(150, 160, 176), anchor="ra")


def progress(frame, t, total):
    d = ImageDraw.Draw(frame)
    d.rectangle([0, 0, W, 6], fill=(255, 255, 255, 24))
    x = int(W * min(1, t / total))
    if x:
        d.rectangle([0, 0, x, 6], fill=ORANGE)
    for s in SCENES[1:]:
        xx = int(W * s["start"] / total)
        d.rectangle([xx - 1, 0, xx + 1, 14], fill=(20, 24, 32))


def light_sweep(frame, prog):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    x = int(-420 + (W + 900) * max(0.0, min(1.0, prog)))
    d.polygon([(x, 0), (x + 240, 0), (x - 220, H), (x - 500, H)], fill=(95, 175, 225, 9))
    return Image.alpha_composite(frame.convert("RGBA"), ov).convert("RGB")


def slow_zoom(frame, prog, amt=0.045):
    z = 1.0 + amt * max(0.0, min(1.0, prog))
    sw, sh = W / z, H / z
    x0, y0 = (W - sw) / 2, (H - sh) / 2
    return frame.transform((W, H), Image.AFFINE, (1 / z, 0, x0, 0, 1 / z, y0), resample=Image.BILINEAR)


def beat_frame(b, lt, t, vis_dur=None):
    img = b.get("img")
    # poster/cover 不要整屏模糊底；结构版式（chat/layers/...）一律用深色渐变底：
    # 它们读起来是界面/图表，垫一张照片反而抢字。
    if b["layout"] in ("data", "poster", "cover", "phone", "diptych") \
            or b["layout"] in STAGE_LAYOUTS:
        bg_img = None
    else:
        bg_img = img
    has_clip = bool(b.get("clip")) and (CLIPS / b["clip"] / "meta.json").exists()
    is_stage = b["layout"] in STAGE_LAYOUTS
    win_clip = has_clip and (b["layout"] in CLIP_WINDOW_LAYOUTS
                             or b["layout"] in CLIP_BG_LAYOUTS) and clip_is_wide(b["clip"])
    bg_clip = has_clip and not win_clip and (b["layout"] in CLIP_BG_LAYOUTS
                                             or b["layout"] in CLIP_WINDOW_LAYOUTS)
    if win_clip:
        frame = BG.copy()
        clip_window(frame, b, lt)
    elif bg_clip:
        frame = clip_bg_fill(b, lt)
    elif bg_img:
        frame = bg_for(bg_img).copy()
    else:
        frame = BG.copy()
    if b["layout"] == "phone" and has_clip:
        clip_phone_card(frame, b, lt)
    elif b["layout"] == "cover" and img:
        cover_card(frame, b, lt)
    elif b["layout"] == "poster" and img:
        poster_card(frame, b, lt)
    elif bg_clip or win_clip:
        pass                      # 整屏底 / 满幅窗口已经在上面画过，不再放卡片
    elif has_clip:
        clip_card(frame, b, lt, y=540 if b["layout"] != "full" else 470,
                  h=608 if b["layout"] != "full" else 760)
    elif b["layout"] in ("card", "hook", "full") and img:
        image_card(frame, b, lt, y=540 if b["layout"] != "full" else 470,
                   h=608 if b["layout"] != "full" else 760,
                   duration=vis_dur)
    if b["layout"] == "text" and not (bg_clip or win_clip):
        # 只在底图偏亮时压暗；深色底图再加 scrim 只会让画面发灰
        mean = bg_mean(bg_img)
        alpha = int(min(140, max(0, (mean - 42) * 2.6)))
        if alpha:
            dark = Image.new("RGBA", (W, H), (3, 5, 9, alpha))
            frame = Image.alpha_composite(frame.convert("RGBA"), dark).convert("RGB")
    if b["layout"] == "data":
        draw_data(frame, b, lt)
    else:
        draw_big(frame, b, lt)
    # 结构版式：大字画完之后在下方舞台区画界面/图表（自带分段入场动画）
    if b["layout"] in STAGE_DRAW:
        STAGE_DRAW[b["layout"]](frame, b, lt)
    elif b["layout"] == "diptych":
        draw_diptych(frame, b, lt)
    # 每个镜头单独做一次线性推近 + 光扫：按 beat 计时，切镜头时重置
    # （按场景计时会摊到 20–30 秒上，每帧只动 0.0001，看起来就是静止画面）
    prog = (t - b["start"]) / max(0.9, b["end"] - b["start"])
    if not has_clip:
        # 静帧/文字/数据卡的移动靠整帧线性推近；片段镜头自己就在动，不再裁边。
        # 结构版式的推近要更轻：推太狠会把卡片边缘和最右一列数字挤出安全区。
        amt = 0.05 if b["layout"] in ("text", "data") else 0.035
        if b["layout"] in STAGE_LAYOUTS:
            amt = 0.022
        frame = slow_zoom(frame, prog, amt)
    frame = light_sweep(frame, prog)
    draw_caption(frame, b, t)
    return frame


def draw_data(frame, b, lt):
    """通用数据卡：主数字 count-up + 说明行 + 展开的强调线，整块上下居中。"""
    d = ImageDraw.Draw(frame)
    ac = accent(b)

    big = b.get("big") or ""
    m = re.match(r"^([0-9][0-9,]*(?:\.[0-9]+)?)(.*)$", big)
    animatable = bool(m) and not re.search(r"\d", m.group(2))
    p = smooth(min(1.0, lt / 0.55))
    if animatable:
        raw, suffix = m.group(1), m.group(2)
        target = float(raw.replace(",", ""))
        cur = target * p
        dec = len(raw.split(".")[1]) if "." in raw else 0
        shown = f"{cur:.{dec}f}" if dec else f"{int(round(cur))}"
        text = shown + suffix
    else:
        text = big

    f, size = fit_big(text, start=200, min_size=88, maxw=940)
    note = b.get("note") or ""
    bbox0 = d.textbbox((0, 0), text, font=f)
    num_h = bbox0[3] - bbox0[1]
    eye_h = 60
    note_h = 56 if note else 0
    if has_win(b):
        top = 140
    else:
        block = eye_h + 18 + num_h + (note_h + 26 if note else 0) + 46 + 34
        top = 260 + max(0, int((820 - block) / 2))

    label = b.get("eyebrow") or "关键数字"
    draw_eyebrow(d, 60, top, label, 32, MUTED, ac)

    ny = top + eye_h + 18
    d.text((62, ny), text, font=f, fill=ac, stroke_width=4, stroke_fill=(4, 6, 10))
    y = ny + bbox0[3]
    if has_win(b):
        # 说明行放到原片窗口下面，别压在画面上
        if note:
            d.text((60, WIN_Y + WIN_H + 16), note, font=font(34, False),
                   fill=(206, 214, 226))
        w = int(320 * ease_out(lt / 0.6))
        if w:
            d.rectangle([62, WIN_Y + WIN_H + 62, 62 + w, WIN_Y + WIN_H + 68], fill=ac)
        return
    if note:
        d.text((62, y + 18), note, font=font(36, False), fill=(226, 231, 240),
               stroke_width=3, stroke_fill=(4, 6, 10))
        y += 18 + note_h
    w = int(360 * ease_out(lt / 0.6))
    if w:
        d.rectangle([62, y + 26, 62 + w, y + 32], fill=ac)
    d.text((60, y + 46), DATA_SOURCE, font=font(28, False), fill=(140, 150, 166))


def title_card(t):
    frame = BG.copy()
    d = ImageDraw.Draw(frame)
    p = ease_out(min(1, t / 0.35))
    # 装饰数字按长度自动缩：230px 的 "0.5g" 会贴右边缘被裁
    gsize = 420
    while gsize > 120 and font(gsize).getlength(TITLE_GHOST) > 640:
        gsize -= 20
    d.text((W - 72, 240), TITLE_GHOST, font=font(gsize), fill=(18, 25, 36),
           stroke_width=2, stroke_fill=(95, 48, 26), anchor="ra")
    y = 720 + int(24 * (1 - p))
    d.text((66, y + 5), TITLE_MAIN, font=font(112), fill=(0, 0, 0))
    d.text((60, y), TITLE_MAIN, font=font(112), fill=WHITE)
    bb = d.textbbox((60, y), TITLE_MAIN, font=font(112))
    d.rectangle([64, bb[3] + 20, 64 + int(300 * p), bb[3] + 28], fill=ORANGE)
    d.text((62, y + 178), TITLE_SUB, font=font(38, False), fill=(214, 220, 230))
    d.text((62, y + 250), TITLE_KICKER, font=font(28, False), fill=(130, 142, 160))
    d.text((62, 1812), TITLE_CREDIT, font=font(22, False), fill=(90, 100, 116))
    return frame


def endcard():
    frame = BG.copy()
    d = ImageDraw.Draw(frame)
    d.text((W // 2, 700), END_L1, font=font(82), fill=WHITE, anchor="mm")
    d.text((W // 2, 830), END_L2, font=font(100), fill=ORANGE, anchor="mm")
    d.rectangle([W // 2 - 90, 920, W // 2 + 90, 926], fill=CYAN)
    d.text((W // 2, 1040), END_Q, font=font(38, False), fill=MUTED, anchor="mm")
    d.text((W // 2, 1118), END_CTA, font=font(28, False), fill=(120, 132, 150), anchor="mm")
    d.text((W // 2, 1660), END_SOURCE, font=font(24, False), fill=(110, 120, 136), anchor="mm")
    d.text((W // 2, 1710), TITLE_CREDIT, font=font(22, False), fill=(88, 98, 114), anchor="mm")
    return frame


def frame_at(t, total):
    if not NO_TITLE and t < 1.0:
        fr = title_card(t)
        fr = slow_zoom(fr, t, 0.05)
        return light_sweep(fr, t)

    # 结尾卡从旁白结束（speech_end）开始：build_audio_cont 把最后一个 beat
    # 的 end 设成总时长，用 last["end"] 触发等于永远不会出现
    END_AT = float(TIMELINE.get("speech_end") or BEATS[-1]["end"])
    if t > END_AT:
        # 硬切到结尾卡（不做叠化），结尾卡同样保持缓慢推近 + 光扫
        span = max(0.6, total - END_AT)
        prog = min(1.0, (t - END_AT) / span)
        fr = endcard()
        fr = slow_zoom(fr, prog, 0.05)
        return light_sweep(fr, prog)

    i = max(0, bisect.bisect_right(STARTS, t) - 1)
    b = BEATS[i]
    nxt = BEATS[i + 1]["start"] if i + 1 < len(BEATS) else TIMELINE["duration"]
    vis = max(0.9, nxt - b["start"])
    frame = beat_frame(b, t - b["start"], t, vis)
    header(frame, scene_label_for(i))
    progress(frame, t, total)
    return frame


def scene_label_for(i):
    s = SCENES[BEATS[i]["scene"]]
    return s["label"]


def preview(times):
    p = OUT / "preview"; p.mkdir(exist_ok=True)
    for t in times:
        t0 = time.time()
        frame_at(t, TIMELINE["duration"]).save(p / f"p_{t:06.2f}.png")
        print(f"{t:.1f}s {time.time()-t0:.2f}s", flush=True)


def video(path, limit=None):
    total = TIMELINE["duration"] if not limit else min(limit, TIMELINE["duration"])
    n = int(total * FPS)
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(OUT / "audio_mix.wav"),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for f in range(n):
        proc.stdin.write(frame_at(f / FPS, TIMELINE["duration"]).tobytes())
        if f % 300 == 0:
            el = time.time() - t0
            r = (f + 1) / max(el, 1e-6)
            print(f"{f}/{n} {r:.1f}fps eta {(n-f)/max(r,1e-6)/60:.1f}min", flush=True)
    proc.stdin.close(); proc.wait()
    if proc.returncode:
        raise RuntimeError("ffmpeg")
    print("done", path, f"{(time.time()-t0)/60:.1f}min")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="video")
    ap.add_argument("nums", nargs="*")
    ap.add_argument("--assets", default=None, help="folder containing the stills")
    a = ap.parse_args()
    if a.assets:
        ASSET_DIR = Path(a.assets)
        ROOT = ASSET_DIR
    if a.mode == "preview":
        preview([float(x) for x in a.nums])
    elif a.mode == "test":
        video(OUT / "test.mp4", limit=float(a.nums[0]) if a.nums else 15)
    else:
        video(OUT / os.environ.get("VIDEO_OUT", "final.mp4"))
