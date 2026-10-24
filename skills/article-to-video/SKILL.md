---
name: article-to-video
description: 把 Markdown 文章（尤其是中文公众号文章）制作成带解说的短视频：VoxCPM2 配音、本地图片、连续长段音频、ASR 词级对齐字幕、手机优先的动态画面。适用于文章转视频、图片链接修复、音色与语速选择、9:16 竖屏或 16:9 横屏、字幕同步，以及卡顿、冻结帧、断音排查。article-to-video / MD → 视频。
---

# 文章 → 解说视频

这是一套从真实公众号改稿中沉淀出来的生产流程：第一版 3:58 横屏被否，原因是“开头太静止、声音太快”；第二版 3:20 竖屏修正了节奏，但下划线压字、音色忽好忽坏；最终 3:00 版修掉了切换冻结、话没说完就切、尾音丢失。下面的规则都是踩过坑之后留下的，按顺序执行。

**语言约定：同等条件下优先中文。** 文档、说明、字幕、口播都用中文；代码、命令、字段名保持原文。

## 适用场景

- “把这篇公众号文章做成视频” / article-to-video / Markdown → 带解说的 MP4。
- Markdown 里的图片指向不存在的 `assets/...`，但图片就在文章同目录。
- 要做手机端竖屏（视频号 / 抖音 / 朋友圈）或 16:9 横屏。
- 已有视频出现：开头静止、语速太快/不可信、图片切换卡顿、字幕抢在话没说完前切换、尾音缺失。
- 需要一套可复用的流程：字幕、解说稿、质量门。

## 硬性规则

1. **绝不把长段 TTS 按句切成小段。** 按估算停顿切，就是丢字的根源。长段音频整体保留，ASR 只用来定画面/字幕时间。
2. **切点对齐到“下一句开口”，不是停顿中点。** 上一句完整播完、下一句开始，才允许切画面。
3. **文字镜头之间不要叠化。** 两行大字或两张复杂插画叠在一起，看起来像渲染故障。硬切 + 连续运动更顺。
4. **每一帧都要动。** 停顿期间也保持线性推拉；文字卡加缓慢推近 + 光扫。先静止再突然跳，观众会感知为卡顿。
5. **下划线用字形 bbox，不能用字号估算。** 中文字形下缘会超出 em 框，`y + font_size` 会正好压到笔画。
6. **验收解码后的 MP4，不是源帧。** 编码器会跳过低运动块；解码后连续多帧完全一样，才是真的冻结。
7. **保留旧版本。** 新版本放新目录或 `out/vN/`；不要覆盖用户要对比的版本。
8. **按手机屏幕验收。** 文字要在 1080×1920 上、避开右侧和底部平台 UI 后仍然可读。

## 新项目脚手架

```bash
# SKILL 是本 skill 的根目录（skill loader 会给出）
SKILL=<本 skill 根目录>   # 例如 /mnt/e/mycode/ghj-skills/skills/article-to-video
PROJ=work/<视频短名>
mkdir -p "$PROJ/audio" "$PROJ/out"
cp "$SKILL"/scripts/*.py "$PROJ"/
cp "$SKILL"/scripts/script_data_template.py "$PROJ"/script_data.py
```

然后：

1. 改 `script_data.py`（场景、beat、`img` 文件名）。
2. 放入 4–8 秒的 `audio/prompt_ref.wav`，把它的准确文本写进 `tts_chunks.py` 的 `PROMPT_TEXT`。
3. 改 `project_config.py` 的 `EXCLUDE`；配音、对齐、构建三个脚本共用这一份，保持一致。
4. 如果图片不在项目目录，设置 `ASSET_DIR`，或渲染时传 `--assets <dir>`。

`build_audio_cont.py` 和 `align_asr.py` 会自动推导 `GROUPS`：每 2 个场景一段，所以 8 个场景 → 4 段，3 个场景 → 2 段；场景数为奇数时，最后一段只含 1 个场景。

## 流程总览

