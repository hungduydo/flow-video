import argparse
from pathlib import Path

from .main import transcribe

p = argparse.ArgumentParser()
p.add_argument("output_dir")
p.add_argument("--model", default="large-v3")
p.add_argument("--transcriber", choices=["whisper", "deepgram"], default="whisper")
a = p.parse_args()
transcribe(Path(a.output_dir), model_size=a.model, provider=a.transcriber)
