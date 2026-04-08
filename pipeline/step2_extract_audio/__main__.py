import sys
from pathlib import Path

from .main import extract_audio

if len(sys.argv) < 2:
    print("Usage: python -m pipeline.step2_extract_audio <output_dir>")
    sys.exit(1)

extract_audio(Path(sys.argv[1]))