| 阶段 | 产出 | 通过标准 |
|---|---|---|
| 0 素材 | 图片映射、画幅决策 | 每张图都看过并匹配段落 |
| 1 脚本 | `script_data.py`，35–50 个 beat | 前 3 秒有钩子；总长 2:45–3:30 |
| 2 配音 | 2–4 个长段 WAV | 段基频 85–115Hz，4.5–6.5 字/秒 |
| 3 音频 | 连续 `narration.wav`、音乐/音效、混音 | −16 LUFS，真峰值 ≤ −1.5dB |
| 4 对齐 | `asr_times.json`、`timeline.json` | 切点 = 下一句开口 |
| 5 渲染 | 1080×1920 或 1920×1080 MP4 | 每个镜头都在动，无叠化 |
| 6 QA | 自动报告、截图、README | CFR、解码干净、无冻结窗口 |

## 阶段 0 — 素材与图片

1. 完整读一遍 Markdown，整理标题、章节、金句、数字、图片出现顺序。
2. **按文章顺序修图片链接，然后逐张打开确认。** 典型坏链接是 `assets/<文章标题>/file-*.png`，真实图片在文章目录。把第 n 张图映射到本地第 n 个 PNG，但一定要看图片内容是否匹配相邻段落，不能只看文件名。
3. 检查尺寸/比例，排除重复图、无关截图。
4. 选画幅：
   - **9:16，1080×1920**：手机优先、视频号、抖音。用户说“普通手机用户”“划走”时默认竖屏。
   - **16:9，1920×1080**：只在文章内嵌播放器或用户明确要横屏时使用。
5. 每个版本单独建项目目录；图片可只读引用，不能覆盖旧版本。

**项目结构**

```
project/
  script_data.py          # 场景、口播、字幕、大字、版式
  tts_chunks.py           # VoxCPM2 长段配音
  align_asr.py            # faster-whisper 词级时间戳
  build_audio_utils.py    # 垫乐、音效、混音、SRT、解说稿
  build_audio_cont.py     # 连续音频 + 时间轴
  render.py               # 竖屏/横屏画面渲染
  qa_video.py             # 自动检查
  audio/
    prompt_ref.wav        # 4–8 秒、文本已知的音色提示
    chunk_0..N.wav        # 长段配音
    asr_times.json
  out/
    timeline.json narration.wav music.wav sfx.wav audio_mix.wav
    subtitles.srt 解说稿.md <成片>.mp4
```

## 阶段 1 — 脚本与分镜

目标总长 **2:45–3:30**，语速 **5.2–5.8 中文字/秒**，通常 900–1100 字。第一版 1667 字、7.8 字/秒，即使 3:58 也显得急。

结构：

1. **钩子（0–3 秒）**：一句具体、反常识的话。例如“一个 AI，为了查清公园门口谁人多，连轴转了十一天。” 开头必须有运动，不要 15 秒静止标题。允许 1 秒动态标题，然后立刻切。
2. **冷开场（3–20 秒）**：4–6 个镜头，每个 2–5 秒，交代前提和最离谱的细节。每出现一个新事实就切。
3. **主体**：4–6 个章节，一个镜头一个观点。保留原文数字和对方回应，不要把评论写成断言。
4. **反转**：反直觉的那句话（“最冷的一句话” / “天网没来”）。
5. **收尾**：短回调 + 一个开放问题，不要长总结。

单个 beat 的字段（`script_data.py`）：

```python
{
  "id": "00_01",
  "text": "它连轴转了十一天。",              # 口播；标点会影响停顿
  "sub": "它连轴转了十一天",                  # 字幕，每行 ≤ 15 个中文字
  "big": "11 天",                          # 画面大字，3–9 字
  "layout": "card",                        # card | text | data | hook
  "accent": "orange",                      # orange | cyan
  "eyebrow": "连轴转",                     # 小标签
  "img": "file-....png",                   # 单 beat 覆盖图片
}
```

规则：

- 一个 beat = 一句字幕 = 一次画面变化。短于 0.8 秒的碎片合并；超过约 28 个中文字拆开。
- 字幕最多 2 行，1080 宽、64px 时每行 ≤ 15 个中文字。长句要手动写 `\n`，不要依赖自动换行。
- `big` 用来说观点，不要重复字幕全文；如果图片里已经有同一句话，换一个角度。
- `card`（图片 + 关键词）、`text`（引语/数字）、`data`（数据）、`hook`（全屏、最快切）交替使用。文字卡不要连续静止超过约 4 秒。
- `text` 里不要放 Markdown、链接、括号备注、舞台提示。

## 阶段 2 — 配音

有 VoxCPM2 就用。注意：实际安装的 CLI/API 可能比 GitHub README 旧，先看真实签名再传 `seed`（2.0.3 包不接受 `seed`，用 `torch.manual_seed`）。核心 API：

