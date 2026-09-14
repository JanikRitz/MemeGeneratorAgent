from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Set

try:
    from config_preparation import ConfigPreparationService
except ImportError:
    from .config_preparation import ConfigPreparationService

try:
    from artifact_cleanup import ArtifactCleanupService
except ImportError:
    from .artifact_cleanup import ArtifactCleanupService

try:
    from job_execution import JobExecutionService
except ImportError:
    from .job_execution import JobExecutionService


CONFIG_PREPARATION_SERVICE = ConfigPreparationService()
ARTIFACT_CLEANUP_SERVICE = ArtifactCleanupService()
JOB_EXECUTION_SERVICE = JobExecutionService(cleanup_service=ARTIFACT_CLEANUP_SERVICE)


def setup_logging(logs_dir: Path) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"meme_job_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger("meme_engine")
    logger.setLevel(logging.WARNING)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.info("Logging initialized at %s", log_file)
    return logger


def rewrite_media_paths(obj: Any, project_root: Path) -> Any:
    return CONFIG_PREPARATION_SERVICE.rewrite_media_paths(obj, project_root)


def contains_stash_references(obj: Any) -> bool:
    return CONFIG_PREPARATION_SERVICE.contains_stash_references(obj)


def contains_hydrus_references(obj: Any) -> bool:
    return CONFIG_PREPARATION_SERVICE.contains_hydrus_references(obj)


def maybe_resolve_stash_references(config: Dict[str, Any]) -> Dict[str, Any]:
    return CONFIG_PREPARATION_SERVICE.maybe_resolve_stash_references(config)


def maybe_resolve_hydrus_references(config: Dict[str, Any]) -> Dict[str, Any]:
    return CONFIG_PREPARATION_SERVICE.maybe_resolve_hydrus_references(config)


def get_output_path_from_config(cfg: Dict[str, Any]) -> Optional[Path]:
    if "pipeline" in cfg:
        for step in reversed(cfg["pipeline"]):
            params = step.get("params", {})
            if "output_path" in params:
                return Path(params["output_path"])
    else:
        params = cfg.get("params", cfg)
        if "output_path" in params:
            return Path(params["output_path"])
    return None


def collect_generated_file_paths(cfg: Dict[str, Any]) -> Set[Path]:
    paths: Set[Path] = set()
    steps = cfg.get("pipeline", [cfg]) if "pipeline" in cfg else [cfg]

    for step in steps:
        if not isinstance(step, dict):
            continue
        operation = step.get("operation")
        params = step.get("params", {})
        if not isinstance(params, dict):
            continue

        output_raw = params.get("output_path")
        output_path = Path(output_raw) if isinstance(output_raw, str) else None
        if output_path is not None:
            paths.add(output_path)
            paths.add(output_path.with_suffix(".png"))

        if operation == "apply_multi_text_overlays":
            overlay_dir_raw = params.get("overlay_dir")
            if not isinstance(overlay_dir_raw, str) and output_path is not None:
                overlay_dir_raw = str(output_path.parent)
            if isinstance(overlay_dir_raw, str):
                overlay_dir = Path(overlay_dir_raw)
                overlays = params.get("overlays", [])
                if isinstance(overlays, list):
                    for index, item in enumerate(overlays):
                        if not isinstance(item, dict):
                            continue
                        name = item.get("overlay_name", f"overlay_{index:03d}")
                        if isinstance(name, str) and name:
                            file_name = name if name.lower().endswith(".png") else f"{name}.png"
                            paths.add(overlay_dir / file_name)

        elif operation == "apply_text_overlay":
            overlay_dir_raw = params.get("overlay_dir")
            if not isinstance(overlay_dir_raw, str) and output_path is not None:
                overlay_dir_raw = str(output_path.parent)
            if isinstance(overlay_dir_raw, str):
                overlay_dir = Path(overlay_dir_raw)
                name = params.get("overlay_name")
                if isinstance(name, str) and name:
                    file_name = name if name.lower().endswith(".png") else f"{name}.png"
                    paths.add(overlay_dir / file_name)
                else:
                    paths.add(overlay_dir / "overlay_000.png")

        elif operation == "add_text_side_box":
            overlay_dir_raw = params.get("overlay_dir")
            if not isinstance(overlay_dir_raw, str) and output_path is not None:
                overlay_dir_raw = str(output_path.parent)
            if isinstance(overlay_dir_raw, str):
                overlay_dir = Path(overlay_dir_raw)
                side = str(params.get("side", "top")).lower()
                panel_name = params.get("panel_png_name") or f"side_box_{side}"
                if isinstance(panel_name, str) and panel_name:
                    file_name = panel_name if panel_name.lower().endswith(".png") else f"{panel_name}.png"
                    paths.add(overlay_dir / file_name)

    return paths


