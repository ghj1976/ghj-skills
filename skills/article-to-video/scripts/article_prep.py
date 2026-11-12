# -*- coding: utf-8 -*-
"""文章地址 → 可直接开写的项目：路径归一、图片落地、配图体检、文章摘要。

为什么单独做这一步：给一个“文章地址”（`E:\\obsidian\\推文\\SRE\\xxx.md`
这种 Windows 路径、带中文和全角引号）时，真正会返工的不是写脚本，而是这几件事：

  1. 路径形态不对（Windows `E:\\` 在 WSL 里打不开；Obsidian 图片链接还带 `%20`）；
  2. 图片链接指向 `assets/<文章标题>/file-*.png`，目录名带全角引号，文件名是时间戳，
     直接抄进 `script_data.py` 既难写又难读；
  3. 没量过内容占比就把“纸上的小人”塞进 1080×608 卡片（见 SKILL.md 规则 20）；
  4. 没数过字数就开始写分镜，最后要么 4 分钟、要么砍到只剩骨架。

这个脚本把上面四件事一次做完，输出：

  - `out/article_digest.md`：按章节的段落/图片/链接/数字清单 + 字数与时长预估；
  - 图片复制到项目 `assets/img01.png` 这类短名，并打印可直接粘进 `script_data.py` 的 `IMG = {...}`；
  - 每张图的内容占比与 `card / poster / 裁切` 建议（复用 `image_margins.analyse`）。

用法（在项目目录里跑，`SKILL` 换成 skill 根目录）：

    python article_prep.py "E:\\obsidian\\推文\\SRE\\某篇文章.md"
    python article_prep.py ../文章.md --copy            # 默认就复制；--no-copy 只体检
    python article_prep.py ../文章.md --digest out/article_digest.md
    python article_prep.py ../文章.md --assets assets   # 图片落到哪里，默认 ./assets

URL 文章（公众号链接）先落成本地 Markdown：用 `wechat-obsidian-archive` skill 存档到
Obsidian，再把这个脚本指过去。
"""
import argparse
import os
import re
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

