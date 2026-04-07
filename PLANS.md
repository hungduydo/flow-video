# PLANS.md — Bilibili Re-Up Pipeline

Tracking implementation of the Vietnamese dub + caption pipeline.
Design doc: `~/.gstack/projects/flow-video/user-unknown-design-20260406-100752.md`

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| [ ] | Not started |
| [~] | In progress |
| [x] | Done |
| [!] | Blocked / needs decision |

---

## Phase 0 — Project Setup

| # | Task | How | When | Status |
|---|------|-----|------|--------|
| 0.1 | Create project structure | `mkdir -p pipeline output` | Day 1 start | [x] |
| 0.2 | Create `requirements.txt` | List all deps (see design doc) | Day 1 start | [x] |
| 0.3 | Create `.env` with `GEMINI_API_KEY` | Copy from Google AI Studio | Day 1 start | [ ] |
| 0.4 | Install system deps | `brew install ffmpeg` (macOS) | Day 1 start | [ ] |
| 0.5 | `pip install -r requirements.txt` | In a virtualenv | Day 1 start | [ ] |
| 0.6 | Verify yt-dlp works on Bilibili | `yt-dlp --dump-json <bilibili_url>` | Day 1 verify | [ ] |

---

## Phase 1 — Download (step1_download.py)

**What:** Download a Bilibili video to `output/{video_id}/original.mp4` + `metadata.json`

**How:**
- Use `yt-dlp` with best quality format selection
- Extract video ID for the output directory name
- Support `--cookies FILE` for login-required videos
- Write `.step1.done` sentinel on success

| # | Task | How | When | Status |
|---|------|-----|------|--------|
| 1.1 | Implement `step1_download.py` | yt-dlp Python API | Day 1 | [x] |
| 1.2 | Test with one public Bilibili URL | Manual run | Day 1 | [ ] |
| 1.3 | Verify `metadata.json` has video ID, title, duration | Print output | Day 1 | [ ] |

---

## Phase 2 — Audio Extraction (step2_extract_audio.py)

**What:** Extract audio from `original.mp4` → `audio.wav` (16kHz mono, optimized for Whisper)

**How:**
- ffmpeg: `-ar 16000 -ac 1 -c:a pcm_s16le`
- Input: `original.mp4`, Output: `audio.wav`
- Write `.step2.done` sentinel on success

| # | Task | How | When | Status |
|---|------|-----|------|--------|
| 2.1 | Implement `step2_extract_audio.py` | ffmpeg-python | Day 1 | [x] |
| 2.2 | Test: verify audio.wav plays clean, no artifacts | `ffplay audio.wav` | Day 1 | [ ] |

---

## Phase 3 — Chinese Transcription (step3_transcribe.py)

**What:** Chinese speech → Chinese text + timestamps → `captions_cn.srt`

**How:**
- `faster-whisper` model: `large-v3`
- `task="transcribe"`, `language="zh"` (forced, do not autodetect)
- Word-level timestamps enabled
- Generate SRT format
- Write `.step3.done` sentinel on success

| # | Task | How | When | Status |
|---|------|-----|------|--------|
| 3.1 | Implement `step3_transcribe.py` | faster-whisper API | Day 1 | [x] |
| 3.2 | First run: download model (~3GB for large-v3) | Automatic on first run | Day 1 | [ ] |
| 3.3 | Spot-check `captions_cn.srt` accuracy | Read file, compare to audio | Day 1 | [ ] |
| 3.4 | Check: timestamps match actual speech | Spot check 5 segments | Day 1 | [ ] |

**Note:** First run downloads the large-v3 model (~3GB). GPU strongly recommended.
CPU transcription for a 10-min video takes ~20-30 minutes.

---

## Phase 4 — Vietnamese Translation (step4_translate.py)

**What:** Chinese SRT text → Vietnamese text → `captions_vn.srt` (same timestamps)

**How:**
- Parse SRT with `srt` library → extract text only
- Send to `gemini-1.5-flash` in batches of 50 segments or ~4,000 chars
- Re-inject original timestamps into translated text (never trust Gemini with SRT format)
- Write `.step4.done` sentinel on success

| # | Task | How | When | Status |
|---|------|-----|------|--------|
| 4.1 | Implement SRT parser (segment in, segment out) | `srt` library | Day 2 | [x] |
| 4.2 | Implement Gemini translation call | `google-generativeai` SDK | Day 2 | [x] |
| 4.3 | Implement batching logic (50 segs or 4K chars) | Python loop | Day 2 | [x] |
| 4.4 | Test: read `captions_vn.srt`, check Vietnamese quality | Manual review | Day 2 | [ ] |
| 4.5 | Test: verify timestamps in VN SRT match CN SRT exactly | diff timestamps | Day 2 | [ ] |

---

## Phase 5 — Vietnamese TTS + Timing (step5_tts.py)

**What:** Vietnamese SRT → per-segment audio → time-stretched → `audio_vn_full.mp3`

