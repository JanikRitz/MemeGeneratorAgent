import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

try:
    from operations.base import OperationContext
    from operations.registry import OperationRegistry
    from operations.trim_video import TrimVideoOperation
    from operations.crop_media import CropMediaOperation
    from operations.scale_media import ScaleMediaOperation
    from operations.stack_media import StackMediaOperation
    from operations.concatenate_clips import ConcatenateClipsOperation
    from operations.generate_text_overlay import GenerateTextOverlayOperation
    from operations.apply_text_overlay import ApplyTextOverlayOperation
    from operations.add_text_side_box import AddTextSideBoxOperation
    from operations.apply_multi_text_overlays import ApplyMultiTextOverlaysOperation
except ImportError:
    from .operations.base import OperationContext
    from .operations.registry import OperationRegistry
    from .operations.trim_video import TrimVideoOperation
    from .operations.crop_media import CropMediaOperation
    from .operations.scale_media import ScaleMediaOperation
    from .operations.stack_media import StackMediaOperation
    from .operations.concatenate_clips import ConcatenateClipsOperation
    from .operations.generate_text_overlay import GenerateTextOverlayOperation
    from .operations.apply_text_overlay import ApplyTextOverlayOperation
    from .operations.add_text_side_box import AddTextSideBoxOperation
    from .operations.apply_multi_text_overlays import ApplyMultiTextOverlaysOperation

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
    _MEDIA_SUFFIX_PRIORITY = {
        ".gif": 0,
        ".mp4": 1,
        ".mov": 2,
        ".mkv": 3,
        ".webm": 4,
        ".avi": 5,
        ".png": 6,
        ".jpg": 7,
        ".jpeg": 8,
        ".webp": 9,
    }

    def __init__(
        self,
        base_dir: str = ".",
        logger: Optional[logging.Logger] = None,
        registry: Optional[OperationRegistry] = None,
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger("meme_engine")
        self.renderer = RichTextRenderer()
        self.registry = registry or self._build_default_registry()

    def _build_default_registry(self) -> OperationRegistry:
        registry = OperationRegistry()
        registry.register(TrimVideoOperation())
        registry.register(CropMediaOperation())
        registry.register(ScaleMediaOperation())
        registry.register(StackMediaOperation())
        registry.register(ConcatenateClipsOperation())
        registry.register(GenerateTextOverlayOperation())
        registry.register(ApplyTextOverlayOperation())
        registry.register(AddTextSideBoxOperation())
        registry.register(ApplyMultiTextOverlaysOperation())
        return registry

    def register_operation(self, handler) -> None:
        self.registry.register(handler)

    def list_operations(self) -> List[str]:
        return self.registry.list()

    def execute(self, operation: str, params: Dict[str, Any], context: Optional[OperationContext] = None) -> str:
        handler = self.registry.get(operation)
        if handler is None:
            raise ValueError(f"Unsupported operation: {operation}")

        effective_context = context or OperationContext(
            engine=self,
            logger=self.logger,
            preview_only_override=None,
            default_font_path=None,
            last_output="",
        )
        return handler.execute(self, params, effective_context)

    @staticmethod
    def _resolve_font_path(font_name_or_path: str) -> Path:
        """Resolve a font name or path to an existing font file.

        Accepts:
        - An absolute or relative path to an existing font file.
        - A bare font family name (e.g. "Montserrat"), which is searched
          for in the system and user font directories. The file whose stem
          most closely matches the name without extra style tokens (italic,
          bold, etc.) is preferred as the regular-weight base font.
        """
        candidate = Path(font_name_or_path)
        if candidate.exists():
            return candidate

        # If the value has directory separators it was intended as an explicit
        # path — don't silently fall through to a name search.
        if candidate.parent != Path("."):
            raise FileNotFoundError(f"Font file not found: {font_name_or_path}")

        font_dirs = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        ]

        _style_tokens = {
            "italic", "bold", "bd", "bi", "light", "thin", "heavy",
            "black", "medium", "semibold", "extrabold", "extralight",
        }

        name_lower = candidate.stem.lower()  # supports "Montserrat" or "Montserrat.ttf"
        want_ext = candidate.suffix.lower() if candidate.suffix else None

        matches = []
        for font_dir in font_dirs:
            if not font_dir.exists():
                continue
            for f in font_dir.iterdir():
                if f.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
                    continue
                if want_ext and f.suffix.lower() != want_ext:
                    continue
                stem_lower = f.stem.lower()
                if not stem_lower.startswith(name_lower):
                    continue
                remainder = stem_lower[len(name_lower):].strip("-_ ")
                parts = re.split(r"[-_]", remainder)
                style_count = sum(1 for p in parts if p in _style_tokens)
                matches.append((style_count, f.name.lower(), f))

        if not matches:
            raise FileNotFoundError(
                f"No font file found matching '{font_name_or_path}' in system font directories. "
                f"Searched: {[str(d) for d in font_dirs if d.exists()]}"
            )

        matches.sort(key=lambda x: (x[0], x[1]))
        return matches[0][2]

    def _get_renderer(self, font_path: Optional[str] = None) -> "RichTextRenderer":
        if not font_path:
            return self.renderer
        fp = self._resolve_font_path(font_path)
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
        return path.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".gif"}

    def resolve_path(self, path_value: str) -> Path:
        candidate = Path(path_value)
        full_path = candidate if candidate.is_absolute() else self.base_dir / candidate
        if not full_path.exists():
            raise FileNotFoundError(f"Asset not found: {full_path}")
        if full_path.is_dir():
            return self._resolve_media_file_from_directory(full_path)
        return full_path

    def _resolve_media_file_from_directory(self, directory: Path) -> Path:
        """Resolve a directory-backed asset to the most likely media file inside it."""
        # Prefer direct children first, then fall back to recursive search for
        # Stash/library layouts that keep media in nested folders.
        media_candidates = [
            path for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in self._MEDIA_SUFFIX_PRIORITY
        ]

        used_recursive_scan = False
        if not media_candidates:
            used_recursive_scan = True
            media_candidates = [
                path for path in directory.rglob("*")
                if path.is_file() and path.suffix.lower() in self._MEDIA_SUFFIX_PRIORITY
            ]

        if not media_candidates:
            raise FileNotFoundError(
                f"Asset resolved to a directory with no supported media files: {directory}"
            )

        directory_name = directory.name.lower()

        def sort_key(path: Path) -> Tuple[int, int, int, str]:
            stem_matches_directory = 0 if path.stem.lower() == directory_name else 1
            suffix_priority = self._MEDIA_SUFFIX_PRIORITY.get(path.suffix.lower(), 99)
            relative_depth = len(path.relative_to(directory).parts)
            return stem_matches_directory, suffix_priority, relative_depth, str(path).lower()

        media_candidates.sort(key=sort_key)
        chosen = media_candidates[0]

        if used_recursive_scan:
            self.logger.info(
                "resolve_path directory=%s selected_media=%s candidate_count=%s via=recursive",
                directory,
                chosen,
                len(media_candidates),
            )
            return chosen

        if len(media_candidates) > 1:
            self.logger.info(
                "resolve_path directory=%s selected_media=%s candidate_count=%s",
                directory,
                chosen,
                len(media_candidates),
            )
        else:
            self.logger.info("resolve_path directory=%s selected_media=%s", directory, chosen)

        return chosen

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

    def _crop_media_impl(
        self,
        input_path: str,
        output_path: str,
        left_px: int = 0,
        right_px: int = 0,
        top_px: int = 0,
        bottom_px: int = 0,
        preview_only: bool = False,
        video_crf: Optional[int] = None,
        video_preset: Optional[str] = None,
        video_bitrate: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
    ) -> str:
        in_p = self.resolve_path(input_path)
        out_p = self.resolve_output_path(output_path)
        media_is_video = self._is_video(in_p)

        # Validate crop values and warn about negatives.
        for name, val in [("left_px", left_px), ("right_px", right_px), ("top_px", top_px), ("bottom_px", bottom_px)]:
            if val < 0:
                self.logger.warning("crop_media %s is negative (%d); treated as 0", name, val)

        left_px = max(0, int(left_px))
        right_px = max(0, int(right_px))
        top_px = max(0, int(top_px))
        bottom_px = max(0, int(bottom_px))

        if media_is_video:
            return self._crop_video(
                in_p, out_p, left_px, right_px, top_px, bottom_px,
                preview_only=preview_only,
                video_crf=video_crf,
                video_preset=video_preset,
                video_bitrate=video_bitrate,
                audio_bitrate=audio_bitrate,
            )
        else:
            return self._crop_image(
                in_p, out_p, left_px, right_px, top_px, bottom_px,
                preview_only=preview_only,
            )

    def _stack_media_impl(
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

    def generate_text_overlay(
        self,
        text_data: str,
        video_width: Optional[int],
        video_height: Optional[int],
        output_path: str,
        media_path: Optional[str] = None,
        horizontal_align: str = "center",
        vertical_align: str = "center",
        padding: int = 6,
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
        return self.execute(
            "generate_text_overlay",
            {
                "text_data": text_data,
                "video_width": video_width,
                "video_height": video_height,
                "output_path": output_path,
                "media_path": media_path,
                "horizontal_align": horizontal_align,
                "vertical_align": vertical_align,
                "padding": padding,
                "stroke_width": stroke_width,
                "stroke_fill": stroke_fill,
                "shadow_enabled": shadow_enabled,
                "font_size": font_size,
                "background_color": background_color,
                "line_height": line_height,
                "paragraph_spacing": paragraph_spacing,
                "paragraph_indent_px": paragraph_indent_px,
                "compose_on_media": compose_on_media,
                "font_path": font_path,
                "image_quality": image_quality,
                "png_compress_level": png_compress_level,
                "optimize": optimize,
            },
        )

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
        text_padding: int = 6,
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
        return self.execute(
            "apply_text_overlay",
            {
                "input_path": input_path,
                "output_path": output_path,
                "text": text,
                "text_structured": text_structured,
                "overlay_dir": overlay_dir,
                "start_time": start_time,
                "end_time": end_time,
                "position": position,
                "width": width,
                "height": height,
                "match_base_size": match_base_size,
                "text_align": text_align,
                "text_vertical_align": text_vertical_align,
                "text_padding": text_padding,
                "font_size": font_size,
                "font_path": font_path,
                "stroke_width": stroke_width,
                "stroke_fill": stroke_fill,
                "shadow_enabled": shadow_enabled,
                "background_color": background_color,
                "line_height": line_height,
                "paragraph_spacing": paragraph_spacing,
                "paragraph_indent_px": paragraph_indent_px,
                "overlay_name": overlay_name,
                "output_duration_sec": output_duration_sec,
                "preview_only": preview_only,
                "video_crf": video_crf,
                "video_preset": video_preset,
                "video_bitrate": video_bitrate,
                "audio_bitrate": audio_bitrate,
            },
        )

    def _apply_multi_text_overlays_impl(
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
        return self.execute(
            "apply_multi_text_overlays",
            {
                "base_media_path": base_media_path,
                "overlays": overlays,
                "output_path": output_path,
                "overlay_dir": overlay_dir,
                "output_duration_sec": output_duration_sec,
                "font_path": font_path,
                "preview_only": preview_only,
                "video_crf": video_crf,
                "video_preset": video_preset,
                "video_bitrate": video_bitrate,
                "audio_bitrate": audio_bitrate,
            },
        )
