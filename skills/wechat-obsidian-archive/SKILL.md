---
name: wechat-obsidian-archive
description: Use when the user asks to archive, save, or backup a WeChat public account (公众号) article link
---

# 公众号文章一键存档

## 概述

将公众号文章链接一键存档为 Markdown 文件，包含标题、作者、发布时间、完整正文（含图片）和自动生成的阅读笔记。

**默认保存到项目当前目录**（即 AI 的工作目录），按 `{年份}/{作者}/` 组织，图片保存在同级的 `assets/{日期}/` 下。也可指定 `--output-dir "~/参考资料库/公众号文章"` 存档到 Obsidian 目录。

## 使用流程

1. 用户提供公众号文章链接
2. 确定 Python 路径，安装依赖（如有缺失）
3. 运行 Python 脚本抓取并解析文章，**用 `--output-json` 参数直接写到 JSON 文件**
4. 读取 JSON 中的 `content`（图片已是本地路径，勿重复下载）
5. 生成阅读笔记（核心观点、金句、思考）
6. 用 Python 写入最终的 Markdown 文件
7. 清理临时文件（`output.json`）
8. 告知用户文件路径

## 步骤

### 0. 确定 Python 路径（避免环境歧义）

用户的 `python` 命令可能指向虚拟环境（如 hermes-agent venv），没有安装依赖。
**务必使用系统 Python 或明确指定路径：**

```powershell
# 方法 A：使用系统 Python（推荐）
$python = "C:\Users\郭红俊\AppData\Local\Programs\Python\Python314\python.exe"

# 方法 B：如果 python 命令可用，先验证依赖
python -c "import bs4, requests, html_to_markdown" 2>$null
if ($LASTEXITCODE -ne 0) { pip install beautifulsoup4 lxml html-to-markdown requests }
$python = "python"
```

依赖检查（如遇缺失则安装）：
```powershell
pip install beautifulsoup4 lxml html-to-markdown requests
```

### 1. 运行抓取脚本，保存 JSON 输出

**使用 `--output-json` 参数直接写文件（避免 pipe 重定向编码问题）：**

默认保存到项目当前目录：
```powershell
$env:PYTHONUTF8=1
& $python <skill_base_dir>/scripts/archive-wechat.py `
  "<文章链接>" `
  --output-dir "." `
  --output-json "output.json"
```

如需存档到 Obsidian：
```powershell
$env:PYTHONUTF8=1
& $python <skill_base_dir>/scripts/archive-wechat.py `
  "<文章链接>" `
  --output-dir "~/参考资料库/公众号文章" `
  --output-json "output.json"
```

脚本输出的 JSON 包含以下字段，**必须保存到文件**（后续步骤需要反复读取）：

| 字段 | 说明 |
|------|------|
| `meta` | 标题、作者、发布时间、URL |
| `content` | **正文 Markdown，图片路径为相对于 `file_path` 的相对路径（已转为 `/`）** |
| `file_path` | 文件将要保存的绝对路径（已展开 `~`） |
| `assets_dir` | 图片存放目录的绝对路径（已展开 `~`） |

### 2. 读取 JSON，准备写入文件

从 `output.json` 中读取数据。**不要重新抓取页面或下载图片**——`content` 中的图片地址已是本地路径，直接使用即可。

### 3. 生成阅读笔记

基于 `content` 生成以下三部分，插入到正文和 YAML frontmatter 之间：

**核心观点（3条）：**
- 提取文章的主要论点、关键信息、重要数据、案例、方法论
- 每条用一句话概括

**金句摘录（3句）：**
- 选取文中可传播的精彩表达
- 直接引用原文

**思考/迭代点：**
- 从我的视角出发的思考
- 启发和应用场景

### 4. 写入最终文件

组装完整的 Markdown 内容，写入 `file_path`。**使用 Python 写入**（避免编码问题）：

```python
import json, os
from datetime import datetime

with open("output.json", "r", encoding="utf-8") as f:
    data = json.load(f)

meta = data["meta"]
content = data["content"]  # 图片是相对路径（如 assets/2026-06-18/abc.jpg），已用 /，直接使用
file_path = data["file_path"]  # 已展开为绝对路径

frontmatter = f"""---
标题: "{meta['title']}"
作者: "{meta['author']}"
发布时间: "{meta['publish_date']}"
来源: 公众号
url: "{meta['url']}"
存档时间: "{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
tags: [公众号存档]
---
"""

reading_notes = """## 核心观点

1. ...
2. ...
3. ...

## 金句摘录

> ...
> ...
> ...
"""

thinking = """

## 思考/迭代

- ...
"""

full_md = frontmatter + reading_notes + "\n## 正文\n\n" + content + thinking

os.makedirs(os.path.dirname(file_path), exist_ok=True)
with open(file_path, "w", encoding="utf-8") as f:
    f.write(full_md)

print(f"Saved: {file_path}")
```

最终文件结构（示例）：

```markdown
---
标题: "..."
作者: "..."
发布时间: "..."
来源: 公众号
url: "..."
存档时间: "..."
tags: [公众号存档]
---

## 核心观点

1. ...
2. ...
3. ...

## 金句摘录

> ...

> ...

> ...

## 正文

{content (图片已是本地路径)}

## 思考/迭代

- ...
```

### 5. 清理临时文件

删除 `output.json`。

### 6. 告知用户

告知用户文件已保存到的路径。

### 关键陷阱：勿重新下载图片

脚本返回的 `content` 中，图片路径已经是相对于 markdown 文件的**相对路径**（如 `assets/2026-06-18/abc.jpg`），写入文件时**直接使用即可**。

**切勿重新抓取页面或再次下载图片**，否则会导致：
- 同一张图片产生多个副本（UUID 文件名不同），浪费磁盘空间
- 两步之间的图片路径不一致，markdown 中的图片链接失效
- 重复的网络请求拖慢流程

### 路径说明

| 路径 | 格式 | 示例（项目目录） | 示例（Obsidian） |
|------|------|---|---|
| `file_path` | 绝对路径（已展开 `~`） | `E:\mycode\project\2026年\作者\file.md` | `C:\Users\郭红俊\参考资料库\...\file.md` |
| `assets_dir` | 绝对路径（已展开 `~`） | `E:\mycode\project\2026年\作者\assets\2026-06-11\` | `C:\Users\郭红俊\参考资料库\...\assets\date\` |
| content 中图片路径 | 相对于 `file_path` 所在目录（**已用 `/`**） | `assets/2026-06-11/abc.jpg` | `assets/2026-06-18/abc.jpg` |

脚本已自动处理 `\` → `/` 转换，无需额外操作。

### Windows 编码问题（脚本已内置修复）

脚本已在 `archive-wechat.py` 开头加入以下兼容代码：

```python
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
```

同时建议运行前设置 `$env:PYTHONUTF8=1` 作为双重保障。

| 问题 | 表现 | 修复方式 |
|------|------|----------|
| pipe 重定向时 `print(json.dumps(...))` 乱码 | `gbk` 编码错误或中文变乱码 | 使用 `--output-json` 参数直接写文件（**推荐**） |
| `subprocess.run` 捕获 curl 输出 | `UnicodeDecodeError` | 脚本已内置 `encoding='utf-8'`，无需额外操作 |
| 写入最终 Markdown 文件 | 中文乱码 | 使用 Python `encoding='utf-8'` 写入 |

### 写入最终 Markdown 文件

由于 PowerShell 在中文环境下存在编码问题，**推荐使用 Python 写入最终文件**。例如：

```python
with open(file_path, "w", encoding="utf-8") as f:
    f.write(full_md_content)
```
