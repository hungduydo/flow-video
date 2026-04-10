## Step 2b — Separate Audio

Splits `audio.wav` into vocals and accompaniment using Demucs `htdemucs` (2-stem mode).

### Entry point
```
separate_audio(output_dir: Path) -> tuple[Path, Path]
```
Returns `(vocals.wav, accompaniment.mp3)`.

### Outputs
| File | Description |
|------|-------------|
| `vocals.wav` | Speech only, resampled to 16 kHz mono (for step3 transcription) |
| `accompaniment.mp3` | Background music at original quality (for step5 final mix) |
| `.step2b.done` | Sentinel |

### How it works
1. Run `python -m demucs -n htdemucs --two-stems vocals --mp3` on `audio.wav`.
2. Resample `vocals.mp3` → `vocals.wav` (16 kHz mono PCM) via ffmpeg.
3. Copy `no_vocals.mp3` → `accompaniment.mp3`.
4. Clean up `demucs_tmp/`.

First run downloads ~80 MB model automatically.

### CLI
```
python -m pipeline.step2b_separate_audio <output_dir>
```

### Notes
- Sentinel is `.step2b.done` (not `.step2.done`) — cleared separately from step2.
- If accompaniment is absent in step5, speech audio is used directly without mixing.
