from __future__ import annotations

from typing import Any, Dict

from .base import OperationContext, OperationHandler


def _parse_time(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    raise ValueError(f"Invalid time format: {value!r}, expected MM:SS or HH:MM:SS")


class TrimVideoOperation(OperationHandler):
    name = "trim_video"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["input_path", "start_sec", "end_sec", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        preview_only = bool(params.get("preview_only", False))
        if context.preview_only_override is not None:
            preview_only = context.preview_only_override

        return engine.trim_video(
            input_path=params["input_path"],
            start_sec=_parse_time(params["start_sec"]),
            end_sec=_parse_time(params["end_sec"]),
            output_path=params["output_path"],
            boomerang=bool(params.get("boomerang", False)),
            preview_only=preview_only,
            video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
            video_preset=params.get("video_preset"),
            video_bitrate=params.get("video_bitrate"),
            audio_bitrate=params.get("audio_bitrate"),
        )
