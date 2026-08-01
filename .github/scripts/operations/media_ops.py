from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .base import OperationContext, OperationHandler
from .registry import register_operation


@register_operation
class CropMediaImplOperation(OperationHandler):
    name = "crop_media_impl"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["input_path", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        in_p = engine.resolve_path(params["input_path"])
        out_p = engine.resolve_output_path(params["output_path"])
        media_is_video = engine._is_video(in_p)

        left_px = max(0, int(params.get("left_px", 0) or 0))
        right_px = max(0, int(params.get("right_px", 0) or 0))
        top_px = max(0, int(params.get("top_px", 0) or 0))
        bottom_px = max(0, int(params.get("bottom_px", 0) or 0))

        if media_is_video:
            return engine._crop_video(
                in_p,
                out_p,
                left_px,
                right_px,
                top_px,
                bottom_px,
                preview_only=bool(params.get("preview_only", False)),
                video_crf=int(params["video_crf"]) if params.get("video_crf") is not None else None,
                video_preset=params.get("video_preset"),
                video_bitrate=params.get("video_bitrate"),
                audio_bitrate=params.get("audio_bitrate"),
            )

        return engine._crop_image(
            in_p,
            out_p,
            left_px,
            right_px,
            top_px,
            bottom_px,
            preview_only=bool(params.get("preview_only", False)),
        )


@register_operation
class StackMediaImplOperation(OperationHandler):
    name = "stack_media_impl"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["path1", "path2", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        p1 = engine.resolve_path(params["path1"])
        p2 = engine.resolve_path(params["path2"])
        out_p = engine.resolve_output_path(params["output_path"])
        orientation = params.get("orientation", "horizontal")
        duration_sec = float(params.get("duration_sec", 3.0))

        try:
            from moviepy.editor import ImageClip, VideoFileClip, clips_array
        except ImportError:
            from moviepy import ImageClip, VideoFileClip, clips_array

        clip1 = VideoFileClip(str(p1)) if engine._is_video(p1) else ImageClip(str(p1)).with_duration(duration_sec)
        clip2 = VideoFileClip(str(p2)) if engine._is_video(p2) else ImageClip(str(p2)).with_duration(duration_sec)

        if clip1.duration != clip2.duration:
            duration = max(clip1.duration, clip2.duration)
            clip1 = clip1.with_duration(duration)
            clip2 = clip2.with_duration(duration)

        if orientation == "horizontal":
            target_h = int(min(clip1.h, clip2.h))
            clip1 = clip1.resized(height=target_h)
            clip2 = clip2.resized(height=target_h)
            grid = [[clip1, clip2]]
        else:
            target_w = int(min(clip1.w, clip2.w))
            clip1 = clip1.resized(width=target_w)
            clip2 = clip2.resized(width=target_w)
            grid = [[clip1], [clip2]]

        final_clip = clips_array(grid)
        fps = float(getattr(clip1, "fps", getattr(clip2, "fps", 24)) or 24)
        engine._write_video(
            final_clip,
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
