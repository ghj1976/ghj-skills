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
