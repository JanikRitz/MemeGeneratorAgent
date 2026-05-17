"""
Query width, height, duration, and type of a media file.

Usage:
    uv run .github/scripts/get_media_info.py media/input.mp4
    uv run .github/scripts/get_media_info.py --input media/input.mp4

Outputs a JSON object to stdout:
    {"path": "...", "is_video": true, "width": 1280, "height": 720, "duration_sec": 12.5}
"""

import argparse
import json
import logging
from pathlib import Path

from MemeEngine import MemeEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Query media file metadata (width, height, duration).")
    parser.add_argument("input_path", nargs="?", help="Path to media file (positional)")
    parser.add_argument("--input", dest="input_flag", help="Path to media file")
    args = parser.parse_args()

    input_path = args.input_flag or args.input_path
    if not input_path:
        parser.error("Provide a media file path as a positional argument or via --input")

    project_root = Path(__file__).resolve().parents[2]
    logger = logging.getLogger("meme_engine")
    logger.addHandler(logging.NullHandler())

    engine = MemeEngine(base_dir=str(project_root), logger=logger)
    info = engine.get_media_info(input_path)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
