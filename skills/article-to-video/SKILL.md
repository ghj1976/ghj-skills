---
name: article-to-video
description: 把 Markdown 文章（尤其是中文公众号文章）制作成带解说的短视频：VoxCPM2 配音、本地图片、连续长段音频、ASR 词级对齐字幕、手机优先的动态画面。适用于文章转视频、参考视频剪 B-roll、图片链接修复、音色与语速选择、9:16 竖屏或 16:9 横屏、字幕同步，以及卡顿、冻结帧、断音排查。article-to-video / MD → 视频。
---

# 文章 → 解说视频

这是一套从真实公众号改稿中沉淀出来的生产流程：第一版 3:58 横屏被否，原因是“开头太静止、声音太快”；第二版 3:20 竖屏修正了节奏，但下划线压字、音色忽好忽坏；最终 3:00 版修掉了切换冻结、话没说完就切、尾音丢失。后来又补了一轮：文章没有配图、只有一条英文原片时，
从原片剪 6 段静音 B-roll（而不是全用截图），顺带修了白底图发灰、数据卡数字停在 0.3、标题数字贴边。
下面的规则都是踩过坑之后留下的，按顺序执行。

**语言约定：同等条件下优先中文。** 文档、说明、字幕、口播都用中文；代码、命令、字段名保持原文。

## 适用场景

- “把这篇公众号文章做成视频” / article-to-video / Markdown → 带解说的 MP4。
- Markdown 里的图片指向不存在的 `assets/...`，但图片就在文章同目录。
- 要做手机端竖屏（视频号 / 抖音 / 朋友圈）或 16:9 横屏。
- 已有视频出现：开头静止、语速太快/不可信、图片切换卡顿、字幕抢在话没说完前切换、尾音缺失。
- 想用某条视频里的解说音色（“用这个声音重做”）：见阶段 2 的默认音色与 `make_voice_ref.py`。
- 文章只有文字，但有一套参考视频（英文原片 / 发布会录像）：从原片剪 **静音 B-roll**，不要只用截图。
- 想给一部分镜头加真实运动（蝴蝶扇翅、贴标签、走路），其余仍是静帧。
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
9. **切点吸附到“开口”。** whisper 的词起点有 ±0.3s 误差，长段之间还有空白；必须把画面切点吸附到真实的语音起点，否则观众感知为“卡一下”。（`build_audio_cont.py` 的 `snap_to_onsets`）
10. **每个镜头单独运动。** 按场景计时推近，摊到 20–30 秒上每帧只动 0.0001，等于静止画面；要按 beat 计时、切镜头时重置。
11. **配图逐句判断，不要“每场景一张默认图”。** 一句讲规模、一句讲预算，却共用一张天平，观众立刻觉得“图不对文”。
12. **第一条音轨的 1 秒内不放音效。** 音乐还在淡入时叠 impact/whoosh，就是开头一声“刺啦”。
13. **一条主线讲透，胜过五条线各说一句。** 用户说“信息量太大/太跳跃”时，砍到一条线（2:00–2:30），而不是加速。
14. **有参考视频就优先用动态 B-roll。** 截图 + Ken Burns 只解决“在动”，解决不了“真的在发生”。4–8 个镜头换成原片片段，只借画面、不借原声（英文人声会和中文旁白打架）。
15. **片段不跨剪辑点、不循环、不在结尾冻结。** 按 beat 时长线性映射：素材短就自然放慢；循环会跳帧，停在末帧会被编码器判成静帧。
16. **片段镜头不再套整帧推近。** 推近会裁掉画面边缘（水印、手部），运动交给素材本身。
17. **白底/高亮图要按亮度自适应压暗底图。** 固定 alpha 150 会把白背景照片糊成一片灰，标题和字幕都没对比。
18. **参考视频选段看精确时间码 + 剪辑点，不要按缩略图序号猜。** 1fps 缩略图的序号和真实秒数会差半拍，很容易把“指尖捏着标签”剪成“研究员对镜头说话”。

## 新项目脚手架