# 图片链接：![](...) / ![alt](<...>) / Obsidian ![[...]]
MD_IMG = re.compile(r"!\[[^\]]*\]\(\s*<?([^)>]+?)>?\s*\)")
WIKI_IMG = re.compile(r"!\[\[([^\]]+?)\]\]")
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*<?(https?://[^)>]+?)>?\s*\)")
HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
NUM = re.compile(r"[0-9]+(?:\.[0-9]+)?\s*(?:%|％|倍|万|亿|B|b|K|k|ms|秒|分钟|小时|天|个|条|次|台|美元|元)")

CPS = 5.9          # 目标语速（字/秒），用来把字数换算成时长


# ---------------------------------------------------------------- 路径归一
def resolve_path(p: str) -> Path:
    """把用户可能给的任意形态变成一个真实存在的路径。

    两个世界都要能进：bash 用 `/mnt/e/...`，Windows python（TTS/渲染）只认 `E:/...`；
    在 Windows 上把 `/mnt/e/x` 当相对路径会得到 `D:\\mnt\\e\\x` 这种鬼东西。
    支持：`E:\\x\\y.md`、`E:/x/y.md`、带引号、`file://`、UNC（`\\\\wsl$\\...`）、
    `/mnt/e/...`、相对路径。
    """
    raw = p.strip().strip('"').strip("'").strip("“”")
    if raw.startswith("file://"):
        raw = raw[7:]
    is_win = os.name == "nt"
    # UNC：\\wsl$\Ubuntu\mnt\e\...
    m = re.match(r"^\\\\wsl\$\\[^\\]+\\(.*)$", raw)
    if m:
        raw = "/" + m.group(1).replace("\\", "/")
    # WSL 路径：Windows python 要换成盘符
    if is_win:
        m = re.match(r"^/mnt/([A-Za-z])/(.*)$", raw)
        if m:
            raw = f"{m.group(1).upper()}:/" + m.group(2)
    # Windows 盘符：POSIX 要换成 /mnt/<盘>
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if m:
        rest = m.group(2).replace("\\", "/")
        raw = (f"{m.group(1).upper()}:/{rest}" if is_win
               else f"/mnt/{m.group(1).lower()}/{rest}")
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (Path.cwd() / p)


def alt_form(p: Path) -> str:
    """同一个文件在“另一个世界”的写法，用来提示/bash 里复跑。"""
    s = p.as_posix()
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    if m:
        return f"/mnt/{m.group(1).lower()}/{m.group(2)}"
    m = re.match(r"^/mnt/([A-Za-z])/(.*)$", s)
    if m:
        return f"{m.group(1).upper()}:/{m.group(2)}"
    return s


def iter_image_links(text):
    """按出现顺序返回 (行号, 原始链接)。兼容 Markdown 与 Obsidian wiki 两种写法。"""
    out = []
    for ln, line in enumerate(text.splitlines(), 1):
        for m in MD_IMG.finditer(line):
            out.append((ln, m.group(1).strip()))
        for m in WIKI_IMG.finditer(line):
            out.append((ln, m.group(1).strip()))
    return out


def locate_image(link: str, art_dir: Path):
    """把文章里的图片链接解析成本地文件；找不到返回 None。

    顺序：URL 解码后的相对路径 → 同目录同名文件 → 文章目录下按文件名搜一遍
    （Obsidian 常见 `assets/文章标题/file-x.png` 与文章同级）。
    """
    from urllib.parse import unquote
    link = unquote(link.split("|")[0].split("#")[0])
    if link.lower().startswith(("http://", "https://")):
        return None
    cand = (art_dir / link)
    if cand.exists():
        return cand.resolve()
    name = Path(link).name
    cand = art_dir / name
    if cand.exists():
        return cand.resolve()
    hits = sorted(art_dir.rglob(name))
    return hits[0].resolve() if hits else None


# ---------------------------------------------------------------- 文章解析
def parse_article(text):
    """粗分章节：标题、每节的段落、图片位置、链接。不追求完美解析，只求够写分镜。"""
    lines = text.splitlines()
    sections = []
    cur = {"level": 0, "title": "（序）", "paras": [], "images": [], "links": []}
    buf = []

    def flush():
        nonlocal buf
        s = plain("".join(buf).strip())
        if s:
            cur["paras"].append(s)
        buf = []

    for ln, line in enumerate(lines, 1):
        h = HEAD.match(line.strip())
        if h:
            flush()
            if cur["paras"] or cur["images"] or cur["title"] != "（序）":
                sections.append(cur)
            cur = {"level": len(h.group(1)), "title": h.group(2).strip(),
                   "paras": [], "images": [], "links": []}
            continue
        if "![" in line or "![" + "[" in line:
            flush()
            for m in MD_IMG.finditer(line):
                cur["images"].append({"line": ln, "link": m.group(1).strip()})
            for m in WIKI_IMG.finditer(line):
                cur["images"].append({"line": ln, "link": m.group(1).strip()})
            continue
        for m in LINK.finditer(line):
            cur["links"].append(m.group(1))
        if not line.strip():
            flush()
        elif line.strip() in ("---", "***", "___"):
            flush()
        else:
            buf.append(line.strip())
    flush()
    if cur["paras"] or cur["images"]:
        sections.append(cur)
    return sections


def plain(s):
    """去掉内联 Markdown：加粗/斜体/行内码/链接（保留链接文字）/图片残留。"""
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[*_`]{1,3}", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def zh_len(s):
    """按“会被念出来的字”数字数：中文 + 英数词，标点不计。"""
    return len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z]+|[0-9]+(?:\.[0-9]+)?", s))


def mmss(sec):
    return f"{int(sec)//60}:{int(sec)%60:02d}"


# ---------------------------------------------------------------- 配图体检
def audit_images(paths):
    """内容占比 + 版式建议。能在没有 image_margins 的环境下退化。"""
    try:
        import image_margins
    except Exception:
        return [{"path": p, "size": None, "why": "（缺 image_margins，未量）"} for p in paths]
    rows = []
    for p in paths:
        try:
            info = image_margins.analyse(p)
        except Exception as e:                       # 坏图不阻断流程
            rows.append({"path": p, "size": None, "why": f"读不了：{e}"})
            continue
        if info is None:
            rows.append({"path": p, "size": None, "why": "空白图"})
        else:
            rows.append(info)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("article", help="文章路径（Windows E:\\... 或 WSL /mnt/e/...）")
    ap.add_argument("--assets", default="assets", help="图片复制的目标目录（默认 ./assets）")
    ap.add_argument("--digest", default="out/article_digest.md", help="摘要输出路径")
    ap.add_argument("--no-copy", action="store_true", help="只体检，不复制图片")
    ap.add_argument("--prefix", default="img", help="复制的短名前缀（默认 img → img01.png）")
    a = ap.parse_args()

    art = resolve_path(a.article)
    if not art.exists():
        raise SystemExit(f"找不到文章：{a.article}\n  试过：{art}\n"
                         f"  （bash 里用 /mnt/e/...，Windows python 里用 E:/...）")
    if art.is_dir():
        mds = sorted(art.glob("*.md"))
        if not mds:
            raise SystemExit(f"目录里没有 .md：{art}")
        art = mds[0]
        print(f"[info] 传的是目录，取第一篇：{art.name}", flush=True)

    text = art.read_text(encoding="utf-8", errors="replace")
    art_dir = art.parent
    print(f"文章：{art}", flush=True)
    print(f"等价路径：{alt_form(art)}", flush=True)

    # 标题：一级标题 > 文件名
    title = art.stem
    for line in text.splitlines():
        m = HEAD.match(line.strip())
        if m and len(m.group(1)) == 1:
            title = m.group(2).strip()
            break

    sections = parse_article(text)
    links = iter_image_links(text)

    # ---- 图片落地
    assets = Path(a.assets)
    mapping, missing, copied = [], [], []
    for i, (ln, link) in enumerate(links, 1):
        src = locate_image(link, art_dir)
        mapping.append({"n": i, "line": ln, "link": link, "src": src})
        if src is None:
            missing.append((ln, link))
    if not a.no_copy:
        assets.mkdir(parents=True, exist_ok=True)
        for m in mapping:
            if m["src"] is None:
                continue
            dst = assets / f"{a.prefix}{m['n']:02d}{m['src'].suffix.lower()}"
            if dst.exists() and dst.stat().st_size == m["src"].stat().st_size:
                pass
            else:
                shutil.copy2(m["src"], dst)
            m["dst"] = dst.name
            copied.append(dst)
    rows = audit_images([m["src"] for m in mapping if m["src"]])

    # ---- 摘要
    total_chars = sum(zh_len(" ".join(s["paras"])) for s in sections)
    est = total_chars / CPS
    out = Path(a.digest)
    out.parent.mkdir(parents=True, exist_ok=True)
    L = [f"# 素材摘要 · {title}", "",
         f"- 文章：`{art}`",
         f"- 章节：{sum(1 for s in sections if s['level'] >= 2)} 个二级标题 / {len(sections)} 个内容块",
         f"- 字数：约 **{total_chars}** 字（只数会念出来的字）",
         f"- 时长预估：**{mmss(est)}**（按 {CPS} 字/秒；要压到 2:15–3:15 就得砍 {max(0, round((est-195)/est*100))}%）",
         f"- 配图：{len(links)} 个链接，{len(links)-len(missing)} 张落地，{len(missing)} 个缺失",
         ""]

    L += ["## 配图清单", "",
          "| # | 行 | 源文件 | 复制为 | 尺寸 | 内容占比 | 建议 |",
          "|---|---|---|---|---|---|---|"]
    for m, r in zip([x for x in mapping if x["src"]], rows):
        size = f"{r['size'][0]}×{r['size'][1]}" if r.get("size") else "—"
        fill = f"{r['fill_w']*100:.0f}% × {r['fill_h']*100:.0f}%" if r.get("fill_w") else "—"
        lay = (r.get("layout", "—") + ("+裁" if r.get("crop") else "")) if r.get("why") else "—"
        L.append(f"| {m['n']} | {m['line']} | `{m['src'].name}` | `{m.get('dst','—')}` | {size} | {fill} | {lay} · {r.get('why','')} |")
    if missing:
        L += ["", "### 缺失的图（链接指向的文件不存在）", ""]
        L += [f"- 第 {ln} 行：`{lk}`" for ln, lk in missing]
        L += ["", "修法：图片通常在文章同目录或其 `assets/` 下，按文件名搜一遍；", 
              "或者重新从原文/公众号里保存。**不要**把缺失的图直接写进 `script_data.py`。"]
    L += [""]

    L += ["## 章节与段落", ""]
    for si, s in enumerate(sections):
        n = zh_len(" ".join(s["paras"]))
        L.append(f"### {s['title']}（{n} 字，约 {n/CPS:.0f}s）")
        L.append("")
        for p in s["paras"]:
            L.append(f"- {p}")
        if s["images"]:
            L.append(f"- 〔本段配图 {len(s['images'])} 张〕")
        if s["links"]:
            L.append(f"- 〔引用链接 {len(s['links'])} 个：{s['links'][0]}〕")
        L.append("")

    nums = sorted(set(NUM.findall(text)))
    if nums:
        L += ["## 出现过的数字（写分镜时对一遍口径）", "", "`" + "  ·  ".join(nums[:40]) + "`", ""]

    out.write_text("\n".join(L), encoding="utf-8")

    # ---- 控制台结论
    print(f"字数 {total_chars} → 预估 {mmss(est)}（{CPS} 字/秒）")
    print(f"配图 {len(links)} 张：落地 {len(links)-len(missing)}，缺失 {len(missing)}")
    if not a.no_copy and copied:
        print(f"已复制到 {assets}/（{len(copied)} 张），可直接粘进 script_data.py：\n")
        print("IMG = {")
        for m in mapping:
            if m.get("dst"):
                print(f'    "{Path(m["dst"]).stem}": "{m["dst"]}",')
        print("}")
    need = [r for r in rows if r.get("crop")]
    if need:
        print(f"\n有 {len(need)} 张需要裁空白边：python image_margins.py {assets} --crop")
    print(f"\n摘要：{out}")
    print("下一步：先写突破点（规则 26）→ 再写 script_data.py；按上面的字数决定砍到几秒。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
