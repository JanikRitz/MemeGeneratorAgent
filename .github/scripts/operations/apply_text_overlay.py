from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .base import OperationContext, OperationHandler


class ApplyTextOverlayOperation(OperationHandler):
    name = "apply_text_overlay"

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

        overlay_dir = params.get("overlay_dir") or str(Path(params["output_path"]).parent)
        return engine.apply_text_overlay(
            input_path=params["input_path"],
            output_path=params["output_path"],
            text=params.get("text"),
            text_structured=params.get("text_structured"),
            overlay_dir=overlay_dir,
            start_time=float(params.get("start_time", 0.0)),
            end_time=float(params["end_time"]) if params.get("end_time") is not None else None,
            position=params.get("position", ["center", "top"]),
            width=int(params["width"]) if params.get("width") is not None else None,
            height=int(params["height"]) if params.get("height") is not None else None,
            match_base_size=bool(params.get("match_base_size", True)),
            text_align=params.get("text_align", "center"),
            text_vertical_align=params.get("text_vertical_align", "center"),
            text_padding=int(params.get("text_padding", 6)),
            font_size=int(params["font_size"]) if params.get("font_size") is not None else None,
            font_path=params.get("font_path") or context.default_font_path,
            stroke_width=int(params.get("stroke_width", 3)),
            stroke_fill=params.get("stroke_fill", "#000000"),
            shadow_enabled=bool(params.get("shadow_enabled", True)),
            background_color=params.get("background_color", "transparent"),
            line_height=float(params.get("line_height", 1.0)),
            paragraph_spacing=int(params["paragraph_spacing"]) if params.get("paragraph_spacing") is not None else None,
            paragraph_indent_px=int(params.get("paragraph_indent_px", 0)),
            overlay_name=params.get("overlay_name"),
            output_duration_sec=float(params["output_duration_sec"]) if params.get("output_duration_sec") is not None else None,
            preview_only=preview_only,
            video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
            video_preset=params.get("video_preset"),
            video_bitrate=params.get("video_bitrate"),
            audio_bitrate=params.get("audio_bitrate"),
        )
