from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

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

        if params.get("text") is None and params.get("text_structured") is None:
            raise ValueError("apply_text_overlay requires text or text_structured")

        resolved_width = int(params["width"]) if params.get("width") is not None else None
        resolved_height = int(params["height"]) if params.get("height") is not None else None

        if not bool(params.get("match_base_size", True)) and resolved_height is None:
            media_info = engine.get_media_info(params["input_path"])
            overlay_width = resolved_width or int(media_info["width"])
            overlay_height = max(1, int(round(int(media_info["height"]) * 0.25)))
            text_data = params.get("text")
            if text_data is None and params.get("text_structured") is not None:
                text_data = "".join(part.get("text", "") for part in params["text_structured"])
            if text_data:
                _renderer = engine._get_renderer(params.get("font_path") or context.default_font_path)
                tokens = _renderer.parse_tokens(text_data)
                font_size = int(params["font_size"]) if params.get("font_size") is not None else None
                if font_size is not None:
                    for token in tokens:
                        token.setdefault("size", int(font_size))
                _, metrics = _renderer.generate_canvas(
                    tokens,
                    overlay_width,
                    overlay_height,
                    horizontal_align=str(params.get("text_align", "center")),
                    vertical_align=str(params.get("text_vertical_align", "center")),
                    padding=int(params.get("text_padding", 6)),
                    stroke_width=int(params.get("stroke_width", 3)),
                    stroke_fill=params.get("stroke_fill", "#000000"),
                    shadow_enabled=bool(params.get("shadow_enabled", True)),
                    background_fill=params.get("background_color", "transparent"),
                    line_height=float(params.get("line_height", 1.0)),
                    paragraph_spacing=int(params["paragraph_spacing"]) if params.get("paragraph_spacing") is not None else None,
                    paragraph_indent_px=int(params.get("paragraph_indent_px", 0)),
                    return_metrics=True,
                )
                required_height = int(metrics.get("text_total_height", 0)) + (int(params.get("text_padding", 6)) * 2)
                resolved_height = max(overlay_height, required_height)

        overlay_item: Dict[str, Any] = {
            "start_time": float(params.get("start_time", 0.0)),
            "position": params.get("position", ["center", "top"]),
            "match_base_size": bool(params.get("match_base_size", True)),
            "text_align": str(params.get("text_align", "center")),
            "text_vertical_align": str(params.get("text_vertical_align", "center")),
            "text_padding": int(params.get("text_padding", 6)),
            "stroke_width": int(params.get("stroke_width", 3)),
            "stroke_fill": params.get("stroke_fill", "#000000"),
            "shadow_enabled": bool(params.get("shadow_enabled", True)),
            "background_color": params.get("background_color", "transparent"),
            "line_height": float(params.get("line_height", 1.0)),
            "paragraph_indent_px": int(params.get("paragraph_indent_px", 0)),
        }

        if params.get("text") is not None:
            overlay_item["text"] = params["text"]
        if params.get("text_structured") is not None:
            overlay_item["text_structured"] = params["text_structured"]
        if params.get("end_time") is not None:
            overlay_item["end_time"] = float(params["end_time"])
        if resolved_width is not None:
            overlay_item["width"] = resolved_width
        if resolved_height is not None:
            overlay_item["height"] = resolved_height
        if params.get("font_size") is not None:
            overlay_item["font_size"] = int(params["font_size"])
        if params.get("paragraph_spacing") is not None:
            overlay_item["paragraph_spacing"] = int(params["paragraph_spacing"])
        if params.get("overlay_name"):
            overlay_item["overlay_name"] = params["overlay_name"]

        overlay_dir = params.get("overlay_dir") or str(Path(params["output_path"]).parent)
        return engine.apply_multi_text_overlays(
            base_media_path=params["input_path"],
            overlays=[overlay_item],
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
