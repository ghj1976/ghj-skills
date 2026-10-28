# -*- coding: utf-8 -*-
"""看一遍参考视频：逐秒缩略图 + 原片剪辑点 + 镜头区间。

为什么需要：从参考视频挑 B-roll 时，最容易犯的错是“按缩略图序号猜时间”。
缩略图序号和真实秒数会差半拍，结果剪出来的片段是另一个镜头（比如想要
“指尖捏着标签”，剪出来却是研究员对着镜头说话）。这个脚本把三件事放在
一张图上：精确时间码、剪辑点、镜头区间。

用法：
  python video_sheet.py --video ../03/01.mp4
  python video_sheet.py --video ../03/01.mp4 --every 0.5 --cols 7 --out out/参考视频分镜.png
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from ffmpeg_path import ffmpeg, ffprobe

BASE = Path(__file__).resolve().parent


def probe_duration(video):
    r = subprocess.run([ffprobe(), "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", str(video)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return float(json.loads(r.stdout)["format"]["duration"])


def scene_cuts(video, thresh):
    """ffmpeg 场景检测：返回剪辑点秒数。"""
    r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "info", "-i", str(video),
                        "-vf", f"select='gt(scene,{thresh})',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    cuts = []
    for line in r.stderr.splitlines():
        if "pts_time:" in line:
            try:
                cuts.append(round(float(line.split("pts_time:")[1].split()[0]), 3))
            except (IndexError, ValueError):
                pass
    return cuts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--every", type=float, default=1.0, help="每多少秒取一帧")
    ap.add_argument("--cols", type=int, default=7)
    ap.add_argument("--width", type=int, default=300)
    ap.add_argument("--scene", type=float, default=0.2, help="场景检测阈值")
    ap.add_argument("--out", default=str(BASE / "out" / "参考视频分镜.png"))
    a = ap.parse_args()

    video = Path(a.video)
    if not video.exists():
        raise SystemExit(f"找不到视频 {video}")
    dur = probe_duration(video)
    cuts = scene_cuts(video, a.scene)
    ends = [0.0] + cuts + [dur]
    ranges = [(ends[i], ends[i + 1]) for i in range(len(ends) - 1)]

    times = []
    t = a.every / 2
    while t < dur:
        times.append(round(t, 2))
        t += a.every

    td = Path(tempfile.mkdtemp())
    tiles = []
    for i, ts in enumerate(times):
        f = td / f"t{i:04d}.jpg"
        subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{ts:.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={a.width}:-1", "-q:v", "3", str(f)],
                       check=True)
        tiles.append((ts, Image.open(f).convert("RGB")))

    w = a.width
    h = int(w * 9 / 16)
    cols = a.cols
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, h * rows), (8, 10, 14))
    d = ImageDraw.Draw(sheet)
    for k, (ts, im) in enumerate(tiles):
        x, y = (k % cols) * w, (k // cols) * h
        sheet.paste(im.resize((w, int(w * im.height / im.width))), (x, y))
        d.rectangle([x, y, x + 64, y + 20], fill=(0, 0, 0))
        d.text((x + 4, y + 4), f"{ts:.1f}s", fill=(255, 240, 0))
        if any(abs(ts - c) < a.every / 2 for c in cuts):
            d.rectangle([x, y, x + w - 1, y + h - 1], outline=(255, 120, 60), width=3)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(a.out, quality=85)

    print(f"时长 {dur:.2f}s，剪辑点 {len(cuts)} 个")
    print("镜头区间（挑 B-roll 时区间不要跨这两个边界）：")
    for s, e in ranges:
        print(f"  {s:7.2f} - {e:7.2f}  ({e - s:.2f}s)")
    print(f"缩略图 -> {a.out}")


if __name__ == "__main__":
    main()
