import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from moviepy.editor import (
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
        clips_array,
        concatenate_videoclips,
    )
except ImportError:
    from moviepy import (
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
        clips_array,
        concatenate_videoclips,
    )

try:
    from RichTextRenderer import RichTextRenderer
except ImportError:
    from .RichTextRenderer import RichTextRenderer

class MemeEngine:
    def __init__(self, base_dir: str = ".", logger: Optional[logging.Logger] = None):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger("meme_engine")
        self.renderer = RichTextRenderer()

    def _is_video(self, path: Path) -> bool:
        return path.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    def resolve_path(self, path_value: str) -> Path:
        candidate = Path(path_value)
        full_path = candidate if candidate.is_absolute() else self.base_dir / candidate
        if not full_path.exists():
            raise FileNotFoundError(f"Asset not found: {full_path}")
        return full_path

    def resolve_output_path(self, path_value: str) -> Path:
        candidate = Path(path_value)
        out_path = candidate if candidate.is_absolute() else self.base_dir / candidate
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return out_path

    def _normalize_position(self, position: Any) -> Tuple[Any, Any]:
        if isinstance(position, (list, tuple)) and len(position) == 2:
            return position[0], position[1]
        if isinstance(position, str):
            return position, "center"
        return "center", "center"

    def trim_video(self, input_path: str, start_sec: float, end_sec: float, output_path: str) -> str:
        in_p = self.resolve_path(input_path)
        out_p = self.resolve_output_path(output_path)
        self.logger.info("trim_video input=%s start=%s end=%s output=%s", in_p, start_sec, end_sec, out_p)
        
        with VideoFileClip(str(in_p)) as clip:
            trimmed = clip.subclip(start_sec, end_sec)
            trimmed.write_videofile(str(out_p), codec="libx264", audio_codec="aac")
        return str(out_p)

    def stack_media(
        self,
        path1: str,
        path2: str,
        output_path: str,
        orientation: str = "horizontal",
        duration_sec: float = 3.0,
    ) -> str:
        p1 = self.resolve_path(path1)
        p2 = self.resolve_path(path2)
        out_p = self.resolve_output_path(output_path)
        self.logger.info(
            "stack_media path1=%s path2=%s output=%s orientation=%s",
            p1,
            p2,
            out_p,
            orientation,
        )

        clip1 = VideoFileClip(str(p1)) if self._is_video(p1) else ImageClip(str(p1)).set_duration(duration_sec)
        clip2 = VideoFileClip(str(p2)) if self._is_video(p2) else ImageClip(str(p2)).set_duration(duration_sec)

        if clip1.duration != clip2.duration:
            duration = max(clip1.duration, clip2.duration)
            clip1 = clip1.set_duration(duration)
            clip2 = clip2.set_duration(duration)

        if orientation == "horizontal":
            target_h = int(min(clip1.h, clip2.h))
            clip1 = clip1.resize(height=target_h)
            clip2 = clip2.resize(height=target_h)
            grid = [[clip1, clip2]]
        else:
            target_w = int(min(clip1.w, clip2.w))
            clip1 = clip1.resize(width=target_w)
            clip2 = clip2.resize(width=target_w)
            grid = [[clip1], [clip2]]

        final_clip = clips_array(grid)
        final_clip.write_videofile(str(out_p), codec="libx264", audio_codec="aac")
        return str(out_p)

    def concatenate_clips(self, clip_paths: List[str], output_path: str) -> str:
        resolved = [self.resolve_path(path) for path in clip_paths]
        self.logger.info("concatenate_clips clip_count=%s output=%s", len(resolved), output_path)
        clips = [VideoFileClip(str(path)) for path in resolved]
        final_clip = concatenate_videoclips(clips, method="compose")
        out_p = self.resolve_output_path(output_path)
        final_clip.write_videofile(str(out_p), codec="libx264", audio_codec="aac")
        return str(out_p)

    def generate_text_overlay(
        self,
        text_data: str,
        video_width: int,
        video_height: int,
        output_path: str,
        horizontal_align: str = "center",
        vertical_align: str = "center",
        padding: int = 24,
        stroke_width: int = 3,
        stroke_fill: str = "#000000",
        shadow_enabled: bool = True,
    ) -> str:
        out_p = self.resolve_output_path(output_path)
        self.logger.info("generate_text_overlay output=%s width=%s height=%s", out_p, video_width, video_height)
        tokens = self.renderer.parse_tokens(text_data)
        canvas = self.renderer.generate_canvas(
            tokens,
            video_width,
            video_height,
            horizontal_align=horizontal_align,
            vertical_align=vertical_align,
            padding=padding,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
            shadow_enabled=shadow_enabled,
        )
        canvas.save(str(out_p), format="PNG")
        return str(out_p)

    def apply_multi_text_overlays(
        self,
        base_media_path: str,
        overlays: List[Dict[str, Any]],
        output_path: str,
        overlay_dir: str = "render",
        output_duration_sec: Optional[float] = None,
    ) -> str:
        base_path = self.resolve_path(base_media_path)
        out_p = self.resolve_output_path(output_path)
        overlay_root = self.resolve_output_path(overlay_dir)
        overlay_root.mkdir(parents=True, exist_ok=True)
        self.logger.info(
            "apply_multi_text_overlays base=%s overlay_count=%s output=%s",
            base_path,
            len(overlays),
            out_p,
        )

        media_is_video = self._is_video(base_path)
        if media_is_video:
            base_clip = VideoFileClip(str(base_path))
            composition_duration = base_clip.duration
        else:
            max_overlay_end = max((float(item.get("end_time", 3.0)) for item in overlays), default=3.0)
            duration = output_duration_sec or max_overlay_end
            base_clip = ImageClip(str(base_path)).set_duration(duration)
            composition_duration = duration

        layered_clips = [base_clip]

        for index, item in enumerate(overlays):
            text_data = item.get("text")
            if not text_data and item.get("text_structured"):
                text_data = "".join(part.get("text", "") for part in item["text_structured"])
            if not text_data:
                self.logger.warning("overlay index=%s skipped due to empty text", index)
                continue

            width = int(item.get("width", base_clip.w))
            height = int(item.get("height", int(base_clip.h * 0.25)))
            start_time = float(item.get("start_time", 0.0))
            end_time = float(item.get("end_time", composition_duration))
            position = self._normalize_position(item.get("position", ["center", "top"]))
            text_align = str(item.get("text_align", "center")).lower()
            text_vertical_align = str(item.get("text_vertical_align", "center")).lower()
            text_padding = int(item.get("text_padding", 24))
            stroke_width = int(item.get("stroke_width", 3))
            stroke_fill = item.get("stroke_fill", "#000000")
            shadow_enabled = bool(item.get("shadow_enabled", True))
            font_size = int(item.get("font_size", self.renderer.default_size))

            overlay_name = item.get("overlay_name", f"overlay_{index:03d}.png")
            overlay_path = overlay_root / overlay_name

            tokens = self.renderer.parse_tokens(text_data)
            for token in tokens:
                token.setdefault("size", font_size)

            canvas = self.renderer.generate_canvas(
                tokens,
                width,
                height,
                horizontal_align=text_align,
                vertical_align=text_vertical_align,
                padding=text_padding,
                stroke_width=stroke_width,
                stroke_fill=stroke_fill,
                shadow_enabled=shadow_enabled,
            )
            canvas.save(str(overlay_path), format="PNG")

            overlay_clip = (
                ImageClip(str(overlay_path))
                .with_start(start_time)
                .with_end(end_time)
                .with_position(position)
            )
            layered_clips.append(overlay_clip)
            self.logger.info(
                "overlay index=%s png=%s start=%s end=%s position=%s text_align=%s text_v_align=%s",
                index,
                overlay_path,
                start_time,
                end_time,
                position,
                text_align,
                text_vertical_align,
            )

        composed = CompositeVideoClip(layered_clips)
        composed.write_videofile(str(out_p), codec="libx264", audio_codec="aac")
        return str(out_p)