# Environment setup (Windows + WSL)

The reference pipeline was built on Windows 11 with WSL, an RTX 5080 Laptop
(16 GB), Python 3.13, and ffmpeg from WinGet. Commands can be launched from WSL
by calling the Windows interpreter directly, e.g.
`/mnt/d/project/.venv-tts/Scripts/python.exe D:\project\script.py`.

## Python / VoxCPM

The system Python may have a CPU-only torch build. Check:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

If it prints `+cpu` / `False`, create an isolated venv that inherits the
installed `voxcpm` and adds CUDA torch:

```bash
python -m venv --system-site-packages .venv-tts
.venv-tts/Scripts/python.exe -m pip install --no-deps \
  torch==2.11.0+cu128 torchaudio==2.11.0+cu128 \
  -f https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/
.venv-tts/Scripts/python.exe -c "import torch; print(torch.cuda.is_available())"
```

- The default PyTorch index can be very slow; the SJTU mirror was ~15 MB/s.
- Do not `pip install` into the system Python for this; keep the venv local.
- VoxCPM model cache: `~/.cache/huggingface/hub/models--openbmb--VoxCPM2` (about 4 GB).
- Two inference processes fit in ~14 GB VRAM. Do not launch 3.
- The pip package may be older than the GitHub README; inspect the actual
  `generate` / `build_prompt_cache` signatures before adding `seed`.

## ffmpeg / ffprobe

WinGet install path:

```
C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe
```

`ffprobe.exe` sits beside it. The scripts read `FFMPEG` from the environment and
derive `FFPROBE` from it. FFmpeg 9 removed `-vsync`; use `-fps_mode passthrough`.

## Fonts

WSL often has no CJK fonts (`fc-list :lang=zh` empty). Render with the Windows
Python and the Windows font files:

```
C:\Windows\Fonts\Noto Sans SC Bold (TrueType).otf
C:\Windows\Fonts\Noto Sans SC Medium (TrueType).otf
```

Pillow can load `.otf` paths with spaces directly. Do not rely on fontconfig.

## ASR (faster-whisper)

```bash
.venv-tts/Scripts/python.exe -m pip install faster-whisper
```

The `small` model downloads on first use (~460 MB). Use CPU `int8`:
CUDA may fail with `Library cublas64_12.dll is not found`; CPU is sufficient for
a 3-minute narration and avoids CUDA-DLL PATH surgery. Always resample to 16 kHz
before `transcribe` (see pitfalls).

## Python packages used by the scripts

`numpy`, `soundfile`, `scipy`, `librosa`, `Pillow`, `torch`, `voxcpm`,
`faster-whisper`. The system Python already had Pillow/numpy/scipy/librosa from
the VoxCPM install; the venv inherits them.

## Path and encoding notes

- Chinese usernames are fine in Python `subprocess`; they may look garbled in
  `ls`/`tasklist` output but resolve correctly.
- Pass Windows paths as raw strings (`r"D:\project\out"`); do not use `cd` with
  Windows-style paths inside WSL.
- The working directory and the DSH checkout are unrelated; never infer paths
  from the checkout location.
- Disk: a 3-minute 1080×1920 CRF 18–20 video is ~40–60 MB; intermediates
  (narration/music/SFX stems) add ~100 MB.
