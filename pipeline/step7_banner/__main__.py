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
parser.add_argument(
    "--sample-interval", type=float, default=1.0, dest="sample_interval", metavar="S",
    help="Seconds between frame samples (default: 1.0; use 0.5 for denser sampling)"
)
parser.add_argument(
    "--force", action="store_true",
    help="Re-run even if .step7.done sentinel already exists"
)
args = parser.parse_args()

output_dir = Path(args.output_dir)
if args.force:
    sentinel = output_dir / ".step7.done"
    if sentinel.exists():
        sentinel.unlink()
        print("[step7] --force: cleared sentinel, re-running")

banner(
    output_dir,
    platform=args.platform,
    model=args.model,
    ollama_url=args.ollama_url,
    sample_interval=args.sample_interval,
)
