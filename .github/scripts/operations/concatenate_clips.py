from __future__ import annotations

from typing import Any, Dict

from .base import OperationContext, OperationHandler


class ConcatenateClipsOperation(OperationHandler):
    name = "concatenate_clips"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["clip_paths", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        preview_only = bool(params.get("preview_only", False))
        if context.preview_only_override is not None:
            preview_only = context.preview_only_override

        return engine.concatenate_clips(
            clip_paths=params["clip_paths"],
            output_path=params["output_path"],
            preview_only=preview_only,
            video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
            video_preset=params.get("video_preset"),
            video_bitrate=params.get("video_bitrate"),
            audio_bitrate=params.get("audio_bitrate"),
        )
