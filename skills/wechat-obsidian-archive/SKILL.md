---
name: wechat-obsidian-archive
description: Use when the user asks to archive, save, or backup a WeChat public account (公众号) article link to Obsidian
---

# 公众号文章一键存档到 Obsidian

## 概述

将公众号文章链接一键存档为 Obsidian Markdown 文件，包含标题、作者、发布时间、完整正文（含图片）和自动生成的阅读笔记。

## 使用流程

1. 用户提供公众号文章链接
2. 运行 Python 脚本抓取并解析文章，JSON 输出保存到文件
3. 读取 JSON 中的 `content`（图片已是本地路径，勿重复下载）
4. 生成阅读笔记（核心观点、金句、思考）
5. 用 Python 写入最终的 Obsidian Markdown 文件
6. 告知用户文件路径

## 步骤

### 1. 运行抓取脚本，保存 JSON 输出

```bash
python .opencode/skills/wechat-obsidian-archive/scripts/archive-wechat.py \
  "<文章链接>" \
  --output-dir "~/参考资料库/公众号文章" \
  > output.json
```

**Windows 用户注意：** 先设置环境变量 `$env:PYTHONIOENCODING='utf-8'`，否则 `print(json.dumps(...))` 会因 gbk 编码报错：
```powershell
$env:PYTHONIOENCODING='utf-8'
python .opencode/skills/wechat-obsidian-archive/scripts/archive-wechat.py `
  "<文章链接>" `
  --output-dir "~/参考资料库/公众号文章" `
  > output.json
```

脚本输出的 JSON 包含以下字段，**必须保存到文件**（后续步骤需要反复读取）：

| 字段 | 说明 |
|------|------|
| `meta` | 标题、作者、发布时间、URL |
| `content` | **正文 Markdown，图片路径为相对于 `file_path` 的相对路径** |
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
content = data["content"]  # 图片是相对路径（如 assets/2026-06-18/abc.jpg），直接使用
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

full_md = frontmatter + reading_notes + "## 正文\n\n" + content + thinking

os.makedirs(os.path.dirname(file_path), exist_ok=True)
with open(file_path, "w", encoding="utf-8") as f:
    f.write(full_md)

print(f"Saved: {file_path}")
```

最终文件结构：

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

## 注意事项

- 首次使用需安装依赖：`pip install -r .opencode/skills/wechat-obsidian-archive/scripts/requirements.txt`
- 需要 `curl` 命令可用。**Windows 必须用 `curl.exe`**（PowerShell 的 `curl` 别名指向 `Invoke-WebRequest`，不是真正的 curl）
- 如果 `.opencode/skills/` 找不到，说明用户没有运行项目根目录，先定位项目目录

### 关键陷阱：勿重新下载图片

脚本返回的 `content` 中，图片路径已经是相对于 markdown 文件的**相对路径**（如 `assets/2026-06-18/abc.jpg`），写入文件时**直接使用即可**。

**切勿重新抓取页面或再次下载图片**，否则会导致：
- 同一张图片产生多个副本（UUID 文件名不同），浪费磁盘空间
- 两步之间的图片路径不一致，markdown 中的图片链接失效
- 重复的网络请求拖慢流程

### 路径说明

| 路径 | 格式 | 示例 |
|------|------|------|
| `file_path` | 绝对路径（已展开 `~`） | `C:\Users\郭红俊\参考资料库\...\file.md` |
| `assets_dir` | 绝对路径（已展开 `~`） | `C:\Users\郭红俊\参考资料库\...\assets\date\` |
| content 中图片路径 | 相对于 `file_path` 所在目录 | `assets\2026-06-18\abc.jpg` |

图片路径在写入 markdown 前建议将 `\` 转为 `/` 以确保跨平台兼容：
```python
import re
content = re.sub(r'!\[图片\]\(([^)]+)\)', lambda m: f"![图片]({m.group(1).replace(chr(92), '/')})", content)
```

### Windows 编码问题

此脚本在 Windows 上可能遇到编码问题，原因如下：

| 问题 | 表现 | 解决方法 |
|------|------|----------|
| `subprocess.run` 捕获 curl 输出 | `UnicodeDecodeError: 'gbk' codec can't decode byte` | 脚本已内置 `encoding='utf-8'` 参数，无需额外操作 |
| `print(json.dumps(...))` 输出 JSON | `UnicodeEncodeError: 'gbk' codec can't encode character` | 运行前设置 `$env:PYTHONIOENCODING='utf-8'` |
| 写入最终 Markdown 文件 | 包含中文的 markdown 内容 | 使用 Python（而非 PowerShell）写文件，指定 `encoding='utf-8'` |

### 写入最终 Markdown 文件

由于 PowerShell 在中文环境下存在编码问题，**推荐使用 Python 写入最终文件**。例如：

```python
with open(file_path, "w", encoding="utf-8") as f:
    f.write(full_md_content)
```
