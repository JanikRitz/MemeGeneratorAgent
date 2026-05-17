# Meme Generator Skill

This skill runs JSON-based meme jobs using Python + MoviePy + Pillow.

## Purpose

Use this skill when you want to:
- Trim a video segment.
- Stack two images/videos horizontally or vertically.
- Concatenate clips in sequence.
- Render styled text overlays (Markdown or HTML inline styles).
- Apply multiple timed text overlays to a base video/image.
- Add a top/bottom/left/right text side-box while keeping the full original video visible.
- Query media width/height/duration with `get_media_info.py` so the agent can auto-build correct configs.
- Resolve Stash scene IDs to media paths and resolve marker timing for trim/overlay windows.

Outputs are written to `render/` and logs to `logs/`. Intermediate overlay PNGs are saved alongside the final output file.

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
uv run .github/scripts/run_meme_job.py --config config/examples/example_overlay.json
```

Force preview-only mode from CLI (without editing config):

```powershell
uv run .github/scripts/run_meme_job.py --config config/examples/example_side_box_right.json --preview-only
```

Positional config path also works:

```powershell
uv run .github/scripts/run_meme_job.py config/examples/example_overlay.json
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

### Query Stash scene info

Set env vars once in your terminal session:

```powershell
$env:STASH_GRAPHQL_ENDPOINT = "http://localhost:9999/graphql"
$env:STASH_API_KEY = "your_api_key_if_needed"
```

Then fetch scene media path + markers:

```powershell
uv run .github/scripts/get_stash_scene_info.py --scene-id 123
```

The output includes a `media_path` and marker list with `start_time` / `end_time` values.

## How to Get Marker IDs, Titles, and Tags from Stash

To use marker-based trimming or overlays, you need the marker IDs or titles for a scene. Here’s how to fetch them:

1. **Set your Stash environment variables:**
   ```powershell
   $env:STASH_GRAPHQL_ENDPOINT = "http://localhost:9999/graphql"
   $env:STASH_API_KEY = "your_api_key_if_needed"
   ```

2. **Query the scene info (including markers):**
   ```powershell
   uv run .github/scripts/get_stash_scene_info.py --scene-id <your_scene_id>
   ```

3. **Read the output:**
   - The output will include:
     - `scene_id`, `title`, and `tags` for the scene
     - `media_path` (absolute path to the video/image)
     - `markers`: a list of objects, each with:
       - `id`: the marker ID (use for configs)
       - `title`: the marker title (can also be used for configs)
       - `start_time`, `end_time`, and `duration`
       - `tags`: list of tag names for the marker
       - `primary_tag`: the main tag for the marker (if set)

4. **Use the marker ID or title in your config:**
   - Example using marker ID:
     ```json
     { "$stash_marker_time": { "scene_id": 123, "marker_id": 456, "time": "start" } }
     ```
   - Example using marker title:
     ```json
     { "$stash_marker_time": { "scene_id": 123, "marker_title": "My Marker", "time": "end" } }
     ```