```bash
# SKILL 是本 skill 的根目录（skill loader 会给出）
SKILL=<本 skill 根目录>   # 例如 /mnt/e/mycode/ghj-skills/skills/article-to-video
PROJ=work/<视频短名>
mkdir -p "$PROJ/audio" "$PROJ/out"
cp "$SKILL"/scripts/*.py "$PROJ"/
cp -r "$SKILL"/scripts/voices "$PROJ"/     # 内置音色（默认 q1），不用自己准备 prompt_ref
cp "$SKILL"/scripts/script_data_template.py "$PROJ"/script_data.py
```

然后：

1. 改 `script_data.py`（场景、beat、`img` 文件名；要动态片段时写 `VIDEO_SRC` / `CLIP_SRC` 并在 beat 第 9 位标 `True`）。
2. 选音色：默认用内置 `voices/q1`（女声，已去伴奏），直接就能配音；要换音色用 `make_voice_ref.py`，或把 4–8 秒的 `audio/prompt_ref.wav` 放进项目（项目内的会覆盖内置音色）。
3. 改 `project_config.py` 的 `EXCLUDE`；配音、对齐、构建三个脚本共用这一份，保持一致。
4. 如果图片不在项目目录，设置 `ASSET_DIR`，或渲染时传 `--assets <dir>`。

`build_audio_cont.py` 和 `align_asr.py` 会自动推导 `GROUPS`：每 2 个场景一段，所以 8 个场景 → 4 段，3 个场景 → 2 段；场景数为奇数时，最后一段只含 1 个场景。

## 流程总览

| 阶段 | 产出 | 通过标准 |
|---|---|---|
| 0 素材 | 图片映射、参考视频镜头区间、画幅决策 | 每张图/每段都看过并匹配段落 |
| 1 脚本 | `script_data.py`，35–50 个 beat | 前 3 秒有钩子；总长 2:45–3:30 |
| 2 配音 | 2–4 个长段 WAV | `check_voice.py` PASS：段间基频极差 ≤30Hz、LTAS ≥0.90、语速 4.0–7.5 字/秒 |
| 2.5 清理 | `clean_audio.py` 处理过的长段 | 段首无瞬态、长停顿 ≤0.55s、语速统一 |
| 3 音频 | 连续 `narration.wav`、音乐/音效、混音 | `check_audio.py` PASS：开头无瞬态、无爆音、切点=开口、−16 LUFS |
| 4 对齐 | `asr_times.json`、`timeline.json` | 切点 = 下一句开口 |
| 5 渲染 | 1080×1920 或 1920×1080 MP4 | 每个镜头都在动，无叠化，配图逐句对得上 |
| 6 QA | 自动报告、截图、README | CFR、解码干净、无冻结窗口 |

## 阶段 0 — 素材与图片（含参考视频）

1. 完整读一遍 Markdown，整理标题、章节、金句、数字、图片出现顺序。
2. **按文章顺序修图片链接，然后逐张打开确认。** 典型坏链接是 `assets/<文章标题>/file-*.png`，真实图片在文章目录。把第 n 张图映射到本地第 n 个 PNG，但一定要看图片内容是否匹配相邻段落，不能只看文件名。
3. 检查尺寸/比例，排除重复图、无关截图。
4. 选画幅：
   - **9:16，1080×1920**：手机优先、视频号、抖音。用户说“普通手机用户”“划走”时默认竖屏。
   - **16:9，1920×1080**：只在文章内嵌播放器或用户明确要横屏时使用。
5. 每个版本单独建项目目录；图片可只读引用，不能覆盖旧版本。

**如果文章没有配图，但有一套参考视频：**

1. 先跑 `python video_sheet.py --video ../03/01.mp4`：输出逐秒缩略图（带精确时间码）、
   剪辑点、镜头区间。挑片段只在这个区间表里选。
2. 选 **4–8 段、每段 2–6 秒**、内容真的对得上台词的镜头（贴标签的手指、扇翅的蝴蝶、
   举网的人、被啃过的乳草叶子）。宁少勿滥；其余镜头继续用静帧或数据/文字卡。
3. 每段都**亲眼看帧确认内容**（`ffmpeg -ss <秒> -i 01.mp4 -frames:v 1 x.png`）。
   不要相信文件名，也不要相信缩略图序号。
4. 在 `script_data.py` 写 `VIDEO_SRC` 与 `CLIP_SRC = {"beat_id": (起点, 终点)}`，
   并在该 beat 元组第 9 位标 `True`。
