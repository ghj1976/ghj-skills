# -*- coding: utf-8 -*-
"""tts_chunks / align_asr / build_audio_cont 共用的项目开关。"""

# Beat ids intentionally left out of the narration. Keep the same set in all
# three scripts by importing this module.
EXCLUDE = set()

# Optional: override the number of scenes per voice chunk (default = 2).
# SCENES_PER_CHUNK = 2

# 音色：默认用技能内置的 voices/<VOICE>/（当前 q1 女声）。
# 项目里放了 audio/prompt_ref.wav 时以项目为准，这里的 VOICE 就不起作用。
# VOICE = "q1"

# 语速：voice.json 里的 atempo 会自动应用（q1 是 0.92）；写在这里可覆盖。
# TEMPO = 0.92

# 可选：逐段 atempo（从 audio/chunk_*_raw.wav 一次到位，只做一次）。
# 同一批生成里各段语速能差 10–13%（实测 6.17 / 5.37 / 5.45 / 6.02 字/秒），
# 统一一个 TEMPO 会“有的快有的慢”；逐段给值能拉到 5.6–5.9。
# 不要为了调速叠第二次 atempo：0.78 再 0.91 会让声音发闷，像换了个人。
# TEMPO_MAP = {"chunk_0": 0.744, "chunk_1": 0.855, "chunk_2": 0.843, "chunk_3": 0.763}
