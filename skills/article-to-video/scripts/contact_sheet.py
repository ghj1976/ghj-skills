# -*- coding: utf-8 -*-
"""把成片按镜头抽帧拼成一张对照图，用来逐句检查“配图是否搭”。

配图没法自动化判断语义，但一张图里能看到 30 多个镜头，扫一眼就能发现
“讲现金牛配了天平”“讲问题一配了资本流向”这类错位。

用法：
  python contact_sheet.py --video out/xxx.mp4 [--tl out/timeline.json] [--cols 9]
                          [--out out/配图对照.png]
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from ffmpeg_path import ffmpeg

BASE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--tl", default=str(BASE / "out" / "timeline.json"))
    ap.add_argument("--cols", type=int, default=9)
    ap.add_argument("--width", type=int, default=200)
    ap.add_argument("--out", default=str(BASE / "out" / "配图对照.png"))
    a = ap.parse_args()

    tl = json.loads(Path(a.tl).read_text(encoding="utf-8"))
    td = Path(tempfile.mkdtemp())
    thumbs = []
    for b in tl["beats"]:
        t = b["start"] + min(1.1, max(0.3, (b["end"] - b["start"]) * 0.5))
        f = td / f"{b['id']}.png"
        subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{t:.2f}", "-i", a.video, "-frames:v", "1", str(f)], check=True)
        thumbs.append((b["id"], Image.open(f)))

    w = a.width
    h = int(w * 16 / 9)
    cols = a.cols
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, h * rows), (0, 0, 0))
    for k, (_, im) in enumerate(thumbs):
        sheet.paste(im.resize((w, h)), ((k % cols) * w, (k // cols) * h))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(a.out)
    print(f"{len(thumbs)} 个镜头 -> {a.out} ({sheet.width}x{sheet.height})")


if __name__ == "__main__":
    main()
