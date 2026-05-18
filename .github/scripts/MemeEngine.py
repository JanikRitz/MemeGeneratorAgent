import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

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

    def _get_renderer(self, font_path: Optional[str] = None) -> "RichTextRenderer":
        if not font_path:
            return self.renderer
        fp = Path(font_path)
        if fp == self.renderer.default_font_path:
            return self.renderer
        return RichTextRenderer(default_font_path=str(fp), default_size=self.renderer.default_size)

    def _clip_with_position(self, clip, position):
        if hasattr(clip, "with_position"):
            return clip.with_position(position)
        return clip.set_position(position)

    def _clip_with_start(self, clip, start_time: float):
        if hasattr(clip, "with_start"):
            return clip.with_start(start_time)
        return clip.set_start(start_time)

    def _clip_with_end(self, clip, end_time: float):
        if hasattr(clip, "with_end"):
            return clip.with_end(end_time)
        return clip.set_end(end_time)

    def _clip_with_duration(self, clip, duration: float):
        if hasattr(clip, "with_duration"):
            return clip.with_duration(duration)
        return clip.with_duration(duration)

    def _clip_with_audio(self, clip, audio_clip):
        if audio_clip is None:
            return clip
        if hasattr(clip, "with_audio"):
            return clip.with_audio(audio_clip)
        return clip.set_audio(audio_clip)

    def get_media_info(self, input_path: str) -> Dict[str, Any]:
        media_path = self.resolve_path(input_path)
        info: Dict[str, Any] = {
            "path": str(media_path),
            "is_video": self._is_video(media_path),
            "width": None,
            "height": None,
            "duration_sec": None,
        }

        if info["is_video"]:
            with VideoFileClip(str(media_path)) as clip:
                info["width"] = int(clip.w)
                info["height"] = int(clip.h)
                info["duration_sec"] = float(clip.duration)
        else:
            with ImageClip(str(media_path)) as clip:
                info["width"] = int(clip.w)
                info["height"] = int(clip.h)

        self.logger.info("get_media_info path=%s width=%s height=%s duration=%s", media_path, info["width"], info["height"], info["duration_sec"])
        return info

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

    def _position_to_pixels(
        self,
        position: Tuple[Any, Any],
        base_w: int,
        base_h: int,
        overlay_w: int,
        overlay_h: int,
    ) -> Tuple[int, int]:
        px, py = position
        if isinstance(px, (int, float)):
            x = int(px)
        elif px == "center":
            x = (base_w - overlay_w) // 2
        elif px == "right":
            x = base_w - overlay_w
        else:  # "left" or unknown
            x = 0
        if isinstance(py, (int, float)):
            y = int(py)
        elif py == "center":
            y = (base_h - overlay_h) // 2
        elif py == "bottom":
            y = base_h - overlay_h
        else:  # "top" or unknown
            y = 0
        return x, y

    def _build_ffmpeg_params(
        self,
        video_crf: Optional[int],
        video_preset: Optional[str],
    ) -> Optional[List[str]]:
        ffmpeg_params: List[str] = []

        if video_crf is not None:
            if video_crf < 0 or video_crf > 51:
                raise ValueError("video_crf must be between 0 and 51")
            ffmpeg_params.extend(["-crf", str(int(video_crf))])

        if video_preset is not None:
            ffmpeg_params.extend(["-preset", str(video_preset)])

        return ffmpeg_params or None

    def _write_video(
        self,
        clip,
        output_path: Path,
        fps: Optional[float] = None,
        video_codec: str = "libx264",
        audio_codec: str = "aac",
        video_crf: Optional[int] = None,
        video_preset: Optional[str] = None,
        video_bitrate: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
    ) -> None:
        write_kwargs: Dict[str, Any] = {
            "codec": video_codec,
            "audio_codec": audio_codec,
        }
        if fps is not None:
            write_kwargs["fps"] = fps
        if video_bitrate:
            write_kwargs["bitrate"] = str(video_bitrate)
        if audio_bitrate:
            write_kwargs["audio_bitrate"] = str(audio_bitrate)

        ffmpeg_params = self._build_ffmpeg_params(video_crf=video_crf, video_preset=video_preset)
        if ffmpeg_params:
            write_kwargs["ffmpeg_params"] = ffmpeg_params

        clip.write_videofile(str(output_path), **write_kwargs)

    def _save_image(
        self,
        image: Image.Image,
        output_path: Path,
        image_quality: Optional[int] = None,
        png_compress_level: Optional[int] = None,
        optimize: Optional[bool] = None,
    ) -> None:
        suffix = output_path.suffix.lower()
        save_kwargs: Dict[str, Any] = {}

        if optimize is not None:
            save_kwargs["optimize"] = bool(optimize)

        if image_quality is not None:
            if image_quality < 1 or image_quality > 100:
                raise ValueError("image_quality must be between 1 and 100")

        if png_compress_level is not None:
            if png_compress_level < 0 or png_compress_level > 9:
                raise ValueError("png_compress_level must be between 0 and 9")

        if suffix in {".jpg", ".jpeg"}:
            if image_quality is not None:
                save_kwargs["quality"] = int(image_quality)
            image.convert("RGB").save(str(output_path), **save_kwargs)
            return

        if suffix == ".webp":
            if image_quality is not None:
                save_kwargs["quality"] = int(image_quality)
            image.save(str(output_path), **save_kwargs)
            return

        if suffix == ".png" and png_compress_level is not None:
            save_kwargs["compress_level"] = int(png_compress_level)

        image.save(str(output_path), **save_kwargs)

    def _compute_scale_factor(
        self,
        width: int,
        height: int,
        max_long_side: Optional[int],
        max_short_side: Optional[int],
        upscale: bool,
    ) -> float:
        factors: List[float] = []
        long_side = max(width, height)
        short_side = min(width, height)

        if max_long_side is not None:
            if max_long_side <= 0:
                raise ValueError("max_long_side must be > 0")
            factors.append(float(max_long_side) / float(long_side))

        if max_short_side is not None:
            if max_short_side <= 0:
                raise ValueError("max_short_side must be > 0")
            factors.append(float(max_short_side) / float(short_side))

        if not factors:
            raise ValueError("Provide at least one of: max_long_side, max_short_side")

        scale_factor = min(factors)
        if not upscale:
            scale_factor = min(scale_factor, 1.0)
        return scale_factor

    def scale_media(
        self,
        input_path: str,
        output_path: str,
        max_long_side: Optional[int] = None,
        max_short_side: Optional[int] = None,
        upscale: bool = False,
        video_crf: Optional[int] = None,
        video_preset: Optional[str] = None,
        video_bitrate: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
        image_quality: Optional[int] = None,
        png_compress_level: Optional[int] = None,
        optimize: Optional[bool] = None,
    ) -> str:
        in_p = self.resolve_path(input_path)
        out_p = self.resolve_output_path(output_path)
        media_is_video = self._is_video(in_p)

        if media_is_video:
            with VideoFileClip(str(in_p)) as clip:
                src_w = int(clip.w)
                src_h = int(clip.h)
                scale_factor = self._compute_scale_factor(
                    src_w,
                    src_h,
                    max_long_side=max_long_side,
                    max_short_side=max_short_side,
                    upscale=upscale,
                )

                target_w = max(2, int(round(src_w * scale_factor)))
                target_h = max(2, int(round(src_h * scale_factor)))

                # x264 is most compatible with even dimensions.
                if target_w % 2 != 0:
                    target_w -= 1
                if target_h % 2 != 0:
                    target_h -= 1

                if target_w == src_w and target_h == src_h:
                    scaled = clip
                else:
                    scaled = clip.resized(new_size=(target_w, target_h))

                fps = float(getattr(clip, "fps", 24) or 24)
                self._write_video(
                    scaled,
                    out_p,
                    fps=fps,
                    video_crf=video_crf,
                    video_preset=video_preset,
                    video_bitrate=video_bitrate,
                    audio_bitrate=audio_bitrate,
                )

                self.logger.info(
                    "scale_media video input=%s source=%sx%s target=%sx%s output=%s",
                    in_p,
                    src_w,
                    src_h,
                    target_w,
                    target_h,
                    out_p,
                )
        else:
            with Image.open(str(in_p)).convert("RGBA") as img:
                src_w, src_h = img.size
                scale_factor = self._compute_scale_factor(
                    src_w,
                    src_h,
                    max_long_side=max_long_side,
                    max_short_side=max_short_side,
                    upscale=upscale,
                )
                target_w = max(1, int(round(src_w * scale_factor)))
                target_h = max(1, int(round(src_h * scale_factor)))

                if target_w == src_w and target_h == src_h:
                    scaled_img = img
                else:
                    scaled_img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

                self._save_image(
                    scaled_img,
                    out_p,
                    image_quality=image_quality,
                    png_compress_level=png_compress_level,
                    optimize=optimize,
                )

                self.logger.info(
                    "scale_media image input=%s source=%sx%s target=%sx%s output=%s",
                    in_p,
                    src_w,
                    src_h,
                    target_w,
                    target_h,
                    out_p,
                )

        return str(out_p)

    def trim_video(
        self,
        input_path: str,
        start_sec: float,
        end_sec: float,
        output_path: str,
        preview_only: bool = False,
        video_crf: Optional[int] = None,
        video_preset: Optional[str] = None,
        video_bitrate: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
    ) -> str:
        in_p = self.resolve_path(input_path)
        out_p = self.resolve_output_path(output_path)
        self.logger.info("trim_video input=%s start=%s end=%s output=%s", in_p, start_sec, end_sec, out_p)

        if preview_only:
            preview_path = out_p.with_suffix(".png")
            with VideoFileClip(str(in_p)) as clip:
                frame = clip.get_frame(float(start_sec))
            Image.fromarray(frame).save(str(preview_path))
            self.logger.info("trim_video preview_only: saved frame at t=%s to %s", start_sec, preview_path)
            return str(preview_path)

        with VideoFileClip(str(in_p)) as clip:
            trimmed = clip.subclipped(start_sec, end_sec)
            fps = float(getattr(clip, "fps", 24) or 24)
            self._write_video(
                trimmed,
                out_p,
                fps=fps,
                video_crf=video_crf,
                video_preset=video_preset,
                video_bitrate=video_bitrate,
                audio_bitrate=audio_bitrate,
            )
        return str(out_p)

    def stack_media(
        self,
        path1: str,
        path2: str,
        output_path: str,
        orientation: str = "horizontal",
        duration_sec: float = 3.0,
        video_crf: Optional[int] = None,
        video_preset: Optional[str] = None,
        video_bitrate: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
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

        clip1 = VideoFileClip(str(p1)) if self._is_video(p1) else ImageClip(str(p1)).with_duration(duration_sec)
        clip2 = VideoFileClip(str(p2)) if self._is_video(p2) else ImageClip(str(p2)).with_duration(duration_sec)

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
        self._write_video(
            final_clip,
            out_p,
            fps=fps,
            video_crf=video_crf,
            video_preset=video_preset,
            video_bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
        )
        return str(out_p)

    def concatenate_clips(
        self,
        clip_paths: List[str],
        output_path: str,
        preview_only: bool = False,
        video_crf: Optional[int] = None,
        video_preset: Optional[str] = None,
        video_bitrate: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
    ) -> str:
        if preview_only:
            out_p = self.resolve_output_path(output_path)
            frames: List[Image.Image] = []
            for path in clip_paths:
                try:
                    p = self.resolve_path(path)
                except FileNotFoundError:
                    candidate = Path(path) if Path(path).is_absolute() else self.base_dir / path
                    png_candidate = candidate.with_suffix(".png")
                    if png_candidate.exists():
                        p = png_candidate
                    else:
                        self.logger.warning("concatenate_clips preview: skipping missing path %s", path)
                        continue

                if self._is_video(p):
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
            orientation = "vertical" if stack_vertical else "horizontal"
            self.logger.info(
                "concatenate_clips preview: stacked %s frames orientation=%s to %s",
                len(scaled),
                orientation,
                preview_path,
            )
            return str(preview_path)

        resolved = [self.resolve_path(path) for path in clip_paths]
        self.logger.info("concatenate_clips clip_count=%s output=%s", len(resolved), output_path)
        clips = [VideoFileClip(str(path)) for path in resolved]
        final_clip = concatenate_videoclips(clips, method="compose")
        out_p = self.resolve_output_path(output_path)
        fps = float(getattr(clips[0], "fps", 24) or 24)
        self._write_video(
            final_clip,
            out_p,
            fps=fps,
            video_crf=video_crf,
            video_preset=video_preset,
            video_bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
        )
        return str(out_p)

    def generate_text_overlay(
        self,
        text_data: str,
        video_width: Optional[int],
        video_height: Optional[int],
        output_path: str,
        media_path: Optional[str] = None,
        horizontal_align: str = "center",
        vertical_align: str = "center",
        padding: int = 24,
        stroke_width: int = 3,
        stroke_fill: str = "#000000",
        shadow_enabled: bool = True,
        font_size: Optional[int] = None,
        background_color: Any = "transparent",
        line_height: float = 1.0,
        paragraph_spacing: Optional[int] = None,
        paragraph_indent_px: int = 0,
        compose_on_media: bool = False,
        font_path: Optional[str] = None,
        image_quality: Optional[int] = None,
        png_compress_level: Optional[int] = None,
        optimize: Optional[bool] = None,
    ) -> str:
        if media_path:
            media_info = self.get_media_info(media_path)
            if not video_width:
                video_width = int(media_info["width"])
            if not video_height:
                video_height = int(media_info["height"])

        if not video_width or not video_height:
            raise ValueError("video_width and video_height are required when media_path is not provided")

        out_p = self.resolve_output_path(output_path)
        self.logger.info("generate_text_overlay output=%s width=%s height=%s media_path=%s", out_p, video_width, video_height, media_path)
        renderer = self._get_renderer(font_path)
        tokens = renderer.parse_tokens(text_data)
        if font_size:
            for token in tokens:
                token.setdefault("size", int(font_size))

        canvas, metrics = renderer.generate_canvas(
            tokens,
            video_width,
            video_height,
            horizontal_align=horizontal_align,
            vertical_align=vertical_align,
            padding=padding,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
            shadow_enabled=shadow_enabled,
            background_fill=background_color,
            line_height=line_height,
            paragraph_spacing=paragraph_spacing,
            paragraph_indent_px=paragraph_indent_px,
            return_metrics=True,
        )
        if compose_on_media:
            if not media_path:
                raise ValueError("compose_on_media requires media_path")

            base_path = self.resolve_path(media_path)
            if self._is_video(base_path):
                raise ValueError("compose_on_media only supports image media_path values")

            with Image.open(str(base_path)).convert("RGBA") as base_img:
                if base_img.size != (int(video_width), int(video_height)):
                    base_img = base_img.resize((int(video_width), int(video_height)))
                composed = base_img.copy()
                composed.alpha_composite(canvas.convert("RGBA"))
                self._save_image(
                    composed,
                    out_p,
                    image_quality=image_quality,
                    png_compress_level=png_compress_level,
                    optimize=optimize,
                )
        else:
            self._save_image(
                canvas,
                out_p,
                image_quality=image_quality,
                png_compress_level=png_compress_level,
                optimize=optimize,
            )

        if metrics.get("overflowed"):
            self.logger.warning(
                "generate_text_overlay truncated text: output=%s rendered_lines=%s total_lines=%s truncated_lines=%s",
                out_p,
                metrics.get("rendered_lines"),
                metrics.get("total_lines"),
                metrics.get("truncated_lines"),
            )
        return str(out_p)

    def add_text_side_box(
        self,
        base_media_path: str,
        text_data: str,
        side: str,
        output_path: str,
        overlay_dir: str = "render",
        box_size_px: Optional[int] = None,
        box_size_ratio: float = 0.22,
        background_color: Any = "#101010",
        text_align: str = "center",
        text_vertical_align: str = "center",
        text_padding: int = 24,
        font_size: Optional[int] = None,
        font_path: Optional[str] = None,
        stroke_width: int = 3,
        stroke_fill: str = "#000000",
        shadow_enabled: bool = True,
        output_duration_sec: Optional[float] = None,
        panel_png_name: Optional[str] = None,
        preview_only: bool = False,
        line_height: float = 1.0,
        paragraph_spacing: Optional[int] = None,
        paragraph_indent_px: int = 0,
        auto_size: bool = True,
        video_crf: Optional[int] = None,
        video_preset: Optional[str] = None,
        video_bitrate: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
        image_quality: Optional[int] = None,
        png_compress_level: Optional[int] = None,
        optimize: Optional[bool] = None,
    ) -> str:
        base_path = self.resolve_path(base_media_path)
        out_p = self.resolve_output_path(output_path)
        overlay_root = self.resolve_output_path(overlay_dir)
        overlay_root.mkdir(parents=True, exist_ok=True)

        side_value = str(side).lower()
        if side_value not in {"top", "bottom", "left", "right"}:
            raise ValueError("side must be one of: top, bottom, left, right")

        media_is_video = self._is_video(base_path)
        if preview_only:
            media_info = self.get_media_info(base_media_path)
            base_w = int(media_info["width"])
            base_h = int(media_info["height"])
            base_clip = None
            duration = float(output_duration_sec or media_info.get("duration_sec") or 5.0)
        elif media_is_video:
            base_clip = VideoFileClip(str(base_path))
            duration = float(base_clip.duration)
            base_w = int(base_clip.w)
            base_h = int(base_clip.h)
        else:
            duration = float(output_duration_sec or 5.0)
            base_clip = self._clip_with_duration(ImageClip(str(base_path)), duration)
            base_w = int(base_clip.w)
            base_h = int(base_clip.h)

        renderer = self._get_renderer(font_path)
        tokens = renderer.parse_tokens(text_data)
        if font_size:
            for token in tokens:
                token.setdefault("size", int(font_size))

        def _measure_panel(width: int, height: int) -> Dict[str, Any]:
            _, metrics = renderer.generate_canvas(
                tokens,
                max(1, int(width)),
                max(1, int(height)),
                horizontal_align=text_align,
                vertical_align=text_vertical_align,
                padding=int(text_padding),
                stroke_width=int(stroke_width),
                stroke_fill=stroke_fill,
                shadow_enabled=bool(shadow_enabled),
                background_fill=background_color,
                line_height=line_height,
                paragraph_spacing=paragraph_spacing,
                paragraph_indent_px=paragraph_indent_px,
                return_metrics=True,
            )
            return metrics

        if side_value in {"top", "bottom"}:
            min_panel_size = int(round(base_h * float(box_size_ratio)))
            panel_size = int(box_size_px if box_size_px else min_panel_size)

            # Auto-grow panel height based on rendered text needs while keeping
            # existing ratio as the minimum baseline.
            if box_size_px is None and bool(auto_size):
                measured = _measure_panel(base_w, panel_size)
                required = int(measured.get("text_total_height", 0)) + (int(text_padding) * 2)
                panel_size = max(panel_size, required)

            panel_w, panel_h = base_w, max(1, panel_size)
            final_w, final_h = base_w, base_h + panel_h
            base_position = (0, panel_h) if side_value == "top" else (0, 0)
            panel_position = (0, 0) if side_value == "top" else (0, base_h)
        else:
            min_panel_size = int(round(base_w * float(box_size_ratio)))
            panel_size = int(box_size_px if box_size_px else min_panel_size)

            # For left/right panels, width controls wrapping and therefore text
            # height. Grow width until text fits in available panel height.
            if box_size_px is None and bool(auto_size):
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
            horizontal_align=text_align,
            vertical_align=text_vertical_align,
            padding=int(text_padding),
            stroke_width=int(stroke_width),
            stroke_fill=stroke_fill,
            shadow_enabled=bool(shadow_enabled),
            background_fill=background_color,
            line_height=line_height,
            paragraph_spacing=paragraph_spacing,
            paragraph_indent_px=paragraph_indent_px,
            return_metrics=True,
        )

        png_name = (panel_png_name or f"side_box_{side_value}") + ".png"
        panel_png_path = overlay_root / png_name
        panel_canvas.save(str(panel_png_path), format="PNG")

        if metrics.get("overflowed"):
            self.logger.warning(
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
            self._save_image(
                composed_preview,
                preview_path,
                image_quality=image_quality,
                png_compress_level=png_compress_level,
                optimize=optimize,
            )
            self.logger.info(
                "add_text_side_box preview_only enabled, skipping video render and returning composed preview=%s",
                preview_path,
            )
            return str(preview_path)

        image_output_exts = {".png", ".jpg", ".jpeg", ".webp"}
        if (not media_is_video) and out_p.suffix.lower() in image_output_exts:
            with Image.open(str(base_path)).convert("RGBA") as base_img:
                if base_img.size != (base_w, base_h):
                    base_img = base_img.resize((base_w, base_h))

                final_image = Image.new("RGBA", (final_w, final_h), (0, 0, 0, 0))
                final_image.paste(base_img, base_position)
                final_image.paste(panel_canvas.convert("RGBA"), panel_position)
                self._save_image(
                    final_image,
                    out_p,
                    image_quality=image_quality,
                    png_compress_level=png_compress_level,
                    optimize=optimize,
                )

            return str(out_p)

        base_layer = self._clip_with_position(base_clip, base_position)
        panel_layer = self._clip_with_position(
            self._clip_with_duration(ImageClip(str(panel_png_path)), duration),
            panel_position,
        )

        composite = CompositeVideoClip([base_layer, panel_layer], size=(final_w, final_h))
        composite = self._clip_with_audio(composite, getattr(base_clip, "audio", None))

        self.logger.info(
            "add_text_side_box base=%s side=%s panel=%sx%s final=%sx%s auto_size=%s output=%s panel_png=%s",
            base_path,
            side_value,
            panel_w,
            panel_h,
            final_w,
            final_h,
            bool(auto_size),
            out_p,
            panel_png_path,
        )
        fps = 24.0 if not media_is_video else float(getattr(base_clip, "fps", 24) or 24)
        self._write_video(
            composite,
            out_p,
            fps=fps,
            video_crf=video_crf,
            video_preset=video_preset,
            video_bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
        )
        return str(out_p)

    def apply_text_overlay(
        self,
        input_path: str,
        output_path: str,
        text: Optional[str] = None,
        text_structured: Optional[List[Dict[str, Any]]] = None,
        overlay_dir: str = "render",
        start_time: float = 0.0,
        end_time: Optional[float] = None,
        position: Any = ("center", "top"),
        width: Optional[int] = None,
        height: Optional[int] = None,
        match_base_size: bool = True,
        text_align: str = "center",
        text_vertical_align: str = "center",
        text_padding: int = 24,
        font_size: Optional[int] = None,
        font_path: Optional[str] = None,
        stroke_width: int = 3,
        stroke_fill: str = "#000000",
        shadow_enabled: bool = True,
        background_color: Any = "transparent",
        line_height: float = 1.0,
        paragraph_spacing: Optional[int] = None,
        paragraph_indent_px: int = 0,
        overlay_name: Optional[str] = None,
        output_duration_sec: Optional[float] = None,
        preview_only: bool = False,
        video_crf: Optional[int] = None,
        video_preset: Optional[str] = None,
        video_bitrate: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
    ) -> str:
        if text is None and text_structured is None:
            raise ValueError("apply_text_overlay requires text or text_structured")

        resolved_width = int(width) if width is not None else None
        resolved_height = int(height) if height is not None else None

        if not bool(match_base_size) and resolved_height is None:
            media_info = self.get_media_info(input_path)
            overlay_width = resolved_width or int(media_info["width"])
            overlay_height = max(1, int(round(int(media_info["height"]) * 0.25)))
            text_data = text
            if text_data is None and text_structured is not None:
                text_data = "".join(part.get("text", "") for part in text_structured)

            if text_data:
                _renderer = self._get_renderer(font_path)
                tokens = _renderer.parse_tokens(text_data)
                if font_size is not None:
                    for token in tokens:
                        token.setdefault("size", int(font_size))

                _, metrics = _renderer.generate_canvas(
                    tokens,
                    overlay_width,
                    overlay_height,
                    horizontal_align=str(text_align),
                    vertical_align=str(text_vertical_align),
                    padding=int(text_padding),
                    stroke_width=int(stroke_width),
                    stroke_fill=stroke_fill,
                    shadow_enabled=bool(shadow_enabled),
                    background_fill=background_color,
                    line_height=float(line_height),
                    paragraph_spacing=int(paragraph_spacing) if paragraph_spacing is not None else None,
                    paragraph_indent_px=int(paragraph_indent_px),
                    return_metrics=True,
                )
                required_height = int(metrics.get("text_total_height", 0)) + (int(text_padding) * 2)
                resolved_height = max(overlay_height, required_height)

        overlay_item: Dict[str, Any] = {
            "start_time": float(start_time),
            "position": position,
            "match_base_size": bool(match_base_size),
            "text_align": str(text_align),
            "text_vertical_align": str(text_vertical_align),
            "text_padding": int(text_padding),
            "stroke_width": int(stroke_width),
            "stroke_fill": stroke_fill,
            "shadow_enabled": bool(shadow_enabled),
            "background_color": background_color,
            "line_height": float(line_height),
            "paragraph_indent_px": int(paragraph_indent_px),
        }

        if text is not None:
            overlay_item["text"] = text
        if text_structured is not None:
            overlay_item["text_structured"] = text_structured
        if end_time is not None:
            overlay_item["end_time"] = float(end_time)
        if resolved_width is not None:
            overlay_item["width"] = resolved_width
        if resolved_height is not None:
            overlay_item["height"] = resolved_height
        if font_size is not None:
            overlay_item["font_size"] = int(font_size)
        if paragraph_spacing is not None:
            overlay_item["paragraph_spacing"] = int(paragraph_spacing)
        if overlay_name:
            overlay_item["overlay_name"] = overlay_name

        return self.apply_multi_text_overlays(
            base_media_path=input_path,
            overlays=[overlay_item],
            output_path=output_path,
            overlay_dir=overlay_dir,
            output_duration_sec=output_duration_sec,
            font_path=font_path,
            preview_only=preview_only,
            video_crf=video_crf,
            video_preset=video_preset,
            video_bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
        )

    def apply_multi_text_overlays(
        self,
        base_media_path: str,
        overlays: List[Dict[str, Any]],
        output_path: str,
        overlay_dir: str = "render",
        output_duration_sec: Optional[float] = None,
        font_path: Optional[str] = None,
        preview_only: bool = False,
        video_crf: Optional[int] = None,
        video_preset: Optional[str] = None,
        video_bitrate: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
    ) -> str:
        base_path = self.resolve_path(base_media_path)
        out_p = self.resolve_output_path(output_path)
        self.logger.info(
            "apply_multi_text_overlays base=%s overlay_count=%s output=%s",
            base_path,
            len(overlays),
            out_p,
        )

        media_is_video = self._is_video(base_path)

        if preview_only:
            if media_is_video:
                with VideoFileClip(str(base_path)) as clip:
                    frame = clip.get_frame(0)
                composite_img = Image.fromarray(frame).convert("RGBA")
            else:
                composite_img = Image.open(str(base_path)).convert("RGBA")
            base_w, base_h = composite_img.size

            for index, item in enumerate(overlays):
                text_data = item.get("text")
                if not text_data and item.get("text_structured"):
                    text_data = "".join(part.get("text", "") for part in item["text_structured"])
                if not text_data:
                    self.logger.warning("overlay index=%s skipped due to empty text", index)
                    continue

                width = int(item.get("width", base_w))
                height = int(item.get("height", int(base_h * 0.25)))
                position = self._normalize_position(item.get("position", ["center", "top"]))
                if bool(item.get("match_base_size", True)):
                    width = int(base_w)
                    height = int(base_h)
                    position = (0, 0)
                text_align = str(item.get("text_align", "center")).lower()
                text_vertical_align = str(item.get("text_vertical_align", "center")).lower()
                text_padding = int(item.get("text_padding", 24))
                stroke_width = int(item.get("stroke_width", 3))
                stroke_fill = item.get("stroke_fill", "#000000")
                shadow_enabled = bool(item.get("shadow_enabled", True))
                item_renderer = self._get_renderer(item.get("font_path") or font_path)
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
                    self.logger.warning(
                        "overlay index=%s truncated text: rendered_lines=%s total_lines=%s truncated_lines=%s",
                        index,
                        metrics.get("rendered_lines"),
                        metrics.get("total_lines"),
                        metrics.get("truncated_lines"),
                    )

                canvas_rgba = canvas.convert("RGBA")
                ox, oy = self._position_to_pixels(position, base_w, base_h, canvas_rgba.width, canvas_rgba.height)
                composite_img.alpha_composite(canvas_rgba, dest=(max(0, ox), max(0, oy)))
                self.logger.info("overlay index=%s composited at (%s, %s) size=%sx%s", index, ox, oy, canvas_rgba.width, canvas_rgba.height)

            preview_path = out_p.with_suffix(".png")
            composite_img.save(str(preview_path))
            self.logger.info("apply_multi_text_overlays preview_only: saved composited image to %s", preview_path)
            return str(preview_path)

        # Normal video-composition path
        overlay_root = self.resolve_output_path(overlay_dir)
        overlay_root.mkdir(parents=True, exist_ok=True)

        if media_is_video:
            base_clip = VideoFileClip(str(base_path))
            composition_duration = base_clip.duration
            base_w = int(base_clip.w)
            base_h = int(base_clip.h)
        else:
            max_overlay_end = max((float(item.get("end_time", 3.0)) for item in overlays), default=3.0)
            duration = output_duration_sec or max_overlay_end
            base_clip = ImageClip(str(base_path)).with_duration(duration)
            composition_duration = duration
            base_w = int(base_clip.w)
            base_h = int(base_clip.h)

        layered_clips = [base_clip]

        for index, item in enumerate(overlays):
            text_data = item.get("text")
            if not text_data and item.get("text_structured"):
                text_data = "".join(part.get("text", "") for part in item["text_structured"])
            if not text_data:
                self.logger.warning("overlay index=%s skipped due to empty text", index)
                continue

            width = int(item.get("width", base_w))
            height = int(item.get("height", int(base_h * 0.25)))
            start_time = float(item.get("start_time", 0.0))
            end_time = float(item.get("end_time", composition_duration))
            position = self._normalize_position(item.get("position", ["center", "top"]))
            if bool(item.get("match_base_size", True)):
                width = int(base_w)
                height = int(base_h)
                position = (0, 0)
            text_align = str(item.get("text_align", "center")).lower()
            text_vertical_align = str(item.get("text_vertical_align", "center")).lower()
            text_padding = int(item.get("text_padding", 24))
            stroke_width = int(item.get("stroke_width", 3))
            stroke_fill = item.get("stroke_fill", "#000000")
            shadow_enabled = bool(item.get("shadow_enabled", True))
            item_renderer = self._get_renderer(item.get("font_path") or font_path)
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
                self.logger.warning(
                    "overlay index=%s truncated text: png=%s rendered_lines=%s total_lines=%s truncated_lines=%s",
                    index,
                    overlay_path,
                    metrics.get("rendered_lines"),
                    metrics.get("total_lines"),
                    metrics.get("truncated_lines"),
                )

            overlay_clip = self._clip_with_position(
                self._clip_with_end(
                    self._clip_with_start(ImageClip(str(overlay_path)), start_time),
                    end_time,
                ),
                position,
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
        fps = 24.0 if not media_is_video else float(getattr(base_clip, "fps", 24) or 24)
        self._write_video(
            composed,
            out_p,
            fps=fps,
            video_crf=video_crf,
            video_preset=video_preset,
            video_bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
        )
        return str(out_p)