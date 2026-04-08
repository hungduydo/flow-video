import argparse
from pathlib import Path

from .main import compose

parser = argparse.ArgumentParser(description="Step 6: compose final video")
parser.add_argument("output_dir")
parser.add_argument("--crf", type=int, default=23)
parser.add_argument("--platform", default="youtube", choices=["youtube", "tiktok", "both"])
parser.add_argument("--tiktok-crop-x", type=int, default=None, dest="tiktok_crop_x")
args = parser.parse_args()
compose(Path(args.output_dir), crf=args.crf, platform=args.platform, tiktok_crop_x=args.tiktok_crop_x)
