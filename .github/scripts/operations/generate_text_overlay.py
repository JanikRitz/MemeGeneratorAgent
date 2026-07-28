from __future__ import annotations

from typing import Any, Dict, Optional

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

        video_width = int(params["video_width"]) if params.get("video_width") is not None else None
        video_height = int(params["video_height"]) if params.get("video_height") is not None else None
        if params.get("media_path"):
            media_info = engine.get_media_info(params["media_path"])
            if not video_width:
                video_width = int(media_info["width"])
            if not video_height:
                video_height = int(media_info["height"])

        if not video_width or not video_height:
            raise ValueError("video_width and video_height are required when media_path is not provided")

        out_p = engine.resolve_output_path(params["output_path"])
        engine.logger.info("generate_text_overlay output=%s width=%s height=%s media_path=%s", out_p, video_width, video_height, params.get("media_path"))
        renderer = engine._get_renderer(params.get("font_path") or context.default_font_path)
        tokens = renderer.parse_tokens(params["text_data"])
        font_size = int(params["font_size"]) if params.get("font_size") is not None else None
        if font_size:
            for token in tokens:
                token.setdefault("size", int(font_size))

        canvas, metrics = renderer.generate_canvas(
            tokens,
            video_width,
            video_height,
            horizontal_align=params.get("horizontal_align", "center"),
            vertical_align=params.get("vertical_align", "center"),
            padding=int(params.get("padding", 6)),
            stroke_width=int(params.get("stroke_width", 3)),
            stroke_fill=params.get("stroke_fill", "#000000"),
            shadow_enabled=bool(params.get("shadow_enabled", True)),
            background_fill=params.get("background_color", "transparent"),
            line_height=float(params.get("line_height", 1.0)),
            paragraph_spacing=int(params["paragraph_spacing"]) if params.get("paragraph_spacing") is not None else None,
            paragraph_indent_px=int(params.get("paragraph_indent_px", 0)),
            return_metrics=True,
        )
        if bool(params.get("compose_on_media", False)):
            media_path = params.get("media_path")
            if not media_path:
                raise ValueError("compose_on_media requires media_path")
            base_path = engine.resolve_path(media_path)
            if engine._is_video(base_path):
                raise ValueError("compose_on_media only supports image media_path values")
            with open(str(base_path), "rb") as handle:
                pass
            from PIL import Image

            with Image.open(str(base_path)).convert("RGBA") as base_img:
                if base_img.size != (int(video_width), int(video_height)):
                    base_img = base_img.resize((int(video_width), int(video_height)))
                composed = base_img.copy()
                composed.alpha_composite(canvas.convert("RGBA"))
                engine._save_image(
                    composed,
                    out_p,
                    image_quality=int(params["image_quality"]) if params.get("image_quality") is not None else None,
                    png_compress_level=int(params["png_compress_level"]) if params.get("png_compress_level") is not None else None,
                    optimize=bool(params["optimize"]) if params.get("optimize") is not None else None,
                )
        else:
            engine._save_image(
                canvas,
                out_p,
                image_quality=int(params["image_quality"]) if params.get("image_quality") is not None else None,
                png_compress_level=int(params["png_compress_level"]) if params.get("png_compress_level") is not None else None,
                optimize=bool(params["optimize"]) if params.get("optimize") is not None else None,
            )

        if metrics.get("overflowed"):
            engine.logger.warning(
                "generate_text_overlay truncated text: output=%s rendered_lines=%s total_lines=%s truncated_lines=%s",
                out_p,
                metrics.get("rendered_lines"),
                metrics.get("total_lines"),
                metrics.get("truncated_lines"),
            )
        return str(out_p)
