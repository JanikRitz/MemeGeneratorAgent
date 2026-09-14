from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


PositiveInt = Annotated[int, Field(gt=0)]
Positive = Annotated[float, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0)]
Nonempty = Annotated[str, Field(min_length=1)]
Identifier = Union[StrictInt, Nonempty]


class HydrusFile(Model):
    file_id: Identifier | None = None
    hash: Nonempty | None = None

    @model_validator(mode="after")
    def one_identifier(self):
        if (self.file_id is None) == (self.hash is None):
            raise ValueError("provide exactly one of file_id or hash")
        return self


class HydrusSearch(Model):
    tags: list[Nonempty] | Nonempty
    index: Annotated[int, Field(ge=0)] = 0
    file_service_keys: list[str] | None = None
    tag_service_key: str | None = None


class StashScene(Model):
    scene: Identifier = Field(alias="$stash_scene_path")


class StashImage(Model):
    image: Identifier = Field(alias="$stash_image_path")


class HydrusSource(Model):
    file: HydrusFile | Identifier = Field(alias="$hydrus_file_path")


class HydrusSearchSource(Model):
    search: HydrusSearch = Field(alias="$hydrus_search_path")


Source = Union[Nonempty, StashScene, StashImage, HydrusSource, HydrusSearchSource]
Style = Nonempty
Quality = Nonempty


class Encoding(Model):
    codec: Nonempty | None = None
    crf: Annotated[int, Field(ge=0, le=51)] | None = None
    preset: Nonempty | None = None
    bitrate: Annotated[str, Field(pattern=r"^\d+(?:\.\d+)?[kKmM]?$")] | None = None
    audio_bitrate: Annotated[str, Field(pattern=r"^\d+(?:\.\d+)?[kKmM]?$")] | None = None
    threads: PositiveInt | None = None
    image_quality: Annotated[int, Field(ge=1, le=100)] | None = None
    png_compress_level: Annotated[int, Field(ge=0, le=9)] | None = None
    optimize: bool | None = None


class Appearance(Model):
    style: Style | None = None
    font: Nonempty | None = None
    size: PositiveInt | None = None
    align: Literal["left", "center", "right"] | None = None
    at: Literal["top", "center", "bottom"] | None = None
    padding: Annotated[int, Field(ge=0)] | None = None
    stroke: Annotated[int, Field(ge=0)] | None = None
    stroke_color: Nonempty | None = None
    shadow: bool | None = None
    background: Nonempty | None = None
    line_height: Positive | None = None
    paragraph_spacing: Annotated[int, Field(ge=0)] | None = None
    indent: Annotated[int, Field(ge=0)] | None = None


class StylePreset(Appearance):
    @model_validator(mode="after")
    def cannot_reference_style(self):
        if self.style is not None:
            raise ValueError("style presets cannot reference another style")
        return self


class QualityPreset(Model):
    image: Encoding | None = None
    video: Encoding | None = None

    @model_validator(mode="after")
    def needs_media_profile(self):
        if self.image is None and self.video is None:
            raise ValueError("quality preset requires image or video settings")
        return self


class Presets(Model):
    styles: dict[Nonempty, StylePreset] = Field(default_factory=dict)
    quality: dict[Nonempty, QualityPreset] = Field(default_factory=dict)


class Step(Model):
    encode: Encoding = Field(default_factory=Encoding)
    intermediate_format: Literal["png", "jpg", "jpeg", "webp", "mp4"] | None = None


class Marker(Model):
    id: Identifier | None = None
    title: Nonempty | None = None
    scene: Identifier | None = None
    fallback_duration: Positive | None = None

    @model_validator(mode="after")
    def one_identifier(self):
        if (self.id is None) == (self.title is None):
            raise ValueError("provide exactly one of marker.id or marker.title")
        return self


class Trim(Step):
    op: Literal["trim"]
    start: Nonnegative | None = None
    end: Positive | None = None
    marker: Marker | None = None
    boomerang: bool = False

    @model_validator(mode="after")
    def valid_interval(self):
        if self.marker is not None:
            if self.start is not None or self.end is not None:
                raise ValueError("marker cannot be combined with start/end")
        elif self.start is None or self.end is None or self.end <= self.start:
            raise ValueError("trim requires 0 <= start < end")
        return self


class Scale(Step):
    op: Literal["scale"]
    max_long_side: PositiveInt | None = None
    max_short_side: PositiveInt | None = None
    upscale: bool = False

    @model_validator(mode="after")
    def needs_bound(self):
        if self.max_long_side is None and self.max_short_side is None:
            raise ValueError("scale requires max_long_side or max_short_side")
        return self


class Crop(Step):
    op: Literal["crop"]
    left: Annotated[int, Field(ge=0)] = 0
    right: Annotated[int, Field(ge=0)] = 0
    top: Annotated[int, Field(ge=0)] = 0
    bottom: Annotated[int, Field(ge=0)] = 0


class TimedText(Appearance):
    text: Nonempty
    start: Nonnegative | None = None
    end: Positive | None = None

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end is not None and self.end <= (self.start or 0):
            raise ValueError("caption end must be greater than start")
        return self


class Caption(Step, TimedText):
    op: Literal["caption"]
    duration: Positive | None = None


class Captions(Step, Appearance):
    op: Literal["captions"]
    items: Annotated[list[TimedText], Field(min_length=1)]
    duration: Positive | None = None


class Panel(Step, Appearance):
    op: Literal["panel"]
    text: Nonempty
    side: Literal["top", "bottom", "left", "right"] = "top"
    ratio: Positive | None = None
    pixels: PositiveInt | None = None
    auto_size: bool | None = None
    duration: Positive | None = None

    @model_validator(mode="after")
    def valid_sizing(self):
        if self.pixels is not None and (self.ratio is not None or self.auto_size is True):
            raise ValueError("pixels cannot be combined with ratio or auto_size=true")
        return self


BranchStep = Annotated[Union[Trim, Scale, Crop], Field(discriminator="op")]


class Branch(Model):
    input: Source
    steps: Annotated[list[BranchStep], Field(min_length=1)]


class Concat(Step):
    op: Literal["concat"]
    with_: Annotated[list[Union[Source, Branch]], Field(min_length=1)] = Field(alias="with")


class Stack(Step):
    op: Literal["stack"]
    with_: Source = Field(alias="with")
    direction: Literal["horizontal", "vertical"] = "horizontal"
    duration: Positive | None = None


JobStep = Annotated[Union[Trim, Scale, Crop, Caption, Captions, Panel, Stack, Concat], Field(discriminator="op")]


class CompactJob(Model):
    format: Literal["meme/v1"]
    input: Source
    output: Nonempty
    steps: Annotated[list[JobStep], Field(min_length=1)]
    font: Nonempty | None = None
    quality: Quality | None = None
    encode: Encoding = Field(default_factory=Encoding)
    duration: Positive | None = None

    @model_validator(mode="after")
    def valid_topology(self):
        for index, step in enumerate(self.steps):
            if index and isinstance(step, Trim) and step.marker is not None:
                raise ValueError(f"steps[{index}]: marker trim must be first")
            if index == len(self.steps) - 1 and step.intermediate_format is not None:
                raise ValueError(f"steps[{index}]: intermediate_format is only for nonfinal steps")
            if isinstance(step, Concat):
                for branch in step.with_:
                    if isinstance(branch, Branch):
                        for branch_index, branch_step in enumerate(branch.steps):
                            if branch_index and isinstance(branch_step, Trim) and branch_step.marker:
                                raise ValueError("branch marker trim must be first")
        return self


def validate_job(value: object) -> CompactJob:
    return CompactJob.model_validate(value)