5. `python make_clips.py` 切出 `clips/<beat_id>/`（1080×608、30fps、JPEG 帧序列 + `meta.json`）。
6. 预览 `python render.py preview <片段时刻>`，确认内容对、边缘没被推近裁掉。

片段只当画面：原片人声一律不用，音轨仍是中文旁白 + 垫乐。16:9 片段正好铺满 1080×608 卡片；
源片只有 854×480 也可以，lanczos + 轻度 unsharp（0.45）升采样，配上真实运动比静帧耐看。

**项目结构**

```
project/
  script_data.py          # 场景、口播、字幕、大字、版式
  tts_chunks.py           # VoxCPM2 长段配音
  align_asr.py            # faster-whisper 词级时间戳
  build_audio_utils.py    # 垫乐、音效、混音、SRT、解说稿
  build_audio_cont.py     # 连续音频 + 时间轴
  render.py               # 竖屏/横屏画面渲染
  make_clips.py           # 参考视频 -> clips/ 帧序列
  video_sheet.py          # 参考视频缩略图 + 剪辑点 + 镜头区间
  qa_video.py             # 自动检查
  make_voice_ref.py       # 从视频/音频抽音色（切片 + 去伴奏）
  check_voice.py          # 量音色/语速是否达标
  voices/q1/              # 内置音色：prompt_ref.wav + reference_ref.wav + voice.json
  clips/<beat_id>/        # 动态 B-roll：f_0001.jpg ... + meta.json
  audio/
    prompt_ref.wav        # 可选：项目自定义音色（覆盖内置）
    chunk_0..N.wav        # 长段配音
    asr_times.json
  out/
    timeline.json narration.wav music.wav sfx.wav audio_mix.wav
    subtitles.srt 解说稿.md <成片>.mp4
```

## 阶段 1 — 脚本与分镜

目标总长 **2:45–3:30**，语速 **5.2–5.8 中文字/秒**，通常 900–1100 字。第一版 1667 字、7.8 字/秒，即使 3:58 也显得急。

**密度优先于覆盖。** 公众号原文常有 4–6 个并列论点；视频里一次只讲一条主线，宁可从 3:20 砍到 2:15。
判据：如果一条线只能用一两句带过（“行业也在跟进”“你也可以自测”），就不要放进视频——一句带过等于没说。
被否的两版分别是：45 个口号各说一句（太跳跃）、5 条线塞进 3:20（没说透）。

**段落式写法，不要口号式拆分。** 每个 beat 是一句完整的话，整段连起来要能读通：

1. 话题句 → 2. 证据（数字/例子）→ 3. 承接下一段的句子。
   例：「那这条边界，是怎么画出来的？」→「第一个条件，是技能半衰期足够短。」→「过去…能用四五年」→「但现在被压缩到一到三年」→「不是人变笨了，是工具贬值太快」。
   反例（口号式）：「被买断的六万人，不是因为能力差。」「真正值得琢磨的不是规模，是边界。」——两句都是结论，中间没有承接，连读像标题滚播。

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

### 默认音色：q1（女声，已内置）

`scripts/voices/q1/` 打包了一套现成音色：prompt 5.7 秒 + reference 14 秒，都是**去掉背景音乐后的干净人声**（prompt 基频中位数约 239Hz，自然语速约 6.6 字/秒）。脚手架把 `voices/` 拷进项目后，`tts_chunks.py` 默认就用它，不必再准备 `audio/prompt_ref.wav`。

- 参数都在 `voices/q1/voice.json`：`prompt_text`（prompt 的准确文本，必需）、`atempo`（0.92，把偏快的语速压到 5.7–6.1 字/秒）、切片区间与来源。
- 项目里放了 `audio/prompt_ref.wav` 时以项目为准（自定义音色优先）；也可用 `VOICE=<name>` 选 `voices/<name>`。
- **换音色**：`python make_voice_ref.py --src ../../02/q1.mp4 --prompt 8.66,14.32 --ref 8.66,22.72 --transcribe` 先打印词级时间戳，挑好边界（落在词的起止，不切在字中间）后去掉 `--transcribe` 重跑，会生成 `voices/<name>/`（含 `voice.json`）。
- **参考音频带 BGM 时必须先去噪**：`make_voice_ref.py` 已内置 ZIP-Enhancer；直接拿带伴奏的原片克隆，会把底噪和音乐一起学走。
- **验收音色**：`python check_voice.py` —— 每段基频落在参考 ±18% 内、段间极差 ≤30Hz、与参考的 LTAS 相关 ≥0.90、语速 4.5–6.5 字/秒。听不出差别时就看这几个数；实测 q1 四段：基频 225–251Hz（参考 239Hz）、LTAS 0.978–0.990、语速 5.7–6.1。

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

