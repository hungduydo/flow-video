import sys
from pathlib import Path

from .main import download

if len(sys.argv) < 2:
    print("Usage: python -m pipeline.step1_download <url> [output_base]")
    sys.exit(1)

_url = sys.argv[1]
_base = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("output")
download(_url, _base)