5. **Tip:**
   - You can use the marker `tags` and `primary_tag` fields to help you or an LLM agent choose the right marker for your workflow.

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
        "output_path": "render/examples/part1.mp4"
      }
    },
    {
      "operation": "apply_multi_text_overlays",
      "params": {
        "base_media_path": "$last_output",
        "output_path": "render/examples/part1_captioned.mp4",
        "overlays": [
          {
            "overlay_name": "part1_bottom.png",
            "text": "**When the build passes**",
            "start_time": 0.0,
            "end_time": 4.0,
            "match_base_size": true,
            "text_align": "center",
            "text_vertical_align": "bottom"
          }
        ]
      }
    }
  ]
}
```

`$last_output` in pipelines is replaced by the previous step's output path.

### 3) Stash references in JSON

`run_meme_job.py` resolves Stash references before running operations.

Supported forms:
- Scene path token: `"stash:scene:<scene_id>"`
- Marker token: `"stash:marker:<scene_id>:<marker_id_or_title>:<start|end>"`
  - Use `title=<exact marker title>` for title lookup.
- Object scene reference: `{ "$stash_scene_path": 123 }`
- Object marker reference:
  - `{ "$stash_marker_time": { "scene_id": 123, "marker_id": 456, "time": "start" } }`
  - `{ "$stash_marker_time": { "scene_id": 123, "marker_title": "Interesting moment", "time": "end", "default_duration_sec": 2.5 } }`

Example:

```json
{
  "operation": "trim_video",
  "params": {
    "input_path": { "$stash_scene_path": 123 },
    "start_sec": { "$stash_marker_time": { "scene_id": 123, "marker_id": 456, "time": "start" } },
    "end_sec": { "$stash_marker_time": { "scene_id": 123, "marker_id": 456, "time": "end", "default_duration_sec": 3.0 } },
    "output_path": "render/examples/stash_trim.mp4"
  }
}
```

Notes:
- `STASH_GRAPHQL_ENDPOINT` (or `STASH_URL`) must be set when a config contains any Stash reference.
- `STASH_API_KEY` is optional and passed via both `ApiKey` and `Authorization: Bearer` headers.

## Supported Operations

### `trim_video`
- Params: `input_path`, `start_sec`, `end_sec`, `output_path`
- Optional quality params: `video_crf`, `video_preset`, `video_bitrate`, `audio_bitrate`
- `trim_video` always cuts the clip to the requested range; there is no implicit "full clip" mode.
- To keep the full clip, do not use `trim_video` in the pipeline, or set `start_sec: 0.0` and `end_sec` to the source duration from `get_media_info.py`.

### `scale_media`
- Params: `input_path`, `output_path`
- Optional: `max_long_side`, `max_short_side`, `upscale` (default `false`)
- Optional quality params:
  - Video outputs: `video_crf`, `video_preset`, `video_bitrate`, `audio_bitrate`
  - Image outputs: `image_quality`, `png_compress_level`, `optimize`
- Preserves aspect ratio for both image and video inputs.
- At least one limit is required:
  - `max_long_side`: caps the larger dimension (great for one-number targets like `1920` for 1080x1920 / 1920x1080)
  - `max_short_side`: caps the smaller dimension
- Recommended usage: first step in a pipeline, then reference `$last_output` for overlay/side-box steps.

### `stack_media`
- Params: `path1`, `path2`, `output_path`
- Optional: `orientation` (`horizontal` or `vertical`), `duration_sec` (for still images)
- Optional quality params: `video_crf`, `video_preset`, `video_bitrate`, `audio_bitrate`

### `concatenate_clips`
- Params: `clip_paths` (array), `output_path`
- Optional quality params: `video_crf`, `video_preset`, `video_bitrate`, `audio_bitrate`

### `generate_text_overlay`
- Params: `text_data`, `video_width`, `video_height`, `output_path`
- Optional sizing params:
  - `media_path` (recommended): auto-uses media width/height so PNG matches source exactly
  - `video_width`, `video_height` (manual fallback)
- Optional style params: `horizontal_align`, `vertical_align`, `padding`, `font_size`, `line_height`, `paragraph_spacing`, `paragraph_indent_px`, `stroke_width`, `stroke_fill`, `shadow_enabled`, `background_color`
- Optional image quality params: `image_quality`, `png_compress_level`, `optimize`

### `apply_multi_text_overlays`
- Params: `base_media_path`, `overlays`, `output_path`
- Optional: `output_duration_sec` (used for image bases)
- Optional quality params: `video_crf`, `video_preset`, `video_bitrate`, `audio_bitrate`

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
- `match_base_size` (bool, **recommended**): PNG is exactly the base media size, placed at (0,0). Use `text_vertical_align` and `text_align` to control where the text appears on screen.
- `text_align` (`left`, `center`, `right`) — horizontal text placement within the PNG
- `text_vertical_align` (`top`, `center`, `bottom`) — vertical text placement within the PNG; with `match_base_size` this directly maps to where the text appears on the video
- `text_padding` (pixels)
- `font_size`
- `line_height` (float, default `1.0`; lower values tighten wrapped line distance)
- `paragraph_spacing` (int pixels; extra vertical gap after manual `\n` line breaks)
- `paragraph_indent_px` (int pixels; horizontal indent for lines that start after manual `\n`)
- `stroke_width`
- `stroke_fill`
- `shadow_enabled`
- `background_color` (default transparent)
- `position`, `width`, `height` — advanced: place a smaller canvas at a specific location on the video. Avoid combining with `match_base_size`.

### `add_text_side_box`
- Params: `base_media_path`, `text_data`, `side`, `output_path`
- Optional: `box_size_px`, `box_size_ratio`, `background_color`, `text_align`, `text_vertical_align`, `text_padding`, `font_size`, `line_height`, `stroke_width`, `stroke_fill`, `shadow_enabled`, `output_duration_sec`, `panel_png_name`
- Optional paragraph params: `paragraph_spacing`, `paragraph_indent_px`
- Optional sizing control: `auto_size` (bool, default `true`)
- Optional quality params:
  - Video outputs: `video_crf`, `video_preset`, `video_bitrate`, `audio_bitrate`
  - Image outputs: `image_quality`, `png_compress_level`, `optimize`
- Optional: `preview_only` (bool)
- Behavior:
  - Expands output canvas at the chosen side (`top`, `bottom`, `left`, `right`)
  - Keeps full original video visible (no crop, no scale)
  - If `box_size_px` is not set and `auto_size=true`, panel size auto-grows to fit text content
  - `box_size_ratio` still acts as a minimum baseline size when auto sizing
  - Saves panel PNG alongside the output file
  - Wraps text to panel width
  - If `preview_only=true`, skips video render and only returns the generated panel PNG path

## Text Syntax

### Markdown-like
- Bold: `**word**`
- Italic: `*word*`
- Color: `[color=#ff3333]word[/color]`
- Hard line break: `\n` (JSON escape) or a literal newline in the string
  - Manual `\n` creates paragraph-style spacing (larger than auto-wrap spacing)
  - Leading spaces after `\n` are preserved, so manual indentation works

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
  - With `match_base_size: true`: set `text_vertical_align` (`top`/`center`/`bottom`) and `text_align` (`left`/`center`/`right`). Do not use `position` — it is ignored when `match_base_size` is set.
  - Without `match_base_size`: adjust `position` (canvas placement on video) and `text_align`/`text_vertical_align` (text placement within the canvas).
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

- Timed text overlays: `config/examples/example_overlay.json`
- Trim + caption pipeline: `config/examples/example_pipeline.json`
- Scale then top side-box (image): `config/examples/scale_then_top_box_image.json`
- Top side-box with hard JPEG compression: `config/examples/side_box_top_image_crunchy.json`
- Top side-box super crunchy JPEG: `config/examples/side_box_top_image_super_crunchy.json`
- Top side-box balanced JPEG: `config/examples/side_box_top_image_balanced.json`
- Top side-box relatively good JPEG: `config/examples/side_box_top_image_good.json`
- Side box (right): `config/examples/example_side_box_right.json`
- Side box (bottom, dense text): `config/examples/example_side_box_bottom.json`
- Video trim + scale + overlay with heavier compression: `config/examples/video_trim_scale_overlay.json`
- Video trim + scale + overlay super crunchy: `config/examples/video_trim_scale_overlay_super_crunchy.json`
- Video trim + scale + overlay balanced: `config/examples/video_trim_scale_overlay_balanced.json`
- Video trim + scale + overlay relatively good: `config/examples/video_trim_scale_overlay_good.json`
- Side box fast preview (PNG only): pass `--preview-only` flag or set `"preview_only": true` in config
- Media metadata query: `uv run .github/scripts/get_media_info.py media/input.mp4`

## Recommended Defaults

For caption overlays (`apply_multi_text_overlays`):
- Use `match_base_size: true` — no need to specify `width`, `height`, or `position`
- Example default: `text_vertical_align: bottom`
- `text_align`: `center`
- `font_size`: 64–72, `stroke_width`: 3–4, `shadow_enabled`: true

For side boxes (`add_text_side_box`):
- `font_size`: ~23, `stroke_width`: 2
- `line_height`: 0.7–0.85 (tighter than default for dense text)
- `text_padding`: 12, `text_align`: `left`
- `auto_size`: true (default) — panel grows to fit content
- Set `panel_png_name` explicitly for reproducible asset filenames

For a "thrown-around-the-internet" compression feel:
- Video: `video_crf: 34-40`, `video_preset: "veryfast"`, and low `video_bitrate` like `500k-900k`
- Image (JPEG/WebP): `image_quality: 18-35`, `optimize: true`

## Quality Ladder Examples

Use these presets as practical anchors, then nudge values to taste.

Video (`.mp4`):
- Super crunchy: `video_crf: 40-41`, `video_preset: "veryfast"`, `video_bitrate: 320k-450k`, `audio_bitrate: 40k-48k`
- Crunchy: `video_crf: 34-36`, `video_preset: "fast"`/`"veryfast"`, `video_bitrate: 700k-1000k`, `audio_bitrate: 64k`
- Balanced: `video_crf: 28-32`, `video_preset: "fast"`, `video_bitrate: 1000k-1600k`, `audio_bitrate: 96k`
- Relatively good: `video_crf: 19-22`, `video_preset: "slow"`, `video_bitrate: 2500k-3500k`, `audio_bitrate: 128k-160k`

Image (`.jpg`/`.webp`):
- Super crunchy: `image_quality: 10-20`, `optimize: true`
- Crunchy: `image_quality: 20-35`, `optimize: true`
- Balanced: `image_quality: 35-55`, `optimize: true`
- Relatively good: `image_quality: 75-90`, `optimize: true`
