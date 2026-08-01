from __future__ import annotations

from typing import Any, Dict

from PIL import Image

try:
    from moviepy.editor import VideoFileClip
except ImportError:
    from moviepy import VideoFileClip

from .base import OperationContext, OperationHandler
from .registry import register_operation


@register_operation
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

        in_p = engine.resolve_path(params["input_path"])
        out_p = engine.resolve_output_path(params["output_path"])
        media_is_video = engine._is_video(in_p)

        if preview_only and media_is_video:
            preview_path = out_p.with_suffix(".png")
            with VideoFileClip(str(in_p)) as clip:
                src_w = int(clip.w)
                src_h = int(clip.h)
                scale_factor = engine._compute_scale_factor(
                    src_w,
                    src_h,
                    max_long_side=int(params["max_long_side"]) if params.get("max_long_side") is not None else None,
                    max_short_side=int(params["max_short_side"]) if params.get("max_short_side") is not None else None,
                    upscale=bool(params.get("upscale", False)),
                )
                target_w = max(1, int(round(src_w * scale_factor)))
                target_h = max(1, int(round(src_h * scale_factor)))
                frame = clip.get_frame(0)
            img = Image.fromarray(frame).resize((target_w, target_h), Image.Resampling.LANCZOS)
            img.save(str(preview_path))
            engine.logger.info("scale_media preview_only: saved frame at %s", preview_path)
            return str(preview_path)

        if media_is_video:
            with VideoFileClip(str(in_p)) as clip:
                src_w = int(clip.w)
                src_h = int(clip.h)
                scale_factor = engine._compute_scale_factor(
                    src_w,
                    src_h,
                    max_long_side=int(params["max_long_side"]) if params.get("max_long_side") is not None else None,
                    max_short_side=int(params["max_short_side"]) if params.get("max_short_side") is not None else None,
                    upscale=bool(params.get("upscale", False)),
                )
                target_w = max(2, int(round(src_w * scale_factor)))
                target_h = max(2, int(round(src_h * scale_factor)))
                if target_w % 2 != 0:
                    target_w -= 1
                if target_h % 2 != 0:
                    target_h -= 1
                if target_w == src_w and target_h == src_h:
                    scaled = clip
                else:
                    scaled = clip.resized(new_size=(target_w, target_h))
                fps = float(getattr(clip, "fps", 24) or 24)
                engine._write_video(
                    scaled,
                    out_p,
                    fps=fps,
                    video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
                    video_preset=params.get("video_preset"),
                    video_bitrate=params.get("video_bitrate"),
                    audio_bitrate=params.get("audio_bitrate"),
                )
                engine.logger.info("scale_media video input=%s source=%sx%s target=%sx%s output=%s", in_p, src_w, src_h, target_w, target_h, out_p)
        else:
            with Image.open(str(in_p)).convert("RGBA") as img:
                src_w, src_h = img.size
                scale_factor = engine._compute_scale_factor(
                    src_w,
                    src_h,
                    max_long_side=int(params["max_long_side"]) if params.get("max_long_side") is not None else None,
                    max_short_side=int(params["max_short_side"]) if params.get("max_short_side") is not None else None,
                    upscale=bool(params.get("upscale", False)),
                )
                target_w = max(1, int(round(src_w * scale_factor)))
                target_h = max(1, int(round(src_h * scale_factor)))
                if target_w == src_w and target_h == src_h:
                    scaled_img = img
                else:
                    scaled_img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                actual_out_p = out_p.with_suffix(".png") if preview_only else out_p
                engine._save_image(
                    scaled_img,
                    actual_out_p,
                    image_quality=int(params["image_quality"]) if params.get("image_quality") is not None else None,
                    png_compress_level=int(params["png_compress_level"]) if params.get("png_compress_level") is not None else None,
                    optimize=bool(params["optimize"]) if params.get("optimize") is not None else None,
                )
                engine.logger.info("scale_media image input=%s source=%sx%s target=%sx%s output=%s", in_p, src_w, src_h, target_w, target_h, actual_out_p)
            return str(actual_out_p)

        return str(out_p)
