from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

try:
    from moviepy.editor import CompositeVideoClip, ImageClip, VideoFileClip
except ImportError:
    from moviepy import CompositeVideoClip, ImageClip, VideoFileClip

from .base import OperationContext, OperationHandler
from .registry import register_operation


@register_operation
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

        base_path = engine.resolve_path(params["base_media_path"])
        out_p = engine.resolve_output_path(params["output_path"])
        engine.logger.info("apply_multi_text_overlays base=%s overlay_count=%s output=%s", base_path, len(params["overlays"]), out_p)

        media_is_video = engine._is_video(base_path)
        overlay_dir = params.get("overlay_dir") or str(Path(params["output_path"]).parent)

        if preview_only:
            if media_is_video:
                with VideoFileClip(str(base_path)) as clip:
                    frame = clip.get_frame(0)
                composite_img = Image.fromarray(frame).convert("RGBA")
            else:
                composite_img = Image.open(str(base_path)).convert("RGBA")
            base_w, base_h = composite_img.size
            for index, item in enumerate(params["overlays"]):
                text_data = item.get("text")
                if not text_data and item.get("text_structured"):
                    text_data = "".join(part.get("text", "") for part in item["text_structured"])
                if not text_data:
                    engine.logger.warning("overlay index=%s skipped due to empty text", index)
                    continue
                width = int(item.get("width", base_w))
                height = int(item.get("height", int(base_h * 0.25)))
                position = engine._normalize_position(item.get("position", ["center", "top"]))
                if bool(item.get("match_base_size", True)):
                    width = int(base_w)
                    height = int(base_h)
                    position = (0, 0)
                text_align = str(item.get("text_align", "center")).lower()
                text_vertical_align = str(item.get("text_vertical_align", "center")).lower()
                text_padding = int(item.get("text_padding", 6))
                stroke_width = int(item.get("stroke_width", 3))
                stroke_fill = item.get("stroke_fill", "#000000")
                shadow_enabled = bool(item.get("shadow_enabled", True))
                item_renderer = engine._get_renderer(item.get("font_path") or params.get("font_path") or context.default_font_path)
                font_size = int(item.get("font_size", item_renderer.default_size))
                background_color = item.get("background_color", "transparent")
                line_height = float(item.get("line_height", 1.0))
                paragraph_spacing = item.get("paragraph_spacing")
                if paragraph_spacing is not None:
                    paragraph_spacing = int(paragraph_spacing)
                paragraph_indent_px = int(item.get("paragraph_indent_px", 0))
                tokens = item_renderer.parse_tokens(text_data)
                for token in tokens:
                    token.setdefault("size", font_size)
                canvas, metrics = item_renderer.generate_canvas(
                    tokens,
                    width,
                    height,
                    horizontal_align=text_align,
                    vertical_align=text_vertical_align,
                    padding=text_padding,
                    stroke_width=stroke_width,
                    stroke_fill=stroke_fill,
                    shadow_enabled=shadow_enabled,
                    background_fill=background_color,
                    line_height=line_height,
                    paragraph_spacing=paragraph_spacing,
                    paragraph_indent_px=paragraph_indent_px,
                    return_metrics=True,
                )
                if metrics.get("overflowed"):
                    engine.logger.warning("overlay index=%s truncated text: rendered_lines=%s total_lines=%s truncated_lines=%s", index, metrics.get("rendered_lines"), metrics.get("total_lines"), metrics.get("truncated_lines"))
                canvas_rgba = canvas.convert("RGBA")
                ox, oy = engine._position_to_pixels(position, base_w, base_h, canvas_rgba.width, canvas_rgba.height)
                composite_img.alpha_composite(canvas_rgba, dest=(max(0, ox), max(0, oy)))
                engine.logger.info("overlay index=%s composited at (%s, %s) size=%sx%s", index, ox, oy, canvas_rgba.width, canvas_rgba.height)
            preview_path = out_p.with_suffix(".png")
            composite_img.save(str(preview_path))
            engine.logger.info("apply_multi_text_overlays preview_only: saved composited image to %s", preview_path)
            return str(preview_path)

        overlay_root = engine.resolve_output_path(overlay_dir)
        overlay_root.mkdir(parents=True, exist_ok=True)
        if media_is_video:
            base_clip = VideoFileClip(str(base_path))
            composition_duration = base_clip.duration
            base_w = int(base_clip.w)
            base_h = int(base_clip.h)
        else:
            max_overlay_end = max((float(item.get("end_time", 3.0)) for item in params["overlays"]), default=3.0)
            duration = params.get("output_duration_sec") or max_overlay_end
            base_clip = ImageClip(str(base_path)).with_duration(duration)
            composition_duration = duration
            base_w = int(base_clip.w)
            base_h = int(base_clip.h)

        layered_clips = [base_clip]
        for index, item in enumerate(params["overlays"]):
            text_data = item.get("text")
            if not text_data and item.get("text_structured"):
                text_data = "".join(part.get("text", "") for part in item["text_structured"])
            if not text_data:
                engine.logger.warning("overlay index=%s skipped due to empty text", index)
                continue
            width = int(item.get("width", base_w))
            height = int(item.get("height", int(base_h * 0.25)))
            start_time = float(item.get("start_time", 0.0))
            end_time = float(item.get("end_time", composition_duration))
            position = engine._normalize_position(item.get("position", ["center", "top"]))
            if bool(item.get("match_base_size", True)):
                width = int(base_w)
                height = int(base_h)
                position = (0, 0)
            text_align = str(item.get("text_align", "center")).lower()
            text_vertical_align = str(item.get("text_vertical_align", "center")).lower()
            text_padding = int(item.get("text_padding", 6))
            stroke_width = int(item.get("stroke_width", 3))
            stroke_fill = item.get("stroke_fill", "#000000")
            shadow_enabled = bool(item.get("shadow_enabled", True))
            item_renderer = engine._get_renderer(item.get("font_path") or params.get("font_path") or context.default_font_path)
            font_size = int(item.get("font_size", item_renderer.default_size))
            background_color = item.get("background_color", "transparent")
            line_height = float(item.get("line_height", 1.0))
            paragraph_spacing = item.get("paragraph_spacing")
            if paragraph_spacing is not None:
                paragraph_spacing = int(paragraph_spacing)
            paragraph_indent_px = int(item.get("paragraph_indent_px", 0))
            overlay_name = item.get("overlay_name", f"overlay_{index:03d}") + ".png"
            overlay_path = overlay_root / overlay_name
            tokens = item_renderer.parse_tokens(text_data)
            for token in tokens:
                token.setdefault("size", font_size)
            canvas, metrics = item_renderer.generate_canvas(
                tokens,
                width,
                height,
                horizontal_align=text_align,
                vertical_align=text_vertical_align,
                padding=text_padding,
                stroke_width=stroke_width,
                stroke_fill=stroke_fill,
                shadow_enabled=shadow_enabled,
                background_fill=background_color,
                line_height=line_height,
                paragraph_spacing=paragraph_spacing,
                paragraph_indent_px=paragraph_indent_px,
                return_metrics=True,
            )
            canvas.save(str(overlay_path), format="PNG")
            if metrics.get("overflowed"):
                engine.logger.warning("overlay index=%s truncated text: png=%s rendered_lines=%s total_lines=%s truncated_lines=%s", index, overlay_path, metrics.get("rendered_lines"), metrics.get("total_lines"), metrics.get("truncated_lines"))
            overlay_clip = engine._clip_with_position(engine._clip_with_end(engine._clip_with_start(ImageClip(str(overlay_path)), start_time), end_time), position)
            layered_clips.append(overlay_clip)
            engine.logger.info("overlay index=%s png=%s start=%s end=%s position=%s text_align=%s text_v_align=%s", index, overlay_path, start_time, end_time, position, text_align, text_vertical_align)

        composed = CompositeVideoClip(layered_clips)
        fps = 24.0 if not media_is_video else float(getattr(base_clip, "fps", 24) or 24)
        engine._write_video(
            composed,
            out_p,
            fps=fps,
            video_codec=params.get("video_codec") or "h264_nvenc",
            video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
            video_preset=params.get("video_preset"),
            video_bitrate=params.get("video_bitrate"),
            audio_bitrate=params.get("audio_bitrate"),
            threads=int(params["threads"]) if params.get("threads") is not None else None,
        )
        return str(out_p)
