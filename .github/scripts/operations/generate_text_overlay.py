from __future__ import annotations

from typing import Any, Dict

from .base import OperationContext, OperationHandler


class GenerateTextOverlayOperation(OperationHandler):
    name = "generate_text_overlay"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["text_data", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        return engine.generate_text_overlay(
            text_data=params["text_data"],
            video_width=int(params["video_width"]) if params.get("video_width") is not None else None,
            video_height=int(params["video_height"]) if params.get("video_height") is not None else None,
            output_path=params["output_path"],
            media_path=params.get("media_path"),
            horizontal_align=params.get("horizontal_align", "center"),
            vertical_align=params.get("vertical_align", "center"),
            padding=int(params.get("padding", 6)),
            stroke_width=int(params.get("stroke_width", 3)),
            stroke_fill=params.get("stroke_fill", "#000000"),
            shadow_enabled=bool(params.get("shadow_enabled", True)),
            font_size=int(params["font_size"]) if params.get("font_size") is not None else None,
            background_color=params.get("background_color", "transparent"),
            line_height=float(params.get("line_height", 1.0)),
            paragraph_spacing=int(params["paragraph_spacing"]) if params.get("paragraph_spacing") is not None else None,
            paragraph_indent_px=int(params.get("paragraph_indent_px", 0)),
            compose_on_media=bool(params.get("compose_on_media", False)),
            font_path=params.get("font_path") or context.default_font_path,
            image_quality=int(params["image_quality"]) if params.get("image_quality") is not None else None,
            png_compress_level=int(params["png_compress_level"]) if params.get("png_compress_level") is not None else None,
            optimize=bool(params["optimize"]) if params.get("optimize") is not None else None,
        )
