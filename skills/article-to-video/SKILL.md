---
name: article-to-video
description: Turn a Markdown article (especially a Chinese 公众号 post) into a narrated short video with VoxCPM2 voice, local images, continuous long-form audio, ASR-aligned captions, and mobile-first motion graphics. Use for article-to-video production, broken image-link repair, voice/pacing selection, vertical 9:16 or 16:9 rendering, caption sync, and debugging stutter, frozen frames, or cut-off audio.
---

# Article → narrated video

A production playbook distilled from a real 公众号 article adaptation: a 3:58 horizontal first cut was rejected as "too static, voice too fast"; a 3:20 vertical rewrite fixed pacing but had a glyph/underline collision and inconsistent voice; a final 3:00 cut fixed frozen transitions, cut-off sentences, and audio loss. The hard-won rules are below; follow them in order.

## When to use

- "把这篇公众号文章做成视频" / article-to-video / MD → narrated MP4.
- Images in the MD point at a missing `assets/...` folder but the files are beside the article.
- Need a mobile-native vertical cut (视频号 / 抖音 / 朋友圈) or a 16:9 cut.
- Existing video has: static opening, rushed/creepy voice, stutter at image changes, captions that change before the sentence ends, or a missing half-second of audio.
- Need a repeatable pipeline with subtitles, narration script, and a quality gate.

## Non-negotiables

1. **Never cut long-form TTS into per-sentence clips.** Cutting at estimated pauses is how words disappear. Keep each long chunk continuous; use ASR timestamps only for visual/caption timing.
2. **Align cuts to the next sentence onset, not to a pause midpoint.** A cut is allowed only after the previous sentence has finished and the next one starts.
3. **No crossfade between text-heavy shots.** Two big captions or two busy illustrations blended together read as a glitch. Hard cut + continuous motion is smoother.
4. **Every frame must move.** Clamp-free, linear camera motion through pauses; text cards get a slow push-in + light sweep. A static hold followed by a jump is perceived as lag.
5. **Underlines use the glyph bbox, never the font size.** CJK ink extends below the nominal em box; `y + font_size` puts the line through the strokes.
6. **Verify the decoded MP4, not the source frames.** Encoders legitimately skip low-motion blocks. Check frame-to-frame differences after decoding; zero-motion runs are real freezes.
7. **Preserve prior versions.** New cut → new folder or `out/vN/`; never overwrite the version the user wants to compare.
8. **QA on a phone-sized canvas.** Text must survive a 1080×1920 screen with platform UI on the right and bottom.

## Scaffold a new project

```bash
# `SKILL` is this skill's base directory, reported by the skill loader.
SKILL=<base dir of this skill>   # e.g. /mnt/e/mycode/ghj-skills/skills/article-to-video
PROJ=work/<video-slug>
mkdir -p "$PROJ/audio" "$PROJ/out"
cp "$SKILL"/scripts/*.py "$PROJ"/
cp "$SKILL"/scripts/script_data_template.py "$PROJ"/script_data.py
```

Then:

1. Edit `script_data.py` (scenes, beats, `img` names).
2. Put a 4–8 s `audio/prompt_ref.wav` in place and set `PROMPT_TEXT` in `tts_chunks.py`.
3. Edit `project_config.py` (`EXCLUDE`) and keep it identical for all three voice/align/build scripts.
4. Set `ASSET_DIR` if images live outside the project folder.

`build_audio_cont.py` and `align_asr.py` derive `GROUPS` automatically: two scenes
per voice chunk, so 8 scenes → 4 chunks, 3 scenes → 2 chunks. If a scene count is
odd, the last chunk has one scene.

## Pipeline at a glance

| Phase | Output | Gate |
|---|---|---|
| 0 Intake | image map, format decision | every image viewed and mapped |
| 1 Script | `script_data.py`, 35–50 beats | hook ≤ 3 s, total 2:45–3:30 |
| 2 Voice | 2–4 long chunk WAVs | chunk f0 85–115 Hz, 4.5–6.5 chars/s |
| 3 Audio | continuous `narration.wav`, music/SFX, mix | −16 LUFS, true peak ≤ −1.5 dB |
| 4 Align | `asr_times.json`, `timeline.json` | cut = next speech onset |
| 5 Render | 1080×1920 or 1920×1080 MP4 | every shot moves, no crossfade |
| 6 QA | `qa` report, stills, README | CFR, clean decode, no zero-frame runs |