1. 用 **4–8 秒 prompt + 更长的 reference**（同一音色）：文本必须已知，写进 `voice.json` 的 `prompt_text`；prompt + reference 比只用 reference 稳。
2. 生成 **2–4 个长段**，每段 30–60 秒，每 2 个场景一段。同一 prompt cache、`torch.manual_seed(20)`、`cfg_value=2.0`、`inference_timesteps=10`。
3. 不要给每段加风格前缀，除非确有必要；风格提示会改变音高。整体偏快就统一做 `atempo`（`voice.json` 的 `atempo` 会自动应用，原始段存 `*_raw.wav`）。
4. 每段测量：基频中位数（librosa.pyin，60–350Hz）+ 字/秒 + 与参考的 LTAS 相关。**重点是段间稳定、与参考同音区**，不要硬套 85–115Hz（女声的 q1 在 225–251Hz 才是对的）；语速 4.5–6.5 字/秒。
5. 跑 `check_voice.py`，PASS 再往下走；不合格先换参考片段/重生成该段，不要用变调硬拉。
6. 长段保留，后面绝不再切。

命令：`scripts/tts_chunks.py`，分别跑 `--part 0 --of 2` 和 `--part 1 --of 2`。生成完先清理、再验音色：

```bash
python clean_audio.py            # 统一 atempo + 去掉段首咔哒 + 压缩 0.9s 这种长停顿
python check_voice.py            # 基频/LTAS/语速门禁
```

`check_voice.py` 报“段间基频极差 >30Hz”时，用 `regen_chunk.py 偏差段号 --seeds 20,21,22` 按种子重生成，
按“基频最接近参考 + 频谱最像”自动挑一条（实测能把 263/248/224 收到 239/249/240）。

`clean_audio.py` 很关键：VoxCPM2 每段开头有 40ms 的 −11dB 瞬态，后面还跟着 0.3–0.4s 静音；
段落拼接点又正好落在章节开头，不清掉就会出现“**每节开头咔一下、停半拍**”。

## 阶段 3 — 连续音频与混音

1. 每段只裁首尾静音（−45dB 阈值，80ms 余量），段间留 0.5–0.6 秒空白（句内停顿已被 `clean_audio.py` 压到 ≤0.45，这里再长就会显停顿）。**不要按 beat 加空隙，也不要按 beat 切。**
2. 48kHz 生成 `narration.wav`、`music.wav`、`sfx.wav`。
3. 混音：口播 `loudnorm=I=-16:TP=-1.5:LRA=11`；音乐约 −38dBFS RMS；音效峰值约 0.30；`amix` 后加 `alimiter=limit=0.95`。
4. 检查分轨：口播 RMS 约 0.13，音乐约 0.010，音效约 0.005，最终真峰值 ≤ −1.5dB。第一版音效峰值到 1.0 直接削波，限幅器修掉了。
5. 音效：场景起点 whoosh、3–4 个重点 beat 用 impact、数字用 tick、反转前一个 riser。要稀疏；每 3 秒一个 whoosh 就成噪音了。**开头 0–1 秒不要放 impact/whoosh**：音乐还在淡入，噪声冲击叠上去就是一声“刺啦”。

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
  卡片内图片按比例 **contain**（16:9 正好铺满；竖图两侧用同一张图模糊压暗填底），不拉变形、不裁掉图上说明文字。
- 字幕：64px 加粗，最多 2 行，居中在 y≈1400–1550，黑色描边 8px，后面加暗色 scrim。
- 安全区：左右留 60px；避开底部 250px、右侧 120px 的平台 UI。

运动规则：

