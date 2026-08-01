from __future__ import annotations

from typing import Any, Dict

from PIL import Image

try:
    from moviepy.editor import VideoFileClip
    from moviepy.video.VideoClip import VideoClip
    from moviepy.editor import concatenate_videoclips
except ImportError:
    from moviepy import VideoFileClip
    from moviepy.video.VideoClip import VideoClip
    from moviepy import concatenate_videoclips

from .base import OperationContext, OperationHandler
from .registry import register_operation


def _parse_time(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    raise ValueError(f"Invalid time format: {value!r}, expected MM:SS or HH:MM:SS")


@register_operation
class TrimVideoOperation(OperationHandler):
    name = "trim_video"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["input_path", "start_sec", "end_sec", "output_path"]
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
        engine.logger.info("trim_video input=%s start=%s end=%s output=%s boomerang=%s", in_p, params["start_sec"], params["end_sec"], out_p, params.get("boomerang", False))

        if preview_only:
            preview_path = out_p.with_suffix(".png")
            with VideoFileClip(str(in_p)) as clip:
                frame = clip.get_frame(float(_parse_time(params["start_sec"])))
            Image.fromarray(frame).save(str(preview_path))
            engine.logger.info("trim_video preview_only: saved frame at t=%s to %s", params["start_sec"], preview_path)
            return str(preview_path)

        with VideoFileClip(str(in_p)) as clip:
            trimmed = clip.subclipped(_parse_time(params["start_sec"]), _parse_time(params["end_sec"]))
            if bool(params.get("boomerang", False)):
                def _reverse_frames(vid_clip):
                    fps = float(getattr(vid_clip, "fps", 24) or 24)
                    duration = vid_clip.duration
                    n_frames = int(fps * duration)

                    def make_frame(t):
                        idx = int((duration - t) * fps)
                        idx = max(0, min(idx, n_frames - 1))
                        return vid_clip.get_frame(float(idx) / fps)

                    return VideoClip(frame_function=make_frame, duration=duration, is_mask=vid_clip.is_mask)

                reversed_clip = _reverse_frames(trimmed)
                final_clip = concatenate_videoclips([trimmed, reversed_clip])
            else:
                final_clip = trimmed
            fps = float(getattr(final_clip, "fps", 24) or 24)
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
