import argparse
from pathlib import Path

from .main import translate

parser = argparse.ArgumentParser(description="Step 4: translate CN → VN subtitles")
parser.add_argument("output_dir")
parser.add_argument("--provider", default="ollama_cloud", choices=["gemini", "claude", "ollama_cloud", "ollama"],
                    help="Translation provider: ollama_cloud (default), gemini, claude, or ollama (local)")
args = parser.parse_args()

translate(Path(args.output_dir), provider=args.provider)
