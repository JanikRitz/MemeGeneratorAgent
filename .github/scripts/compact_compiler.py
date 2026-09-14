from __future__ import annotations

import hashlib
import json
import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import Field

from compact_jobs import (
    Appearance, Branch, Caption, Captions, CompactJob, Concat, Crop, Model,
    Panel, Presets, Scale, Stack, StashScene, Trim,
)
from config_preparation import ConfigPreparationService


STYLES = {
    "meme": dict(size=40, align="center", at="center", padding=6, stroke=3, stroke_color="#000000", shadow=True, background="transparent", line_height=1.0, indent=0),
    "headline": dict(size=24, align="center", at="center", padding=10, stroke=3, stroke_color="#000000", shadow=True, background="transparent", line_height=1.0, indent=0),
    "meme-compact": dict(size=20, align="center", at="center", padding=8, stroke=2, stroke_color="#000000", shadow=True, background="transparent", line_height=1.0, indent=0),
    "panel": dict(size=72, align="center", at="center", padding=16, stroke=0, stroke_color="#000000", shadow=False, background="#ffffff", line_height=1.0, indent=0),
}
QUALITY = {
    "good": {"image": dict(image_quality=82, optimize=True), "video": dict(crf=20, preset="slow", bitrate="3000k", audio_bitrate="160k")},
    "balanced": {"image": dict(image_quality=42, optimize=True), "video": dict(crf=30, preset="fast", bitrate="1200k", audio_bitrate="96k")},
    "crunchy": {"image": dict(image_quality=24, optimize=True)},
    "super_crunchy": {"image": dict(image_quality=14, optimize=True), "video": dict(crf=40, preset="veryfast", bitrate="380k", audio_bitrate="40k")},
}
TEXT_KEYS = {
    "font": "font_path", "size": "font_size", "align": "text_align", "at": "text_vertical_align",
    "padding": "text_padding", "stroke": "stroke_width", "stroke_color": "stroke_fill",
    "shadow": "shadow_enabled", "background": "background_color", "line_height": "line_height",
    "paragraph_spacing": "paragraph_spacing", "indent": "paragraph_indent_px",
}
ENCODE_KEYS = {"codec": "video_codec", "crf": "video_crf", "preset": "video_preset", "bitrate": "video_bitrate"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


class PlannedStep(Model):
    source: str
    operation: str
    params: dict[str, Any]


class ExecutionPlan(Model):
    format: str = "meme-plan/v1"
    output: str
    scratch: str
    steps: list[PlannedStep] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)

    def execute(self, engine, preview: bool = False, release: bool = False) -> str:
        from operations.base import OperationContext

        scratch = Path(self.scratch)
        scratch.mkdir(parents=True, exist_ok=False)
        outputs: dict[str, str] = {}
        succeeded = False
        try:
            result = ""
            for step in self.steps:
                params = dict(step.params)
                for key in ("input_path", "base_media_path", "media_path", "path1", "path2"):
                    if key in params:
                        params[key] = outputs.get(params[key], params[key])
                if "clip_paths" in params:
                    params["clip_paths"] = [outputs.get(path, path) for path in params["clip_paths"]]
                context = OperationContext(engine=engine, logger=engine.logger, preview_only_override=preview)
                try:
                    result = engine.execute(step.operation, params, context)
                except Exception as exc:
                    raise ValueError(f"{step.source}: {exc}") from exc
                outputs[step.params["output_path"]] = result
            succeeded = True
            return result
        finally:
            if release or not succeeded:
                shutil.rmtree(scratch)


@dataclass
class Media:
    path: str
    is_video: bool
    width: int | None
    height: int | None
    duration: float | None


