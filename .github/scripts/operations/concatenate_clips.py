from __future__ import annotations

from typing import Any, Dict, List

from PIL import Image

try:
    from moviepy.editor import VideoFileClip, concatenate_videoclips
except ImportError:
    from moviepy import VideoFileClip, concatenate_videoclips

from .base import OperationContext, OperationHandler
from .registry import register_operation


@register_operation
class ConcatenateClipsOperation(OperationHandler):
    name = "concatenate_clips"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["clip_paths", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        preview_only = bool(params.get("preview_only", False))
        if context.preview_only_override is not None:
            preview_only = context.preview_only_override

        clip_paths: List[str] = params["clip_paths"]
        out_p = engine.resolve_output_path(params["output_path"])

        if preview_only:
            frames: List[Image.Image] = []
            for path in clip_paths:
                try:
                    p = engine.resolve_path(path)
                except FileNotFoundError:
                    candidate = path if path.startswith("/") else engine.base_dir / path
                    png_candidate = candidate.with_suffix(".png") if hasattr(candidate, "with_suffix") else None
                    if png_candidate and png_candidate.exists():
                        p = png_candidate
                    else:
                        engine.logger.warning("concatenate_clips preview: skipping missing path %s", path)
                        continue

                if engine._is_video(p):
                    with VideoFileClip(str(p)) as clip:
                        frame = clip.get_frame(0)
                    img = Image.fromarray(frame).convert("RGBA")
                else:
                    img = Image.open(str(p)).convert("RGBA")
                frames.append(img)

            if not frames:
                raise ValueError("concatenate_clips preview: no valid frames found for any clip path")

            first_frame = frames[0]
            stack_vertical = first_frame.width >= first_frame.height
            scaled: List[Image.Image] = []
            if stack_vertical:
                target_w = first_frame.width
                for img in frames:
                    if img.width != target_w:
                        new_h = max(1, int(img.height * target_w / img.width))
                        img = img.resize((target_w, new_h), Image.Resampling.LANCZOS)
                    scaled.append(img)
                total_h = sum(img.height for img in scaled)
                stacked = Image.new("RGBA", (target_w, total_h), (0, 0, 0, 255))
                y = 0
                for img in scaled:
                    stacked.paste(img, (0, y))
                    y += img.height
            else:
                target_h = first_frame.height
                for img in frames:
                    if img.height != target_h:
                        new_w = max(1, int(img.width * target_h / img.height))
                        img = img.resize((new_w, target_h), Image.Resampling.LANCZOS)
                    scaled.append(img)
                total_w = sum(img.width for img in scaled)
                stacked = Image.new("RGBA", (total_w, target_h), (0, 0, 0, 255))
                x = 0
                for img in scaled:
                    stacked.paste(img, (x, 0))
                    x += img.width

            preview_path = out_p.with_suffix(".png")
            stacked.save(str(preview_path))
            engine.logger.info("concatenate_clips preview: stacked %s frames orientation=%s to %s", len(scaled), "vertical" if stack_vertical else "horizontal", preview_path)
            return str(preview_path)

        resolved = [engine.resolve_path(path) for path in clip_paths]
        engine.logger.info("concatenate_clips clip_count=%s output=%s", len(resolved), params["output_path"])
        clips = [VideoFileClip(str(path)) for path in resolved]
        final_clip = concatenate_videoclips(clips, method="compose")
        fps = float(getattr(clips[0], "fps", 24) or 24)
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
