## Step 4 — Translate

Translates `captions_cn.srt` (Chinese) → `captions_vn.srt` (Vietnamese).

### Entry point
```
translate(output_dir: Path, provider: str = "gemini") -> Path
```
Returns path to `captions_vn.srt`.

### Outputs
| File | Description |
|------|-------------|
| `captions_vn.srt` | Vietnamese subtitles |
| `.step4.done` | Sentinel |

### File layout
| File | Responsibility |
|------|----------------|
| `main.py` | Entry point only — loads subtitles, scenes, dispatches to provider |
| `prompt.py` | Shared `SYSTEM_PROMPT` constant |
| `utils.py` | `batch()`, `parse_json_response()`, `build_prompt()`, `clean_subtitles()`, `_build_scene_note()` |
| `providers/gemini.py` | Gemini 2.0 Flash (`GEMINI_API_KEY`) |
| `providers/claude.py` | Claude Sonnet 4.6 (`ANTHROPIC_API_KEY`) |

### Providers
Both implement `run(subtitles: list[srt.Subtitle], system_prompt: str) -> list[str]`.

Batching: 50 segments or 4000 chars per batch, with 3-segment context overlap.

### Scene awareness
`main.py` reads `scenes.json` (if present) and appends cut timestamps to `system_prompt` before passing to the provider. This hints the LLM to produce concise translations near scene boundaries.

### Adding a new provider
Create `providers/yourprovider.py` with:
```python
def run(subtitles: list[srt.Subtitle], system_prompt: str) -> list[str]: ...
```

### CLI
```
python -m pipeline.step4_translate <output_dir> [gemini|claude]
```