## Phase 0 — intake and assets

1. Read the Markdown completely. Extract title, section headings, pull-quotes, numbers, and image order.
2. **Repair image links by order, then look at every image.** A typical broken link looks like `assets/<article-title>/file-*.png` while the real files sit in the article directory. Map image *n* in the MD to the *n*-th local PNG, but open the image and confirm its content matches the adjacent paragraph. Do not trust filenames alone.
3. Verify dimensions/aspect and that no image is a duplicate or a screenshot of unrelated UI.
4. Choose format:
   - **9:16, 1080×1920** for phone-first / 视频号 / 抖音. This is the default when the user says "普通手机用户" or "划走".
   - **16:9, 1920×1080** only when the destination is an embedded article player or the user asks for horizontal.
5. Create a new project folder per version; copy the source images or reference them read-only. Never overwrite the previous cut.

**Project layout**

```
project/
  script_data.py          # scenes, beat text, captions, big keywords, layouts
  tts_chunks.py           # VoxCPM2 long-form generation
  align_asr.py            # faster-whisper word timestamps
  build_audio_utils.py    # music, SFX, mix, SRT, script export
  build_audio_cont.py     # continuous timeline + stems
  render.py               # vertical/horizontal frame renderer
  qa_video.py             # automated checks
  audio/
    prompt_ref.wav        # 4–8 s known-transcript voice prompt
    chunk_0..N.wav        # long-form narration
    asr_times.json
  out/
    timeline.json narration.wav music.wav sfx.wav audio_mix.wav
    subtitles.srt 解说稿.md <name>.mp4
```

## Phase 1 — script and storyboard

Target **2:45–3:30** at 5.2–5.8 Chinese characters/second. A 900–1100-character script is typical. The first cut's 1667 characters at 7.8 chars/s felt rushed even at 3:58.

Structure:

1. **Hook (0–3 s):** one concrete, surprising sentence. Example: "一个 AI，为了查清公园门口谁人多，连轴转了十一天。" Start with motion, not a 15-second title card. A 1-second kinetic title is acceptable, then cut immediately.
2. **Cold open (3–20 s):** 4–6 shots, each 2–5 s, that set up the premise and the weirdest detail. Cut on every new fact.
3. **Body:** 4–6 chapters, one idea per shot. Keep the article's numbers and the opposing side's response; do not turn commentary into assertion.
4. **Turn:** the counter-intuitive line ("最冷的一句话" / "天网没来").
5. **Close:** a short callback + an open question. No long recap.

Per-beat schema (`script_data.py`):

```python
{
  "id": "00_01",
  "text": "它连轴转了十一天。",              # spoken; punctuation matters
  "sub": "它连轴转了十一天",                  # displayed, ≤ 15 CJK chars/line
  "big": "11 天",                          # 3–9 char keyword on screen
  "layout": "card",                        # card | text | data | hook
  "accent": "orange",                      # orange | cyan
  "eyebrow": "连轴转",                     # small editorial label
  "img": "file-....png",                   # per-beat override
}
```

Rules:

- One beat = one subtitle = one visual change. Merge fragments shorter than 0.8 s; split anything over ~28 CJK chars.
- Keep captions ≤ 2 lines, ≤ 15 CJK chars/line at 64 px on 1080-wide. Longer lines auto-wrap badly; write explicit `\n`.
- Use `big` for the idea, not a duplicate of the full caption. If the image already contains the same text, choose a different angle.
- Alternate `card` (image + keyword), `text` (quote/stat), `data` (numbers), and `hook` (full-bleed, fastest cuts). Never leave a text card static for more than ~4 s without a cut.
- Do not include markdown, links, parentheticals, or stage directions in `text`.

## Phase 2 — voice

Use VoxCPM2 when available. The installed CLI/API may be older than the GitHub README: check the actual signature before passing `seed` (the 2.0.3 package does not accept it; use `torch.manual_seed`). The core API is `model.tts_model.build_prompt_cache(...)` + `generate_with_prompt_cache(target_text=..., prompt_cache=..., inference_timesteps=10)`.

