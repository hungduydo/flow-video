## Step 2 — Extract Audio

Extracts audio from `original.mp4` into a 16 kHz mono WAV suitable for Whisper transcription.

### Entry point
```
extract_audio(output_dir: Path) -> Path
```
Returns path to `audio.wav`.

### Outputs
| File | Description |
|------|-------------|
| `audio.wav` | 16 kHz, mono, PCM s16le — Whisper-ready |
| `.step2.done` | Sentinel |

### How it works
Single `ffmpeg` call: `-ar 16000 -ac 1 -c:a pcm_s16le`.

### CLI
```
python -m pipeline.step2_extract_audio <output_dir>
```