**How:**
- Primary: Gemini audio generation (`gemini-2.0-flash-exp` or current audio model)
- Fallback: `edge-tts` with `vi-VN-HoaiMyNeural` voice (if Gemini TTS unavailable)
- Per-segment: generate audio → measure duration → calculate `atempo` ratio
  - `atempo = tts_duration / original_duration`
  - If atempo > 2.0: chain `atempo=2.0,atempo=X`
  - If atempo > 4.0: truncate at segment boundary + log warning
- Concatenate all stretched segments → `audio_vn_full.mp3`
- Exponential backoff for rate limits (1s → 2s → 4s → ... max 60s)
- Write `.step5.done` sentinel on success

| # | Task | How | When | Status |
|---|------|-----|------|--------|
| 5.1 | Test Gemini TTS on free tier (single segment) | API call, check response | Day 2 | [x] (using edge-tts as primary) |
| 5.2 | If Gemini TTS unavailable → implement edge-tts fallback | `edge-tts` CLI/API | Day 2 | [x] (edge-tts is primary) |
| 5.3 | Implement atempo stretch logic | ffmpeg-python | Day 2 | [x] |
| 5.4 | Implement concatenation of segments | ffmpeg concat demuxer | Day 2 | [x] |
| 5.5 | Listen to `audio_vn_full.mp3` — check timing sync | `ffplay` | Day 2 | [ ] |
| 5.6 | Add backoff + retry for rate limit errors | `time.sleep` + exception catch | Day 2 | [x] |

**Decision needed (5.2):** Check if `gemini-2.0-flash-exp` audio output works on free tier
before building the Gemini TTS path. If not available, go straight to edge-tts.

---

## Phase 6 — Video Composition (step6_compose.py)

**What:** Combine watermark-removed video + VN audio + VN captions → `final.mp4`

**How:**
```
ffmpeg:
  1. -vf "scale=iw*1.05:ih*1.05, crop=iw/1.05:ih/1.05"  ← zoom 5% (watermark)
  2. -i audio_vn_full.mp3                                  ← replace audio
  3. -vf "subtitles=captions_vn.srt:force_style='...'"    ← burn captions
  4. -c:v libx264 -crf 23 -preset fast -c:a aac
```
Note: `crop` dimensions reference the *scaled* frame, not original.
Write `.step6.done` sentinel on success.

| # | Task | How | When | Status |
|---|------|-----|------|--------|
| 6.1 | Implement watermark zoom/crop | ffmpeg-python filter chain | Day 2 | [x] |
| 6.2 | Implement audio replacement | `-map` to select VN audio | Day 2 | [x] |
| 6.3 | Implement caption burning | `subtitles` vf filter | Day 2 | [x] |
| 6.4 | Watch `final.mp4` — check watermark, audio, captions | VLC / QuickTime | Day 2 | [ ] |
| 6.5 | Adjust caption style (font size, color, position) | `force_style` params | Day 2 | [ ] |

---

## Phase 7 — Orchestrator (main.py)

**What:** Tie all steps together with checkpoint/resume logic

**How:**
```
python main.py <url> [--force] [--from-step N] [--crf 23] [--cookies FILE]
```

| # | Task | How | When | Status |
|---|------|-----|------|--------|
| 7.1 | Implement URL → video_id extraction | Parse from yt-dlp metadata | Day 3 | [x] |
| 7.2 | Implement sentinel-based skip logic | Check `.stepN.done` files | Day 3 | [x] |
| 7.3 | Implement `--force` and `--from-step N` flags | argparse + sentinel deletion | Day 3 | [x] |
| 7.4 | Implement `--crf` and `--cookies` passthrough | argparse | Day 3 | [x] |
| 7.5 | End-to-end test: full pipeline from URL to final.mp4 | One real Bilibili URL | Day 3 | [ ] |
| 7.6 | End-to-end test: crash at step 3, re-run, verify resume | Kill process, re-run | Day 3 | [ ] |

---

## Known Risks / Blockers

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Gemini TTS not on free tier | Step 5 blocked | Fallback to edge-tts (task 5.2) |
| Bilibili blocks yt-dlp | Step 1 fails | Update yt-dlp, try cookies |
| faster-whisper large-v3 too slow on CPU | Step 3 takes 30+ min | Use `medium` model instead |
| atempo >4x on short segments | Audio truncation | Log warning, acceptable tradeoff |
| ffmpeg not installed | All compose steps fail | Add preflight check in main.py |

---

## Done Definition

Pipeline is complete when:
- [ ] `python main.py <bilibili_url>` produces `final.mp4` without errors
- [ ] Re-running the same URL resumes without re-downloading or re-transcribing
- [ ] `final.mp4` has: no Bilibili watermark, Vietnamese audio, Vietnamese burned-in captions
- [ ] A 10-min video completes end-to-end in under 45 minutes (CPU) / 15 minutes (GPU)
