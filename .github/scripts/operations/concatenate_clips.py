from __future__ import annotations

import json
import math
import shutil
import subprocess
from contextlib import ExitStack
from typing import Any, Dict

import numpy as np
from PIL import Image
from moviepy import AudioClip, CompositeAudioClip, CompositeVideoClip, VideoFileClip, concatenate_videoclips

from .base import OperationContext, OperationHandler
from .registry import register_operation


def canvas_size(sizes: list[tuple[int, int]]) -> tuple[int, int]:
    if not sizes or any(width <= 0 or height <= 0 for width, height in sizes):
        raise ValueError("concat requires positive input dimensions")
    first_width, first_height = sizes[0]
    factor = max(max(size) for size in sizes) / max(first_width, first_height)
    return 2 * math.ceil(first_width * factor / 2), 2 * math.ceil(first_height * factor / 2)


def fitted_size(size: tuple[int, int], canvas: tuple[int, int]) -> tuple[int, int]:
    factor = min(canvas[0] / size[0], canvas[1] / size[1])
    return max(1, min(canvas[0], round(size[0] * factor))), max(1, min(canvas[1], round(size[1] * factor)))


def display_size(clip) -> tuple[int, int]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("Concatenation requires ffprobe on PATH to normalize pixel aspect ratios")
    process = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=sample_aspect_ratio", "-of", "json", clip.filename],
        check=True, capture_output=True, text=True,
    )
    streams = json.loads(process.stdout).get("streams", [])
    ratio = streams[0].get("sample_aspect_ratio", "1:1") if streams else "1:1"
    width, height = clip.size
    if ratio not in ("N/A", "0:1"):
        numerator, denominator = map(int, ratio.split(":"))
        if numerator > 0 and denominator > 0:
            if clip.reader.rotation in (90, 270):
                height = round(height * numerator / denominator)
            else:
                width = round(width * numerator / denominator)
    return max(1, width), max(1, height)


@register_operation
class ConcatenateClipsOperation(OperationHandler):
    name = "concatenate_clips"

    def validate(self, params: Dict[str, Any]) -> None:
        paths = params.get("clip_paths")
        if not isinstance(paths, list) or len(paths) < 2 or any(not isinstance(path, str) or not path for path in paths):
            raise ValueError("clip_paths must contain at least two media paths")
        if not params.get("output_path"):
            raise ValueError("output_path is required")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        self.validate(params)
        preview = context.preview_only_override
        if preview is None:
            preview = bool(params.get("preview_only", False))
        paths = [engine.resolve_path(path) for path in params["clip_paths"]]
        output = engine.resolve_output_path(params["output_path"])
        with ExitStack() as resources:
            clips, sizes, frames = [], [], []
            for path in paths:
                if engine._is_video(path):
                    clip = resources.enter_context(VideoFileClip(str(path)))
                    clips.append(clip)
                    sizes.append(display_size(clip))
                    if preview:
                        frames.append(Image.fromarray(clip.get_frame(0)).convert("RGB"))
                elif preview:
                    with Image.open(path) as image:
                        frames.append(image.convert("RGB"))
                        sizes.append(image.size)
                else:
                    raise ValueError("concat requires video/GIF inputs, not still images")
            canvas = canvas_size(sizes)
            if preview:
                sheet = Image.new("RGB", (canvas[0], canvas[1] * len(frames)), "black")
                for index, (frame, size) in enumerate(zip(frames, sizes)):
                    fitted = frame.resize(fitted_size(size, canvas), Image.Resampling.LANCZOS)
                    sheet.paste(fitted, ((canvas[0] - fitted.width) // 2, index * canvas[1] + (canvas[1] - fitted.height) // 2))
                output = output.with_suffix(".png")
                sheet.save(output)
                return str(output)
            normalized = []
            for clip, size in zip(clips, sizes):
                target = fitted_size(size, canvas)
                resized = clip.resized(new_size=target).with_position(((canvas[0] - target[0]) // 2, (canvas[1] - target[1]) // 2))
                resources.callback(resized.close)
                composed = CompositeVideoClip([resized], size=canvas, bg_color=(0, 0, 0)).with_duration(clip.duration)
                resources.callback(composed.close)
                if clip.audio is not None:
                    def silent_frame(time, channels=clip.audio.nchannels):
                        return np.zeros((len(time), channels)) if isinstance(time, np.ndarray) else np.zeros(channels)

                    silence = AudioClip(silent_frame, duration=clip.duration, fps=44100)
                    resources.callback(silence.close)
                    audio = clip.audio.subclipped(0, min(clip.duration, clip.audio.duration))
                    padded_audio = CompositeAudioClip([silence, audio]).with_duration(clip.duration)
                    resources.callback(padded_audio.close)
                    composed = composed.with_audio(padded_audio)
                    resources.callback(composed.close)
                normalized.append(composed)
            final_clip = concatenate_videoclips(normalized, method="compose", bg_color=(0, 0, 0))
            resources.callback(final_clip.close)
            fps = float(clips[0].reader.infos.get("video_fps") or 24)
            engine._write_video(
                final_clip, output, fps=fps, video_codec=params.get("video_codec") or "libx264",
                video_crf=params.get("video_crf"), video_preset=params.get("video_preset"),
                video_bitrate=params.get("video_bitrate"), audio_bitrate=params.get("audio_bitrate"), threads=params.get("threads"),
            )
            return str(output)
