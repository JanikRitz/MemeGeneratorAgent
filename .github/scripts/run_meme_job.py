import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Set

from MemeEngine import MemeEngine

from operations.base import OperationContext
from operations.registry import build_default_registry

try:
    from stash_client import StashClient
except ImportError:
    from .stash_client import StashClient

try:
    from hydrus_client import HydrusClient
except ImportError:
    from .hydrus_client import HydrusClient


REGISTRY = build_default_registry()


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


def _replace_last_output(value: Any, last_output: str) -> Any:
    if isinstance(value, str):
        return last_output if value == "$last_output" else value
    if isinstance(value, list):
        return [_replace_last_output(item, last_output) for item in value]
    if isinstance(value, dict):
        return {k: _replace_last_output(v, last_output) for k, v in value.items()}
    return value

def _parse_time(value) -> float:
    """Parse 'MM:SS' or 'HH:MM:SS' string to total seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    raise ValueError(f"Invalid time format: {value!r}, expected MM:SS or HH:MM:SS")

def execute_step(
    engine: MemeEngine,
    step: Dict[str, Any],
    last_output: str = "",
    preview_only_override: Optional[bool] = None,
    default_font_path: Optional[str] = None,
) -> str:
    operation = step.get("operation")
    params = step.get("params", {})
    if last_output:
        params = _replace_last_output(params, last_output)

    if not operation:
        raise ValueError("Each step must define an operation")

    context = OperationContext(
        engine=engine,
        logger=engine.logger,
        preview_only_override=preview_only_override,
        default_font_path=default_font_path,
        last_output=last_output,
    )

    handler = REGISTRY.get(operation)
    if handler is None:
        raise ValueError(f"Unsupported operation: {operation}")

    return handler.execute(engine, params, context)


def rewrite_media_paths(obj: Any, project_root: Path) -> Any:
    if isinstance(obj, dict):
        return {k: rewrite_media_paths(v, project_root) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rewrite_media_paths(item, project_root) for item in obj]
    if isinstance(obj, str):
        for prefix in ("media/", "render/", "logs/", "config/"):
            if obj.startswith(prefix):
                return str(project_root / obj)
        return obj
    return obj


def contains_stash_references(obj: Any) -> bool:
    if isinstance(obj, dict):
        if "$stash_scene_path" in obj or "$stash_marker_time" in obj or "$stash_image_path" in obj:
            return True
        return any(contains_stash_references(value) for value in obj.values())
    if isinstance(obj, list):
        return any(contains_stash_references(item) for item in obj)
    if isinstance(obj, str):
        return obj.startswith("stash:scene:") or obj.startswith("stash:marker:") or obj.startswith("stash:image:")
    return False


def contains_hydrus_references(obj: Any) -> bool:
    if isinstance(obj, dict):
        if "$hydrus_file_path" in obj or "$hydrus_search_path" in obj:
            return True
        return any(contains_hydrus_references(value) for value in obj.values())
    if isinstance(obj, list):
        return any(contains_hydrus_references(item) for item in obj)
    if isinstance(obj, str):
        return obj.startswith("hydrus:file_id:") or obj.startswith("hydrus:hash:")
    return False


def _parse_stash_marker_token(token: str) -> Dict[str, Any]:
    # Format: stash:marker:<scene_id>:<marker_id_or_title>:<start|end>
    # Prefix a marker title with title= to disambiguate from numeric marker IDs.
    parts = token.split(":", 5)
    if len(parts) != 5:
        raise ValueError(
            "Invalid stash marker token. Expected stash:marker:<scene_id>:<marker_id_or_title>:<start|end>"
        )

    scene_id = parts[2]
    marker_ref = parts[3]
    time_value = parts[4]

    spec: Dict[str, Any] = {
        "scene_id": scene_id,
        "time": time_value,
    }
    if marker_ref.startswith("title="):
        spec["marker_title"] = marker_ref[len("title=") :]
    else:
        spec["marker_id"] = marker_ref
    return spec


def resolve_stash_references(obj: Any, stash: StashClient) -> Any:
    if isinstance(obj, dict):
        if "$stash_scene_path" in obj:
            return stash.get_scene_path(obj["$stash_scene_path"])

        if "$stash_image_path" in obj:
            return stash.get_image_path(obj["$stash_image_path"])

        if "$stash_marker_time" in obj:
            spec = obj["$stash_marker_time"]
            if not isinstance(spec, dict):
                raise ValueError("$stash_marker_time must be an object")

            default_duration = spec.get("default_duration_sec")
            return stash.resolve_marker_time(
                scene_id=spec["scene_id"],
                marker_id=spec.get("marker_id"),
                marker_title=spec.get("marker_title"),
                time_value=str(spec.get("time", "start")),
                default_duration_sec=float(default_duration) if default_duration is not None else None,
            )

        return {key: resolve_stash_references(value, stash) for key, value in obj.items()}

    if isinstance(obj, list):
        return [resolve_stash_references(item, stash) for item in obj]

    if isinstance(obj, str):
        if obj.startswith("stash:scene:"):
            scene_id = obj[len("stash:scene:") :]
            return stash.get_scene_path(scene_id)

        if obj.startswith("stash:image:"):
            image_id = obj[len("stash:image:") :]
            return stash.get_image_path(image_id)

        if obj.startswith("stash:marker:"):
            spec = _parse_stash_marker_token(obj)
            return stash.resolve_marker_time(
                scene_id=spec["scene_id"],
                marker_id=spec.get("marker_id"),
                marker_title=spec.get("marker_title"),
                time_value=str(spec.get("time", "start")),
            )

    return obj


def _coerce_hydrus_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def resolve_hydrus_references(obj: Any, hydrus: HydrusClient) -> Any:
    if isinstance(obj, dict):
        if "$hydrus_file_path" in obj:
            spec = obj["$hydrus_file_path"]
            if isinstance(spec, dict):
                return hydrus.get_media_path(
                    file_id=spec.get("file_id"),
                    hash_=spec.get("hash"),
                )
            return hydrus.get_media_path(file_id=spec)

        if "$hydrus_search_path" in obj:
            spec = obj["$hydrus_search_path"]
            if not isinstance(spec, dict):
                raise ValueError("$hydrus_search_path must be an object")

            return hydrus.search_file_path(
                tags=_coerce_hydrus_tags(spec.get("tags")),
                index=int(spec.get("index", 0)),
                file_service_keys=spec.get("file_service_keys"),
                tag_service_key=spec.get("tag_service_key"),
            )

        return {key: resolve_hydrus_references(value, hydrus) for key, value in obj.items()}

    if isinstance(obj, list):
        return [resolve_hydrus_references(item, hydrus) for item in obj]

    if isinstance(obj, str):
        if obj.startswith("hydrus:file_id:"):
            file_id = obj[len("hydrus:file_id:") :]
            return hydrus.get_media_path(file_id=file_id)

        if obj.startswith("hydrus:hash:"):
            hash_value = obj[len("hydrus:hash:") :]
            return hydrus.get_media_path(hash_=hash_value)

    return obj


def maybe_resolve_stash_references(config: Dict[str, Any]) -> Dict[str, Any]:
    if not contains_stash_references(config):
        return config

    endpoint = os.getenv("STASH_GRAPHQL_ENDPOINT") or os.getenv("STASH_URL")
    api_key = os.getenv("STASH_API_KEY")
    if not endpoint:
        raise ValueError(
            "Config contains Stash references but STASH_GRAPHQL_ENDPOINT (or STASH_URL) is not set"
        )

    stash = StashClient(endpoint=endpoint, api_key=api_key)
    return resolve_stash_references(config, stash)


def maybe_resolve_hydrus_references(config: Dict[str, Any]) -> Dict[str, Any]:
    if not contains_hydrus_references(config):
        return config

    endpoint = os.getenv("HYDRUS_API_URL") or os.getenv("HYDRUS_URL")
    access_key = os.getenv("HYDRUS_ACCESS_KEY") or os.getenv("HYDRUS_API_KEY")

    hydrus = HydrusClient(endpoint=endpoint, access_key=access_key)
    return resolve_hydrus_references(config, hydrus)


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
            # Preview outputs are written as output_path with a .png extension.
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
    removed = 0
    keep_resolved = str(keep_path.resolve()) if keep_path is not None else None

    for path in sorted(paths, key=lambda p: str(p)):
        try:
            if keep_resolved is not None and str(path.resolve()) == keep_resolved:
                continue
            if path.exists() and path.is_file():
                path.unlink()
                removed += 1
        except Exception as exc:
            if logger:
                logger.warning("cleanup failed for %s: %s", path, exc)

    return removed


def execute_config(
    config: Dict[str, Any],
    engine: MemeEngine,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> str:
    if "pipeline" in config:
        logger.info("Running pipeline with %s steps", len(config["pipeline"]))
        last_output = ""
        for index, step in enumerate(config["pipeline"]):
            logger.info("Executing step %s: %s", index, step.get("operation"))
            last_output = execute_step(
                engine,
                step,
                last_output=last_output,
                preview_only_override=(True if args.preview_only else None),
                default_font_path=config.get("font_path"),
            )
            logger.info("Step %s output: %s", index, last_output)
        return last_output

    logger.info("Running single operation: %s", config.get("operation"))
    output = execute_step(
        engine,
        config,
        preview_only_override=(True if args.preview_only else None),
        default_font_path=config.get("font_path"),
    )
    logger.info("Operation output: %s", output)
    return output


def run_config_file(
    config_path: Path,
    config: Dict[str, Any],
    project_root: Path,
    args: argparse.Namespace,
    logger: Optional[logging.Logger] = None,
) -> bool:
    effective_logger = logger or setup_logging(project_root / "logs")
    engine = MemeEngine(base_dir=str(project_root), logger=effective_logger)

    generated_files = collect_generated_file_paths(config) if args.release else set()
    output_path = get_output_path_from_config(config)

    if output_path and output_path.exists() and output_path.stat().st_mtime > config_path.stat().st_mtime:
        if args.release:
            removed = cleanup_files(generated_files, keep_path=output_path, logger=effective_logger)
            if removed:
                print(f"Release cleanup for {config_path}: removed {removed} stale intermediates/previews")
        print(f"Skipping {config_path} (output newer than config)")
        return True

    if args.release:
        removed = cleanup_files(generated_files, keep_path=output_path, logger=effective_logger)
        if removed:
            print(f"Release pre-cleanup for {config_path}: removed {removed} stale intermediates/previews")

    print(f"Running config: {config_path}")
    try:
        run_result = execute_config(config, engine, args, effective_logger)
        if args.release and run_result:
            removed = cleanup_files(generated_files, keep_path=Path(run_result), logger=effective_logger)
            if removed:
                print(f"Release post-cleanup for {config_path}: removed {removed} intermediate/preview files")
        print(run_result)
        return True
    except Exception as exc:
        print(f"Error running {config_path}: {exc}")
        return False


def main() -> None:
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
            with cfg_file.open("r", encoding="utf-8") as fh:
                try:
                    config = json.load(fh)
                except Exception as exc:
                    print(f"Failed to load {cfg_file}: {exc}")
                    continue

            try:
                config = rewrite_media_paths(config, project_root)
                config = maybe_resolve_stash_references(config)
                config = maybe_resolve_hydrus_references(config)
            except Exception as exc:
                print(f"Error preparing {cfg_file}: {exc}")
                continue

            run_config_file(cfg_file, config, project_root, args)
        return

    # Single file mode
    with config_path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    project_root = Path(config_path).resolve().parents[2]
    try:
        config = rewrite_media_paths(config, project_root)
        config = maybe_resolve_stash_references(config)
        config = maybe_resolve_hydrus_references(config)
    except Exception as exc:
        print(f"Error preparing {config_path}: {exc}")
        sys.exit(1)

    success = run_config_file(config_path, config, project_root, args)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