### Environment

System Python often has CPU-only torch. On a CUDA machine, create an isolated venv that inherits the installed `voxcpm` package and adds CUDA torch:

```bash
python -m venv --system-site-packages .venv-tts
.venv-tts/Scripts/python.exe -m pip install --no-deps \
  torch==2.11.0+cu128 torchaudio==2.11.0+cu128 \
  -f https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/
```

The default PyTorch index may be slow; the SJTU mirror was ~15 MB/s. CPU inference was ~40× realtime (30 s audio ≈ 20 min) and tool calls timed out; CUDA brought a 3-min script to ~5 min of generation.

### The one rule that matters: long-form, not per-sentence

Per-sentence cloning drifts speaker identity. In the rejected cut, 45 independently generated beats measured **71–154 Hz** median f0. Four long chunks generated with the same prompt/reference measured **100 / 103 / 100 / 98 Hz**. Do not generate each beat separately "for exact timing"; exact timing comes from ASR later.

1. Prepare a **4–8 s `prompt_ref.wav`** with a known transcript, low pitch, calm delivery. A generated beat or a clean example voice works; save the transcript in `PROMPT_TEXT`. The voice prompt plus reference (same file is fine) is more stable than reference-only.
2. Generate **2–4 long chunks**, 30–60 s each, grouping 2 scenes per chunk. Keep the same prompt cache, `torch.manual_seed(20)`, `cfg_value=2.0`, `inference_timesteps=10`.
3. Do not prepend a style control to every chunk unless it is needed; style prompts can change pitch. If pace is too fast, use a fixed style on **all** chunks or a mild `atempo` later.
4. Measure each chunk: median f0 (librosa.pyin, 60–350 Hz) and chars/s. Accept 85–115 Hz and 4.5–6.5 chars/s. Regenerate a chunk outside the range rather than pitch-shifting it.
5. Keep the chunks; the audio is never cut afterwards.

Commands: `scripts/tts_chunks.py` (run `--part 0 --of 2` and `--part 1 --of 2`).

## Phase 3 — continuous audio and mix

1. Trim only leading/trailing silence per chunk (threshold −45 dB, 80 ms pad). Concatenate chunks with 0.6–0.7 s gaps. **No per-beat gaps and no per-beat cuts.**
2. Build `narration.wav`, `music.wav`, `sfx.wav` at 48 kHz.
3. Mix: narration `loudnorm=I=-16:TP=-1.5:LRA=11`; music ≈ −38 dBFS RMS; SFX peak ≈ 0.30; add `alimiter=limit=0.95` after `amix`.
4. Check stems: narration RMS ~0.13, music ~0.010, sfx ~0.005, final true peak ≤ −1.5 dB. The first cut's SFX peaked at 1.0 and clipped; the limiter fixed it.
5. SFX: whoosh at scene starts, impact at 3–4 key beats, ticks for numbers, one riser before the turn. Keep them sparse; a whoosh every 3 s becomes noise.

`scripts/build_audio_cont.py` + `scripts/build_audio_utils.py` implement this.

## Phase 4 — ASR alignment (the fix for cut-off sentences)

Visual/caption cuts must land on the **start of the next sentence**, after the previous sentence has fully played.

1. Transcribe each chunk with faster-whisper (`small`, CPU `int8` is enough). **Resample 48 kHz → 16 kHz first**; passing 48 kHz makes Whisper hear 3× slow audio and hallucinate English.
2. Get word timestamps (`word_timestamps=True`, `language="zh"`).
3. Normalize expected text and transcript (remove punctuation/spaces, lowercase). Match characters with `difflib.SequenceMatcher`; for each beat record the first matched transcript char.
4. Boundary after beat *i* = **start time of the first matched word of beat *i+1***. The last beat ends at the chunk end.
5. If ASR fails, fall back to character-proportional expected time, biased **late**, never early. A late cut holds the old image through a pause; an early cut chops the sentence.
6. Write `asr_times.json` and build the timeline from it. Verify three points: last word end of sentence A, pause, first word start of sentence B; the cut must equal B's onset.

