import argparse
from pathlib import Path

from .main import translate

parser = argparse.ArgumentParser(description="Step 4: translate CN → VN subtitles")
parser.add_argument("output_dir")
parser.add_argument("--provider", default="gemini", choices=["gemini", "claude"],
                    help="Translation provider: gemini (default) or claude")
args = parser.parse_args()

translate(Path(args.output_dir), provider=args.provider)
