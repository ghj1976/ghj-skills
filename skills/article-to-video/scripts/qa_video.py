# -*- coding: utf-8 -*-
"""成片自动 QA。

检查：规格、CFR PTS、完整解码、切点附近冻结帧、响度。
用法：python qa_video.py path/to/video.mp4 [--times 9.5,49,175]
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from ffmpeg_path import ffmpeg as _ffmpeg, ffprobe as _ffprobe

BASE = Path(__file__).resolve().parent
FFMPEG = _ffmpeg()
FFPROBE = _ffprobe()


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe(path):
    r = run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    return json.loads(r.stdout)


def pts_check(path):
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(path)])
    vals = []
    for line in r.stdout.splitlines():
        line = line.strip().strip(",")
        if line:
            try:
                vals.append(float(line))
            except ValueError:
                pass
    d = np.diff(vals)
    return len(vals), float(d.min()) if len(d) else 0, float(d.max()) if len(d) else 0, int((d < 0.001).sum())


def decode_check(path):
    r = run([FFMPEG, "-v", "error", "-i", str(path), "-f", "null", "-"])
    return r.returncode == 0 and not r.stderr.strip(), r.stderr.strip()[:300]


def diffs(path, start, dur=1.2):
    with tempfile.TemporaryDirectory() as td:
        run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-fps_mode", "passthrough",
             str(Path(td) / "%03d.png")])
        files = sorted(Path(td).glob("*.png"))
        prev, ds = None, []
        for f in files:
            a = np.asarray(Image.open(f).resize((270, 480)), dtype=np.float32)
            if prev is not None:
                ds.append(float(np.mean(np.abs(a - prev))))
            prev = a
        return ds


def frozen_runs(ds, thresh=0.02, run=3):
    cnt, bad = 0, []
    for i, v in enumerate(ds):
        cnt = cnt + 1 if v < thresh else 0
        if cnt == run:
            bad.append(i - run + 1)
    return bad


def loudness(path):
    r = run([FFMPEG, "-hide_banner", "-nostats", "-i", str(path),
             "-af", "ebur128=peak=true", "-f", "null", "-"])
    txt = r.stderr
    i = re.search(r"Integrated loudness:\s*\n\s*I:\s+(-?[\d.]+)\s+LUFS", txt)
    p = re.search(r"True peak:\s*\n\s*Peak:\s+(-?[\d.]+)\s+dBFS", txt)
    return (float(i.group(1)) if i else None, float(p.group(1)) if p else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?", default=str(BASE / "out" / "video.mp4"))
    ap.add_argument("--times", default="")
    a = ap.parse_args()
    path = Path(a.video)
    ok = True
    print("video:", path)
    if not path.exists():
        print("FAIL: missing file")
        return 1

    info = probe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    print(f"duration={dur:.2f}s  video={v['codec_name']} {v['width']}x{v['height']} "
          f"{v['r_frame_rate']}  audio={au['codec_name'] if au else 'NONE'}")

    n, dmin, dmax, dups = pts_check(path)
    print(f"frames={n} dt=[{dmin:.4f},{dmax:.4f}] duplicates={dups}")
    if dups or abs(dmin - 1 / 30) > 0.002 or abs(dmax - 1 / 30) > 0.002:
        print("FAIL: non-CFR timing")
        ok = False

    good, err = decode_check(path)
    print("decode:", "ok" if good else f"FAIL {err}")
    ok &= good

    times = []
    if a.times:
        times = [float(x) for x in a.times.split(",") if x.strip()]
    else:
        tl = BASE / "out" / "timeline.json"
        if tl.exists():
            data = json.loads(tl.read_text(encoding="utf-8"))
            starts = [s["start"] for s in data["scenes"][1:]]
            times = [round(x + 2.0, 2) for x in starts[:3]]
    for t in times:
        ds = diffs(path, t)
        bad = frozen_runs(ds)
        print(f"window {t:.1f}s frames={len(ds)} zero_runs={len(bad)} "
              f"min_diff={min(ds) if ds else 0:.3f}")
        if bad:
            print("FAIL: frozen frames at", bad)
            ok = False

    I, peak = loudness(path)
    print(f"loudness={I} LUFS true_peak={peak} dBFS")
    if I is None or not (-17.5 <= I <= -14.5):
        print("FAIL: integrated loudness out of range")
        ok = False
    if peak is None or peak > -1.0:
        print("FAIL: true peak too high")
        ok = False

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
