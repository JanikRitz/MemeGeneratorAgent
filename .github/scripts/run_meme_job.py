from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from compact_compiler import CompactCompiler
from compact_jobs import CompactJob, Presets, validate_job
from MemeEngine import MemeEngine
from plan_executor import PlanExecutor


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run compact meme/v1 jobs from JSON.")
    parser.add_argument("config_path", nargs="?", help="Path to JSON config or directory (positional)")
    parser.add_argument("--config", help="Path to JSON config or directory")
    parser.add_argument("--presets", type=Path, help="Path to JSON style and quality preset overrides")
    parser.add_argument("--project-root", type=Path, default=Path.cwd(), help="Base directory for relative paths (defaults to the current working directory)")
    parser.add_argument("--example", help="Select a named job from a compact example catalog")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate", action="store_true", help="Validate compact job structure without resolving media or rendering")
    mode.add_argument("--expand", action="store_true", help="Print the resolved execution plan without rendering")
    mode.add_argument("--schema", action="store_true", help="Print the compact job JSON Schema; no config required")
    parser.add_argument("--preview-only", action="store_true", help="Render PNG previews instead of full outputs")
    cache = parser.add_mutually_exclusive_group()
    cache.add_argument("--force", action="store_true", help="Rebuild all steps and refresh their cache entries")
    cache.add_argument("--no-cache", action="store_true", help="Render without reading or writing the persistent cache")
    parser.add_argument("--cache-dir", type=Path, help="Cache directory, relative to project root (default: .meme-cache)")
    parser.add_argument("--release", action="store_true", help="Remove this run's scratch files; preserve final output and persistent cache")
    parser.add_argument("--verbose", action="store_true", help="Log step cache hits and misses and rendering details")
    parser.add_argument("--video-codec", help="Override video codec globally (e.g. h264_nvenc, libx264, h264_qsv, h264_amf)")
    parser.add_argument("--threads", type=int, help="Override threads per video encode (not parallel jobs)")
    parser.add_argument("--video-crf", type=int, help="Override video CRF/CQ quality parameter globally")
    parser.add_argument("--video-preset", help="Override video encoding preset globally (e.g. fast, medium, slow, p4)")
    return parser


def load_config_file(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    if args.schema:
        print(json.dumps(CompactJob.model_json_schema(), indent=2))
        return
    config_arg = args.config or args.config_path
    if not config_arg:
        parser.error("Provide --config <path> or a positional config path")
    config_path = Path(config_arg)
    config_files = sorted(config_path.glob("*.json")) if config_path.is_dir() else [config_path]
    if not config_files:
        parser.error(f"No JSON config files found in {config_path}")
    if args.expand and len(config_files) > 1:
        parser.error("--expand requires one config file")
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        parser.error("--project-root must be an existing directory")
    presets = None
    if args.presets:
        preset_path = args.presets if args.presets.is_absolute() else project_root / args.presets
        try:
            presets = Presets.model_validate(load_config_file(preset_path))
        except Exception as exc:
            parser.error(f"Invalid --presets file {preset_path}: {str(exc).strip() or repr(exc)}")
    cache_dir = args.cache_dir or Path(".meme-cache")
    cache_dir = (cache_dir if cache_dir.is_absolute() else project_root / cache_dir).resolve()
    executor = PlanExecutor(None if args.no_cache else cache_dir)
    logger = logging.getLogger("meme_engine")
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
        logger.setLevel(logging.INFO)
    failed = False
    for config_file in config_files:
        try:
            config = load_config_file(config_file)
            if args.example:
                examples = {**config.get("examples", {}), **config.get("additional_examples", {})}
                if args.example not in examples:
                    raise ValueError(f"Unknown example: {args.example}")
                config = examples[args.example]
            if "operation" in config or "pipeline" in config:
                raise ValueError("Legacy configs are no longer supported; use a compact meme/v1 job with input, output, and steps")
            job = validate_job(config)
            if args.validate:
                print(f"Valid: {config_file}" + (f" ({args.example})" if args.example else ""))
                continue
            engine = MemeEngine(str(project_root), logger)
            overrides = {"codec": args.video_codec, "crf": args.video_crf, "preset": args.video_preset, "threads": args.threads}
            plan = CompactCompiler(project_root, engine, presets=presets).compile(job, preview=args.preview_only, overrides=overrides)
            if args.expand:
                print(plan.model_dump_json(indent=2))
            else:
                print(executor.execute(plan, engine, preview=args.preview_only, release=args.release, force=args.force))
        except Exception as exc:
            print(f"Error in {config_file}: {str(exc).strip() or repr(exc)}", file=sys.stderr)
            failed = True
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()