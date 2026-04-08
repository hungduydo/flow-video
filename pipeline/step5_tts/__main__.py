import sys
from pathlib import Path

from .main import generate_tts

if len(sys.argv) < 2:
    print("Usage: python -m pipeline.step5_tts <output_dir> [provider]")
    sys.exit(1)

_provider = sys.argv[2] if len(sys.argv) > 2 else "edge_tts"
generate_tts(Path(sys.argv[1]), provider=_provider)
