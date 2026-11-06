---
name: exam-paper-pdf
description: 把扫描版/图片版试卷 PDF 做成「原题（含原卷插图）+ 答案 + 详细解析」的 A4 可打印文档：抽页图识题、按墨迹包围盒裁插图、Markdown→HTML→PDF 流水线、逐页目检。适用于高考/期中期末/模拟卷的答案册、讲义、题目重排，以及“截图被切了”“图不全”“PDF 不是 A4”“打印出来缺页”“页脚没有页码”等返工场景。exam paper / 试卷答案 / 原题+解析 / A4 打印。
---

# 扫描试卷 → 原题·答案·解析（A4 打印稿）

这是从一份真实高三化学期中卷（10 页扫描件、19 道题、15 张插图）做出来的流程。
第一版只给了答案和解析，被要求“把原题也带上”；加原题时用了肉眼估的裁剪框，
第 2 题的分子模型被切掉半个球、第 10 题表格丢了左边框、第 19 题装置图少了分液漏斗——
于是重做了一遍：**所有插图按像素墨迹包围盒定位，四周留白，出 PDF 前拼版目检、出 PDF 后逐页目检**。
下面每条规则都是那两轮返工换来的。

**语言约定：文档、说明、注释一律中文；代码、命令、字段名保持原文。**

## 适用场景

- “给这份 PDF 试卷出一份答案，带解析” → 先看是不是扫描件（见阶段 0）。
- “答案和解析要把原题也带上” → 原题文字 + 原卷插图，两者都要（阶段 1–2）。
- “做成 A4 可打印的 PDF” → 阶段 4；要页脚页码就上 CDP（命令行打印做不到）。
- “截图不全 / 图被切了 / 表格缺边” → 阶段 2 的墨迹包围盒 + `figcrop.mjs`。
- “打印出来是 Letter / 页边距不对 / 末页空白太多” → 阶段 4 的 print CSS。
- 任何“Markdown → 带图表 → 打印级 PDF”的活，脚本都能直接复用。

## 硬性规则

1. **先判 PDF 类型，再决定路线。** 打开二进制搜 `/Subtype /Image` 和 `/Font`：有大量 Image、没有 Font，就是图片型 PDF，`pdftotext` 没意义，直接抽页图（`extract_scan_images.py`）。
2. **原题 = 原文 + 原图，缺一不可。** 只把题干抄成文字，用户会问“图呢”；只贴整页截图，又不能复制、不能改。文字转写 + 插图裁切，两份都给。
3. **插图边界用像素量，不用眼睛估。** `figcrop.mjs auto` 在窗口内求墨迹包围盒；窗口四边如果“贴边”，说明图被窗口截断或窗口混进了邻行文字，换窗口重量，直到四边都不贴。
4. **裁图四周必须留 8–15px 白边，且不能带进邻近文字行。** 贴边=大概被切；带进文字=脏。用 `figcrop.mjs check` + `figcrop.mjs sheet` 双保险，肉眼看拼版图确认。
5. **小图不要硬放大。** 原卷上 14mm 宽的分子模型，裁出来就只有 140px；按原始像素显示即可，硬撑到通栏只会更糊。
6. **页脚页码只能用 CDP 的 `footerTemplate`。** `chrome --print-to-pdf` 没有页眉页脚参数；用 `position:fixed` 假页脚，在 CDP 打印里会叠到正文上（实测压在第一行正文）。见 `makepdf.mjs`。
7. **Node 里一律写 WSL 路径 `/mnt/x/...`。** 传 `D:\test\out.pdf` 会被当成当前目录下的文件名，生成一个叫 `D:\test\out.pdf` 的怪文件。
8. **出 PDF 前逐图体检，出 PDF 后逐页渲染目检。** 只看 HTML 预览不算验收——分页是打印时才发生的（`render_pages.mjs`）。
9. **Markdown 转换器必须容忍三件事：** 跨行 `**加粗**`（用 `\*\*([\s\S]+?)\*\*`）、`- ` 列表行（不能被段落吞掉）、`![说明](路径)` 图片行（转 `<figure>` 并重算相对路径）。
10. **打印 CSS 参数照抄，别现场调：** A4；页边距 14/13/15/13mm；正文 10.2pt/1.56；表格 9.6pt；`figure img{max-height:67mm}`；`h2,h3{break-after:avoid}`；`table,figure{break-inside:avoid}`。图高给到 78mm 就会频繁把整块图推到下一页、留大段白。
11. **化学式用 Unicode，不用 LaTeX。** H₂SO₄、Fe³⁺、SO₄²⁻、⇌、↑、↓、ΔH、Ksp——复制到微信/Word 都不掉格式。
12. **选择题要逐项判，并且写清“其他三项为什么对”。** 只说答案不叫解析；“性质—用途对应关系”类要看因果是否成立（例：CaSO₄→CaCO₃ 靠 Ksp 差异，不是“Na₂CO₃ 显碱性”）。
13. **每题固定三段：题目 → 答案 → 解析。** 卷首一张“答案速查表”，卷末一段“易错点提示”。
14. **答案里不确定的地方要标出来。** 扫描件识读难免有 1–2 处拿不准（箭头方向、导管长短），在交付说明里点名，让用户对原卷核。

## 工作流程

### 阶段 0　环境与素材

```bash
# 1. 判类型
python3 - <<'PY'
import re
d=open('试卷.pdf','rb').read()
print('images', len(re.findall(rb'/Subtype\s*/Image', d)), 'fonts', len(re.findall(rb'/Font', d)), 'pages', len(re.findall(rb'/Type\s*/Page[^s]', d)))
PY

# 2. 图片型 → 抽页图
python3 scripts/extract_scan_images.py 试卷.pdf -o work/img
```

