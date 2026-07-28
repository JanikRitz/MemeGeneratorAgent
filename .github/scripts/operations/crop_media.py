from __future__ import annotations

from typing import Any, Dict

from PIL import Image

try:
    from moviepy.editor import VideoFileClip
except ImportError:
    from moviepy import VideoFileClip

from .base import OperationContext, OperationHandler


class CropMediaOperation(OperationHandler):
    name = "crop_media"

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

        in_p = engine.resolve_path(params["input_path"])
        out_p = engine.resolve_output_path(params["output_path"])
        media_is_video = engine._is_video(in_p)

        left_px = max(0, int(params.get("left_px", 0) or 0))
        right_px = max(0, int(params.get("right_px", 0) or 0))
        top_px = max(0, int(params.get("top_px", 0) or 0))
        bottom_px = max(0, int(params.get("bottom_px", 0) or 0))

        if media_is_video:
            if preview_only:
                preview_path = out_p.with_suffix(".png")
                with VideoFileClip(str(in_p)) as clip:
                    src_w = int(clip.w)
                    src_h = int(clip.h)
                    frame = clip.get_frame(0)
                    cropped_frame = frame[top_px:src_h - bottom_px, left_px:src_w - right_px]
                Image.fromarray(cropped_frame).save(str(preview_path))
                engine.logger.info("crop_media video preview_only: saved frame at t=0 to %s source=%sx%s output=%sx%s", preview_path, src_w, src_h, src_w - left_px - right_px, src_h - top_px - bottom_px)
                return str(preview_path)

            with VideoFileClip(str(in_p)) as clip:
                src_w = int(clip.w)
                src_h = int(clip.h)
                new_w = src_w - left_px - right_px
                new_h = src_h - top_px - bottom_px
                if new_w <= 0 or new_h <= 0:
                    raise ValueError(f"Crop removes entire video: source={src_w}x{src_h}, left={left_px} right={right_px} top={top_px} bottom={bottom_px}")
                if new_w % 2 != 0:
                    new_w -= 1
                if new_h % 2 != 0:
                    new_h -= 1
                from moviepy.video.VideoClip import VideoClip

                def _crop_frame(t):
                    frame = clip.get_frame(t)
                    return frame[top_px:new_h + top_px, left_px:new_w + left_px]

                cropped = VideoClip(frame_function=_crop_frame, duration=clip.duration, is_mask=clip.is_mask)
                fps = float(getattr(clip, "fps", 24) or 24)
                engine._write_video(
                    cropped,
                    out_p,
                    fps=fps,
                    video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
                    video_preset=params.get("video_preset"),
                    video_bitrate=params.get("video_bitrate"),
                    audio_bitrate=params.get("audio_bitrate"),
                )
            engine.logger.info("crop_media video input=%s source=%sx%s output=%sx%s left=%d right=%d top=%d bottom=%d", in_p, src_w, src_h, new_w, new_h, left_px, right_px, top_px, bottom_px)
            return str(out_p)

        actual_out_p = out_p.with_suffix(".png") if preview_only else out_p
        with Image.open(str(in_p)).convert("RGBA") as img:
            w, h = img.size
            crop_left = min(left_px, w)
            crop_right = min(right_px, w - crop_left)
            crop_top = min(top_px, h)
            crop_bottom = min(bottom_px, h - crop_top)
            if crop_left + crop_right >= w or crop_top + crop_bottom >= h:
                raise ValueError(f"Crop removes entire image: source={w}x{h}, left={crop_left} right={crop_right} top={crop_top} bottom={crop_bottom}")
            cropped = img.crop((crop_left, crop_top, w - crop_right, h - crop_bottom))
            engine._save_image(cropped, actual_out_p)
        engine.logger.info("crop_media image input=%s source=%sx%s output=%sx%s left=%d right=%d top=%d bottom=%d", in_p, w, h, cropped.width, cropped.height, crop_left, crop_right, crop_top, crop_bottom)
        return str(actual_out_p)
