import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

try:
    from operations.base import OperationContext
    from operations.registry import OperationRegistry, build_default_registry
except ImportError:
    from .operations.base import OperationContext
    from .operations.registry import OperationRegistry, build_default_registry

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
        return build_default_registry()

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
        return self.execute("get_media_info", {"input_path": input_path})

    def _get_media_info_impl(self, input_path: str) -> Dict[str, Any]:
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
        return self.execute("resolve_path", {"path_value": path_value})

    def _resolve_path_impl(self, path_value: str) -> Path:
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
        return self.execute("resolve_output_path", {"path_value": path_value})

    def _resolve_output_path_impl(self, path_value: str) -> Path:
        candidate = Path(path_value)
        out_path = candidate if candidate.is_absolute() else self.base_dir / candidate
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return out_path

    def _normalize_position(self, position: Any) -> Tuple[Any, Any]:
        return self.execute("normalize_position", {"position": position})

    def _position_to_pixels(
        self,
        position: Tuple[Any, Any],
        base_w: int,
        base_h: int,
        overlay_w: int,
        overlay_h: int,
    ) -> Tuple[int, int]:
        return self.execute(
            "position_to_pixels",
            {
                "position": position,
                "base_w": base_w,
                "base_h": base_h,
                "overlay_w": overlay_w,
                "overlay_h": overlay_h,
            },
        )

    def _write_video(
        self,
        clip,
        output_path: Path,
        fps: Optional[float] = None,
        video_codec: str = "h264_nvenc",
        audio_codec: str = "aac",
        video_crf: Optional[int] = None,
        video_preset: Optional[str] = None,
        video_bitrate: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
        threads: Optional[int] = None,
    ) -> None:
        self.execute(
            "write_video",
            {
                "clip": clip,
                "output_path": output_path,
                "fps": fps,
                "video_codec": video_codec,
                "audio_codec": audio_codec,
                "video_crf": video_crf,
                "video_preset": video_preset,
                "video_bitrate": video_bitrate,
                "audio_bitrate": audio_bitrate,
                "threads": threads,
            },
        )

    def _save_image(
        self,
        image: Image.Image,
        output_path: Path,
        image_quality: Optional[int] = None,
        png_compress_level: Optional[int] = None,
        optimize: Optional[bool] = None,
    ) -> None:
        self.execute(
            "save_image",
            {
                "image": image,
                "output_path": output_path,
                "image_quality": image_quality,
                "png_compress_level": png_compress_level,
                "optimize": optimize,
            },
        )

    def _compute_scale_factor(
        self,
        width: int,
        height: int,
        max_long_side: Optional[int],
        max_short_side: Optional[int],
        upscale: bool,
    ) -> float:
        return self.execute(
            "compute_scale_factor",
            {
                "width": width,
                "height": height,
                "max_long_side": max_long_side,
                "max_short_side": max_short_side,
                "upscale": upscale,
            },
        )

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
        video_codec: Optional[str] = None,
        threads: Optional[int] = None,
    ) -> str:
        return self.execute(
            "crop_media_impl",
            {
                "input_path": input_path,
                "output_path": output_path,
                "left_px": left_px,
                "right_px": right_px,
                "top_px": top_px,
                "bottom_px": bottom_px,
                "preview_only": preview_only,
                "video_crf": video_crf,
                "video_preset": video_preset,
                "video_bitrate": video_bitrate,
                "audio_bitrate": audio_bitrate,
                "video_codec": video_codec,
                "threads": threads,
            },
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
        video_codec: Optional[str] = None,
        threads: Optional[int] = None,
    ) -> str:
        return self.execute(
            "stack_media_impl",
            {
                "path1": path1,
                "path2": path2,
                "output_path": output_path,
                "orientation": orientation,
                "duration_sec": duration_sec,
                "video_crf": video_crf,
                "video_preset": video_preset,
                "video_bitrate": video_bitrate,
                "audio_bitrate": audio_bitrate,
                "video_codec": video_codec,
                "threads": threads,
            },
        )

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
        video_codec: Optional[str] = None,
        threads: Optional[int] = None,
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
                "video_codec": video_codec,
                "threads": threads,
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
        video_codec: Optional[str] = None,
        threads: Optional[int] = None,
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
                "video_codec": video_codec,
                "threads": threads,
            },
        )
