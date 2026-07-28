from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .base import OperationContext, OperationHandler


class ApplyMultiTextOverlaysOperation(OperationHandler):
    name = "apply_multi_text_overlays"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["base_media_path", "overlays", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        preview_only = bool(params.get("preview_only", False))
        if context.preview_only_override is not None:
            preview_only = context.preview_only_override

        overlay_dir = params.get("overlay_dir") or str(Path(params["output_path"]).parent)
        return engine.apply_multi_text_overlays(
            base_media_path=params["base_media_path"],
            overlays=params["overlays"],
            output_path=params["output_path"],
            overlay_dir=overlay_dir,
            output_duration_sec=params.get("output_duration_sec"),
            font_path=params.get("font_path") or context.default_font_path,
            preview_only=preview_only,
            video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
            video_preset=params.get("video_preset"),
            video_bitrate=params.get("video_bitrate"),
            audio_bitrate=params.get("audio_bitrate"),
        )
