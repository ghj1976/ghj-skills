---
name: article-illustrator
description: 分析文章内容，自动生成配图并插入对应位置。当用户要求"给文章配图""生成插图"时使用
---

# 文章配图技能

## 工作流程

### 第一步：分析文章

逐段阅读文章，标记需要配图的位置。

**适合配图的场景：**
- 抽象概念需要可视化（如"注意力机制"、"特征提取"）
- 流程/步骤需要图解（如"训练过程分为三步"）
- 对比关系需要可视化（如"方案A vs 方案B"）
- 数据/指标需要图表化（如"准确率从70%提升到95%"）
- 核心观点需要强化记忆

**不需要配图的场景：**
- 代码示例
- 简单列表（1-3项）
- 已经很直观的描述
- 过渡性段落

**数量原则：** 宁可少而关键，也不要多而分散。每篇文章配图控制在 2-5 张，只在不配图难以理解的位置才配图。

### 第二步：选择风格

根据文章主题和语气选择统一风格，同一篇文章内保持一致。

|   风格   |        适用场景        |
|---------|------------------------|
| 科技感   | AI、算法、数据、技术话题 |
| 手绘涂鸦 | 轻松、思考、科普类内容   |
| 极简扁平 | 流程、对比、通用话题     |
| 信息图表 | 数据、流程、对比类内容   |

风格确定后，在后续所有提示词中统一加入风格描述。

### 第三步：生成配图计划

为每张配图输出以下内容：

```yaml
配图计划:
  - 文件名: "01-concept-comparison"     # 两位编号 + 英文描述
    插入位置: "在「什么是X」段落之后"       # 明确指示
    配图目的: "帮助理解抽象概念"            # 为什么需要配图
    视觉内容: "..."                        # 图片展示的具体内容
    风格: "科技感"                         # 与第二步保持一致
```

文件名规则：
- 两位数字编号（01、02、03...）
- 连字符连接英文关键词
- 示例：`01-model-architecture`、`02-performance-comparison`

### 第四步：生成图片

为每张配图依次执行：

1. **撰写提示词**：基于配图计划中的"视觉内容"，扩展为详细的英文提示词（50-100词），包含风格描述、主体、背景、光影、构图等细节。

2. **保存提示词**：将提示词保存到 `imgs/prompts/` 目录：
   ```
   imgs/prompts/01-concept-comparison.md
   ```

3. **调用脚本生成图片**：
   ```bash
   python scripts/generate_image.py \
     --prompt "A clean product photo of a glass cube on a white studio background..." \
     --filename "01-concept-comparison" \
     --output-dir "./imgs" \
     --size "1024x768"
   ```

4. **验证结果**：检查 `imgs/` 目录下是否生成了对应文件。如果生成失败，脚本会自动重试一次。

5. **异常处理**：如果脚本返回非零退出码，检查错误信息后重新生成。

### 第五步：插入文章

将图片插入到文章对应位置，格式要求：

```markdown

![概念对比示意图](imgs/01-concept-comparison.png)

```

规则：
- 图片前后各留一个空行
- alt 文本用简洁的中文描述
- 路径为相对文章文件的路径

---

## 文件结构

```
article-folder/
├── article.md
├── imgs/
│   ├── prompts/
│   │   ├── 01-concept-comparison.md
│   │   └── 02-workflow-diagram.md
│   ├── 01-concept-comparison.png
│   └── 02-workflow-diagram.png
└── scripts/
    └── generate_image.py
```

## 注意事项

- 配图服务于内容，避免为了配图而配图
- 敏感人物使用卡通形象替代，不要使用真实人物照片
- 提示词使用英文撰写，可以获得更稳定的生成效果
- 如果 API 返回 429 限流错误，等待几秒后重试
- 脚本依赖环境变量 `AGNES_API_KEY`，使用前确认已设置

## 常见异常及处理

### 1. 文件名含全角/特殊 Unicode 字符导致 Edit 工具找不到文件

**现象：** 中文文件名包含全角引号（`""`，U+201C/U+201D）、全角逗号（`，`，U+FF0C）、全角问号（`？`，U+FF1F）等特殊 Unicode 字符时，Edit、Read 等工具传入的路径字面量与实际文件名不匹配，提示 "File not found"。

**原因：** 工具或 Shell 传递路径时自动将全角引号转为半角引号，导致路径不一致。

**处理方式：** 改用 Python 脚本处理文件操作。示例：
```python
import os
for f in os.listdir(article_dir):
    if f.endswith('.md'):
        filepath = os.path.join(article_dir, f)
        break
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()
# 修改内容后写回
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
```

### 2. PowerShell 终端中文输出乱码

**现象：** PowerShell 输出的中文内容显示为乱码（如 `华为` 显示为 `��Ϊ`）。

**原因：** PowerShell 的代码页与文件实际编码（UTF-8）不匹配。

**处理方式：** 不依赖 Shell 输出的中文内容判断结果。改用以 Python 读取文件并验证：
```python
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()
# 通过索引位置、英文关键词或 .png 等非中文特征判断
for i, line in enumerate(lines, 1):
    if '.png' in line:
        print(f'Image found at line {i}')
```

### 3. Python 脚本中中文字符串替换/匹配失败

**现象：** 将含中文的旧/新字符串写入 `.py` 文件再执行，replace() 返回 0 次匹配。

**原因：** Write 工具写入文件时，中文 Uncode 字符的编码可能发生变化，导致脚本中的字符串字面量与目标文件的实际字节不匹配。

**处理方式（优先级从高到低）：**
- **按索引位置插入（推荐）：** 定位目标位置附近的唯一非中文锚点（如 `---`、`## `），用 `content.find()` 找到索引后切片插入，避免中文精确匹配：
  ```python
  idx = content.find('---\n\n## 第二章')
  image_md = '![配图](imgs/01-image.png)\n\n'
  content = content[:idx] + image_md + content[idx:]
  ```
- **定位锚点后整体替换：** 用英文/数字/符号作为锚点，减少中文匹配：
  ```python
  # 用唯一上下文行做匹配，包裹少量中文
  old = '快走到了尽头。\n\n\n\n---'
  content = content.replace(old, new, 1)
  ```
- **直接使用 Python 交互：** 不经过 Write 工具写脚本文件，直接在 `python -c` 内联执行（注意 Shell 转义问题）。

### 4. 字符串替换时空行数量不匹配

**现象：** replace() 返回 0 次匹配，但肉眼确认文本存在。

**原因：** 原始文本和替换字符串中的空行（`\n`）数量不一致。例如文件中有 3 个空行（`\n\n\n\n`），但替换字符串写了 4 个空行（`\n\n\n\n\n`）。

**处理方式：** 先用 repr() 确认精确的空行数量：
```python
idx = content.find('目标段落末尾关键词')
print(repr(content[idx:idx+80]))  # 查看精确的换行符数量
```
然后按实际数量编写替换字符串，或改用索引插入。

### 5. 多张配图并行生成导致同时调用 API

**现象：** 同时调用多个 `generate_image.py` 进程，可能触发 API 限流（429）。

**处理方式：** 默认并行调用通常是安全的，但如果遇到 429 错误，改为串行生成，每张之间等待 2-3 秒。脚本内置了 1 次自动重试，如果重试后仍失败，手动等待后单独重试该图片。
