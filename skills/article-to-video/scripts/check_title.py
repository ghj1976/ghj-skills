# -*- coding: utf-8 -*-
"""发布标题的字符白名单门禁（视频号 / 抖音）。

为什么单做一个脚本：标题在列表页被平台判“含特殊字符”，这条片子就白发——
视频、封面、摘要都救不回来。规则是平台定的，不写下来每个人都会再踩一次：
**符号只认 书名号、引号、冒号、加号、问号、百分号、摄氏度；逗号可以换成空格。**
`@ # 顿号 感叹号 括号 破折号 斜杠 小数点` 一律不过。

用法：
  python check_title.py "AI同事最狠的设计：少说话" "你群里那个AI 会自己找Bug"
  python check_title.py --file out/发布文案.md          # 读“一、短标题”表里的反引号标题
  python check_title.py --file out/发布文案.md --max 16

退出码：全过 0，有不过 1（可以直接接在出片流程最后）。
"""
import argparse
import re
import sys
from pathlib import Path

# 平台允许的符号（中英文两套都收，避免“全角冒号能过、半角过不了”这种冤案）
ALLOWED_PUNCT = set("《》“”‘’\"'：:＋+？?％%℃")

# 逗号按平台要求换成空格；其余不给自动替换，只提示“删掉/换说法”
COMMA = set("，,")

TITLE_SECTION = re.compile(r"^##\s*[一二三四五六七八九十]+、短标题", re.M)


def scan(title):
    """返回 [(位置, 字符)]，位置从 1 开始，只报白名单外的符号。"""
    bad = []
    for i, ch in enumerate(title, 1):
        if ch.isspace() or ch.isalnum():
            continue
        if ch in ALLOWED_PUNCT:
            continue
        bad.append((i, ch))
    return bad


def suggest(title):
    """逗号换空格、其余坏符号删掉；只给机械建议，语义还得人来改。"""
    out = []
    for ch in title:
        if ch in COMMA:
            out.append(" ")
        elif ch.isspace() or ch.isalnum() or ch in ALLOWED_PUNCT:
            out.append(ch)
    s = re.sub(r"\s+", " ", "".join(out)).strip()
    return s


def check(title, max_len=16):
    bad = scan(title)
    n = len(title)
    ok = not bad and n <= max_len
    print(f"[{'PASS' if ok else 'FAIL'}] {title}   {n} 字（≤{max_len}）")
    if n > max_len:
        print(f"       超长 {n - max_len} 字：列表页会被截断，砍到 {max_len} 字以内")
    if bad:
        shown = "、".join(f"{ch}（第 {i} 字符）" for i, ch in bad)
        print(f"       不支持的符号：{shown}")
        print(f"       建议：{suggest(title)}")
        if any(ch not in COMMA for _, ch in bad):
            print("       注意：删掉符号后可能读不通，要人工改写一句话，而不是硬删")
        if any(ch == "." for _, ch in bad):
            print("       小数点别直接删（29.5 会变成 295）：改整数（29 分钟）或中文（半小时）")
        if any(ch == "@" for _, ch in bad):
            print("       “@”换成“叫”/“点名”/“提醒”：没人叫它、没人点名它")
        if any(ch == "-" for _, ch in bad):
            print("       英文连字符也不在白名单：Super-agent 写成 Super Agent")
    return ok


def titles_from_file(path):
    text = Path(path).read_text(encoding="utf-8")
    m = TITLE_SECTION.search(text)
    seg = text[m.start():] if m else text
    nxt = re.search(r"\n##\s", seg[3:])
    if nxt:
        seg = seg[:3 + nxt.start()]
    titles = []
    for line in seg.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        for c in cells:
            mm = re.search(r"`([^`]+)`", c)
            if mm:
                titles.append(mm.group(1))
                break
    return titles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("titles", nargs="*", help="直接传标题")
    ap.add_argument("--file", help="从 out/发布文案.md 的“短标题”表里读")
    ap.add_argument("--max", type=int, default=16, help="字数上限（默认 16）")
    a = ap.parse_args()

    titles = list(a.titles)
    if a.file:
        titles += titles_from_file(a.file)
    if not titles:
        raise SystemExit("没有标题可查：传标题参数，或用 --file out/发布文案.md")

    print(f"检查 {len(titles)} 个标题（白名单：书名号 引号 冒号 加号 问号 百分号 摄氏度）\n")
    results = [check(t, a.max) for t in titles]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} PASS")
    if passed != len(results):
        print("FAIL：改完重跑；标题过不了，视频做得再好也发不出去")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
