from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .base import OperationContext, OperationHandler


class AddTextSideBoxOperation(OperationHandler):
    name = "add_text_side_box"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["base_media_path", "text_data", "side", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        preview_only = bool(params.get("preview_only", False))
        if context.preview_only_override is not None:
            preview_only = context.preview_only_override

        overlay_dir = params.get("overlay_dir") or str(Path(params["output_path"]).parent)
        return engine.add_text_side_box(
            base_media_path=params["base_media_path"],
            text_data=params["text_data"],
            side=params["side"],
            output_path=params["output_path"],
            overlay_dir=overlay_dir,
            box_size_px=int(params["box_size_px"]) if params.get("box_size_px") is not None else None,
            box_size_ratio=float(params.get("box_size_ratio", 0.22)),
            background_color=params.get("background_color", "#101010"),
            text_align=params.get("text_align", "center"),
            text_vertical_align=params.get("text_vertical_align", "center"),
            text_padding=int(params.get("text_padding", 6)),
            font_size=int(params["font_size"]) if params.get("font_size") is not None else None,
            font_path=params.get("font_path") or context.default_font_path,
            stroke_width=int(params.get("stroke_width", 3)),
            stroke_fill=params.get("stroke_fill", "#000000"),
            shadow_enabled=bool(params.get("shadow_enabled", True)),
            output_duration_sec=float(params["output_duration_sec"]) if params.get("output_duration_sec") is not None else None,
            panel_png_name=params.get("panel_png_name"),
            preview_only=preview_only,
            line_height=float(params.get("line_height", 1.0)),
            paragraph_spacing=int(params["paragraph_spacing"]) if params.get("paragraph_spacing") is not None else None,
            paragraph_indent_px=int(params.get("paragraph_indent_px", 0)),
            auto_size=bool(params.get("auto_size", True)),
            video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
            video_preset=params.get("video_preset"),
            video_bitrate=params.get("video_bitrate"),
            audio_bitrate=params.get("audio_bitrate"),
            image_quality=int(params["image_quality"]) if params.get("image_quality") is not None else None,
            png_compress_level=int(params["png_compress_level"]) if params.get("png_compress_level") is not None else None,
            optimize=bool(params["optimize"]) if params.get("optimize") is not None else None,
        )
