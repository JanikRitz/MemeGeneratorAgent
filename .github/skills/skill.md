# Meme Generator Skill

This skill runs JSON-based meme jobs using Python + MoviePy + Pillow.

## Purpose

Use this skill when you want to:
- Trim a video segment.
- Stack two images/videos horizontally or vertically.
- Concatenate clips in sequence.
- Render styled text overlays (Markdown or HTML inline styles).
- Apply multiple timed text overlays to a base video/image.
- Generate full-frame overlay PNGs that can be applied directly without scaling.
- Add a top/bottom/left/right text side-box while keeping the full original video visible.
- Query media width/height/duration with `get_media_info.py` so the agent can auto-build correct configs.

Outputs are written to `render/` and logs to `logs/`.
Overlay PNG assets are preserved (not deleted) in `render/` by default.

## Runtime Assumptions

- Python environment is managed by the user.
- Dependencies are installed from `requirements.txt`.
- `ffmpeg` is available in Windows `PATH`.
- Paths in JSON are either:
  - relative to project root, or
  - absolute Windows paths.

## Entry Commands

Use `uv run` as the default way to execute jobs so the project-managed environment and dependencies are used consistently.
Avoid calling `python` directly unless you explicitly need a specific interpreter.

### Run a job config

```powershell
uv run .github/scripts/run_meme_job.py --config config/example_overlay.json
```

Force preview-only mode from CLI (without editing config):

```powershell
uv run .github/scripts/run_meme_job.py --config config/example_side_box_right.json --preview-only
```

Positional config path also works:

```powershell
uv run .github/scripts/run_meme_job.py config/example_overlay.json
```

The command prints the final output path and writes a timestamped run log file.

### Query media info

Use the dedicated `get_media_info.py` script to inspect a media file's width, height, duration, and type.
This is the preferred way to look up dimensions before building configs — it does not require a job JSON file.

```powershell
uv run .github/scripts/get_media_info.py media/input.mp4
```

Positional or flag form:

```powershell
uv run .github/scripts/get_media_info.py --input media/input.mp4
```

Outputs a JSON object to stdout:

```json
{
  "path": "C:/ProgrammingProjects/MemeGenerator/media/input.mp4",
  "is_video": true,
  "width": 1280,
  "height": 720,
  "duration_sec": 12.5
}
```

## JSON Job Formats

### 1) Single operation

```json
{
  "operation": "trim_video",
  "params": {
    "input_path": "media/input.mp4",
    "start_sec": 2.0,
    "end_sec": 8.0,
    "output_path": "render/trimmed.mp4"
  }
}
```

### 2) Pipeline operation

```json
{
  "pipeline": [
    {
      "operation": "trim_video",
      "params": {
        "input_path": "media/source.mp4",
        "start_sec": 1.0,
        "end_sec": 5.0,
        "output_path": "render/part1.mp4"
      }
    },
    {
      "operation": "apply_multi_text_overlays",
      "params": {
        "base_media_path": "$last_output",
        "output_path": "render/part1_captioned.mp4",
        "overlay_dir": "render",
        "overlays": [
          {
            "overlay_name": "top.png",
            "text": "**HELLO** [color=#ff3333]WORLD[/color]",
            "start_time": 0.0,
            "end_time": 3.0,
            "position": ["center", "top"],
            "width": 1280,
            "height": 240,
            "text_align": "center",
            "text_vertical_align": "center",
            "text_padding": 24,
            "font_size": 72,
            "stroke_width": 4,
            "stroke_fill": "#000000",
            "shadow_enabled": true
          }
        ]
      }
    }
  ]
}
```

`$last_output` in pipelines is replaced by the previous step's output path.

## Supported Operations

### `trim_video`
- Params: `input_path`, `start_sec`, `end_sec`, `output_path`
- `trim_video` always cuts the clip to the requested range; there is no implicit "full clip" mode.
- To keep the full clip, do not use `trim_video` in the pipeline, or set `start_sec: 0.0` and `end_sec` to the source duration from `get_media_info`.

### `stack_media`
- Params: `path1`, `path2`, `output_path`
- Optional: `orientation` (`horizontal` or `vertical`), `duration_sec` (for still images)

### `concatenate_clips`
- Params: `clip_paths` (array), `output_path`

### `generate_text_overlay`
- Params: `text_data`, `video_width`, `video_height`, `output_path`
- Optional sizing params:
  - `media_path` (recommended): auto-uses media width/height so PNG matches source exactly
  - `video_width`, `video_height` (manual fallback)
- Optional style params: `horizontal_align`, `vertical_align`, `padding`, `font_size`, `line_height`, `stroke_width`, `stroke_fill`, `shadow_enabled`, `background_color`

