"""
Workflow: Hybrid — Music + Voice (Group 5)

Videos with significant background music AND voice-over (vlog, music review).
Uses the full narration pipeline; Demucs separates vocals from music so the
accompaniment can be mixed back under the Vietnamese TTS in step5.

Delegates entirely to the narration workflow.
"""

from .narration import run  # noqa: F401 — re-exported for workflow routing
