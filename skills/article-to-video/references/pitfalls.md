# Pitfalls and measured evidence

These are the failures that caused real re-cuts. The numbers are from the
AI-article project; treat them as expected orders of magnitude, not constants.

## 1. Per-sentence voice cloning changes the speaker

**Symptom:** "声音时好时不好" — one line is deep and calm, the next is brighter
and faster, as if another person read it.

**Measurement:** 45 independently generated beats had median f0 from **71 Hz to
154 Hz**. Four long chunks generated with the same prompt/reference measured
**100 / 103 / 100 / 98 Hz**. The chunk medians were consistent; the beat medians
were not.

**Cause:** zero-shot cloning samples speaker characteristics at the start of each
generation. Short texts and different punctuation give the model more freedom.

**Fix:** generate 3–4 long chunks (30–60 s each), same prompt cache, same seed,
same `inference_timesteps=10`. Do not regenerate each beat. Measure each chunk
with `librosa.pyin(fmin=60, fmax=350)`; reject outside 85–115 Hz.

## 2. Fast, high-pitched voice feels untrustworthy

**Symptom:** "语速太快了，让人感觉不信任."

**Measurement:** the first cut was **7.8 chars/s** (1667 chars in 217 s of
speech) and f0 ≈ 171 Hz. The accepted cut is **5.2–5.6 chars/s**, f0 ≈ 95–105 Hz.

**Fix:** low-pitch prompt/reference, calm known-transcript sample, target
5.2–5.8 chars/s. If a few lines are still >7 chars/s, apply a mild per-beat
`atempo` (0.85–0.95), never a pitch shift. Do not slow the whole mix with
`atempo=0.8`; it makes the pauses unnatural.

## 3. Cutting long-form audio per sentence loses words

**Symptom:** "话没说完，就切成另外一个了。感觉丢了段声音."

**Measurement:** the sentence "它连轴转了十一天" occupied 1.5 s of audio. The
per-beat splitter gave it **1.08 s** because it cut at a nearby RMS minimum,
removing the last ~0.5 s.

**Cause:** a min-energy point is not necessarily a sentence end. Cutting and
reassembling per-beat clips also adds artificial gaps and can move the tail into
the next clip.

**Fix:** never cut the long-form audio. Concatenate the chunks with gaps and use
ASR only for **timing**. The narration remains continuous; the worst case is a
caption arriving slightly early/late, never a missing word.

## 4. ASR alignment: boundary must be the next sentence onset

**Symptom:** the previous sentence is still audible when the image/caption
changes, or the caption appears before its audio.

**Fix:** for each beat, find the first matched transcript word; set the boundary
to the **start of the first word of the next beat**. That is the definition of
"the next sentence has started." Do not cut at the middle of a pause, and do not
use char proportion alone (it drifts when the TTS speeds up or slows down).

**Numbers:** ASR-aligned boundaries for the first chunk were
`[0, 6.2, 8.54, 10.96, 13.9, 16.52, 20.6, 27.8, 32.74, 37.94]`. The cut at 9.54 s
matched the next speech onset; the old cut at 7.67 s chopped the sentence.

## 5. Whisper transcribes 48 kHz arrays as slow audio

**Symptom:** faster-whisper returns English gibberish ("I said I don't know how")
for Chinese speech, with timestamps beyond the clip duration.

**Cause:** faster-whisper assumes 16 kHz for numpy input. A 48 kHz array is
interpreted as 16 kHz, i.e. 3× slower.

**Fix:** `librosa.resample(y, orig_sr=48000, target_sr=16000)` before
`model.transcribe`. After that, the Chinese transcript was correct.

## 6. ctranslate2 cannot find cuBLAS

**Symptom:** `RuntimeError: Library cublas64_12.dll is not found or cannot be loaded`.

**Fix:** run faster-whisper on CPU (`device="cpu", compute_type="int8"`); a 3-minute
Chinese narration aligns in a couple of minutes. Alternatively prepend torch's
`lib` directory to PATH, but CPU is less fragile.

## 7. Stutter/freeze at image changes

The final video had four compounding causes:

1. **Clamped zoom during pauses.** `progress = min(1, lt / beat_duration)` and
   `lt` exceeded the beat duration during the 0.34 s gap, so the image froze for
   0.34 s, then the next shot jumped. Fix: use `next_beat.start - start` as the
   visual duration and **linear** progress, no clamp until the cut.
2. **Smoothstep easing.** `smoothstep` has zero velocity at t=0 and t=1, so
   every shot started/ended with a near-static hold. Fix: linear or ease-out
   with a non-zero end velocity.
3. **Integer crop.** `int(2048/zoom)` changed every 2–3 frames, then jumped 1 px.
   Fix: `Image.transform(..., AFFINE, (sx,0,x0,0,sy,y0))` with float values.
4. **Crossfade double exposure.** Two big captions or illustrations blended for
   0.2–0.3 s looked like a rendering glitch. Fix: hard cut; the whoosh covers it.

**Verification:** decode the MP4, take 36 frames around a cut, compute mean abs
difference on 270×480 copies. Before the fix, 9–14 frames had diff < 0.02
(visually identical) followed by a 26–74 spike. After: 0 zero frames.

## 8. Static text cards are encoded as frozen frames

Even with a slow whole-frame zoom, a 7.5 % change over an 18 s scene is
~0.004 %/frame, often below the encoder's update threshold. A static text card
then looks frozen for seconds.

**Fix:** a slow whole-frame zoom plus a moving low-alpha light sweep on text/data
layouts. Verify **decoded** frames, not source frames.

## 9. Underline through the glyphs

**Symptom:** the orange line cuts through the bottom strokes of
"一把钥匙" / "自己想办法".

**Cause:** CJK glyph ink extends below the em box; `y + font_size + 22` is not
below the glyph.

**Fix:**

```python
bbox = d.textbbox((x, y), text, font=f)
line_y = bbox[3] + 16
d.rectangle([x, line_y, x + width, line_y + 8], fill=accent)
```

## 10. SFX clipping and loudness drift

The SFX track normalized to RMS 0.02 still had peaks at **1.0**, and the mix
clipped. Fix: normalize SFX **peak** to 0.30, add `alimiter=limit=0.95` after
`amix`, and check `ebur128` true peak. Target −16 LUFS, peak ≤ −1.5 dB.

## 11. CPU PyTorch smells like a VoxCPM bug

The system Python had `torch 2.14.1+cpu`. VoxCPM worked, but 30 s of audio took
20+ minutes (~40× realtime) and tool calls timed out. This is not a VoxCPM
problem. Create a venv with `--system-site-packages` and install
`torch/torchaudio +cu128`; generation drops to roughly realtime×0.3–2 on a
desktop GPU.

## 12. Broken image links are the norm in exported articles

Markdown often contains `assets/<title>/file-*.png`, while the images are in the
article directory. Map by **article order**, then open each image and confirm it
matches the paragraph. Do not rely on the filename alone, and do not silently
drop an image.

## 13. 16:9 vs 9:16

A 16:9 first cut was rejected for phone viewing. 1080×1920 is the default for
mobile platforms; 16:9 remains only for embedded players or explicit requests.
Keep the old cut in a separate folder — the user explicitly asked for side-by-side
comparison.
