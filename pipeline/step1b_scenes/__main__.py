import sys
from pathlib import Path

from .main import detect_scenes

if len(sys.argv) < 2:
    print("Usage: python -m pipeline.step1b_scenes <output_dir>")
    sys.exit(1)

detect_scenes(Path(sys.argv[1]))
