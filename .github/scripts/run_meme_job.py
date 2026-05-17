import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from MemeEngine import MemeEngine


def setup_logging(logs_dir: Path) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"meme_job_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger("meme_engine")
    logger.setLevel(logging.INFO)
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


def execute_step(engine: MemeEngine, step: Dict[str, Any], last_output: str = "") -> str:
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
            video_width=int(params["video_width"]),
            video_height=int(params["video_height"]),
            output_path=params["output_path"],
            horizontal_align=params.get("horizontal_align", "center"),
            vertical_align=params.get("vertical_align", "center"),
            padding=int(params.get("padding", 24)),
            stroke_width=int(params.get("stroke_width", 3)),
            stroke_fill=params.get("stroke_fill", "#000000"),
            shadow_enabled=bool(params.get("shadow_enabled", True)),
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
    parser.add_argument("--config", required=True, help="Path to JSON config")
    args = parser.parse_args()

    config_path = Path(args.config)
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
            last_output = execute_step(engine, step, last_output=last_output)
            logger.info("Step %s output: %s", index, last_output)
        print(last_output)
        return

    logger.info("Running single operation: %s", config.get("operation"))
    output = execute_step(engine, config)
    logger.info("Operation output: %s", output)
    print(output)


if __name__ == "__main__":
    main()
