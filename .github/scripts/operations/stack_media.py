from __future__ import annotations

from typing import Any, Dict

from PIL import Image

try:
    from moviepy.editor import ImageClip, VideoFileClip, clips_array
except ImportError:
    from moviepy import ImageClip, VideoFileClip, clips_array

from .base import OperationContext, OperationHandler
from .registry import register_operation


@register_operation
class StackMediaOperation(OperationHandler):
    name = "stack_media"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["path1", "path2", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        preview_only = bool(params.get("preview_only", False))
        if context.preview_only_override is not None:
            preview_only = context.preview_only_override

        path1 = params["path1"]
        path2 = params["path2"]
        out_p = engine.resolve_output_path(params["output_path"])

        still_output = not engine._is_video(engine.resolve_path(path1)) and not engine._is_video(engine.resolve_path(path2)) and out_p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        if preview_only or still_output:
            p1 = engine.resolve_path(path1)
            p2 = engine.resolve_path(path2)
            if engine._is_video(p1):
                with VideoFileClip(str(p1)) as clip:
                    frame1 = clip.get_frame(0)
                img1 = Image.fromarray(frame1).convert("RGBA")
            else:
                img1 = Image.open(str(p1)).convert("RGBA")

            if engine._is_video(p2):
                with VideoFileClip(str(p2)) as clip:
                    frame2 = clip.get_frame(0)
                img2 = Image.fromarray(frame2).convert("RGBA")
            else:
                img2 = Image.open(str(p2)).convert("RGBA")

            orientation = params.get("orientation", "horizontal")
            if orientation == "horizontal":
                target_h = int(min(img1.height, img2.height))
                img1 = img1.resize((max(1, int(img1.width * target_h / img1.height)), target_h), Image.Resampling.LANCZOS)
                img2 = img2.resize((max(1, int(img2.width * target_h / img2.height)), target_h), Image.Resampling.LANCZOS)
                composite = Image.new("RGBA", (img1.width + img2.width, target_h), (0, 0, 0, 0))
                composite.paste(img1, (0, 0))
                composite.paste(img2, (img1.width, 0))
            else:
                target_w = int(min(img1.width, img2.width))
                img1 = img1.resize((target_w, max(1, int(img1.height * target_w / img1.width))), Image.Resampling.LANCZOS)
                img2 = img2.resize((target_w, max(1, int(img2.height * target_w / img2.width))), Image.Resampling.LANCZOS)
                composite = Image.new("RGBA", (target_w, img1.height + img2.height), (0, 0, 0, 0))
                composite.paste(img1, (0, 0))
                composite.paste(img2, (0, img1.height))

            preview_path = out_p.with_suffix(".png") if preview_only else out_p
            engine._save_image(composite, preview_path, image_quality=params.get("image_quality"), png_compress_level=params.get("png_compress_level"), optimize=params.get("optimize"))
            engine.logger.info("stack_media preview_only: wrote composite preview to %s", preview_path)
            return str(preview_path)

        return engine._stack_media_impl(
            path1=path1,
            path2=path2,
            output_path=params["output_path"],
            orientation=params.get("orientation", "horizontal"),
            duration_sec=float(params.get("duration_sec", 3.0)),
            video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
            video_preset=params.get("video_preset"),
            video_bitrate=params.get("video_bitrate"),
            audio_bitrate=params.get("audio_bitrate"),
            video_codec=params.get("video_codec"),
            threads=params.get("threads"),
        )
