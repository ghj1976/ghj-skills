# -*- coding: utf-8 -*-
"""从参考视频里切出动态 B-roll 帧序列，供 render.py 贴进图片卡。

为什么用帧序列：render.py 逐帧出图、再用管道送进 ffmpeg 编码；在同一个进程里
再拉一个解码器容易互相抢 IO。先把每段切好，渲染时每帧只是读一张 1080×608 的
JPEG，最稳也最快。

约定（写在 project 的 script_data.py 里）：

    VIDEO_SRC = "../03/01.mp4"          # 参考视频（相对本目录）
    CLIP_SRC = {                        # beat_id -> (起点, 终点)，源片秒数
        "00_00": (0.15, 3.30),
        "01_02": (23.00, 25.50),
    }

    # beat 元组第 9 位标 True，表示这个镜头用同名片段
    ("...", "...", "回形针", "hook", "orange", "真实研究", "bf1.png", "", True),

区间要落在同一个原片镜头内（用 video_sheet.py 看剪辑点），别跨剪辑点；
不要配原片人声：片段只当画面，音轨仍是中文旁白。

用法：
  python make_clips.py                 # 生成 clips/<beat_id>/
  python make_clips.py --only 00_00
  SOURCE_VIDEO=../03/01.mp4 python make_clips.py
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

import script_data

from ffmpeg_path import ffmpeg

BASE = Path(__file__).resolve().parent
OUT = BASE / "clips"
FPS = 30
CARD = (1080, 608)


def source_video():
    path = os.environ.get("SOURCE_VIDEO") or getattr(script_data, "VIDEO_SRC", "")
    if not path:
        raise SystemExit("缺少参考视频：在 script_data.py 写 VIDEO_SRC，或设环境变量 SOURCE_VIDEO")
    p = Path(path)
    if not p.is_absolute():
        p = (BASE / p).resolve()
    if not p.exists():
        raise SystemExit(f"找不到参考视频 {p}")
    return p


def beat_durations():
    """有 timeline.json 就按真实时长打印倍速，方便判断片段够不够长。"""
    tl = BASE / "out" / "timeline.json"
    if not tl.exists():
        return {}
    data = json.loads(tl.read_text(encoding="utf-8"))
    return {b["id"]: b["duration"] for b in data.get("beats", [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只做某个 beat，如 00_00")
    ap.add_argument("--width", type=int, default=CARD[0])
    ap.add_argument("--height", type=int, default=CARD[1])
    a = ap.parse_args()

    src = source_video()
    clips = getattr(script_data, "CLIP_SRC", {})
    want = [b for b in script_data.flatten() if b.get("clip")]
    if not want:
        raise SystemExit("script_data 里没有 beat 标 clip（beat 元组第 9 位写 True）")
    durations = beat_durations()

    for b in want:
        if a.only and b["clip"] != a.only:
            continue
        cid = b["clip"]
        if cid not in clips:
            raise SystemExit(f"{cid} 标了 clip，但 CLIP_SRC 里没有源区间")
        start, end = clips[cid]
        if end <= start:
            raise SystemExit(f"{cid} 的 CLIP_SRC 区间不合法：{start}-{end}")
        d = OUT / cid
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("f_*.jpg"):
            old.unlink()
        cmd = [ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
               "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(src),
               "-vf", f"scale={a.width}:{a.height}:flags=lanczos,"
                      "unsharp=5:5:0.45:5:5:0",
               "-r", str(FPS), "-q:v", "2", "-start_number", "1",
               str(d / "f_%04d.jpg")]
        subprocess.run(cmd, check=True)
        n = len(list(d.glob("f_*.jpg")))
        (d / "meta.json").write_text(json.dumps(
            {"frames": n, "fps": FPS, "src": [start, end]}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        dur = n / FPS
        speed = ""
        if cid in durations and durations[cid] > 0:
            speed = f" / beat {durations[cid]:.2f}s → {dur / durations[cid]:.2f}×"
        print(f"{cid}: {n} 帧 = {dur:.2f}s  <- {start:.2f}-{end:.2f}s{speed}", flush=True)

    total = sum(len(list((OUT / b["clip"]).glob("f_*.jpg")))
                for b in want if (OUT / b["clip"]).exists())
    print(f"共 {len(want)} 段 / {total} 帧 -> {OUT}")


if __name__ == "__main__":
    main()
