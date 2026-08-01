from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from .base import OperationContext, OperationHandler
from .registry import register_operation


@register_operation
class WriteVideoOperation(OperationHandler):
    name = "write_video"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["clip", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> None:
        self.validate(params)
        clip = params["clip"]
        output_path = params["output_path"]
        output_path_path = output_path if isinstance(output_path, Path) else Path(output_path)
        write_kwargs: Dict[str, Any] = {
            "codec": params.get("video_codec", "libx264"),
            "audio_codec": params.get("audio_codec", "aac"),
        }
        if params.get("fps") is not None:
            write_kwargs["fps"] = float(params["fps"])
        if params.get("video_bitrate"):
            write_kwargs["bitrate"] = str(params["video_bitrate"])
        if params.get("audio_bitrate"):
            write_kwargs["audio_bitrate"] = str(params["audio_bitrate"])

        ffmpeg_params = self._build_ffmpeg_params(params.get("video_crf"), params.get("video_preset"))
        if ffmpeg_params:
            write_kwargs["ffmpeg_params"] = ffmpeg_params

        clip.write_videofile(str(output_path_path), **write_kwargs)

    def _build_ffmpeg_params(self, video_crf: Optional[int], video_preset: Optional[str]) -> Optional[List[str]]:
        ffmpeg_params: List[str] = []
        if video_crf is not None:
            if video_crf < 0 or video_crf > 51:
                raise ValueError("video_crf must be between 0 and 51")
            ffmpeg_params.extend(["-crf", str(int(video_crf))])
        if video_preset is not None:
            ffmpeg_params.extend(["-preset", str(video_preset)])
        return ffmpeg_params or None


@register_operation
class SaveImageOperation(OperationHandler):
    name = "save_image"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["image", "output_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> None:
        self.validate(params)
        image = params["image"]
        output_path = params["output_path"]
        output_path_path = output_path if isinstance(output_path, Path) else Path(output_path)
        suffix = output_path_path.suffix.lower()
        save_kwargs: Dict[str, Any] = {}

        if params.get("optimize") is not None:
            save_kwargs["optimize"] = bool(params["optimize"])

        image_quality = params.get("image_quality")
        if image_quality is not None:
            if image_quality < 1 or image_quality > 100:
                raise ValueError("image_quality must be between 1 and 100")

        png_compress_level = params.get("png_compress_level")
        if png_compress_level is not None:
            if png_compress_level < 0 or png_compress_level > 9:
                raise ValueError("png_compress_level must be between 0 and 9")

        if suffix in {".jpg", ".jpeg"}:
            if image_quality is not None:
                save_kwargs["quality"] = int(image_quality)
            image.convert("RGB").save(str(output_path_path), **save_kwargs)
            return

        if suffix == ".webp":
            if image_quality is not None:
                save_kwargs["quality"] = int(image_quality)
            image.save(str(output_path_path), **save_kwargs)
            return

        if suffix == ".png" and png_compress_level is not None:
            save_kwargs["compress_level"] = int(png_compress_level)

        image.save(str(output_path_path), **save_kwargs)


@register_operation
class ComputeScaleFactorOperation(OperationHandler):
    name = "compute_scale_factor"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["width", "height"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> float:
        self.validate(params)
        width = int(params["width"])
        height = int(params["height"])
        max_long_side = params.get("max_long_side")
        max_short_side = params.get("max_short_side")
        upscale = bool(params.get("upscale", False))
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


@register_operation
class NormalizePositionOperation(OperationHandler):
    name = "normalize_position"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["position"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> Tuple[Any, Any]:
        self.validate(params)
        position = params["position"]
        if isinstance(position, (list, tuple)) and len(position) == 2:
            return position[0], position[1]
        if isinstance(position, str):
            return position, "center"
        return "center", "center"


@register_operation
class PositionToPixelsOperation(OperationHandler):
    name = "position_to_pixels"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["position", "base_w", "base_h", "overlay_w", "overlay_h"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> Tuple[int, int]:
        self.validate(params)
        position = params["position"]
        base_w = int(params["base_w"])
        base_h = int(params["base_h"])
        overlay_w = int(params["overlay_w"])
        overlay_h = int(params["overlay_h"])
        px, py = position
        if isinstance(px, (int, float)):
            x = int(px)
        elif px == "center":
            x = (base_w - overlay_w) // 2
        elif px == "right":
            x = base_w - overlay_w
        else:
            x = 0
        if isinstance(py, (int, float)):
            y = int(py)
        elif py == "center":
            y = (base_h - overlay_h) // 2
        elif py == "bottom":
            y = base_h - overlay_h
        else:
            y = 0
        return x, y
