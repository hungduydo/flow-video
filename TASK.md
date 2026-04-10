# Task: Scene Detection Metadata Layer + TTS Pacing + Translate Awareness

Design doc: `~/.gstack/projects/flow-video/user-main-design-20260410-001923.md`
Designed: 2026-04-10 | Status: Ready to implement

## Problem

Dubbed audio bleeds across visual scene cuts. The translator also generates translations
without knowing scene boundaries, causing TTS audio that is too long for its scene slot.

## Solution

Write `scenes.json` once (new `pipeline/step1b_scenes/`). TTS and translate both read it.

---

## Implementation Tasks

### 1. `pipeline/step1b_scenes/` — NEW step

- [ ] Create `pipeline/step1b_scenes/__init__.py` — export `detect_scenes()`
- [ ] Create `pipeline/step1b_scenes/__main__.py` — mirror pattern from e.g. `pipeline/step1_download/__main__.py`
- [ ] Create `pipeline/step1b_scenes/main.py`:
  - `detect_scenes(output_dir: Path) -> Path` — main entry point
  - Find source video (non-`final_*.mp4` or `.mkv` in output_dir)
  - Primary detection: `_detect_with_ffmpeg(video_path)` using `scdet=threshold=10:sc_pass=1`
    - Parse stderr for `lavfi.scd.time:` lines (wrap float() in try/except)
  - Fallback: `_detect_with_pyscenedetect(video_path)` if ffmpeg yields 0 cuts
    - `from scenedetect import detect, AdaptiveDetector` — pin to `>=0.6,<1.0`
  - `_get_video_duration(video_path)` — ffprobe, returns 0.0 on failure (log warning)
  - `_cuts_to_scenes(cuts, duration)` — [(0.0, 12.3), (12.3, 45.1), ...]
  - Write `scenes.json` + touch `.step1b.done` sentinel
  - scenes.json format: `{"cuts": [...], "scenes": [...], "detector": "...", "video_duration": N}`

- [ ] Test: `python -m pipeline.step1b_scenes output/<some_id>/`
  - Verify `scenes.json` exists and cuts look reasonable
  - Verify re-run is skipped (sentinel exists)

### 2. `pipeline/step5_tts/main.py` — scene-aware silence

- [ ] In `generate_tts()`, after loading subtitles, load `scenes.json`:
  ```python
  cuts: set[float] = set()
  scenes_path = output_dir / "scenes.json"
  if scenes_path.exists():
      data = json.loads(scenes_path.read_text(encoding="utf-8"))
      cuts = set(data.get("cuts", []))
  ```

- [ ] Add helpers (before or after existing helpers):
  ```python
  def _has_cut_in_range(cuts, start, end):
      # inclusive — cut at boundary → enforce gap silence
      return any(start <= c <= end for c in cuts)

  def _earliest_cut_in_range(cuts, start, end):
      # exclusive — cut exactly at sub_start/end is handled by gap logic
      in_range = [c for c in cuts if start < c < end]
      return min(in_range) if in_range else None

  def _trim_audio(input_path, output_path, duration):
      # ffmpeg -t {duration} trim
  ```

- [ ] In segment loop, extend gap insertion:
  - If cut falls in [prev_end, sub_start]: `gap = max(gap, MIN_DURATION)`

- [ ] In segment loop, after TTS generation for each segment:
  - Check `_earliest_cut_in_range(cuts, sub_start, sub_end)`
  - If cut found within segment:
    - `trim_duration = cut - sub_start`
    - `pad_duration = sub_end - cut`
    - If `trim_duration > MIN_DURATION`: trim audio + append trimmed + append silence pad + continue
    - Else (too short): emit full-slot silence instead of TTS + continue
  - **Critical:** The pad silence fills the remainder of the subtitle slot so A/V sync is preserved.
    Total (trimmed audio + pad) must equal original subtitle duration. Atempo pass stays correct.

- [ ] Test: delete `.step5.done`, re-run step5 on a video with known fast cuts
  - Watch `audio_vn_speech.mp3` — should have silence at cut timestamps

### 3. `pipeline/step4_translate/utils.py` — scene-aware prompt

- [ ] Read existing `build_prompt()` signature first
- [ ] Add `cuts: list[float] | None = None` parameter (default None — backward compat)
- [ ] Add `_build_scene_note(batch, cuts)` helper:
  - Filter cuts to those within batch time range
  - If any found, return a note string about scene boundaries
  - If none, return ""
- [ ] Append `scene_note` to the returned prompt string

### 4. `pipeline/step4_translate/main.py` — load and pass cuts

- [ ] After loading subtitles, load `scenes.json` (same pattern as step5)
- [ ] In the batching loop, add `cuts=cuts` to the `build_prompt()` call
- [ ] No changes to provider interface (`gemini.py`, `claude.py`)

### 5. Wire into `main.py` and `flow_v2/main_v2.py`

- [ ] `main.py`: `from pipeline.step1b_scenes import detect_scenes`
  - Call `detect_scenes(output_dir)` between step1 and step2
- [ ] `flow_v2/main_v2.py`: same pattern
- [ ] Sentinel clearing: when `--from-step 1` or `--force`, also delete `.step1b.done`
  - Look for `_NUMBERED_SENTINELS` in main.py and add the step1b clearing alongside step1

### 6. `requirements.txt`

- [ ] Add comment block:
  ```
  # Optional: higher-quality scene detection for step1b_scenes
  # (primary path uses ffmpeg scdet which is always available)
  # pip install "scenedetect>=0.6,<1.0"
  ```

---

## Notes for implementer

- `MIN_DURATION = 0.3` already exists at top of `step5_tts/main.py` — reuse it
- `_has_cut_in_range` is inclusive, `_earliest_cut_in_range` is exclusive (intentional —
  see design doc for boundary convention)
- `all_paths` in step5 is concatenated in strict order — trim+pad appended consecutively
  preserves silence placement
- scenes.json is always optional: if absent, all steps run exactly as before
- `flow_v2` music workflow may produce too many cuts with default scdet threshold=10
  (fast edits on music videos) — consider a `--scene-threshold N` flag as follow-up

## Follow-up (not in scope for this PR)

- Step3 (Whisper) segmentation hints from scene boundaries
- Step6 chapter markers in YouTube video metadata from scenes.json
- Per-workflow-type scene detection threshold defaults in flow_v2
