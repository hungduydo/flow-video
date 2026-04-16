"""
Prerequisite checking for pipeline steps.

Usage (inside any step's main function, after its own sentinel/skip check):

    from pipeline.prereqs import check_prerequisites

    def translate(output_dir: Path, ...) -> Path:
        sentinel = output_dir / ".step4.done"
        if sentinel.exists():
            return ...                              # skip — already done

        check_prerequisites("step4_translate", output_dir)  # ← raises if deps missing

        # ... proceed with the step
"""
from __future__ import annotations

import re
from pathlib import Path

from pipeline.registry import REGISTRY


class PrerequisiteError(RuntimeError):
    """Raised when one or more required pipeline steps have not completed."""


def check_prerequisites(step_id: str, output_dir: Path) -> None:
    """Check that all declared dependencies of step_id have completed.

    Reads dependency info from pipeline.registry.REGISTRY. Raises a
    PrerequisiteError with an actionable message if any sentinel is missing.

    Args:
        step_id:    Registry key for the step about to run (e.g. "step4_translate").
        output_dir: The pipeline output directory for this video.

    Raises:
        KeyError:           If step_id is not in REGISTRY.
        PrerequisiteError:  If any required dependency sentinel is missing.
    """
    step = REGISTRY[step_id]

    # ALL required deps must be done
    missing = [
        REGISTRY[dep_id]
        for dep_id in step.dependencies
        if not (output_dir / REGISTRY[dep_id].sentinel).exists()
    ]

    # AT LEAST ONE of dep_any must be done
    any_missing: list = []
    if step.dep_any:
        if not any((output_dir / REGISTRY[d].sentinel).exists() for d in step.dep_any):
            any_missing = [REGISTRY[d] for d in step.dep_any]

    if not missing and not any_missing:
        return

    lines: list[str] = []
    min_num = 99

    for dep in missing:
        lines.append(f"  • {dep.name} ({dep.sentinel})")
        n = _step_num(dep.sentinel)
        if n < min_num:
            min_num = n

    if any_missing:
        names = " or ".join(d.name for d in any_missing)
        lines.append(f"  • need at least one of: {names}")
        n = min(_step_num(d.sentinel) for d in any_missing)
        if n < min_num:
            min_num = n

    raise PrerequisiteError(
        f"[{step.name}] Missing prerequisite(s):\n" + "\n".join(lines) +
        f"\n  Resume with: --from-step {min_num}"
    )


def _step_num(sentinel: str) -> int:
    m = re.search(r"step(\d+)", sentinel)
    return int(m.group(1)) if m else 99
