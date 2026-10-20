# -*- coding: utf-8 -*-
"""Vertical 1080x1920 mobile cut: kinetic typography, blurred stills, 30fps."""
import bisect
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

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

# --- project copy: edit these for each video ---
BRAND = os.environ.get("VIDEO_BRAND", "AI 失控 11 天")
TITLE_MAIN = os.environ.get("VIDEO_TITLE", "AI 失控 11 天")
TITLE_SUB = os.environ.get("VIDEO_SUBTITLE", "不毁灭世界，只想查清哪个门人多")
TITLE_KICKER = os.environ.get("VIDEO_KICKER", "真实事件 · 一份 AI 安全报告")
TITLE_CREDIT = os.environ.get("VIDEO_CREDIT", "AI 配音：VoxCPM2")
END_L1 = os.environ.get("VIDEO_END_1", "有些事，人类早忘了")
END_L2 = os.environ.get("VIDEO_END_2", "AI 还在较真")
END_Q = os.environ.get("VIDEO_END_Q", "你猜，它下一个执念会是什么？")
END_CTA = os.environ.get("VIDEO_END_CTA", "你怎么看？评论区聊聊")
END_SOURCE = os.environ.get("VIDEO_SOURCE", "资料来源：Swarmcha.se 报告 / 腾讯方面回应")

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
        dark = Image.new("RGBA", (W, H), (4, 6, 10, 150))
        _BG[img] = Image.alpha_composite(crop.convert("RGBA"), dark).convert("RGB")
    return _BG[img]


def fg_for(img):
    if img not in _FG:
        src = Image.open(ROOT / img).convert("RGB")
        _FG[img] = src.resize((1600, 900), Image.LANCZOS)
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
    f, size = fit_big(big, start=132, min_size=64, maxw=960)
    y = 690 + int(12 * (1 - ease_out(lt / 0.28)))
    d.text((63, y + 4), big, font=f, fill=(0, 0, 0))
    d.text((60, y), big, font=f, fill=ac)
    bbox = d.textbbox((60, y), big, font=f)
    ly = bbox[3] + 18
    w = int(min(320, f.getlength(big) * 0.55) * ease_out(lt / 0.35))
    if w:
        d.rectangle([60, ly, 60 + w, ly + 8], fill=ac)


def image_card(frame, b, lt, y=540, h=608, zoom_max=0.10, duration=None):
    prog = min(1.0, max(0.0, lt / max(0.4, duration or b["duration"])))
    v = sum(int(c) for c in b["id"] if c.isdigit()) % 3
    if b["layout"] == "hook":
        base, zm, cx0, cy0 = 1.008, 0.14, 800.0, 450.0
    elif v == 0:
        base, zm, cx0, cy0 = 1.008, 0.10, 800.0, 450.0
    elif v == 1:
        base, zm, cx0, cy0 = 1.10, 0.05, 665.0, 470.0
    else:
        base, zm, cx0, cy0 = 1.14, 0.05, 950.0, 430.0
    zoom = base + zm * prog
    src = fg_for(b["img"])
    sw, sh = 1600.0 / zoom, 900.0 / zoom
    cx, cy = cx0 + 20.0 * (prog - 0.5), cy0 + 8.0 * (prog - 0.5)
    x0 = min(max(0.0, cx - sw / 2), 1600.0 - sw)
    y0 = min(max(0.0, cy - sh / 2), 900.0 - sh)
    sx, sy = sw / W, sh / h
    crop = src.transform((W, h), Image.AFFINE, (sx, 0, x0, 0, sy, y0), resample=Image.BILINEAR)
    frame.paste(crop, (0, y))
    d = ImageDraw.Draw(frame)
    d.rectangle([0, y, W, y + 3], fill=accent(b))
    # dim bottom for caption separation
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
    d.polygon([(x, 0), (x + 240, 0), (x - 220, H), (x - 500, H)], fill=(95, 175, 225, 13))
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
    if b["layout"] in ("card", "hook", "full") and img:
        image_card(frame, b, lt, y=540 if b["layout"] != "full" else 470,
                   h=608 if b["layout"] != "full" else 760,
                   zoom_max=0.14 if b["layout"] == "hook" else 0.10,
                   duration=vis_dur)
    if b["layout"] == "text":
        dark = Image.new("RGBA", (W, H), (3, 5, 9, 125))
        frame = Image.alpha_composite(frame.convert("RGBA"), dark).convert("RGB")
    if b["layout"] == "data":
        draw_data(frame, b, lt)
    else:
        draw_big(frame, b, lt)
    draw_caption(frame, b, t)
    if b["layout"] in ("text", "data"):
        sc = SCENES[b["scene"]]
        prog = (t - sc["start"]) / max(0.9, sc["end"] - sc["start"])
        frame = slow_zoom(frame, prog, 0.075)
        frame = light_sweep(frame, prog)
    return frame


def draw_data(frame, b, lt):
    d = ImageDraw.Draw(frame)
    ac = accent(b)
    d.text((60, 200), "数字对不上", font=font(30, False), fill=MUTED)
    d.rectangle([60, 246, 96, 250], fill=ac)
    # labels + count up
    p = smooth(min(1, lt / 1.2))
    n1 = int(35300 * p); n2 = int(2818 * p)
    d.text((58, 360), f"{n1:,}", font=font(168), fill=ORANGE)
    d.text((62, 610), "次网络请求 · Swarmcha.se 报告", font=font(34, False), fill=(214, 219, 228))
    d.text((58, 720), f"{n2:,}", font=font(150), fill=CYAN)
    d.text((62, 952), "次访问尝试 · 腾讯方面回应", font=font(34, False), fill=(214, 219, 228))
    big = b.get("big")
    if big:
        f, size = fit_big(big, start=86, min_size=60, maxw=940)
        d.text((60, 1040), big, font=f, fill=WHITE)
    d.text((60, 1160), "统计口径不同，不能当作无争议定论", font=font(28, False), fill=(196, 160, 118))


def title_card(t):
    frame = BG.copy()
    d = ImageDraw.Draw(frame)
    p = ease_out(min(1, t / 0.35))
    d.text((W - 60, 250), "11", font=font(420), fill=(18, 25, 36),
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
        return title_card(t)
    i = max(0, bisect.bisect_right(STARTS, t) - 1)
    b = BEATS[i]
    nxt = BEATS[i + 1]["start"] if i + 1 < len(BEATS) else TIMELINE["duration"]
    vis = max(0.9, nxt - b["start"])
    frame = beat_frame(b, t - b["start"], t, vis)
    # endcard
    last = BEATS[-1]
    if t > last["end"]:
        a = ease_out((t - last["end"]) / 0.7)
        if a >= 1:
            frame = endcard()
        else:
            frame = Image.blend(frame, endcard(), a)
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