See `scripts/align_asr.py`. Example result: "它连轴转了十一天" played 7.5–9.0 s, pause 9.0–9.5 s, cut at 9.54 s when the next sentence began. The earlier per-beat cut gave that sentence only 1.08 s and chopped its tail.

## Phase 5 — render

Defaults for mobile: 1080×1920, 30 fps, H.264 High, AAC-LC 48 kHz stereo, CRF 18–20, `-preset veryfast`, `+faststart`.

Layout (vertical):

- Top: 4–6 px progress bar; chapter label at y≈75; small brand at top-right.
- Big keyword block at y≈220–500: eyebrow 27 px, keyword 90–170 px (auto-shrink to 960 px width), underline via `textbbox`.
- Image card: full width 1080×608 at y≈540; blurred, darkened cover of the same image fills the 1920 canvas.
- Captions: 64 px bold, 2 lines max, centered at y≈1400–1550, black stroke 8 px, dark scrim behind.
- Safe area: keep text 60 px from sides; avoid the bottom 250 px and right 120 px (platform UI).

Motion rules:

- **Linear**, clamp-free Ken Burns across the whole shot including pauses: `prog = min(1, lt / (next_start - start))`. Do not use smoothstep; its zero start/end velocity creates holds.
- Subpixel sampling: `Image.transform(..., Image.AFFINE, ...)` with float scale/translate. Integer `crop().resize()` steps 1 px every few frames and shimmers.
- **Hard cuts**, no crossfade. Crossfade double-exposes big text and looks like a glitch. A whoosh covers the cut.
- Text/data cards: slow whole-frame zoom (≈7.5 % per scene) + a moving low-alpha light sweep. Otherwise the encoder skips identical frames and the card freezes.
- No punch-in at every cut and no white flash; both amplify the "jerk" feeling.
- Underline: `bbox = d.textbbox((x, y), text, font=f); y_line = bbox[3] + 16`.
- Text-only layouts: add a dark scrim (`alpha≈125`) before drawing text so light images do not wash it out.
- Use `Noto Sans SC Bold` / `Medium` from `C:\Windows\Fonts`; pass full `.otf` paths, including spaces.

`scripts/render.py` is the working vertical renderer. Before the first render, edit its project copy block (`BRAND`, `TITLE_MAIN`, `TITLE_SUB`, `TITLE_KICKER`, `TITLE_CREDIT`, `END_L1/L2/Q/CTA/SOURCE`) or set the matching `VIDEO_*` environment variables. Do not ship the example branding.

## Phase 6 — QA and delivery

Automated (`scripts/qa_video.py`):

- `ffprobe`: duration, 1080×1920, 30/1, H.264/AAC.
- PTS intervals: every `1/30` s, no duplicate timestamps, full decode with `-f null -`.
- Frame-diff: decode windows around 3–5 known cuts; flag runs of ≥3 frames with mean abs diff < 0.02. Those are freezes.
- Audio: `ebur128=peak=true`, integrated ≈ −16 LUFS, true peak ≤ −1.0 dB (target −1.5).

Manual:

- View stills at the hook, a cut, a text card, the underline fix, and the end card.
- Check captions against speech at 2–3 boundaries; the previous caption must persist until the next sentence starts.
- Check that no words are missing: play the boundary region once.
- Confirm the original version still exists and is linked in the README.

Deliver: MP4, SRT, timestamped narration script, README with the exact regenerate commands, and a one-paragraph note on voice/format decisions.

## Troubleshooting

