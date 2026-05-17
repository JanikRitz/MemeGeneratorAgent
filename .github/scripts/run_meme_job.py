import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from MemeEngine import MemeEngine

try:
    from stash_client import StashClient
except ImportError:
    from .stash_client import StashClient


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


def execute_step(
    engine: MemeEngine,
    step: Dict[str, Any],
    last_output: str = "",
    preview_only_override: Optional[bool] = None,
) -> str:
    operation = step.get("operation")
    params = step.get("params", {})
    if last_output:
        params = _replace_last_output(params, last_output)

    video_quality_kwargs = {
        "video_crf": int(params["video_crf"]) if params.get("video_crf") is not None else None,
        "video_preset": params.get("video_preset"),
        "video_bitrate": params.get("video_bitrate"),
        "audio_bitrate": params.get("audio_bitrate"),
    }
    image_quality_kwargs = {
        "image_quality": int(params["image_quality"]) if params.get("image_quality") is not None else None,
        "png_compress_level": int(params["png_compress_level"]) if params.get("png_compress_level") is not None else None,
        "optimize": bool(params["optimize"]) if params.get("optimize") is not None else None,
    }

    if operation == "trim_video":
        return engine.trim_video(
            input_path=params["input_path"],
            start_sec=float(params["start_sec"]),
            end_sec=float(params["end_sec"]),
            output_path=params["output_path"],
            **video_quality_kwargs,
        )

    if operation == "scale_media":
        return engine.scale_media(
            input_path=params["input_path"],
            output_path=params["output_path"],
            max_long_side=int(params["max_long_side"]) if params.get("max_long_side") is not None else None,
            max_short_side=int(params["max_short_side"]) if params.get("max_short_side") is not None else None,
            upscale=bool(params.get("upscale", False)),
            **video_quality_kwargs,
            **image_quality_kwargs,
        )

    if operation == "stack_media":
        return engine.stack_media(
            path1=params["path1"],
            path2=params["path2"],
            output_path=params["output_path"],
            orientation=params.get("orientation", "horizontal"),
            duration_sec=float(params.get("duration_sec", 3.0)),
            **video_quality_kwargs,
        )

    if operation == "concatenate_clips":
        return engine.concatenate_clips(
            clip_paths=params["clip_paths"],
            output_path=params["output_path"],
            **video_quality_kwargs,
        )

    if operation == "generate_text_overlay":
        return engine.generate_text_overlay(
            text_data=params["text_data"],
            video_width=int(params["video_width"]) if params.get("video_width") is not None else None,
            video_height=int(params["video_height"]) if params.get("video_height") is not None else None,
            output_path=params["output_path"],
            media_path=params.get("media_path"),
            horizontal_align=params.get("horizontal_align", "center"),
            vertical_align=params.get("vertical_align", "center"),
            padding=int(params.get("padding", 24)),
            stroke_width=int(params.get("stroke_width", 3)),
            stroke_fill=params.get("stroke_fill", "#000000"),
            shadow_enabled=bool(params.get("shadow_enabled", True)),
            font_size=int(params["font_size"]) if params.get("font_size") is not None else None,
            background_color=params.get("background_color", "transparent"),
            line_height=float(params.get("line_height", 1.0)),
            paragraph_spacing=int(params["paragraph_spacing"]) if params.get("paragraph_spacing") is not None else None,
            paragraph_indent_px=int(params.get("paragraph_indent_px", 0)),
            compose_on_media=bool(params.get("compose_on_media", False)),
            **image_quality_kwargs,
        )

    if operation == "add_text_side_box":
        preview_only = bool(params.get("preview_only", False))
        if preview_only_override is not None:
            preview_only = preview_only_override

        overlay_dir = params.get("overlay_dir") or str(Path(params["output_path"]).parent)
        return engine.add_text_side_box(
            base_media_path=params["base_media_path"],
            text_data=params["text_data"],
            side=params["side"],
            output_path=params["output_path"],
            overlay_dir=overlay_dir,
            box_size_px=int(params["box_size_px"]) if params.get("box_size_px") is not None else None,
            box_size_ratio=float(params.get("box_size_ratio", 0.22)),
            background_color=params.get("background_color", "#101010"),
            text_align=params.get("text_align", "center"),
            text_vertical_align=params.get("text_vertical_align", "center"),
            text_padding=int(params.get("text_padding", 24)),
            font_size=int(params["font_size"]) if params.get("font_size") is not None else None,
            stroke_width=int(params.get("stroke_width", 3)),
            stroke_fill=params.get("stroke_fill", "#000000"),
            shadow_enabled=bool(params.get("shadow_enabled", True)),
            output_duration_sec=float(params["output_duration_sec"]) if params.get("output_duration_sec") is not None else None,
            panel_png_name=params.get("panel_png_name"),
            preview_only=preview_only,
            line_height=float(params.get("line_height", 1.0)),
            paragraph_spacing=int(params["paragraph_spacing"]) if params.get("paragraph_spacing") is not None else None,
            paragraph_indent_px=int(params.get("paragraph_indent_px", 0)),
            auto_size=bool(params.get("auto_size", True)),
            **video_quality_kwargs,
            **image_quality_kwargs,
        )

    if operation == "apply_multi_text_overlays":
        overlay_dir = params.get("overlay_dir") or str(Path(params["output_path"]).parent)
        return engine.apply_multi_text_overlays(
            base_media_path=params["base_media_path"],
            overlays=params["overlays"],
            output_path=params["output_path"],
            overlay_dir=overlay_dir,
            output_duration_sec=params.get("output_duration_sec"),
            **video_quality_kwargs,
        )

    raise ValueError(f"Unsupported operation: {operation}")


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
        if "$stash_scene_path" in obj or "$stash_marker_time" in obj:
            return True
        return any(contains_stash_references(value) for value in obj.values())
    if isinstance(obj, list):
        return any(contains_stash_references(item) for item in obj)
    if isinstance(obj, str):
        return obj.startswith("stash:scene:") or obj.startswith("stash:marker:")
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

        if obj.startswith("stash:marker:"):
            spec = _parse_stash_marker_token(obj)
            return stash.resolve_marker_time(
                scene_id=spec["scene_id"],
                marker_id=spec.get("marker_id"),
                marker_title=spec.get("marker_title"),
                time_value=str(spec.get("time", "start")),
            )

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MemeEngine jobs from a JSON config file.")
    parser.add_argument("config_path", nargs="?", help="Path to JSON config (positional)")
    parser.add_argument("--config", help="Path to JSON config")
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Force preview-only mode for add_text_side_box operations, overriding config",
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
                except Exception as e:
                    print(f"Failed to load {cfg_file}: {e}")
                    continue

            config = rewrite_media_paths(config, project_root)
            config = maybe_resolve_stash_references(config)

            output_path = get_output_path_from_config(config)
            if output_path and output_path.exists():
                if output_path.stat().st_mtime > cfg_file.stat().st_mtime:
                    print(f"Skipping {cfg_file} (output newer than config)")
                    continue

            logger = setup_logging(project_root / "logs")
            engine = MemeEngine(base_dir=str(project_root), logger=logger)

            print(f"Running config: {cfg_file}")
            try:
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
                        )
                        logger.info("Step %s output: %s", index, last_output)
                    print(last_output)
                else:
                    logger.info("Running single operation: %s", config.get("operation"))
                    output = execute_step(
                        engine,
                        config,
                        preview_only_override=(True if args.preview_only else None),
                    )
                    logger.info("Operation output: %s", output)
                    print(output)
            except Exception as e:
                print(f"Error running {cfg_file}: {e}")
        return

    # Single file mode (original logic)
    with config_path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    project_root = Path(config_path).resolve().parents[2]

    config = rewrite_media_paths(config, project_root)
    config = maybe_resolve_stash_references(config)

    logger = setup_logging(project_root / "logs")
    engine = MemeEngine(base_dir=str(project_root), logger=logger)

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
            )
            logger.info("Step %s output: %s", index, last_output)
        print(last_output)
        return

    logger.info("Running single operation: %s", config.get("operation"))
    output = execute_step(
        engine,
        config,
        preview_only_override=(True if args.preview_only else None),
    )
    logger.info("Operation output: %s", output)
    print(output)


if __name__ == "__main__":
    main()
