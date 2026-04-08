import sys
from pathlib import Path

from .main import separate_audio

if len(sys.argv) < 2:
    print("Usage: python -m pipeline.step2b_separate_audio <output_dir>")
    sys.exit(1)

separate_audio(Path(sys.argv[1]))