```python
model.tts_model.build_prompt_cache(...)
model.tts_model.generate_with_prompt_cache(
    target_text=..., prompt_cache=..., inference_timesteps=10)
```

### 环境

系统 Python 常常是 CPU 版 torch。有 CUDA 时，建一个继承已安装 `voxcpm` 的隔离 venv，只补 CUDA torch：

```bash
python -m venv --system-site-packages .venv-tts
.venv-tts/Scripts/python.exe -m pip install --no-deps \
  torch==2.11.0+cu128 torchaudio==2.11.0+cu128 \
  -f https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/
```

默认 PyTorch 源可能很慢；SJTU 镜像实测约 15MB/s。CPU 推理约 40 倍实时（30 秒音频约 20 分钟），工具调用会超时；CUDA 把 3 分钟脚本压到约 5 分钟生成。

### 最重要的一条：长段生成，不要逐句

逐句克隆会让音色漂移。被否的版本里，45 个独立 beat 的基频中位数在 **71–154Hz**；同一 prompt/reference 生成的 4 个长段是 **100 / 103 / 100 / 98Hz**。不要为了“时间精确”逐句生成；时间精确靠后面的 ASR。

1. 准备 **4–8 秒 `prompt_ref.wav`**：文本已知、低音、平稳。可以用生成的一个 beat 或干净的示例音色；把准确文本写进 `PROMPT_TEXT`。prompt + reference（同一个文件也可以）比只用 reference 更稳。
2. 生成 **2–4 个长段**，每段 30–60 秒，每 2 个场景一段。同一 prompt cache、`torch.manual_seed(20)`、`cfg_value=2.0`、`inference_timesteps=10`。
3. 不要给每段加风格前缀，除非确有必要；风格提示会改变音高。如果整体偏快，给**所有段**用同一个固定风格，或后期做轻微 `atempo`。
4. 每段测量：基频中位数（librosa.pyin，60–350Hz）和字/秒。接受 85–115Hz、4.5–6.5 字/秒；超出范围就重生成该段，不要用变调硬拉。
5. 长段保留，后面绝不再切。

命令：`scripts/tts_chunks.py`，分别跑 `--part 0 --of 2` 和 `--part 1 --of 2`。

## 阶段 3 — 连续音频与混音

1. 每段只裁首尾静音（−45dB 阈值，80ms 余量），段间留 0.6–0.7 秒空白。**不要按 beat 加空隙，也不要按 beat 切。**
2. 48kHz 生成 `narration.wav`、`music.wav`、`sfx.wav`。
3. 混音：口播 `loudnorm=I=-16:TP=-1.5:LRA=11`；音乐约 −38dBFS RMS；音效峰值约 0.30；`amix` 后加 `alimiter=limit=0.95`。
4. 检查分轨：口播 RMS 约 0.13，音乐约 0.010，音效约 0.005，最终真峰值 ≤ −1.5dB。第一版音效峰值到 1.0 直接削波，限幅器修掉了。
5. 音效：场景起点 whoosh、3–4 个重点 beat 用 impact、数字用 tick、反转前一个 riser。要稀疏；每 3 秒一个 whoosh 就成噪音了。

对应脚本：`scripts/build_audio_cont.py` + `scripts/build_audio_utils.py`。

## 阶段 4 — ASR 对齐（修“话没说完就切”）

画面/字幕切换必须落在**下一句开口**，且上一句已经完整播完。

1. 用 faster-whisper（`small`，CPU `int8` 足够）转写每个长段。**先把 48kHz 重采样到 16kHz**；直接喂 48kHz 会让 Whisper 听到 3 倍慢速音频，输出英文幻觉。
2. 取词级时间戳：`word_timestamps=True`、`language="zh"`。
3. 归一化原文和转写（去标点/空格、转小写），用 `difflib.SequenceMatcher` 做字符匹配；记录每个 beat 匹配到的第一个转写字符。
4. 第 *i* 个 beat 的结束边界 = **第 *i+1* 个 beat 第一个匹配词的开始时间**。最后一个 beat 到段尾结束。
5. ASR 失败时，回退到按字数比例的时间，并**偏晚**，绝不偏早。偏晚只是画面多停一拍；偏早就是切掉句子。
6. 写出 `asr_times.json`，用它构建时间轴。抽三个点验证：A 句最后词结束、停顿、B 句第一个词开始；切点必须等于 B 的开口。

