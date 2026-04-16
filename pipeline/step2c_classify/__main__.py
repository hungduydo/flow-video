import sys
from pathlib import Path

from .main import classify

if len(sys.argv) < 2:
    print("Usage: python -m pipeline.step2c_classify <output_dir> [model_size]")
    sys.exit(1)

_model = sys.argv[2] if len(sys.argv) > 2 else "small"
classify(Path(sys.argv[1]), model_size=_model)
