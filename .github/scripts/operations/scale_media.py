from __future__ import annotations

from typing import Any, Dict

from .base import OperationContext, OperationHandler


class ScaleMediaOperation(OperationHandler):
    name = "scale_media"

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

        input_path = str(engine.resolve_path(params["input_path"]))
        engine.logger.info("scale_media resolved input_path=%s", input_path)

        return engine.scale_media(
            input_path=input_path,
            output_path=params["output_path"],
            max_long_side=int(params["max_long_side"]) if params.get("max_long_side") is not None else None,
            max_short_side=int(params["max_short_side"]) if params.get("max_short_side") is not None else None,
            upscale=bool(params.get("upscale", False)),
            preview_only=preview_only,
            video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
            video_preset=params.get("video_preset"),
            video_bitrate=params.get("video_bitrate"),
            audio_bitrate=params.get("audio_bitrate"),
            image_quality=int(params["image_quality"]) if params.get("image_quality") is not None else None,
            png_compress_level=int(params["png_compress_level"]) if params.get("png_compress_level") is not None else None,
            optimize=bool(params["optimize"]) if params.get("optimize") is not None else None,
        )
