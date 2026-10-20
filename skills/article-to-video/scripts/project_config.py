# -*- coding: utf-8 -*-
"""Per-project switches shared by tts_chunks / align_asr / build_audio_cont."""

# Beat ids intentionally left out of the narration. Keep the same set in all
# three scripts by importing this module.
EXCLUDE = set()

# Optional: override the number of scenes per voice chunk (default = 2).
# SCENES_PER_CHUNK = 2
