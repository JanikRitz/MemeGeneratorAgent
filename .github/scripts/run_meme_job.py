import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from MemeEngine import MemeEngine


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

    if operation == "trim_video":
        return engine.trim_video(
            input_path=params["input_path"],
            start_sec=float(params["start_sec"]),
            end_sec=float(params["end_sec"]),
            output_path=params["output_path"],
        )

    if operation == "stack_media":
        return engine.stack_media(
            path1=params["path1"],
            path2=params["path2"],
            output_path=params["output_path"],
            orientation=params.get("orientation", "horizontal"),
            duration_sec=float(params.get("duration_sec", 3.0)),
        )

    if operation == "concatenate_clips":
        return engine.concatenate_clips(
            clip_paths=params["clip_paths"],
            output_path=params["output_path"],
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
        )

    if operation == "add_text_side_box":
        preview_only = bool(params.get("preview_only", False))
        if preview_only_override is not None:
            preview_only = preview_only_override

        return engine.add_text_side_box(
            base_media_path=params["base_media_path"],
            text_data=params["text_data"],
            side=params["side"],
            output_path=params["output_path"],
            overlay_dir=params.get("overlay_dir", "render"),
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
        )

    if operation == "apply_multi_text_overlays":
        return engine.apply_multi_text_overlays(
            base_media_path=params["base_media_path"],
            overlays=params["overlays"],
            output_path=params["output_path"],
            overlay_dir=params.get("overlay_dir", "render"),
            output_duration_sec=params.get("output_duration_sec"),
        )

    raise ValueError(f"Unsupported operation: {operation}")


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
    with config_path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    project_root = Path(config_path).resolve().parents[1]
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
