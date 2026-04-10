import argparse
from pathlib import Path

from .main import banner

parser = argparse.ArgumentParser(description="Step 7: generate video banner thumbnails")
parser.add_argument("output_dir", help="Pipeline output directory (contains final_youtube.mp4)")
parser.add_argument(
    "--platform", default="both", choices=["youtube", "tiktok", "both"],
    help="Which platform banner(s) to generate (default: both)"
)
parser.add_argument(
    "--model", default="gemini-3-flash-preview:cloud",
    help="Ollama Cloud model for LLM frame selection (default: gemini-3-flash-preview:cloud)"
)
parser.add_argument(
    "--ollama-url", default=None, dest="ollama_url",
    help="Ollama Cloud base URL (default: https://ollama.com or OLLAMA_URL env var)"
)
args = parser.parse_args()

banner(
    Path(args.output_dir),
    platform=args.platform,
    model=args.model,
    ollama_url=args.ollama_url,
)
