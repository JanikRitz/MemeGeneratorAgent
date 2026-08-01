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
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Force preview-only mode for add_text_side_box operations, overriding config",
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

    config_arg = args.config or args.config_path
    if not config_arg:
        parser.error("Provide --config <path> or a positional config path")

    config_path = Path(config_arg)
    if config_path.is_dir():
        config_files = sorted(config_path.glob("*.json"))
        if not config_files:
            print(f"No JSON config files found in {config_path}")
            return

        project_root = config_path.resolve().parents[1]
        for cfg_file in config_files:
            try:
                config = prepare_config_for_run(cfg_file, load_config_file(cfg_file), project_root)
            except Exception as exc:
                err_msg = str(exc).strip() or repr(exc)
                print(f"Error preparing {cfg_file}: {err_msg}")
                continue

            run_config_file(cfg_file, config, project_root, args)
        return

    try:
        config = prepare_config_for_run(config_path, load_config_file(config_path), Path(config_path).resolve().parents[2])
    except Exception as exc:
        err_msg = str(exc).strip() or repr(exc)
        print(f"Error preparing {config_path}: {err_msg}")
        sys.exit(1)

    success = run_config_file(config_path, config, Path(config_path).resolve().parents[2], args)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
