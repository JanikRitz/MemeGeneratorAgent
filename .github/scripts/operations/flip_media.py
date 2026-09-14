from __future__ import annotations

from typing import Any, Dict

import numpy as np
from PIL import Image

try:
    from moviepy.editor import VideoFileClip
except ImportError:
    from moviepy import VideoFileClip

from .base import OperationContext, OperationHandler
from .registry import register_operation

_VALID_DIRECTIONS = ("horizontal", "vertical")


@register_operation
class FlipMediaOperation(OperationHandler):
    name = "flip_media"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["input_path", "output_path", "direction"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")
        if params["direction"] not in _VALID_DIRECTIONS:
            raise ValueError(f"Invalid direction: {params['direction']!r}; expected one of {_VALID_DIRECTIONS}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        direction = params["direction"]
        preview_only = bool(params.get("preview_only", False))
        if context.preview_only_override is not None:
            preview_only = context.preview_only_override

        in_p = engine.resolve_path(params["input_path"])
        out_p = engine.resolve_output_path(params["output_path"])
        media_is_video = engine._is_video(in_p)

        if media_is_video:
            with VideoFileClip(str(in_p)) as clip:
                if direction == "horizontal":
                    flipped = clip.image_transform(lambda frame: np.fliplr(frame))
                else:
                    flipped = clip.image_transform(lambda frame: np.flipud(frame))

                if preview_only:
                    preview_path = out_p.with_suffix(".png")
                    frame = flipped.get_frame(0)
                    Image.fromarray(frame).save(str(preview_path))
                    engine.logger.info("flip_media preview_only: saved frame at %s", preview_path)
                    return str(preview_path)

                fps = float(getattr(clip, "fps", 24) or 24)
                engine._write_video(
                    flipped,
                    out_p,
                    fps=fps,
                    video_codec=params.get("video_codec") or "h264_nvenc",
                    video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
                    video_preset=params.get("video_preset"),
                    video_bitrate=params.get("video_bitrate"),
                    audio_bitrate=params.get("audio_bitrate"),
                    threads=int(params["threads"]) if params.get("threads") is not None else None,
                )
                engine.logger.info("flip_media video input=%s direction=%s output=%s", in_p, direction, out_p)
        else:
            with Image.open(str(in_p)).convert("RGBA") as img:
                if direction == "horizontal":
                    flipped_img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                else:
                    flipped_img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                actual_out_p = out_p.with_suffix(".png") if preview_only else out_p
                engine._save_image(
                    flipped_img,
                    actual_out_p,
                    image_quality=int(params["image_quality"]) if params.get("image_quality") is not None else None,
                    png_compress_level=int(params["png_compress_level"]) if params.get("png_compress_level") is not None else None,
                    optimize=bool(params["optimize"]) if params.get("optimize") is not None else None,
                )
                engine.logger.info("flip_media image input=%s direction=%s output=%s", in_p, direction, actual_out_p)
            return str(actual_out_p)

        return str(out_p)
