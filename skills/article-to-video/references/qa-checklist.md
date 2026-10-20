# QA checklist

Run from the project folder (scripts beside `script_data.py`). Set `FFMPEG` if
the default WinGet path does not exist.

## Automated

```bash
# set once
export FFMPEG="C:/Users/<user>/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffmpeg.exe"
export FFPROBE="$(dirname "$FFMPEG")/ffprobe.exe"

# specs, CFR, decode, frozen windows, loudness
python qa_video.py out/final.mp4 --times 9.5,49,175
```

Pass criteria:

| Check | Pass |
|---|---|
| duration | matches `out/timeline.json` ±0.1 s |
| video | 1080×1920 (or 1920×1080), H.264, `r_frame_rate=30/1` |
| PTS | every `dt=0.0333`, no duplicate timestamps |
| decode | `ffmpeg -v error -i final.mp4 -f null -` prints nothing |
| frozen windows | `zero_runs=0`; no run of ≥3 frames with diff < 0.02 |
| loudness | I = −17.5…−14.5 LUFS; true peak ≤ −1.0 dB |
| audio | AAC 48 kHz stereo |

Manual spot checks (extract stills):

```bash
for t in 2.5 9.3 9.7 75 178; do
  "$FFMPEG" -y -i out/final.mp4 -ss "$t" -frames:v 1 "out/still/f_$t.png"
done
```

- [ ] Hook frame has the premise + motion, not a static title.
- [ ] At a cut boundary, the previous caption is visible until the next speech
      starts; no sentence is missing.
- [ ] Underline sits below the glyph, not through it (look at a large CJK word).
- [ ] Text on the brightest image is readable (scrim present).
- [ ] End card has source, credit, and a CTA.
- [ ] No double captions / double images during transitions.
- [ ] No frame with two big headers overlapping.

## Audio boundary check

Pick a cut and inspect the mixed audio energy:

```bash
"$FFMPEG" -hide_banner -nostats -ss 7.5 -t 2.5 -i out/audio_mix.wav \
  -af volumedetect -f null -
```

Better: print 100 ms RMS in Python around the boundary. Speech should end, then
a pause, then the next sentence starts exactly at the visual cut. If the cut is
inside speech, the ASR times are wrong; re-run `align_asr.py` and rebuild.

## Delivery

- [ ] `out/*.mp4` plays on a phone (system gallery + browser).
- [ ] `out/subtitles.srt` opens and timestamps match.
- [ ] `out/解说稿.md` has `mm:ss` for every beat.
- [ ] `README.md` lists regenerate commands and the voice/format decisions.
- [ ] Previous version still exists (separate folder or `out/vN/`).
- [ ] File name is human-readable and does not contain the old version's title.
