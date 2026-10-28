# -*- coding: utf-8 -*-
"""1080×1920 竖屏：动态大字、模糊底图、30fps。

支持两种图片镜头：
  - 静帧（img）：整图铺满卡片，整帧慢推近 + 光扫；
  - 动态 B-roll（clip）：读 clips/<beat_id>/ 的帧序列，按 beat 时长线性播放。
"""
import bisect
import json
import re
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

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


def bg_for(img):
    if img not in _BG:
        src = Image.open(ROOT / img).convert("RGB")
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
        src = Image.open(ROOT / img).convert("RGB")
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


def draw_big(frame, b, lt):
    if b["layout"] == "text":
        return draw_text_layout(frame, b, lt)
    d = ImageDraw.Draw(frame)
    ac = accent(b)
    eye = b.get("eyebrow") or ""
    if eye:
        d.text((60, 214), eye.upper(), font=font(27, False), fill=ac)
        d.rectangle([60, 252, 96, 256], fill=ac)
    big = b.get("big")
    if not big:
        return
    f, size = fit_big(big)
    y = 292 + int(10 * (1 - ease_out(lt / 0.28)))
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
    d.text((44, 350), "“", font=font(240), fill=(ac[0] // 4, ac[1] // 4, ac[2] // 4))
    eye = b.get("eyebrow") or ""
    if eye:
        d.text((60, 600), eye, font=font(28, False), fill=ac)
        d.rectangle([60, 642, 96, 646], fill=ac)
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


def image_card(frame, b, lt, y=540, h=608, zoom_max=0.10, duration=None):
    """整图按比例放进卡片：不裁切、不拉变形，保留图片自带说明文字。

    16:9 素材正好铺满；竖图/方图按 contain 摆中间，空白处用同一张图放大压暗填底。
    运动交给整帧 slow_zoom + 光扫，避免把图上文字切掉。
    """
    src = fg_for(b["img"])
    scale = min(W / src.width, h / src.height)
    nw, nh = max(1, int(round(src.width * scale))), max(1, int(round(src.height * scale)))
    if (nw, nh) != (W, h):
        cover = ImageOps.fit(src, (W, h), method=Image.LANCZOS).filter(ImageFilter.GaussianBlur(16))
        shade = Image.new("RGBA", (W, h), (0, 0, 0, 130))
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
    img = None if b["layout"] == "data" else b.get("img")
    if img:
        frame = bg_for(img).copy()
    else:
        frame = BG.copy()
    has_clip = bool(b.get("clip")) and (CLIPS / b["clip"] / "meta.json").exists()
    if has_clip:
        clip_card(frame, b, lt, y=540 if b["layout"] != "full" else 470,
                  h=608 if b["layout"] != "full" else 760)
    elif b["layout"] in ("card", "hook", "full") and img:
        image_card(frame, b, lt, y=540 if b["layout"] != "full" else 470,
                   h=608 if b["layout"] != "full" else 760,
                   duration=vis_dur)
    if b["layout"] == "text":
        # 只在底图偏亮时压暗；深色底图再加 scrim 只会让画面发灰
        mean = bg_mean(img)
        alpha = int(min(140, max(0, (mean - 42) * 2.6)))
        if alpha:
            dark = Image.new("RGBA", (W, H), (3, 5, 9, alpha))
            frame = Image.alpha_composite(frame.convert("RGBA"), dark).convert("RGB")
    if b["layout"] == "data":
        draw_data(frame, b, lt)
    else:
        draw_big(frame, b, lt)
    # 每个镜头单独做一次线性推近 + 光扫：按 beat 计时，切镜头时重置
    # （按场景计时会摊到 20–30 秒上，每帧只动 0.0001，看起来就是静止画面）
    prog = (t - b["start"]) / max(0.9, b["end"] - b["start"])
    if not has_clip:
        # 静帧/文字/数据卡的移动靠整帧线性推近；片段镜头自己就在动，不再裁边
        amt = 0.05 if b["layout"] in ("text", "data") else 0.035
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
        shown = f"{cur:.1f}" if "." in raw else f"{int(round(cur))}"
        text = shown + suffix
    else:
        text = big

    f, size = fit_big(text, start=200, min_size=88, maxw=940)
    note = b.get("note") or ""
    bbox0 = d.textbbox((0, 0), text, font=f)
    num_h = bbox0[3] - bbox0[1]
    eye_h = 48
    note_h = 56 if note else 0
    block = eye_h + 18 + num_h + (note_h + 26 if note else 0) + 46 + 34
    top = 260 + max(0, int((820 - block) / 2))

    label = b.get("eyebrow") or "关键数字"
    d.text((60, top), label, font=font(32, False), fill=MUTED)
    d.rectangle([60, top + 42, 96, top + 46], fill=ac)

    ny = top + eye_h + 18
    d.text((62, ny), text, font=f, fill=ac)
    y = ny + bbox0[3]
    if note:
        d.text((62, y + 18), note, font=font(36, False), fill=(214, 219, 228))
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
    if t < 1.0:
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
