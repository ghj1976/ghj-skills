#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从扫描版 PDF 中抽取内嵌页面图像（jpg/png），供后续逐页识读。

用法:
    python3 extract_scan_images.py 试卷.pdf -o work/img
    python3 extract_scan_images.py 试卷.pdf -o work/img --format jpg

为什么需要它:
    很多试卷 PDF 是"图片型 PDF"（扫描/拍照后转 PDF），没有文字层，
    pdftotext 抽出来是空。这类 PDF 的每一页通常就是一张 DCTDecode(JPEG)
    或 FlateDecode 的 XObject，直接把流抠出来即可，不需要 poppler/ghostscript。

输出:
    work/img/p01.jpg p02.jpg ...  （按页顺序命名）
"""
import argparse
import os
import re
import sys

IMG_DICT = re.compile(
    rb"<</BitsPerComponent\s+(\d+)/ColorSpace\s*/(\w+)/Filter\s*/(\w+)"
    rb"(?:/DecodeParms[^/]*?)?/Height\s+(\d+)/Length\s+(\d+)/Subtype/Image/Type/XObject/Width\s+(\d+)>>stream\r?\n",
    re.S,
)
# 备用：属性顺序不同的写法
IMG_DICT2 = re.compile(
    rb"/Subtype\s*/Image[^>]*?/Width\s+(\d+)[^>]*?/Height\s+(\d+)[^>]*?/Length\s+(\d+)",
    re.S,
)


def extract(path, outdir, fmt="jpg"):
    os.makedirs(outdir, exist_ok=True)
    data = open(path, "rb").read()
    n = 0
    for m in IMG_DICT.finditer(data):
        bpc, cs, filt, h, length, w = m.groups()
        length = int(length)
        payload = data[m.end():m.end() + length]
        n += 1
        if filt == b"DCTDecode":
            ext = "jpg"
            if not payload.startswith(b"\xff\xd8"):
                print(f"  ! 第 {n} 张不是完整 JPEG，跳过", file=sys.stderr)
                continue
        elif filt == b"FlateDecode":
            import zlib
            ext = "png"  # 原始像素，不是真 PNG，见下
            try:
                payload = zlib.decompress(payload)
            except Exception as e:
                print(f"  ! 第 {n} 张解压失败: {e}", file=sys.stderr)
                continue
            print(f"  · 第 {n} 张是 FlateDecode 原始像素 {w}x{h}，需要自己拼 PNG 头", file=sys.stderr)
            ext = "raw"
        else:
            print(f"  ! 第 {n} 张编码 {filt!r} 不支持（JBIG2/CCITT 需外挂工具）", file=sys.stderr)
            continue
        out = os.path.join(outdir, f"p{n:02d}.{fmt if ext == 'jpg' else ext}")
        open(out, "wb").write(payload)
        print(f"{os.path.basename(out)}  {int(w)}x{int(h)}  {len(payload)//1024} KB")
    if n == 0:
        print("没有找到内嵌图像。可能是矢量 PDF（有文字层）——先用 pdftotext / pdfplumber 抽文字。",
              file=sys.stderr)
        return 1
    print(f"\n共 {n} 页图，输出到 {outdir}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="抽取扫描版 PDF 的页面图像")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--outdir", default="work/img")
    ap.add_argument("--format", default="jpg", choices=["jpg"])
    a = ap.parse_args()
    sys.exit(extract(a.pdf, a.outdir, a.format))


if __name__ == "__main__":
    main()
