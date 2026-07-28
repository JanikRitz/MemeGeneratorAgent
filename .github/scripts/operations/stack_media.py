from __future__ import annotations

from typing import Any, Dict

from .base import OperationContext, OperationHandler


class StackMediaOperation(OperationHandler):
    name = "stack_media"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["path1", "path2", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        return engine._stack_media_impl(
            path1=params["path1"],
            path2=params["path2"],
            output_path=params["output_path"],
            orientation=params.get("orientation", "horizontal"),
            duration_sec=float(params.get("duration_sec", 3.0)),
            video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
            video_preset=params.get("video_preset"),
            video_bitrate=params.get("video_bitrate"),
            audio_bitrate=params.get("audio_bitrate"),
        )