脚本：`scripts/align_asr.py`。实测：“它连轴转了十一天”在 7.5–9.0 秒播完，9.0–9.5 秒停顿，切点 9.54 秒正好是下一句开口。早先逐句切只给了这句 1.08 秒，尾音被切掉。

## 阶段 5 — 渲染

手机默认：1080×1920，30fps，H.264 High，AAC-LC 48kHz 立体声，CRF 18–20，`-preset veryfast`，`+faststart`。

竖屏版式：

- 顶部 4–6px 进度条；左上章节标签在 y≈75；右上小品牌名。
- 大字区在 y≈220–500：eyebrow 27px，主关键词 90–170px（自动缩到 960px 宽），下划线用 `textbbox`。
- 图片卡：全宽 1080×608，y≈540；同一张图做模糊、压暗后铺满 1920 背景。
- 字幕：64px 加粗，最多 2 行，居中在 y≈1400–1550，黑色描边 8px，后面加暗色 scrim。
- 安全区：左右留 60px；避开底部 250px、右侧 120px 的平台 UI。

运动规则：

- **线性、无 clamp 的 Ken Burns**，覆盖包含停顿的整个镜头：`prog = min(1, lt / (next_start - start))`。不要用 smoothstep，它首尾速度为 0，会制造停顿。
- 亚像素采样：`Image.transform(..., Image.AFFINE, ...)`，用浮点缩放/位移。整数 `crop().resize()` 会每隔几帧跳 1px，产生微抖。
- **硬切，不叠化。** 叠化会让两行大字双重曝光，看起来像故障。切点用 whoosh 盖住。
- 文字/数据卡：整个画面缓慢推近（每场景约 7.5%）+ 低透明度光扫。否则编码器会跳过相同帧，卡片就冻住了。
- 不要在每次切换做 punch-in，也不要白闪；这两个都会放大“顿一下”的感觉。
- 下划线：

  ```python
  bbox = d.textbbox((x, y), text, font=f)
  y_line = bbox[3] + 16
  ```

- 纯文字版式：画字前先加暗色 scrim（alpha≈125），避免浅色图片把字洗掉。
- 字体用 `C:\Windows\Fonts` 下的 `Noto Sans SC Bold` / `Medium`，传完整 `.otf` 路径（含空格）。

`scripts/render.py` 是可直接用的竖屏渲染器。首次渲染前改项目副本里的 `BRAND`、`TITLE_MAIN`、`TITLE_SUB`、`TITLE_KICKER`、`TITLE_CREDIT`、`END_L1/L2/Q/CTA/SOURCE`，或设置对应的 `VIDEO_*` 环境变量。不要带着示例品牌名出片。

## 阶段 6 — QA 与交付

自动检查（`scripts/qa_video.py`）：

- `ffprobe`：时长、1080×1920、30/1、H.264/AAC。
- PTS 间隔：每个 `1/30` 秒，无重复时间戳；`-f null -` 完整解码无错误。
- 帧差：在 3–5 个已知切点附近解码取帧；连续 ≥3 帧平均绝对差 <0.02 判为冻结。
- 音频：`ebur128=peak=true`，整体约 −16 LUFS，真峰值 ≤ −1.0dB（目标 −1.5）。

人工抽查：

- 看钩子、切点、文字卡、下划线修正、结尾卡这几帧。
- 在 2–3 个边界对照字幕和语音；上一句字幕必须保留到下一句开口。
- 听一遍边界附近，确认没有丢字。
- 确认旧版本还在，README 里有链接。

交付：MP4、SRT、带时间码的解说稿、写清重跑命令的 README，以及一段话说明音色/画幅选择。

## 排错表