class CompactCompiler:
    def __init__(
        self, root: Path, engine, resolve: Callable[[Any], Any] | None = None,
        probe: Callable[[str], dict] | None = None, presets: Presets | None = None,
    ):
        self.root = root.resolve()
        self.engine = engine
        preparation = ConfigPreparationService()
        self.resolve = resolve or (lambda value: preparation.prepare_config({"value": value}, self.root)["value"])
        self.probe = probe or engine.get_media_info
        self.require_existing_sources = probe is None
        self.media_cache: dict[str, Media] = {}
        preset_values = presets or Presets()
        self.styles = dict(STYLES)
        for name, value in preset_values.styles.items():
            self.styles[name] = {**STYLES.get(name, STYLES["meme"]), **value.model_dump(exclude_none=True)}
        self.quality = dict(QUALITY)
        for name, value in preset_values.quality.items():
            profile = self.quality.get(name, {})
            override = value.model_dump(exclude_none=True)
            self.quality[name] = {
                kind: {**profile.get(kind, {}), **settings}
                for kind, settings in {**profile, **override}.items()
            }

    def source(self, value, label: str) -> Media:
        raw = value.model_dump(by_alias=True, exclude_none=True) if isinstance(value, Model) else value
        cache_key = json.dumps(raw, sort_keys=True)
        if cache_key not in self.media_cache:
            try:
                resolved = self.resolve(raw)
                candidate = Path(str(resolved))
                candidate = candidate if candidate.is_absolute() else self.root / candidate
                if self.require_existing_sources and not candidate.exists():
                    raise FileNotFoundError(f"Asset not found: {candidate}")
                path = str(self.engine.resolve_path(str(candidate)).resolve())
                info = self.probe(path)
                self.media_cache[cache_key] = Media(path, info["is_video"], info["width"], info["height"], info.get("duration_sec"))
            except Exception as exc:
                raise ValueError(f"{label}: {exc}") from exc
        return self.media_cache[cache_key]

    def compile(self, job: CompactJob, preview: bool = False, overrides: dict | None = None) -> ExecutionPlan:
        self.job = job
        self.preview = preview
        self.overrides = {key: value for key, value in (overrides or {}).items() if value is not None}
        self.media_cache.clear()
        output = Path(job.output)
        output = (output if output.is_absolute() else self.root / output).resolve()
        if output.suffix.lower() not in IMAGE_SUFFIXES | VIDEO_SUFFIXES:
            raise ValueError("output: use a supported image or video extension (GIF export is not supported)")
        actual_output = output.with_suffix(".png") if preview else output
        digest = hashlib.sha256(job.model_dump_json(by_alias=True).encode()).hexdigest()[:12]
        scratch = output.parent / ".meme-scratch" / f"{digest}-{uuid.uuid4().hex}"
        self.plan = ExecutionPlan(output=str(actual_output), scratch=str(scratch))
        current = self.source(job.input, "input")
        for index, step in enumerate(job.steps):
            if preview and isinstance(step, Concat) and index != len(job.steps) - 1:
                raise ValueError(f"steps[{index}]: preview concat must be the final step")
            current = self.compile_step(step, current, f"steps[{index}]", output if index == len(job.steps) - 1 else None, job.input if index == 0 else None)
        self.plan.sources = sorted({media.path for media in self.media_cache.values()})
        for source in self.plan.sources:
            if actual_output == Path(source) or output == Path(source):
                raise ValueError("output: must not overwrite an input source")
        return self.plan

    def text(self, entry: Appearance, shared: Appearance | None = None, panel: bool = False) -> dict:
        style = entry.style or (shared.style if shared else None) or ("panel" if panel else "meme")
        if style not in self.styles:
            raise ValueError(f"unknown style {style!r}")
        values = dict(self.styles[style])
        if self.job.font:
            values["font"] = self.job.font
        for layer in (shared, entry):
            if layer is not None:
                values.update({key: value for key, value in layer.model_dump(exclude_none=True).items() if key in TEXT_KEYS})
        if values.get("font"):
            self.engine._resolve_font_path(values["font"])
        from PIL import ImageColor
        for key in ("background", "stroke_color"):
            if values[key] != "transparent":
                ImageColor.getcolor(values[key], "RGBA")
        return {TEXT_KEYS[key]: value for key, value in values.items()}

    def encoding(self, step, suffix: str) -> dict:
        kind = "image" if suffix in IMAGE_SUFFIXES else "video"
        if self.job.quality is not None and self.job.quality not in self.quality:
            raise ValueError(f"unknown quality {self.job.quality!r}")
        profile = self.quality.get(self.job.quality, {})
        if profile and kind not in profile:
            raise ValueError(f"quality {self.job.quality!r} has no {kind} profile")
        values = dict(profile.get(kind, {}))
        values.update(self.job.encode.model_dump(exclude_none=True))
        values.update(step.encode.model_dump(exclude_none=True))
        values.update(self.overrides)
        if kind == "image":
            allowed = {"optimize"}
            allowed.add("png_compress_level" if suffix == ".png" else "image_quality")
        else:
            allowed = {"codec", "crf", "preset", "bitrate", "audio_bitrate", "threads"}
            values.setdefault("codec", "libx264")
            codec = values["codec"]
            preset = values.get("preset")
            explicit_preset = any("preset" in layer for layer in (self.job.encode.model_dump(exclude_none=True), step.encode.model_dump(exclude_none=True), self.overrides))
            if codec == "h264_nvenc" and preset and not explicit_preset:
                values["preset"] = {"slow": "p6", "fast": "p4", "veryfast": "p2"}.get(preset, preset)
                preset = values["preset"]
            valid = {"libx264": {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo"}, "h264_nvenc": {f"p{index}" for index in range(1, 8)}}
            if preset and codec in valid and preset not in valid[codec]:
                raise ValueError(f"encode.preset {preset!r} is invalid for {codec}")
        return {ENCODE_KEYS.get(key, key): value for key, value in values.items() if key in allowed}

    def compile_step(self, step, media: Media, label: str, final: Path | None = None, original=None) -> Media:
        try:
            return self._compile_step(step, media, label, final, original)
        except Exception as exc:
            raise ValueError(f"{label}: {exc}") from exc

    def _compile_step(self, step, media: Media, label: str, final: Path | None, original) -> Media:
        width, height, duration = media.width, media.height, media.duration
        video = media.is_video or isinstance(step, (Trim, Concat, Captions))
        branch_paths = []
        if isinstance(step, Concat):
            if not shutil.which("ffprobe"):
                raise ValueError("concat requires ffprobe on PATH")
            if not media.is_video:
                raise ValueError("concat requires video/GIF inputs, not still images")
            branch_paths.append(media.path)
            branch_durations = [duration]
            for index, item in enumerate(step.with_):
                branch_label = f"{label}.with[{index}]"
                other = self.source(item.input if isinstance(item, Branch) else item, branch_label)
                if not other.is_video:
                    raise ValueError(f"{branch_label}: concat requires video/GIF inputs")
                if isinstance(item, Branch):
                    for branch_index, branch_step in enumerate(item.steps):
                        other = self.compile_step(branch_step, other, f"{branch_label}.steps[{branch_index}]", original=item.input if branch_index == 0 else None)
                branch_paths.append(other.path)
                branch_durations.append(other.duration)
            duration = sum(branch_durations) if all(value is not None for value in branch_durations) else None
            width = height = None
        other = None
        if isinstance(step, Stack):
            if isinstance(step.with_, Branch):
                other = self.source(step.with_.input, f"{label}.with")
                for branch_index, branch_step in enumerate(step.with_.steps):
                    other = self.compile_step(branch_step, other, f"{label}.with.steps[{branch_index}]", original=step.with_.input if branch_index == 0 else None)
            else:
                other = self.source(step.with_, f"{label}.with")
            video = video or other.is_video
            width = height = None
        requested_suffix = final.suffix.lower() if final else "." + (step.intermediate_format or ("mp4" if video else "png"))
        if isinstance(step, (Caption, Panel)) and requested_suffix in VIDEO_SUFFIXES:
            video = True
        if requested_suffix in IMAGE_SUFFIXES and video and not self.preview:
            raise ValueError("video output requires a video suffix; use --preview-only for a PNG")
        if requested_suffix in VIDEO_SUFFIXES and not video:
            if isinstance(step, Stack):
                video = True
            else:
                raise ValueError("this operation cannot convert a still image to video")
        output = final or Path(self.plan.scratch) / f"{len(self.plan.steps):03d}-{step.op}{requested_suffix}"
        if self.preview:
            output = output.with_suffix(".png")
        params: dict[str, Any] = {"output_path": str(output), **self.encoding(step, requested_suffix)}
        operation = ""
        if isinstance(step, Trim):
            if self.preview and Path(media.path).suffix.lower() in IMAGE_SUFFIXES:
                raise ValueError("preview trim must precede transformations that produce a still preview")
            if not media.is_video:
                raise ValueError("trim requires video/GIF input")
            start, end = step.start, step.end
            if step.marker:
                scene = step.marker.scene
                if scene is None and isinstance(original, StashScene):
                    scene = original.scene
                if scene is None and isinstance(original, str) and original.startswith("stash:scene:"):
                    scene = original.removeprefix("stash:scene:")
                if scene is None:
                    raise ValueError("marker.scene is required unless the input is a Stash scene")
                spec = {"scene_id": scene, "marker_id" if step.marker.id is not None else "marker_title": step.marker.id if step.marker.id is not None else step.marker.title}
                start = self.resolve({"$stash_marker_time": {**spec, "time": "start"}})
                end_spec = {**spec, "time": "end"}
                if step.marker.fallback_duration is not None:
                    end_spec["default_duration_sec"] = step.marker.fallback_duration
                end = self.resolve({"$stash_marker_time": end_spec})
            if start is None or end is None or not 0 <= start < end or (duration is not None and end > duration + 0.001):
                raise ValueError("trim range must satisfy 0 <= start < end <= source duration")
            duration = (end - start) * (2 if step.boomerang else 1)
            operation = "trim_video"
            params.update(input_path=media.path, start_sec=start, end_sec=end, boomerang=step.boomerang)
        elif isinstance(step, Scale):
            operation = "scale_media"
            params.update(input_path=media.path, max_long_side=step.max_long_side, max_short_side=step.max_short_side, upscale=step.upscale)
            if width and height:
                factors = [limit / bound for limit, bound in ((step.max_long_side, max(width, height)), (step.max_short_side, min(width, height))) if limit is not None]
                factor = min(factors + ([] if step.upscale else [1.0]))
                width, height = max(1, round(width * factor)), max(1, round(height * factor))
                if video and not self.preview:
                    width, height = max(2, width - width % 2), max(2, height - height % 2)
        elif isinstance(step, Crop):
            operation = "crop_media"
            params.update(input_path=media.path, left_px=step.left, right_px=step.right, top_px=step.top, bottom_px=step.bottom)
            if width and height:
                width -= step.left + step.right
                height -= step.top + step.bottom
                if width <= 0 or height <= 0:
                    raise ValueError("crop removes the entire frame")
                if video and not self.preview:
                    width, height = width - width % 2, height - height % 2
                    if width < 2 or height < 2:
                        raise ValueError("video crop must leave at least 2x2 pixels")
        elif isinstance(step, (Caption, Captions, Panel)):
            duration_override = step.duration or self.job.duration
            if not media.is_video and video:
                duration = duration_override or (max((item.end or 3.0 for item in step.items), default=3.0) if isinstance(step, Captions) else 5.0 if isinstance(step, Panel) else 3.0)
            if isinstance(step, Caption) and not video:
                if step.start is not None or step.end is not None:
                    raise ValueError("still-image captions cannot have timing")
                operation = "generate_text_overlay"
                appearance = self.text(step)
                for old, new in (("text_align", "horizontal_align"), ("text_vertical_align", "vertical_align"), ("text_padding", "padding")):
                    appearance[new] = appearance.pop(old)
                params.update(appearance, media_path=media.path, text_data=step.text, compose_on_media=True)
            else:
                params.update(base_media_path=media.path, overlay_dir=str(Path(self.plan.scratch) / f"{len(self.plan.steps):03d}-overlays"))
                if duration_override is not None:
                    params["output_duration_sec"] = duration_override
                if isinstance(step, Panel):
                    operation = "add_text_side_box"
                    params.update(self.text(step, panel=True), text_data=step.text, side=step.side, auto_size=step.auto_size if step.auto_size is not None else step.pixels is None)
                    if step.ratio is not None:
                        params["box_size_ratio"] = step.ratio
                    if step.pixels is not None:
                        params["box_size_px"] = step.pixels
                    width = height = None
                else:
                    operation = "apply_multi_text_overlays"
                    items = step.items if isinstance(step, Captions) else [step]
                    overlays = []
                    for item in items:
                        overlay = dict(self.text(item, step if isinstance(step, Captions) else None), text=item.text, match_base_size=True, start_time=item.start or 0)
                        if item.end is not None:
                            overlay["end_time"] = item.end
                        if duration is not None and item.end is not None and item.end > duration:
                            logging.getLogger("meme_engine").warning("%s: caption end exceeds input duration", label)
                        overlays.append(overlay)
                    params["overlays"] = overlays
                    if media.is_video and any(item.end is not None for item in items):
                        duration = max([duration or 0] + [item.end for item in items if item.end is not None])
        elif isinstance(step, Stack):
            operation = "stack_media"
            params.update(path1=media.path, path2=other.path, orientation=step.direction, duration_sec=step.duration or self.job.duration or 3.0)
            duration = None
        elif isinstance(step, Concat):
            operation = "concatenate_clips"
            params["clip_paths"] = branch_paths
        self.plan.steps.append(PlannedStep(source=label, operation=operation, params=params))
        return Media(str(output), video, width, height, duration)