- **线性、无 clamp 的 Ken Burns**，覆盖包含停顿的整个镜头：`prog = min(1, lt / (next_start - start))`。不要用 smoothstep，它首尾速度为 0，会制造停顿。
- **按 beat 计，不按场景计。** 场景有 8–10 个 beat、20–30 秒，`prog` 摊到整场后每帧只变 0.0001，等于静止画面；按 beat 计时，每个镜头 3%–5% 推近，切镜头时重置（重置被硬切掩盖，看不出来）。
- 亚像素采样：`Image.transform(..., Image.AFFINE, ...)`，用浮点缩放/位移。整数 `crop().resize()` 会每隔几帧跳 1px，产生微抖。
- **硬切，不叠化。** 叠化会让两行大字双重曝光，看起来像故障。切点用 whoosh 盖住。
- 文字/数据卡：整个画面缓慢推近（每场景约 7.5%）+ 低透明度光扫。否则编码器会跳过相同帧，卡片就冻住了。
- **动态片段镜头**：`idx = lt / duration * frames` 按 beat 进度取帧，不循环、不冻结；
  这些镜头跳过整帧 `slow_zoom`，免得把画面边缘（水印、手）裁掉。
- **底图压暗按亮度自适应**：`alpha = clamp(150 + (mean − 55) × 1.15, 150, 215)`。
  白底照片用固定 150 会整屏发灰，标题和字幕都没对比。
- **数据卡 count-up 压到 0.55 秒**：1.1 秒的动画放在 1.18 秒的镜头上，观众几乎整段看到“0.3 克”。
- **标题卡装饰数字按长度自动缩**：`getlength > 640` 就减字号；230px 的 “0.5g” 会贴右边缘被裁。
- **结尾卡从 `speech_end` 触发**：`build_audio_cont` 把最后一个 beat 的 end 设成总时长，
  用 `last["end"]` 判断等于永远不会出现。
- 不要在每次切换做 punch-in，也不要白闪；这两个都会放大“顿一下”的感觉。
- 下划线：

  ```python
  bbox = d.textbbox((x, y), text, font=f)
  y_line = bbox[3] + 16
  ```

- 纯文字版式：底图偏亮时加暗色 scrim；压暗量按底图平均亮度算，深色底图不要硬加（会发灰）。
- 字体用 `C:\Windows\Fonts` 下的 `Noto Sans SC Bold` / `Medium`，传完整 `.otf` 路径（含空格）。

**配图规则（本轮返工两次）：**

- 逐句判断，只在这句话和图片内容真的对得上时才配图（`script_data.py` 每个 beat 的第 7 位单独指定，`None` 表示不用图）。
- 原文配图通常自带中文标题（“资本流向，决定岗位边界”“工具贬值快于人成长”）；如果图上文字和这句语义相反，就不要配这张图（例：讲“过去能顶四五年”却配“工具贬值快”）。
- 一个 30 多镜头的视频，**一半有图、一半是数据/文字卡**是正常的；宁可少配图，也不要每场景套同一张默认图。
- 配图没法自动判语义，但可以自动拼图：`python contact_sheet.py --video out/xxx.mp4` 生成 `out/配图对照.png`，一眼扫完 30 多个镜头。

`scripts/render.py` 是可直接用的竖屏渲染器。首次渲染前改项目副本里的 `BRAND`、`TITLE_MAIN`、`TITLE_SUB`、`TITLE_KICKER`、`TITLE_CREDIT`、`END_L1/L2/Q/CTA/SOURCE`，或设置对应的 `VIDEO_*` 环境变量。不要带着示例品牌名出片。

## 阶段 6 — QA 与交付

自动检查（`scripts/qa_video.py`）：

- `ffprobe`：时长、1080×1920、30/1、H.264/AAC。
- PTS 间隔：每个 `1/30` 秒，无重复时间戳；`-f null -` 完整解码无错误。
- 帧差：在 3–5 个已知切点附近解码取帧，**帧差要 0–1 归一化**；连续 ≥3 帧完全相同（diff = 0）才判冻结。慢推拉每帧只差 0.00005 是正常的，不要用 0.02 这种阈值把慢镜头判死。
- 音频：`ebur128=peak=true`，整体约 −16 LUFS，真峰值 ≤ −1.0dB（目标 −1.5）。

人工抽查：

- 看钩子、切点、文字卡、下划线修正、结尾卡这几帧。
- 在 2–3 个边界对照字幕和语音；上一句字幕必须保留到下一句开口。
- 听一遍边界附近，确认没有丢字。
- 有动态片段时，每个片段抽两帧确认内容与运动，并确认没有混进原片人声。
- 确认旧版本还在，README 里有链接。