| 现象 | 根因 | 修法 |
|---|---|---|
| 每隔几句音色就变 | 逐句克隆重新采样说话人 | 改 2–4 个长段；同 prompt + reference；测段基频 |
| 语速太快/不可信 | 7–8 字/秒、基频高 | 低音平稳 prompt，5.2–5.8 字/秒；个别句轻微 atempo，不要变调 |
| 丢字/话没说完 | 按估算停顿逐句切音频 | 长段整体保留；ASR 对齐；绝不切 |
| 字幕抢在句尾前切换 | 用停顿中点或按字数比例 | 用 ASR 的“下一 beat 第一个词”起点 |
| 图片切换卡顿 | 停顿期间推拉被 clamp；静止后跳；叠化 | 全镜头线性运动、不 clamp；硬切；文字卡推近+光扫 |
| 慢推拉微抖 | 整数裁切跳步 | 仿射亚像素变换 |
| 文字卡像冻住 | 只有静止文字，编码器跳过块 | 整帧缓慢推近 + 光扫 |
| 下划线压字 | 线画在 `y+font_size` | `textbbox()[3] + margin` |
| 切换时双影 | 字幕/图片叠化 | 硬切 |
| 音效削波/太响 | 音效峰值 1.0、无限幅 | 音效峰值归一 0.3；`alimiter=0.95` |
| ASR 输出英文乱码 | 48kHz 被当成 16kHz | 先重采样到 16kHz |
| CUDA whisper 报 `cublas64_12.dll` | ctranslate2 找不到 cuBLAS | CPU `int8` 足够；或把 torch/lib 加进 PATH |
| CPU VoxCPM 慢 40 倍 | CPU 版 torch | 隔离 venv 装 CUDA torch |
| 字体豆腐块 | WSL 没有中文字体 | 用 Windows Python + `C:\Windows\Fonts\NotoSansSC...` |
| 图片链接全坏 | MD 指向 `assets/...` | 按文章顺序映射，逐张看图，修 `img` |

## 完成标准

- [ ] 每张图都映射并目检过。
- [ ] 前 3 秒有钩子；静止标题不超过 1 秒。
- [ ] 35–50 个 beat；总长 2:45–3:30；字幕每行 ≤ 15 个中文字。
- [ ] 2–4 个长段配音；段基频 85–115Hz；4.5–6.5 字/秒。
- [ ] 音频连续，没有按 beat 切；切点经 ASR 对齐。
- [ ] 无叠化；每个镜头都在动；亚像素推拉；下划线用 bbox。
- [ ] −16 LUFS，真峰值 ≤ −1.0dB，音效峰值 ≤ 0.3。
- [ ] CFR 30fps，完整解码干净，切点附近无连续冻结帧。
- [ ] `render.py` 项目文案已改（没有示例品牌名）。
- [ ] SRT + 解说稿 + README；旧版本保留。
- [ ] 在手机尺寸播放器上实际看过一遍。

## 详细参考

- [踩坑与实测数据](references/pitfalls.md)
- [QA 命令与人工清单](references/qa-checklist.md)
- [Windows/WSL 环境搭建](references/environment.md)
- [分镜 schema 示例](scripts/script_data_template.py)

## 脚本

复制到项目里、和 `script_data.py` 放在一起。默认假设 `audio/prompt_ref.wav`、`audio/chunk_0..N.wav`、`out/`、Windows Python/ffmpeg；需要时用环境变量覆盖。

- `scripts/tts_chunks.py` — VoxCPM2 长段配音。
- `scripts/align_asr.py` — 16kHz faster-whisper 词级对齐 → `asr_times.json`。
- `scripts/build_audio_utils.py` — 垫乐、音效、混音、SRT、解说稿。
- `scripts/build_audio_cont.py` — 连续音频 + 分轨 + `timeline.json`。
- `scripts/render.py` — 竖屏渲染器（含运动/下划线修复）。
- `scripts/qa_video.py` — CFR/解码/帧差/响度检查。
- `scripts/project_config.py` — 共享 `EXCLUDE`。
- `scripts/ffmpeg_path.py` — 自动定位 ffmpeg/ffprobe（避开 WSL 下 `%USERNAME%` 乱码）。

环境变量：`FFMPEG`、`FFPROBE`、`FONT_BOLD`、`FONT_MED`、`ASSET_DIR`（或 `render.py --assets <dir>`；WSL 不会自动透传任意环境变量，除非写进 `WSLENV`）、`VOX_MODEL`、`VOX_STEPS`、`VOX_SEED`、`VOX_CFG`、`VIDEO_BRAND`、`VIDEO_TITLE`、`VIDEO_SUBTITLE`、`VIDEO_KICKER`、`VIDEO_CREDIT`、`VIDEO_END_*`、`VIDEO_SOURCE`、`VIDEO_OUT`。

当前故事的音效重点 beat 在 `build_audio_utils.py` 的 `IMPACT_IDS` / `RISER_BEFORE` 里改。
