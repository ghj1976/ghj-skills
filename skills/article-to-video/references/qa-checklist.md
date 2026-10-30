# QA 清单

在项目目录下执行（脚本和 `script_data.py` 放在一起）。默认 WinGet 路径不存在时，先设 `FFMPEG`。

## 自动检查

```bash
# 设置一次
export FFMPEG="C:/Users/<user>/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffmpeg.exe"
export FFPROBE="$(dirname "$FFMPEG")/ffprobe.exe"

# 规格、CFR、解码、冻结窗口、响度
python qa_video.py out/final.mp4 --times 9.5,49,175
```

通过标准：

| 检查项 | 通过条件 |
|---|---|
| 时长 | 与 `out/timeline.json` 相差 ±0.1 秒 |
| 视频 | 1080×1920（或 1920×1080），H.264，`r_frame_rate=30/1` |
| PTS | 每个 `dt=0.0333`，无重复时间戳 |
| 解码 | `ffmpeg -v error -i final.mp4 -f null -` 无输出 |
| 冻结窗口 | `zero_runs=0`；没有连续 ≥3 帧完全相同（帧差归一化后 diff = 0） |
| 响度 | I = −17.5…−14.5 LUFS；真峰值 ≤ −1.0dB |
| 音频 | AAC 48kHz 立体声 |

人工抽查（抽帧）：

```bash
for t in 2.5 9.3 9.7 75 178; do
  "$FFMPEG" -y -i out/final.mp4 -ss "$t" -frames:v 1 "out/still/f_$t.png"
done
```

- [ ] 钩子帧有前提 + 运动，不是静止标题。
- [ ] 切点处上一句字幕保留到下一句开口；没有丢句。
- [ ] 下划线在字形下方，不穿过笔画（找一个大的中文字看）；小标签（eyebrow）的下划线也要和字分开 12px 以上，缩到 480 宽看一遍。
- [ ] 最亮图片上的文字仍然可读（有 scrim）。
- [ ] 结尾卡有来源、署名、互动引导。
- [ ] 转场没有双字幕/双画面。
- [ ] 没有两行大字重叠的帧。

## 主题与开头

- [ ] `script_data.py` 顶部有一句写下来的主题句。
- [ ] 前 20 秒内能听到主题句；不是 30 秒背景铺垫。
- [ ] 章节标题连起来是一条叙事线，不是并列素材。
- [ ] 每一章都能回答“它如何支撑主题句”。
- [ ] 删掉任何一章，主题句仍成立 → 这章是支线，已砍掉或压成一句注脚。
- [ ] 主题词/比喻在开头、转折、结尾各出现一次（例：“账单”）。
- [ ] 只看前 20 秒，能说出“要论证什么、接下来讲哪三件事”。

## 音频边界检查

选一个切点，看混音能量：

```bash
"$FFMPEG" -hide_banner -nostats -ss 7.5 -t 2.5 -i out/audio_mix.wav \
  -af volumedetect -f null -
```

更直接的做法：用 Python 打印边界附近每 100ms 的 RMS。应该是“上一句结束 → 停顿 → 下一句在画面切点处开口”。如果切点落在语音中间，说明 ASR 时间不对；重跑 `align_asr.py` 再构建。

## 交付

- [ ] `out/*.mp4` 能在手机系统相册和浏览器里播放。
- [ ] `out/subtitles.srt` 能打开，时间戳对得上。
- [ ] `out/解说稿.md` 每个 beat 都有 `mm:ss`。
- [ ] `README.md` 写了重跑命令和音色/画幅决策。
- [ ] 旧版本还在（单独目录或 `out/vN/`）。
- [ ] 文件名可读，且不包含旧版本的标题。

## 声音门禁（`python check_audio.py`）

| 检查 | 通过标准 |
|---|---|
| 开头瞬态 | 开口前最大样本跳变 ≤0.2，20ms 最大跳升 ≤12dB（音乐淡入期不能有音效） |
| 爆音 | 全片相邻样本跳变 >0.6 的个数 = 0 |
| 句间停顿 | 正文（不含章节边界）最长静音 ≤0.65s（在 `narration.wav` 上量，音乐会把静音填满） |
| 切点 | 每个章节 start 与最近开口的偏差 ≤0.15s |
| 响度 | −17.5…−14.5 LUFS，真峰值 ≤ −1.0dB |

实测一次失败案例：切点比开口早 0.22–0.52s（`scene.start` 被接成上一节 end，跨过了长段空白），
以及 1.0s 的句内长停顿没被清掉（停顿被 60ms 气口切成两段，阈值 −45dB 检测不到）。

## 动态 B-roll 检查（项目里有 `clips/` 时）

自动：

```bash
# 片段内“真的在动”：同一条片段相隔 0.5–1 秒取两帧，平均绝对差应 >0.005
ffmpeg -v error -ss 18.2 -i out/final.mp4 -frames:v 1 out/still/c1.png
ffmpeg -v error -ss 18.8 -i out/final.mp4 -frames:v 1 out/still/c2.png
python -c "from PIL import Image; import numpy as np; \
a=np.asarray(Image.open('out/still/c1.png'),float); b=np.asarray(Image.open('out/still/c2.png'),float); \
print(np.abs(a-b).mean()/255)"
```

- [ ] 每个片段都抽帧看过：内容对得上这句字幕（不是“研究员对镜头说话”被当成“贴标签”）。
- [ ] 片段没有跨原片剪辑点（没有中途跳镜）。
- [ ] 片段内没有循环跳帧、没有停在末帧；短素材是整体放慢，不是硬撑。
- [ ] 片段边缘没有裁掉水印、手指或关键画面（片段镜头不套整帧推近）。
- [ ] 原片人声没有混进音轨；听的仍是中文旁白 + 垫乐。
- [ ] 白底/高亮图铺底后不发灰；标题、字幕对比正常。
- [ ] 数据卡数字在镜头结束前到达目标值（`0.5 克` 不能停在 `0.3 克`）。
- [ ] 标题装饰数字没有贴边被裁。
- [ ] 结尾卡在旁白结束后出现，来源和互动引导完整。
