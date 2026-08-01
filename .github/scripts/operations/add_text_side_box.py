from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from PIL import Image

try:
    from moviepy.editor import CompositeVideoClip, ImageClip, VideoFileClip
except ImportError:
    from moviepy import CompositeVideoClip, ImageClip, VideoFileClip

from .base import OperationContext, OperationHandler
from .registry import register_operation


@register_operation
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

        base_path = engine.resolve_path(params["base_media_path"])
        out_p = engine.resolve_output_path(params["output_path"])
        overlay_root = engine.resolve_output_path(params.get("overlay_dir") or str(Path(params["output_path"]).parent))
        overlay_root.mkdir(parents=True, exist_ok=True)

        side_value = str(params["side"]).lower()
        if side_value not in {"top", "bottom", "left", "right"}:
            raise ValueError("side must be one of: top, bottom, left, right")

        media_is_video = engine._is_video(base_path)
        if preview_only:
            media_info = engine.get_media_info(params["base_media_path"])
            base_w = int(media_info["width"])
            base_h = int(media_info["height"])
            base_clip = None
            duration = float(params.get("output_duration_sec") or media_info.get("duration_sec") or 5.0)
        elif media_is_video:
            base_clip = VideoFileClip(str(base_path))
            duration = float(base_clip.duration)
            base_w = int(base_clip.w)
            base_h = int(base_clip.h)
        else:
            duration = float(params.get("output_duration_sec") or 5.0)
            base_clip = engine._clip_with_duration(ImageClip(str(base_path)), duration)
            base_w = int(base_clip.w)
            base_h = int(base_clip.h)

        renderer = engine._get_renderer(params.get("font_path") or context.default_font_path)
        tokens = renderer.parse_tokens(params["text_data"])
        font_size = int(params["font_size"]) if params.get("font_size") is not None else None
        if font_size:
            for token in tokens:
                token.setdefault("size", int(font_size))

        def _measure_panel(width: int, height: int) -> Dict[str, Any]:
            _, metrics = renderer.generate_canvas(
                tokens,
                max(1, int(width)),
                max(1, int(height)),
                horizontal_align=params.get("text_align", "center"),
                vertical_align=params.get("text_vertical_align", "center"),
                padding=int(params.get("text_padding", 6)),
                stroke_width=int(params.get("stroke_width", 3)),
                stroke_fill=params.get("stroke_fill", "#000000"),
                shadow_enabled=bool(params.get("shadow_enabled", True)),
                background_fill=params.get("background_color", "#101010"),
                line_height=float(params.get("line_height", 1.0)),
                paragraph_spacing=int(params["paragraph_spacing"]) if params.get("paragraph_spacing") is not None else None,
                paragraph_indent_px=int(params.get("paragraph_indent_px", 0)),
                return_metrics=True,
            )
            return metrics

        if side_value in {"top", "bottom"}:
            min_panel_size = int(round(base_h * float(params.get("box_size_ratio", 0.22))))
            panel_size = int(params["box_size_px"] if params.get("box_size_px") is not None else min_panel_size)
            if params.get("box_size_px") is None and bool(params.get("auto_size", True)):
                measured = _measure_panel(base_w, panel_size)
                required = int(measured.get("text_total_height", 0)) + (int(params.get("text_padding", 6)) * 2)
                panel_size = max(panel_size, required)
            panel_w, panel_h = base_w, max(1, panel_size)
            final_w, final_h = base_w, base_h + panel_h
            base_position = (0, panel_h) if side_value == "top" else (0, 0)
            panel_position = (0, 0) if side_value == "top" else (0, base_h)
        else:
            min_panel_size = int(round(base_w * float(params.get("box_size_ratio", 0.22))))
            panel_size = int(params["box_size_px"] if params.get("box_size_px") is not None else min_panel_size)
            if params.get("box_size_px") is None and bool(params.get("auto_size", True)):
                max_panel_width = max(panel_size, int(base_w * 3.0))
                if _measure_panel(panel_size, base_h).get("overflowed"):
                    low = panel_size
                    high = panel_size
                    while high < max_panel_width and _measure_panel(high, base_h).get("overflowed"):
                        low = high
                        high = min(max_panel_width, high * 2)
                    if _measure_panel(high, base_h).get("overflowed"):
                        panel_size = high
                    else:
                        left = low + 1
                        right = high
                        best = high
                        while left <= right:
                            mid = (left + right) // 2
                            if _measure_panel(mid, base_h).get("overflowed"):
                                left = mid + 1
                            else:
                                best = mid
                                right = mid - 1
                        panel_size = best
            panel_w, panel_h = max(1, panel_size), base_h
            final_w, final_h = base_w + panel_w, base_h
            base_position = (panel_w, 0) if side_value == "left" else (0, 0)
            panel_position = (0, 0) if side_value == "left" else (base_w, 0)

        panel_canvas, metrics = renderer.generate_canvas(
            tokens,
            panel_w,
            panel_h,
            horizontal_align=params.get("text_align", "center"),
            vertical_align=params.get("text_vertical_align", "center"),
            padding=int(params.get("text_padding", 6)),
            stroke_width=int(params.get("stroke_width", 3)),
            stroke_fill=params.get("stroke_fill", "#000000"),
            shadow_enabled=bool(params.get("shadow_enabled", True)),
            background_fill=params.get("background_color", "#101010"),
            line_height=float(params.get("line_height", 1.0)),
            paragraph_spacing=int(params["paragraph_spacing"]) if params.get("paragraph_spacing") is not None else None,
            paragraph_indent_px=int(params.get("paragraph_indent_px", 0)),
            return_metrics=True,
        )

        png_name = (params.get("panel_png_name") or f"side_box_{side_value}") + ".png"
        panel_png_path = overlay_root / png_name
        panel_canvas.save(str(panel_png_path), format="PNG")

        if metrics.get("overflowed"):
            engine.logger.warning(
                "add_text_side_box truncated text: panel_png=%s rendered_lines=%s total_lines=%s truncated_lines=%s",
                panel_png_path,
                metrics.get("rendered_lines"),
                metrics.get("total_lines"),
                metrics.get("truncated_lines"),
            )

        if preview_only:
            if media_is_video:
                with VideoFileClip(str(base_path)) as clip:
                    frame = clip.get_frame(0)
                base_img = Image.fromarray(frame).convert("RGBA")
            else:
                base_img = Image.open(str(base_path)).convert("RGBA")
            if base_img.size != (base_w, base_h):
                base_img = base_img.resize((base_w, base_h), Image.Resampling.LANCZOS)
            composed_preview = Image.new("RGBA", (final_w, final_h), (0, 0, 0, 0))
            composed_preview.paste(base_img, base_position)
            composed_preview.paste(panel_canvas.convert("RGBA"), panel_position)
            preview_path = out_p.with_suffix(".png")
            engine._save_image(
                composed_preview,
                preview_path,
                image_quality=int(params["image_quality"]) if params.get("image_quality") is not None else None,
                png_compress_level=int(params["png_compress_level"]) if params.get("png_compress_level") is not None else None,
                optimize=bool(params["optimize"]) if params.get("optimize") is not None else None,
            )
            engine.logger.info("add_text_side_box preview_only enabled, skipping video render and returning composed preview=%s", preview_path)
            return str(preview_path)

        image_output_exts = {".png", ".jpg", ".jpeg", ".webp"}
        if (not media_is_video) and out_p.suffix.lower() in image_output_exts:
            with Image.open(str(base_path)).convert("RGBA") as base_img:
                if base_img.size != (base_w, base_h):
                    base_img = base_img.resize((base_w, base_h))
                final_image = Image.new("RGBA", (final_w, final_h), (0, 0, 0, 0))
                final_image.paste(base_img, base_position)
                final_image.paste(panel_canvas.convert("RGBA"), panel_position)
                engine._save_image(
                    final_image,
                    out_p,
                    image_quality=int(params["image_quality"]) if params.get("image_quality") is not None else None,
                    png_compress_level=int(params["png_compress_level"]) if params.get("png_compress_level") is not None else None,
                    optimize=bool(params["optimize"]) if params.get("optimize") is not None else None,
                )
            return str(out_p)

        base_layer = engine._clip_with_position(base_clip, base_position)
        panel_layer = engine._clip_with_position(engine._clip_with_duration(ImageClip(str(panel_png_path)), duration), panel_position)
        composite = CompositeVideoClip([base_layer, panel_layer], size=(final_w, final_h))
        composite = engine._clip_with_audio(composite, getattr(base_clip, "audio", None))
        engine.logger.info("add_text_side_box base=%s side=%s panel=%sx%s final=%sx%s auto_size=%s output=%s panel_png=%s", base_path, side_value, panel_w, panel_h, final_w, final_h, bool(params.get("auto_size", True)), out_p, panel_png_path)
        fps = 24.0 if not media_is_video else float(getattr(base_clip, "fps", 24) or 24)
        engine._write_video(
            composite,
            out_p,
            fps=fps,
            video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
            video_preset=params.get("video_preset"),
            video_bitrate=params.get("video_bitrate"),
            audio_bitrate=params.get("audio_bitrate"),
        )
        return str(out_p)