依赖（缺什么装什么，全部是 npm 包，不需要编译工具链）：

```bash
cd work && npm i @napi-rs/canvas pdfjs-dist puppeteer-core
```

Chrome 用系统的即可（WSL 里直接调 Windows 版，见 `references/environment.md`）。
**不要指望 pandoc / libreoffice / pdftoppm / PIL**：这四样在目标机器上大概率没有。

### 阶段 1　识题与解题

1. 整页图按 ~1700px 宽读一遍，通读题干和选项（`read_image`）。
2. 读不清的局部（上下标、箭头、表格单元格）用 `figcrop.mjs crop` 放大到 3–6 倍再看。
3. 边读边把题目**原文**敲进 Markdown：题干、四个选项、每个小问的空格、已知条件表。
4. 解题时逐项写理由；选择题的干扰项套路（VSEPR 模型 vs 空间结构、吸氧腐蚀写 Fe²⁺/OH⁻、平衡移动方向、晶胞粒子数、Ksp 沉淀转化）见 `references/pitfalls.md` 的“学科侧”。

### 阶段 2　插图裁剪

```bash
# 先量（窗口要只框住这张图）
node scripts/figcrop.mjs auto work/img/p01.jpg 780 1600 1150 1800 --pad 10
# → box=(772,1618,142,128)；若提示“贴边”，把窗口放大重量

# 批量裁：spec.json 里写 name/page/box（box 也可写 "auto"+window）
node scripts/figcrop.mjs crop spec.json -o figs

# 体检 + 拼版目检
node scripts/figcrop.mjs check figs --min 3
node scripts/figcrop.mjs sheet figs review.png --width 720
```

判读顺序：`check` 报贴边 → 看 `review.png` → 判断是“被切了”（扩窗口）还是“混进文字了”（收窗口）。

### 阶段 3　排版（Markdown 结构）

```markdown
## 一、选择题答案速查
| 题号 | 1 | 2 | … |
|------|---|---|----|
| 答案 | B | B | … |

### 1．
> **题目**　题干原文……
> A．选项
> B．选项

![第2题B选项插图](figs/q2.png)

**答案：B**

**解析**
- A．……正确。
- B．……错误。
```

- `>` 引用块 = 题目框（浅底 + 左色条），渲染成"原卷那一块"。
- `![说明](figs/x.png)` 独占一行 = 带图注的插图。
- 图片路径按 HTML 所在目录自动重算，md 和 html 可以不同层。

### 阶段 4　出 A4 PDF

```bash
# 1. Markdown → 打印版 HTML
node scripts/md2page.mjs 答案.md work/print.html print

# 2. 起带调试端口的 Chrome（只需一次）
"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless=new --disable-gpu --remote-debugging-port=9333 \
  --user-data-dir="C:\\Temp\\chrome-cdp" about:blank &

# 3. 打印（页脚页码在这里注入）
node scripts/makepdf.mjs work/print.html "答案_A4.pdf" --footer "2026 朝阳高三期中化学 · 参考答案与解析"

# 4. 体检
python3 scripts/check_pdf.py 答案_A4.pdf --expect A4
```

### 阶段 5　验收

```bash
node scripts/render_pages.mjs 答案_A4.pdf work/pages --scale 1.6
```

逐页看图，重点看四件事：①每张插图四边有没有被切；②有没有图把题目和答案劈开；
③表格有没有跨页断行；④末页是不是只剩两三行（可以压字号或调图高）。清单见 `references/qa-checklist.md`。

## 交付

一次给三份，用途不同：

| 文件 | 用途 |
|---|---|
| `xxx.md` | 纯文本，可复制到微信/QQ/Word，可改 |
| `xxx.html` | 单文件网页，双击即读，可“另存为 PDF” |
| `xxx_A4.pdf` | 直接打印/转发，带页脚页码 |

文件名带卷别和内容（`2026朝阳高三期中化学_原题+答案+解析_A4.pdf`），并在回复里给打印建议
（A4 纵向、100% 比例、双面、黑白打印即可）。

## 故障对照表

| 症状 | 原因 | 处理 |
|---|---|---|
| `pdftotext` 抽出空 | 图片型 PDF | 抽页图，走 OCR/人眼读 |
| 截图缺一块 | 肉眼估的裁剪框 | `figcrop.mjs auto` 重量，留 8–15px |
| 截图带进下一行字 | 窗口下沿太低 | 按行墨迹投影找空白带，收窗口 |
| PDF 是 Letter | `@page size` 没写或没生效 | `@page { size: A4 }` + CDP `format:'A4'` |
| 没有页码 | 用了命令行打印 | 改 CDP `footerTemplate` |
| 页脚压住正文 | `position:fixed` 假页脚 | 删掉 DOM 页脚，用 CDP 页脚 |
| 生成的文件名带 `D:\` | 给 Node 传了 Windows 路径 | 改 `/mnt/d/...` |
| 加粗没生效 | `**…**` 里有换行 | 正则用 `[\s\S]+?` |
| 列表变成一段 | 段落循环吞了 `- ` 行 | 段落终止条件加 `^- ` |
| 一堆图堆到下一页、留大片白 | `figure img` 太高 | `max-height:67mm` |
| 末页只有两行 | 整体略超一页 | 字号降 0.2pt / 行距降 0.04 / 图高压 5mm |

## 参考文件

- `references/pitfalls.md`　两轮返工的完整踩坑记录（含具体数值、坐标、报错）
- `references/qa-checklist.md`　交付前逐项勾选清单
- `references/environment.md`　WSL + Windows Chrome 的工具链、命令、依赖
- `templates/answer-doc.md`　答案册骨架（速查表 + 逐题三段 + 易错点）
