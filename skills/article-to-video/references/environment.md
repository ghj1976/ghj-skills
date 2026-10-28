# 环境搭建（Windows + WSL）

参考流程跑在 Windows 11 + WSL、RTX 5080 Laptop（16GB）、Python 3.13、WinGet 安装的 ffmpeg 上。可以从 WSL 直接调用 Windows 解释器，例如：

```bash
/mnt/d/project/.venv-tts/Scripts/python.exe D:\project\script.py
```

## Python / VoxCPM

系统 Python 可能是 CPU 版 torch。先检查：

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

如果输出 `+cpu` / `False`，建一个继承已安装 `voxcpm` 的隔离 venv，补 CUDA torch：

```bash
python -m venv --system-site-packages .venv-tts
.venv-tts/Scripts/python.exe -m pip install --no-deps \
  torch==2.11.0+cu128 torchaudio==2.11.0+cu128 \
  -f https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/
.venv-tts/Scripts/python.exe -c "import torch; print(torch.cuda.is_available())"
```

- 默认 PyTorch 源可能很慢；SJTU 镜像实测约 15MB/s。
- 不要为此往系统 Python 里 `pip install`；venv 放项目本地。
- VoxCPM 模型缓存：`~/.cache/huggingface/hub/models--openbmb--VoxCPM2`，约 4GB。
- 两个推理进程约占 14GB 显存，不要开 3 个。
- pip 包可能比 GitHub README 旧；加 `seed` 前先看真实的 `generate` / `build_prompt_cache` 签名。

## ffmpeg / ffprobe

WinGet 安装路径：

```
C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe
```

`ffprobe.exe` 在同目录。脚本通过 `ffmpeg_path.py` 自动查找（`FFMPEG`/`FFPROBE` 环境变量优先，然后 PATH，再 glob WinGet 目录），这样不依赖 `%USERNAME%`——从 WSL 启动 Windows Python 时该变量可能乱码。FFmpeg 9 移除了 `-vsync`，用 `-fps_mode passthrough`。

## 字体

WSL 通常没有中文字体（`fc-list :lang=zh` 为空）。用 Windows Python + Windows 字体文件渲染：

```
C:\Windows\Fonts\Noto Sans SC Bold (TrueType).otf
C:\Windows\Fonts\Noto Sans SC Medium (TrueType).otf
```

Pillow 可以直接加载带空格的 `.otf` 路径。不要依赖 fontconfig。

## ASR（faster-whisper）

```bash
.venv-tts/Scripts/python.exe -m pip install faster-whisper
```

`small` 模型首次使用会下载（约 460MB）。用 CPU `int8`：CUDA 可能报 `Library cublas64_12.dll is not found`；3 分钟口播用 CPU 足够，也省去修 CUDA DLL PATH。`transcribe` 前一定重采样到 16kHz（见踩坑文档）。

## 脚本用到的 Python 包

`numpy`、`soundfile`、`scipy`、`librosa`、`Pillow`、`torch`、`voxcpm`、`faster-whisper`。系统 Python 通常已随 VoxCPM 装了 Pillow/numpy/scipy/librosa，venv 会继承。

## 路径与编码注意事项

- Python `subprocess` 能处理中文用户名；`ls`/`tasklist` 里可能显示乱码，但路径本身能解析。
- Windows 路径用原始字符串传（`r"D:\project\out"`）；不要在 WSL 里 `cd` 到 Windows 风格路径。
- 当前工作目录和 DSH checkout 无关；不要从 checkout 位置推断项目路径。
- 磁盘：3 分钟、1080×1920、CRF 18–20 的成片约 40–60MB；中间文件（口播/音乐/音效分轨）再加约 100MB；
  有动态 B-roll 时 `clips/` 再加约 40MB。
- **从 WSL 调 Windows Python 时，环境变量不会自动透传**（Win32 进程默认只拿 `WSLENV` 白名单）。
  `VIDEO_OUT=xxx.mp4 python.exe render.py` 实测被忽略，成片写进了默认文件名。改脚本默认值，
  或把变量写进 `WSLENV`。
- **WSL 里调 Windows ffmpeg，输出路径必须是 Windows 路径**：`ffmpeg ... "$(wslpath -w out/x.mp4)"`，
  否则报 `Could not open file`。用 Windows Python 跑脚本时则直接用 `D:\...` 或相对路径。
- `.agents/skills/...` 在 Windows 侧可能是 WSL 符号链接，Windows Python 读不到（`WinError 1920`）；
  要测试 skill 脚本，先复制到普通目录（如 `_skilltest/`）再跑。

## torchcodec / ZIP-Enhancer

VoxCPM2 的 `ZipEnhancer` 用 `torchaudio.load`，而 torchaudio 2.11 默认走 torchcodec。Windows 上如果没装 **shared** FFmpeg（WinGet 的 Gyan 包是静态编译），会报：

```
FileNotFoundError: Could not find module '...\torchcodec\libtorchcodec_core4.dll'
```

不要为此换 ffmpeg。`scripts/make_voice_ref.py` 在调用去噪前把 `torchaudio.load/save` 换成 soundfile 实现即可：

```python
import soundfile as sf, torch, torchaudio
torchaudio.load = lambda p, **k: (torch.from_numpy(sf.read(str(p), dtype="float32", always_2d=True)[0].T.copy()),
                                 sf.info(str(p)).samplerate)
torchaudio.save = lambda p, w, sr, **k: sf.write(str(p), w.detach().cpu().numpy().T, int(sr))
```

去噪模型从 ModelScope 拉取，首次约几十 MB，缓存后离线可用。