def cleanup_files(paths: Set[Path], keep_path: Optional[Path] = None, logger: Optional[logging.Logger] = None) -> int:
    return ARTIFACT_CLEANUP_SERVICE.cleanup_files(paths, keep_path=keep_path, logger=logger)


def execute_step(
    engine: Any,
    step: Dict[str, Any],
    last_output: str = "",
    preview_only_override: Optional[bool] = None,
    default_font_path: Optional[str] = None,
) -> str:
    return JOB_EXECUTION_SERVICE.execute_step(
        engine,
        step,
        last_output=last_output,
        preview_only_override=preview_only_override,
        default_font_path=default_font_path,
    )


def execute_config(
    config: Dict[str, Any],
    engine: Any,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> str:
    return JOB_EXECUTION_SERVICE.execute_config(config, engine, args, logger)


def run_config_file(
    config_path: Path,
    config: Dict[str, Any],
    project_root: Path,
    args: argparse.Namespace,
    logger: Optional[logging.Logger] = None,
) -> bool:
    return JOB_EXECUTION_SERVICE.run_config_file(
        config_path,
        config,
        project_root,
        args,
        logger=logger,
        output_path_resolver=lambda cfg: get_output_path_from_config(cfg),
        generated_path_collector=lambda cfg: collect_generated_file_paths(cfg),
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MemeEngine jobs from a JSON config file.")
    parser.add_argument("config_path", nargs="?", help="Path to JSON config (positional)")
    parser.add_argument("--config", help="Path to JSON config")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2], help="Base directory for relative media and output paths")
    parser.add_argument("--example", help="Select a named job from a compact example catalog")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate", action="store_true", help="Validate compact job structure without resolving media or rendering")
    mode.add_argument("--expand", action="store_true", help="Print the resolved compact execution plan without rendering")
    mode.add_argument("--schema", action="store_true", help="Print the compact job JSON Schema; no config required")
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Force preview-only mode for operations that support it, overriding config",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even when the output is newer than the config",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="Release mode: clean old intermediate/preview files and keep only the final output artifact",
    )
    parser.add_argument(
        "--video-codec",
        help="Override video codec globally (e.g. h264_nvenc, libx264, h264_qsv, h264_amf)",
    )
    parser.add_argument(
        "--threads",
        type=int,
        help="Override number of threads globally for video encoding (e.g. 4)",
    )
    parser.add_argument(
        "--video-crf",
        type=int,
        help="Override video CRF/CQ quality parameter globally",
    )
    parser.add_argument(
        "--video-preset",
        help="Override video encoding preset globally (e.g. fast, medium, slow, p4)",
    )
    return parser


def load_config_file(config_path: Path) -> Dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def prepare_config_for_run(config_path: Path, config: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    return CONFIG_PREPARATION_SERVICE.prepare_config(config, project_root)


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.schema:
        from compact_jobs import CompactJob
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
    failed = False
    for cfg_file in config_files:
        try:
            config = load_config_file(cfg_file)
            if args.example:
                examples = {**config.get("examples", {}), **config.get("additional_examples", {})}
                if args.example not in examples:
                    raise ValueError(f"Unknown example: {args.example}")
                config = examples[args.example]
            if "format" in config or "steps" in config or args.validate or args.expand:
                from compact_jobs import validate_job
                from compact_compiler import CompactCompiler
                job = validate_job(config)
                if args.validate:
                    print(f"Valid: {cfg_file}" + (f" ({args.example})" if args.example else ""))
                    continue
                engine = JOB_EXECUTION_SERVICE.engine_factory(str(project_root), logging.getLogger("meme_engine"))
                overrides = {"codec": args.video_codec, "crf": args.video_crf, "preset": args.video_preset, "threads": args.threads}
                plan = CompactCompiler(project_root, engine).compile(job, preview=args.preview_only, overrides=overrides)
                if args.expand:
                    print(plan.model_dump_json(indent=2))
                else:
                    print(plan.execute(engine, preview=args.preview_only, release=args.release))
            else:
                config = prepare_config_for_run(cfg_file, config, project_root)
                if not run_config_file(cfg_file, config, project_root, args):
                    failed = True
        except Exception as exc:
            print(f"Error in {cfg_file}: {str(exc).strip() or repr(exc)}", file=sys.stderr)
            failed = True
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
