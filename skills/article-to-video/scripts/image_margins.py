# -*- coding: utf-8 -*-
"""量出配图的空白边，并按情况给出裁切/版式建议。

为什么需要：素材常常是“一张大画布 + 中间一个小人”。实测一张 1024×572 的插画，
内容只占中间 38.5% 宽，左右各 31% 是纯米色；直接塞进 1080×608 的宽卡片，
观众看到的是“一张纸上画了个小人”，小人只有 416px 宽。
但反过来，见到空白就裁也会出问题：留白本身就是构图的一部分，裁完贴边反而难看。

所以先量，再按这套规则决定：

  1. 图本身是超宽横幅（宽高比 ≥ 2.2）：
     不裁，直接 card——render.py 会给它配深色卡底（gap > 0.28h 分支）。
  2. 内容在横竖两个方向都 ≥ 80%：不裁，直接 card。
     16:9 插画通常落在这里，四周那点边是设计的一部分。
  3. 某一边空白很大（内容 < 80%）：
     裁到内容 → 用 asset_path 能读到的 assets/ 衍生图，再看裁完的比例：
       · 宽高比 < 1.15（近方/竖）：改用 poster 版式（卡片按图收窄，图铺满卡片）
       · 宽高比 ≥ 1.15（横幅）：仍用 card，只是图变大了
  4. 透明 PNG：用 alpha 通道定 bbox，不用背景色阈值。

用法：
  python image_margins.py ../06                       # 只看报告和建议
  python image_margins.py ../06 --crop                # 顺带裁到 assets/
  python image_margins.py a.png b.png --crop --pad 8
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

BASE = Path(__file__).resolve().parent
ASSETS = BASE / "assets"
EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def ink_mask(im, threshold):
    """返回 (mask, 背景色)。透明图走 alpha，不透明图按四角中位色算背景。"""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        a = np.asarray(rgba)[:, :, 3]
        return a > 16, None
    rgb = im.convert("RGB")
    arr = np.asarray(rgb).astype(np.int16)
    h, w, _ = arr.shape
    corners = np.array([arr[0, 0], arr[0, w - 1], arr[h - 1, 0], arr[h - 1, w - 1]])
    bg = np.median(corners, axis=0)
    return np.abs(arr - bg).max(axis=2) > threshold, bg


def content_bbox(mask, ink=0.02):
    """墨迹 bbox。用“整列/整行墨迹占比”判，避免一个杂点把 bbox 撑到整幅。"""
    h, w = mask.shape
    cols = mask.sum(axis=0) > h * ink
    rows = mask.sum(axis=1) > w * ink * 0.25
    if not cols.any() or not rows.any():
        return None
    xs, ys = np.where(cols)[0], np.where(rows)[0]
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def analyse(path, threshold=12):
    im = Image.open(path)
    mask, bg = ink_mask(im, threshold)
    w, h = im.size
    box = content_bbox(mask)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    fill_w, fill_h = bw / w, bh / h
    img_ar, cut_ar = w / h, bw / bh

    if img_ar >= 2.2:
        layout, crop, why = "card", False, "超宽横幅，深色卡底"
    elif fill_w >= 0.80 and fill_h >= 0.80:
        layout, crop, why = "card", False, "空白不多，留白是构图的一部分"
    elif cut_ar < 1.15:
        layout, crop, why = "poster", True, f"内容只占 {fill_w*100:.0f}% 宽且近方形/竖构图"
    else:
        layout, crop, why = "card", True, f"内容占 {fill_w*100:.0f}% 宽，裁完仍是横幅"

    return {
        "path": path, "size": (w, h), "box": box, "fill_w": fill_w, "fill_h": fill_h,
        "img_ar": img_ar, "cut_ar": cut_ar, "layout": layout, "crop": crop, "why": why,
    }


def crop_to_content(info, pad=6, out_dir=None):
    out_dir = Path(out_dir) if out_dir else ASSETS
    out_dir.mkdir(parents=True, exist_ok=True)
    src_path = Path(info["path"])
    im = Image.open(src_path)
    w, h = im.size
    x0, y0, x1, y1 = info["box"]
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
    out = out_dir / f"{src_path.stem}_crop.png"
    im.crop((x0, y0, x1, y1)).save(out)
    return out, (x0, y0, x1, y1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="图片文件或目录")
    ap.add_argument("--crop", action="store_true", help="把建议要裁的图裁到 assets/")
    ap.add_argument("--pad", type=int, default=6, help="裁切时四周留几像素")
    ap.add_argument("--out", default=None, help="裁切输出目录，默认 assets/")
    ap.add_argument("--threshold", type=int, default=12, help="背景色差阈值")
    a = ap.parse_args()

    files = []
    for p in a.paths:
        p = Path(p)
        if p.is_dir():
            files += sorted(q for q in p.iterdir() if q.suffix.lower() in EXTS)
        elif p.suffix.lower() in EXTS:
            files.append(p)
    if not files:
        sys.exit("没找到图片")

    print(f"{'文件':40s} {'尺寸':11s} {'内容宽':>6s} {'内容高':>6s} {'比例':>6s}  建议")
    todo = []
    for f in files:
        info = analyse(f, a.threshold)
        if info is None:
            print(f"{f.name:40s} 全是背景色？跳过")
            continue
        print(f"{f.name:40s} {info['size'][0]:4d}x{info['size'][1]:<6d} "
              f"{info['fill_w']*100:5.0f}% {info['fill_h']*100:5.0f}% "
              f"{info['cut_ar']:6.2f}  {info['layout']:6s} "
              f"{'裁' if info['crop'] else '不裁'} — {info['why']}")
        if info["crop"]:
            todo.append(info)

    if a.crop and todo:
        print("\n裁切结果（放进项目 assets/，不动原素材）：")
        for info in todo:
            out, box = crop_to_content(info, a.pad, a.out)
            im = Image.open(out)
            print(f"  {Path(info['path']).name} -> {out.name}  {im.size[0]}x{im.size[1]}  "
                  f"bbox={box}  layout={info['layout']}")
        print("\nscript_data.py 里这样写（图片名指向 assets/ 里的衍生图）：")
        for info in todo:
            name = f"{Path(info['path']).stem}_crop.png"
            print(f'    ("口播", "字幕", "大字", "{info["layout"]}", "orange", "标签", "{name}"),')
    elif todo:
        print(f"\n有 {len(todo)} 张建议裁切；加 --crop 生成 assets/ 衍生图。")


if __name__ == "__main__":
    main()