交付：MP4、SRT、带时间码的解说稿、写清重跑命令的 README，以及一段话说明音色/画幅选择。

## 排错表

| 现象 | 根因 | 修法 |
|---|---|---|
| 每隔几句音色就变 | 逐句克隆重新采样说话人 | 改 2–4 个长段；同 prompt + reference；测段基频 |
| 克隆出来带底噪/伴奏 | 参考音频本身有 BGM | 先过 ZIP-Enhancer 去噪（`make_voice_ref.py`） |
| 音色“说不清哪里不对” | 没量化，参考片段切在字中间 | `check_voice.py` 看段间基频极差与 LTAS；按词边界重切 |
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
| 去噪报 `libtorchcodec_core4.dll` 找不到 | torchaudio 2.11 走 torchcodec，缺 shared FFmpeg DLL | `make_voice_ref.py` 已把 `torchaudio.load/save` 换成 soundfile 实现 |
| CPU VoxCPM 慢 40 倍 | CPU 版 torch | 隔离 venv 装 CUDA torch |
| 字体豆腐块 | WSL 没有中文字体 | 用 Windows Python + `C:\Windows\Fonts\NotoSansSC...` |
| 图片链接全坏 | MD 指向 `assets/...` | 按文章顺序映射，逐张看图，修 `img` |
| 开头“刺啦”一声 | 音乐淡入期叠了 impact/whoosh | 第一秒不放音效；转场 whoosh 降到 0.45 |
| 每节开头声音卡一下 | 长段段首 40ms 瞬态 + 0.3s 静音，拼接点落在章节首 | `clean_audio.py` 去瞬态/压停顿；段间空白 0.5–0.6s |
| 画面像静止画面 | 推近按场景计，摊到 20–30 秒每帧 0.0001 | 改按 beat 计；文字卡再加光扫 |
| 配图和内容不搭 | 每场景一张默认图 | `BEAT_IMG` 逐句覆盖；对不上就不配图，用数据/文字卡 |
| 音色一段一变 | 长段生成方差，段间基频可差 40Hz | `regen_chunk.py` 换种子重生成偏差段；`check_voice.py` 把关 |
| 切点比开口早/晚半拍 | whisper 词起点误差 + 长段空白 | `snap_to_onsets` 吸附到真实开口（容差 0.55s，单调约束 0.4s） |
| 白底照片整屏发灰、字没对比 | 底图固定 alpha 150 | 按底图平均亮度自适应压暗（150–215） |
| 数据卡数字停在 0.3 | count-up 1.1s 比镜头 1.18s 还长 | 动画压到 ≤0.55s |
| 标题装饰数字被裁 | 字号写死 230px / 420px | 按 `textlength` 自动缩到 ≤640px |
| 片段剪出来是“对镜头说话” | 按缩略图序号猜时间，跨了剪辑点 | `video_sheet.py` 看精确时间码与镜头区间；每段先抽帧确认 |
| 片段结尾跳一下/冻住 | 素材比 beat 短，循环或停在末帧 | 按 beat 时长线性映射，短则放慢 |
| 片段边缘水印被裁 | 片段镜头又套了整帧推近 | 片段镜头跳过 `slow_zoom` |
| 结尾卡一直不出现 | 触发条件用了 `last["end"]`（= 总时长） | 改用 timeline 的 `speech_end` |

## 完成标准

- [ ] 每张图都映射并目检过。
- [ ] 前 3 秒有钩子；静止标题不超过 1 秒。
- [ ] 35–50 个 beat；总长 2:45–3:30；字幕每行 ≤ 15 个中文字。
- [ ] 2–4 个长段配音；段间基频极差 ≤30Hz 且落在参考 ±18%；4.5–6.5 字/秒；`check_voice.py` PASS。
- [ ] 音频连续，没有按 beat 切；切点经 ASR 对齐。
- [ ] 无叠化；每个镜头都在动；亚像素推拉；下划线用 bbox。
- [ ] −16 LUFS，真峰值 ≤ −1.0dB，音效峰值 ≤ 0.3。
- [ ] CFR 30fps，完整解码干净，切点附近无连续冻结帧。
- [ ] `render.py` 项目文案已改（没有示例品牌名）。
- [ ] SRT + 解说稿 + README；旧版本保留。
- [ ] `check_audio.py` PASS：开头无瞬态、无爆音、最长停顿 ≤0.65s、切点=开口（±0.15s）。
- [ ] `contact_sheet.py` 生成对照图，逐镜头看过配图是否对得上。
- [ ] 动态片段：每段都抽帧看过内容；不跨剪辑点；不循环/冻结；原片人声没混进来。
- [ ] 白底图/标题/数据卡：底图不发灰，数字动画在镜头结束前到位。
- [ ] 在手机尺寸播放器上实际看过一遍。

