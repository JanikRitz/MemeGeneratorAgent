# MemeEngine Improvements TODO

This document outlines planned improvements for `MemeEngine`, categorized into performance, architecture, rich text features, and developer experience. Each task includes the goal, specific files/code to touch, and step-by-step verification instructions.

---

## Pillar 1: Performance & Resource Management

### 1. Font Resolution & Loading Caching [COMPLETED]
- **Goal**: Eliminate disk I/O overhead caused by repeated font file searches and `ImageFont.truetype(...)` calls during text layout, line wrapping, and metric estimations.
- **Code to Touch**:
  - [`RichTextRenderer.py`](file:///.github/scripts/RichTextRenderer.py): Wrap `_load_font` and `_font_path_for_style` with `functools.lru_cache`.
  - [`MemeEngine.py`](file:///.github/scripts/MemeEngine.py): Add caching to `_resolve_font_path`.
- **Verification**:
  - Run `uv run python -m unittest discover tests`
  - Benchmark `RichTextRenderer.generate_canvas(...)` over 100 iterations with complex text to confirm reduced latency.

### 2. Explicit MoviePy Resource & Clip Cleanup
- **Goal**: Prevent OS file handle leaks, orphaned temp files, and memory growth during video operations by ensuring `VideoFileClip` and `CompositeVideoClip` instances are closed via context managers or explicit `try...finally` blocks.
- **Code to Touch**:
  - [`operations/apply_text_overlay.py`](file:///.github/scripts/operations/apply_text_overlay.py)
  - [`operations/apply_multi_text_overlays.py`](file:///.github/scripts/operations/apply_multi_text_overlays.py)
  - [`operations/stack_media.py`](file:///.github/scripts/operations/stack_media.py)
  - [`operations/concatenate_clips.py`](file:///.github/scripts/operations/concatenate_clips.py)
  - [`operations/crop_media.py`](file:///.github/scripts/operations/crop_media.py)
  - [`operations/trim_video.py`](file:///.github/scripts/operations/trim_video.py)
- **Verification**:
  - Run a pipeline job with multiple video steps.
  - Monitor open file handles and process memory usage to confirm clips are released immediately upon completion.

### 3. FFmpeg Hardware Acceleration & Multithreading Flags [COMPLETED]
- **Goal**: Significantly reduce render times for video memes by supporting hardware-accelerated encoders (`h264_nvenc`, `h264_qsv`, `h264_amf`) and configurable thread counts (`threads=N`).
- **Code to Touch**:
  - [`operations/utility_ops.py`](file:///.github/scripts/operations/utility_ops.py): Update `WriteVideoOperation` to accept `threads` and hardware codec parameters.
  - [`MemeEngine.py`](file:///.github/scripts/MemeEngine.py): Update `_write_video` parameter signature.
- **Verification**:
  - Pass `threads=4` or hardware video codec parameters to a video render job.
  - Verify that FFmpeg receives correct parameters and video renders without errors.

---

## Pillar 2: Architecture & Design System

### 4. Decorator-Based Operation Auto-Registration [COMPLETED]
- **Goal**: Replace verbose manual handler registrations in `build_default_registry()` with a clean `@registry.register` decorator and/or module auto-discovery.
- **Code to Touch**:
  - [`operations/registry.py`](file:///.github/scripts/operations/registry.py): Implement decorator and auto-discovery helpers.
  - [`operations/base.py`](file:///.github/scripts/operations/base.py)
- **Verification**:
  - Run `uv run python -m unittest tests/test_operation_registry.py` to confirm all operation handlers register cleanly.

### 5. Typed Schema Validation for Operation Parameters
- **Goal**: Replace unstructured `Dict[str, Any]` dictionary parameter checks with strongly-typed schemas (e.g. `dataclasses` or `pydantic` models) so invalid job parameters fail fast with descriptive error messages before video rendering begins.
- **Code to Touch**:
  - [`operations/base.py`](file:///.github/scripts/operations/base.py): Extend `OperationHandler` interface with typed parameter validation.
  - All operation handlers in [`operations/`](file:///.github/scripts/operations/).
- **Verification**:
  - Add test cases in `tests/test_operation_registry.py` passing invalid/missing parameters and assert `ValueError` is raised with detailed error messages.

### 6. Pipeline Scratch Workspace Manager
- **Goal**: Automatically track and clean up intermediate PNG text overlays and temporary media assets generated during multi-step pipeline execution upon completion or failure.
- **Code to Touch**:
  - [`operations/base.py`](file:///.github/scripts/operations/base.py): Add workspace scratch directory manager to `OperationContext`.
  - [`job_execution.py`](file:///.github/scripts/job_execution.py): Integrate scratch cleanup with `JobExecutionService.execute_config`.
- **Verification**:
  - Execute a multi-step pipeline job and verify intermediate overlay files are removed while preserving final output artifacts.

---

## Pillar 3: Rich Text & Meme Rendering Features

### 7. Auto-Fit / Dynamic Font Resizing
- **Goal**: Automatically calculate and scale down `font_size` when text exceeds the target bounding container height/width, preventing unexpected text clipping or line overflow.
- **Code to Touch**:
  - [`RichTextRenderer.py`](file:///.github/scripts/RichTextRenderer.py): Add auto-fit font sizing logic to `generate_canvas`.
  - [`operations/generate_text_overlay.py`](file:///.github/scripts/operations/generate_text_overlay.py): Add `auto_fit` parameter.
- **Verification**:
  - Render a text overlay with a long string in a small container with `auto_fit=True`.
  - Check returned `metrics["overflowed"]` is `False` and text is fully contained in the output image.

### 8. Word-Level Highlight Pills & Rounded Text Backgrounds
- **Goal**: Support background pill boxes with custom padding, fill colors, and corner radii behind individual styled words or lines (useful for speech bubbles or news caption memes).
- **Code to Touch**:
  - [`RichTextRenderer.py`](file:///.github/scripts/RichTextRenderer.py): Enhance `parse_tokens` and `generate_canvas` rendering loop to calculate word background bounds and draw rounded rectangles.
- **Verification**:
  - Render text containing `[bg=#ff0000]highlighted[/bg]` or HTML `<span style="background-color: red">` tokens.
  - Verify rendered PNG contains background boxes behind specified words.

### 9. Two-Pass Animated GIF Palette Optimization
- **Goal**: Generate sharp, high-quality, compact animated GIFs by utilizing FFmpeg's `palettegen` and `paletteuse` filters during GIF output rendering.
- **Code to Touch**:
  - [`operations/utility_ops.py`](file:///.github/scripts/operations/utility_ops.py): Extend `WriteVideoOperation` to handle GIF palette optimization parameters.
- **Verification**:
  - Export an animated GIF meme job and verify output visual quality and file size comparison against standard export.

---

## Pillar 4: Developer Experience & Quality Assurance

### 10. Standardize Execution & Environment Management via `uv`
- **Goal**: Enforce `uv` across all development workflows for environment isolation, script execution, and test execution.
- **Code to Touch**:
  - [`concept.md`](file:///concept.md) & [`TODO.md`](file:///TODO.md): Standardize documentation commands to use `uv`.
- **Verification**:
  - Execute `uv run python -m unittest discover tests` and verify tests run successfully.

### 11. Expand Unit Test Coverage
- **Goal**: Add comprehensive unit tests covering `RichTextRenderer` layout calculation, operation parameter validation, and pipeline error recovery.
- **Code to Touch**:
  - `tests/test_rich_text_renderer.py` [NEW]: Unit tests for word wrapping, HTML/markdown parsing, and metric calculations.
  - [`tests/test_operation_registry.py`](file:///tests/test_operation_registry.py): Expanded operation validation tests.
  - [`tests/test_run_meme_job.py`](file:///tests/test_run_meme_job.py): Expanded pipeline integration tests.
- **Verification**:
  - Run `uv run python -m unittest discover tests` and confirm 100% test pass rate.
