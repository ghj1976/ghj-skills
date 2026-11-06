#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打印前体检 PDF：是不是 A4、几页、字体有没有嵌进去。

用法:
    python3 check_pdf.py out/答案_A4.pdf
    python3 check_pdf.py out/答案_A4.pdf --expect A4 --max-pages 20

只用标准库，不依赖 poppler / pypdf。
判定:
    MediaBox ≈ 595×842 pt 才是 A4；若得到 612×792 就是 Letter，说明 @page 没生效。
    字体名带 'BAAAAA+' 前缀 = 子集已嵌入，打印/转发不会缺字。
"""
import argparse
import re
import sys

A4 = (595, 842)
LETTER = (612, 792)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--expect", default="A4", choices=["A4", "Letter"])
    ap.add_argument("--max-pages", type=int, default=0)
    a = ap.parse_args()

    data = open(a.pdf, "rb").read()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    boxes = set(re.findall(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", data))
    fonts = sorted({m.decode("latin1") for m in re.findall(rb"/BaseFont\s*/([A-Za-z0-9+\-,]+)", data)})

    print(f"文件      {a.pdf}")
    print(f"大小      {len(data)//1024} KB")
    print(f"页数      {pages}")
    ok = True
    for b in boxes:
        w, h = float(b[2]), float(b[3])
        name = "A4" if abs(w - A4[0]) < 3 and abs(h - A4[1]) < 3 else (
               "Letter" if abs(w - LETTER[0]) < 3 and abs(h - LETTER[1]) < 3 else "自定义/混合")
        print(f"页面尺寸  {w:.0f}×{h:.0f} pt  ({w/72*25.4:.0f}×{h/72*25.4:.0f} mm) → {name}")
        if a.expect == "A4" and name != "A4":
            ok = False
    if len(boxes) > 1:
        print("⚠ 页面尺寸不统一，检查是否有整页图片或 @page 覆盖")
        ok = False
    print("字体      " + (", ".join(fonts) if fonts else "（无嵌入字体，可能是纯图片 PDF）"))
    if fonts and not any("+" in f for f in fonts):
        print("⚠ 字体看起来没有子集嵌入，换机器打印可能缺字")
    if a.max_pages and pages > a.max_pages:
        print(f"⚠ 页数 {pages} 超过预期 {a.max_pages}")
        ok = False
    print("结论      " + ("OK" if ok else "需要修"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
