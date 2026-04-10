## Step 5 — TTS

Converts `captions_vn.srt` → per-segment TTS audio → `audio_vn_full.mp3`.

### Entry point
```
generate_tts(output_dir: Path, provider: str = "edge_tts") -> Path
```
Returns path to `audio_vn_full.mp3`.

### Outputs
| File | Description |
|------|-------------|
| `audio_vn/seg_NNNN.mp3` | Natural-speed TTS per segment |
| `audio_vn_speech.mp3` | Concatenated segments + silence gaps |
| `audio_vn_speech_adjusted.mp3` | After global atempo speed adjustment |
| `audio_vn_full.mp3` | Final — speed-adjusted + mixed with accompaniment |
| `.step5.done` | Sentinel |

### Providers
Located in `tts_providers/`. Both implement the `TTSProvider` interface (`synth(text, path)`).

| Provider | Notes |
|----------|-------|
| `edge_tts` (default) | Microsoft Edge TTS, free, no API key |
| `elevenlabs` | High-quality, requires `ELEVENLABS_API_KEY` |

### Speed adjustment
All segments are generated at natural speed. A single global `atempo` pass (clamped `0.9–1.2×`) is applied to match the total Vietnamese audio duration to the original audio duration. This avoids per-segment mechanical stretching.

### Scene-aware silence
If `scenes.json` exists, `generate_tts()` loads cut timestamps and:
- **Gap enforcement**: if a scene cut falls between `prev_end` and `sub_start`, gap silence is extended to at least `MIN_DURATION`.
- **Segment trimming**: if a cut falls strictly inside a subtitle slot, the TTS is trimmed at the cut and the remainder is filled with silence. This preserves A/V sync — `trimmed_audio + pad_silence = original subtitle duration`.
  - If the pre-cut portion is shorter than `MIN_DURATION`, the whole slot is replaced with silence.

### Key constants
| Constant | Value | Meaning |
|----------|-------|---------|
| `MIN_DURATION` | `0.3s` | Skip TTS / enforce minimum gap |
| `SPEED_MIN` | `0.9` | atempo lower bound |
| `SPEED_MAX` | `1.2` | atempo upper bound |

### Scene-aware helpers
| Helper | Description |
|--------|-------------|
| `_has_cut_in_range(cuts, start, end)` | Inclusive — used for gap boundary check |
| `_earliest_cut_in_range(cuts, start, end)` | Exclusive — used for in-segment trim |
| `_trim_audio(input, output, duration)` | ffmpeg `-t` trim |

### CLI
```
python -m pipeline.step5_tts <output_dir> [edge_tts|elevenlabs]
```