## 详细参考

- [踩坑与实测数据](references/pitfalls.md)
- [QA 命令与人工清单](references/qa-checklist.md)
- [Windows/WSL 环境搭建](references/environment.md)
- [分镜 schema 示例](scripts/script_data_template.py)

## 脚本

复制到项目里、和 `script_data.py` 放在一起；`voices/` 也要一起拷（内置 q1 音色）。默认假设 `audio/chunk_0..N.wav`、`out/`、Windows Python/ffmpeg；音色优先用 `audio/prompt_ref.wav`，没有就用 `voices/<VOICE>/`。

- `scripts/tts_chunks.py` — VoxCPM2 长段配音（默认 q1 音色，自动套用 `voice.json` 的 atempo）。
- `scripts/clean_audio.py` — 统一 atempo、去段首瞬态、压缩长停顿（修“每节卡一下”）。
- `scripts/regen_chunk.py` — 音色漂移时按种子重生成某段，挑基频/频谱最像的。
- `scripts/make_voice_ref.py` — 从视频/音频抽音色：词级时间戳 → 切片 → 去伴奏 → `voices/<name>/`。
- `scripts/check_voice.py` — 量段基频/LTAS/语速，判断音色是否达标。
- `scripts/align_asr.py` — 16kHz faster-whisper 词级对齐 → `asr_times.json`。
- `scripts/build_audio_utils.py` — 垫乐、音效、混音、SRT、解说稿。
- `scripts/build_audio_cont.py` — 连续音频 + 分轨 + `timeline.json`；切点吸附到开口。
- `scripts/render.py` — 竖屏渲染器（静帧推近 + 动态 B-roll + 自适应压暗 + 下划线修复）。
- `scripts/make_clips.py` — 参考视频 → `clips/<beat_id>/` 帧序列（按 beat 时长映射）。
- `scripts/video_sheet.py` — 参考视频逐秒缩略图 + 剪辑点 + 镜头区间。
- `scripts/qa_video.py` — CFR/解码/帧差/响度检查。
- `scripts/check_audio.py` — 声音门禁：开头瞬态/爆音/长停顿/切点对齐/响度。
- `scripts/contact_sheet.py` — 按镜头抽帧拼成 `配图对照.png`，人工核对配图。
- `scripts/project_config.py` — 共享 `EXCLUDE`，可选 `TEMPO` / `VOICE`。
- `scripts/ffmpeg_path.py` — 自动定位 ffmpeg/ffprobe（避开 WSL 下 `%USERNAME%` 乱码）。

环境变量：`FFMPEG`、`FFPROBE`、`FONT_BOLD`、`FONT_MED`、`ASSET_DIR`（或 `render.py --assets <dir>`；WSL 不会自动透传任意环境变量，除非写进 `WSLENV`）、`VOICE`、`TEMPO`、`PROMPT_WAV`、`REFERENCE_WAV`、`PROMPT_TEXT`、`VOX_MODEL`、`VOX_STEPS`、`VOX_SEED`、`VOX_CFG`、`VIDEO_BRAND`、`VIDEO_TITLE`、`VIDEO_SUBTITLE`、`VIDEO_KICKER`、`VIDEO_CREDIT`、`VIDEO_END_*`、`VIDEO_SOURCE`、`VIDEO_TITLE_GHOST`、`VIDEO_DATA_SOURCE`、`VIDEO_OUT`、`SOURCE_VIDEO`（参考视频路径，优先于 `script_data.VIDEO_SRC`）。

当前故事的音效重点 beat 在 `build_audio_utils.py` 的 `IMPACT_IDS` / `RISER_BEFORE` 里改。