| Symptom | Root cause | Fix |
|---|---|---|
| Voice sounds different every few sentences | per-sentence cloning resamples speaker | generate 3–4 long chunks; same prompt+reference; verify chunk f0 |
| Speech too fast / "untrustworthy" | 7–8 chars/s, high f0 | calm low-pitch prompt, 5.2–5.8 chars/s; slow outliers with mild atempo, never pitch-shift |
| Words missing / sentence cut off | per-beat audio cutting at estimated pauses | keep chunks continuous; ASR align; never cut |
| Caption changes before the sentence ends | boundary at pause midpoint or char proportion | boundary = first word of next beat from ASR |
| Stutter/freeze at image changes | zoom clamped during pauses; static hold; crossfade | linear motion through the shot; no clamp; hard cut; text-card zoom/sweep |
| Micro-jitter during slow zoom | integer crop steps | affine subpixel transform |
| Text card looks frozen | only static text; encoder skips blocks | whole-frame slow zoom + light sweep |
| Underline crosses the glyphs | line placed at `y+font_size` | `textbbox()[3] + margin` |
| Double text on transition | crossfade between captions | hard cut |
| SFX clips / loud | SFX peak 1.0, no limiter | normalize SFX peak 0.3; `alimiter=0.95` |
| ASR outputs English gibberish | 48 kHz fed as 16 kHz | resample to 16 kHz first |
| CUDA whisper fails `cublas64_12.dll` | ctranslate2 can't find cuBLAS | CPU `int8` is enough; or add torch/lib to PATH |
| CPU VoxCPM 40× slower | CPU torch build | isolated venv with CUDA torch |
| Fonts missing / tofu | WSL has no CJK fonts | render with Windows Python and `C:\Windows\Fonts\NotoSansSC...` |
| Image links broken | MD points to `assets/...` | map by article order, open each image, fix per-beat `img` |

## Definition of done

- [ ] Every MD image mapped and visually verified.
- [ ] Hook in the first 3 s; no static title > 1 s.
- [ ] 35–50 beats; total 2:45–3:30; captions ≤ 15 CJK chars/line.
- [ ] 2–4 long voice chunks; chunk f0 85–115 Hz; 4.5–6.5 chars/s.
- [ ] Audio continuous, not per-beat cut; ASR-aligned cut points.
- [ ] No crossfade; every shot has motion; subpixel zoom; underline via bbox.
- [ ] −16 LUFS, true peak ≤ −1.0 dB, SFX peak ≤ 0.3.
- [ ] CFR 30 fps, clean full decode, no zero-frame runs at cuts.
- [ ] Project text in `render.py` edited (no leftover example branding).
- [ ] SRT + narrated script + README; earlier version preserved.
- [ ] Final file opened locally and spot-checked on a phone-sized player.

## Detailed references

- [Pitfalls and measured evidence](references/pitfalls.md)
- [QA commands and manual checklist](references/qa-checklist.md)
- [Windows/WSL environment setup](references/environment.md)
- [Storyboard schema example](scripts/script_data_template.py)

## Scripts

Copy these beside `script_data.py` in the project folder. They assume `audio/prompt_ref.wav`, `audio/chunk_0..N.wav`, `out/`, and Windows Python/ffmpeg by default; override `FFMPEG`, `FONT_BOLD`, `FONT_MED` via environment variables if needed.

- `scripts/tts_chunks.py` — long-form VoxCPM2 generation.
- `scripts/align_asr.py` — 16 kHz faster-whisper word alignment → `asr_times.json`.
- `scripts/build_audio_utils.py` — music, SFX, mix, SRT, script.
- `scripts/build_audio_cont.py` — continuous timeline + stems + `timeline.json`.
- `scripts/render.py` — vertical renderer with the motion/underline fixes.
- `scripts/qa_video.py` — CFR/decode/frame-diff/loudness checks.
- `scripts/project_config.py` — shared `EXCLUDE` beat ids.
- `scripts/ffmpeg_path.py` — locates ffmpeg/ffprobe without `%USERNAME%` (mojibake under WSL).

Environment overrides: `FFMPEG`, `FFPROBE`, `FONT_BOLD`, `FONT_MED`, `ASSET_DIR` (or `render.py --assets <dir>`; WSL does not
forward arbitrary env vars unless listed in `WSLENV`),
`VOX_MODEL`, `VOX_STEPS`, `VOX_SEED`, `VOX_CFG`, `VIDEO_BRAND`, `VIDEO_TITLE`,
`VIDEO_SUBTITLE`, `VIDEO_KICKER`, `VIDEO_CREDIT`, `VIDEO_END_*`, `VIDEO_SOURCE`,
`VIDEO_OUT`.
Edit `IMPACT_IDS` / `RISER_BEFORE` in `build_audio_utils.py` for the current story.
