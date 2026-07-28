from __future__ import annotations

from typing import Any, Dict

from .base import OperationContext, OperationHandler


class CropMediaOperation(OperationHandler):
    name = "crop_media"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["input_path", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        preview_only = bool(params.get("preview_only", False))
        if context.preview_only_override is not None:
            preview_only = context.preview_only_override

        return engine.crop_media(
            input_path=params["input_path"],
            output_path=params["output_path"],
            left_px=int(params["left_px"]) if params.get("left_px") is not None else 0,
            right_px=int(params["right_px"]) if params.get("right_px") is not None else 0,
            top_px=int(params["top_px"]) if params.get("top_px") is not None else 0,
            bottom_px=int(params["bottom_px"]) if params.get("bottom_px") is not None else 0,
            preview_only=preview_only,
            video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
            video_preset=params.get("video_preset"),
            video_bitrate=params.get("video_bitrate"),
            audio_bitrate=params.get("audio_bitrate"),
        )
