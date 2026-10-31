# -*- coding: utf-8 -*-
"""从成片抽一帧做发布用封面（默认取钩子镜头中段）。

为什么单独做一个脚本：封面不是“随便截一帧”。视频号的封面在信息流里只有拇指大，
要用的是**第一眼就能看懂主题**的那一帧——通常是钩子镜头（大数字 + 大字）中段，
既避开 0–1 秒的标题卡，也避开太靠后的转场。

默认取 `out/timeline.json` 里第 0 个 beat 的起点 +2 秒；没有 timeline 就用 3.0 秒。
9:16 直接输出；再按 `--ratios` 追加别比例的居中裁切版（平台要求 6:7 / 16:9 时用）。

用法：
  python make_cover.py                              # 用 out/ 里唯一的 mp4
  python make_cover.py --at 3.2                     # 指定秒数
  python make_cover.py --ratios 9:16,6:7,16:9       # 额外输出 封面_6x7.png / 封面_16x9.png
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(BASE))

from ffmpeg_path import ffmpeg  # noqa: E402


def pick_video(explicit=None):
    if explicit:
        return Path(explicit)
    vids = sorted(OUT.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    vids = [v for v in vids if not v.name.startswith("test")]
    if not vids:
        raise SystemExit("out/ 里没有 mp4，用 --video 指定")
    return vids[0]


def pick_time(tl_path, at):
    if at is not None:
        return float(at)
    if tl_path.exists():
        tl = json.loads(tl_path.read_text(encoding="utf-8"))
        if tl.get("beats"):
            return round(tl["beats"][0]["start"] + 2.0, 2)
    return 3.0


def crop_to(im, ratio, offset=0.5):
    """按比例裁切：offset=0 贴顶，1 贴底，0.5 居中（跨比例裁切时 0.4 常更保大字）。"""
    rw, rh = ratio
    w, h = im.size
    if w * rh > h * rw:                      # 太宽 -> 裁宽
        nw = int(round(h * rw / rh))
        x0 = int(round((w - nw) * offset))
        box = (x0, 0, x0 + nw, h)
    else:                                    # 太高 -> 裁高
        nh = int(round(w * rh / rw))
        y0 = int(round((h - nh) * offset))
        box = (0, y0, w, y0 + nh)
    return im.crop(box)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=None)
    ap.add_argument("--at", type=float, default=None, help="抽帧秒数（默认钩子镜头 +2s）")
    ap.add_argument("--out", default=None, help="9:16 封面输出路径，默认 out/封面.png")
    ap.add_argument("--ratios", default="9:16", help="逗号分隔，如 9:16,6:7,16:9")
    ap.add_argument("--offset", type=float, default=0.5,
                    help="跨比例裁切时的纵向重心：0 贴顶 / 0.5 居中 / 1 贴底（0.4 常更保大字）")
    a = ap.parse_args()

    video = pick_video(a.video)
    t = pick_time(OUT / "timeline.json", a.at)
    out9 = Path(a.out) if a.out else OUT / "封面.png"
    tmp = OUT / "_cover_frame.png"
    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(t), "-i", str(video), "-frames:v", "1", "-q:v", "1",
                    str(tmp)], check=True)

    frame = Image.open(tmp)
    made = []
    for r in [x.strip() for x in a.ratios.split(",") if x.strip()]:
        rw, rh = (int(v) for v in r.split(":"))
        im = crop_to(frame, (rw, rh), a.offset)
        if (rw, rh) == (9, 16):
            path = out9
        else:
            path = out9.with_name(f"{out9.stem}_{rw}x{rh}{out9.suffix}")
        im.save(path)
        made.append((path, im.size))
    tmp.unlink(missing_ok=True)

    print(f"视频 {video.name}  抽帧 {t:.1f}s")
    for path, size in made:
        try:
            shown = path.resolve().relative_to(BASE)
        except ValueError:            # --out 指到项目外时直接打绝对路径
            shown = path
        print(f"  {shown}  {size[0]}x{size[1]}")
    print("\n封面检查：在 390px 宽的手机缩略图下，大字和钩子数字是否一眼可读；"
          "别用 0–1 秒的标题卡做封面。")


if __name__ == "__main__":
    main()