### `apply_multi_text_overlays`
- Params: `base_media_path`, `overlays`, `output_path`
- Optional: `overlay_dir`, `output_duration_sec` (used for image bases)

Timing behavior (from implementation):
- `start_time` defaults to `0.0` when omitted.
- For video bases, `end_time` defaults to the base clip duration when omitted.
- For image bases, composition duration is derived from `output_duration_sec` or the largest overlay `end_time`.
- If you want an overlay to stay for the full video without cutting, set `start_time: 0.0` and omit `end_time`.
- If you set both times manually, keep `end_time > start_time` and within the base duration for predictable results.

Each overlay item can include:
- `overlay_name` (png filename)
- `text` (Markdown or HTML)
- `start_time`, `end_time`
- `position` (e.g. `["center", "top"]`, `["center", "bottom"]`, `[120, 480]`)
- `width`, `height`
- `text_align` (`left`, `center`, `right`)
- `text_vertical_align` (`top`, `center`, `bottom`)
- `text_padding` (pixels)
- `font_size`
- `line_height` (float, default `1.0`; lower values tighten wrapped line distance)
- `stroke_width`
- `stroke_fill`
- `shadow_enabled`
- `background_color` (default transparent)
- `match_base_size` (bool): make PNG exactly base media size and force overlay position `(0,0)`

### `add_text_side_box`
- Params: `base_media_path`, `text_data`, `side`, `output_path`
- Optional: `overlay_dir`, `box_size_px`, `box_size_ratio`, `background_color`, `text_align`, `text_vertical_align`, `text_padding`, `font_size`, `line_height`, `stroke_width`, `stroke_fill`, `shadow_enabled`, `output_duration_sec`, `panel_png_name`
- Optional: `preview_only` (bool)
- Behavior:
  - Expands output canvas at the chosen side (`top`, `bottom`, `left`, `right`)
  - Keeps full original video visible (no crop, no scale)
  - Saves panel PNG in `overlay_dir`
  - Wraps text to panel width
  - If `preview_only=true`, skips video render and only returns the generated panel PNG path

## Text Syntax

### Markdown-like
- Bold: `**word**`
- Italic: `*word*`
- Color: `[color=#ff3333]word[/color]`
- Hard line break: `\n` (JSON escape) or a literal newline in the string
  - Leading spaces after `\n` are ignored (no indent support)

### HTML-like
- Bold: `<b>word</b>` or `<strong>word</strong>`
- Italic: `<i>word</i>` or `<em>word</em>`
- Color: `<span style="color:#00ccff">word</span>`

## Troubleshooting

- Text not visible:
  - Increase `font_size`.
  - Keep `stroke_width` >= 3 and `stroke_fill` dark.
  - Ensure overlay `start_time`/`end_time` overlap the base clip duration.
- Text location looks wrong:
  - Adjust `position` (overlay placement in video).
  - Adjust `text_align` and `text_vertical_align` (text placement inside the PNG canvas).
  - Increase/decrease `width`, `height`, and `text_padding`.
- Overlay PNG should match source exactly:
  - Use `generate_text_overlay` with `media_path`.
  - Or set `match_base_size: true` for an item in `apply_multi_text_overlays`.
- Paths not found:
  - Verify relative paths are project-root relative.
  - Use absolute Windows paths when needed.
- Text gets cut off:
  - The renderer logs a warning with rendered and truncated line counts.
  - Increase panel size (`box_size_px`/`box_size_ratio`) or reduce `font_size`/padding.
- Bold/italic look identical to regular text or appear mismatched:
  - The renderer looks for variant files in the same font family (e.g. `arialbd.ttf` for bold when using `arial.ttf`).
  - Fonts like **Impact** (`impact.ttf`) have no bold/italic variant files, so styled tokens render in the same Impact font — no visual difference, but rendering stays consistent.
  - To get working bold/italic, set the default font to one that ships all variants. Arial works: `C:\Windows\Fonts\arial.ttf`.
  - Alternatively, use `[color=...]` for emphasis instead of bold/italic when the Impact font is preferred.

## Quick Examples

- Full-frame overlay PNG from media dimensions: `config/example_overlay_fullframe.json`
- Side text box composition: `config/example_side_box_right.json`
- Side text box fast preview (PNG only): `config/example_side_box_preview.json`
- Media metadata query: `uv run .github/scripts/get_media_info.py media/input.mp4`

## Recommended Defaults

For meme top/bottom captions:
- `position`: top/bottom center
- `width`: full video width
- `height`: ~18-25% of video height
- `text_align`: center
- `text_vertical_align`: center
- `stroke_width`: 4
- `shadow_enabled`: true
