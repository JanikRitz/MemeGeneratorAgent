# Compact Meme Jobs

Status: implemented. The runner accepts standalone `meme/v1` jobs. All original
examples have been migrated, and two concatenation examples have been added.

## Running Jobs

From the project root, with the project dependencies installed:

```powershell
python .github/scripts/run_meme_job.py config/examples/video_concat_two_trimmed.json --validate
python .github/scripts/run_meme_job.py config/examples/video_concat_two_trimmed.json --expand
python .github/scripts/run_meme_job.py config/examples/video_concat_two_trimmed.json --release
python .github/scripts/run_meme_job.py config/examples/video_concat_two_trimmed.json --preview-only --release
python .github/scripts/run_meme_job.py --schema
```

`--validate` is offline structural validation. `--expand` resolves sources and
prints a typed execution plan without rendering or creating scratch directories.
`--schema` prints JSON Schema generated from the same models used for validation.
Relative media/output paths resolve against the current working directory by default; use `--project-root`
to change it. The example files refer to media you must provide; remote references
require the existing Stash/Hydrus environment variables and working services.

Concatenation requires FFmpeg's `ffprobe` executable on PATH, in addition to the
FFmpeg binary MoviePy uses. Text jobs require the referenced fonts to be installed.
Compact video encoding defaults to `libx264` so an NVIDIA GPU is not required.
Use `--video-codec`, `--video-crf`, `--video-preset`, and `--threads` for overrides.
`--config` (or the positional argument) always selects the compact job. To replace
built-in style/quality presets or add named ones, pass a separate `--presets` JSON
file, resolved relative to `--project-root`:

```powershell
python .github/scripts/run_meme_job.py --config config/examples/video_bottom_text_box.json --presets config/my-presets.json --release
```

```json
{
  "styles": {
    "meme": {"size": 48, "stroke": 4},
    "subtle": {"size": 28, "shadow": false, "background": "transparent"}
  },
  "quality": {
    "good": {"video": {"crf": 18, "preset": "slow", "bitrate": "5000k"}},
    "archive": {"image": {"image_quality": 96, "optimize": true}}
  }
}
```

Each entry merges into the built-in preset with the same name. New style names use
the `meme` style as a baseline, and new quality names define their own image and/or
video profile. New names can be referenced by `style` or `quality` in the job. A
style preset accepts caption/panel appearance fields except `style`; a quality
preset must have an `image` and/or `video` `encode`-field map.

Only compact `meme/v1` jobs are accepted. Legacy operation/pipeline configs and their
timestamp-only execution path have been removed.

### Persistent Cache and Publication

Jobs execute sequentially through a shared plan executor. Each step is cached under
`<project-root>/.meme-cache/`. Use `--cache-dir <path>` to change it (relative paths
are based on `--project-root`), `--force` to rebuild and refresh all steps, or
`--no-cache` to bypass both cache reads and writes.

Rendering runs show a single `tqdm` progress bar on interactive stderr; stdout
retains the final output path. The bar shows the current operation and cache phase,
completed/total operations, and elapsed time. It advances after successful publication,
including on cache hits; it measures completed operations, not frames or bytes.
Each completed operation leaves one line with its index, source field, operation
name, cache status (hit, miss, forced rebuild, or disabled), and elapsed time.
Redirecting stderr disables the bar and uses plain phase/timing logs instead.
MoviePy's progress bars/messages are disabled; warnings and render errors remain
visible above the bar. `--verbose` adds full cache keys, per-operation phase timings,
and engine details. Execution timing totals remain visible without it. `--validate`,
`--expand`, and `--schema` do not emit this rendering progress.

Timings use elapsed wall-clock seconds. Compilation includes engine initialization,
remote source resolution, and metadata inspection. Execution reports the runtime
fingerprint, then per-operation key generation (input/font hashing), restore
(checksum verification and copying), rendering, cache storage, and publication.
The execution summary includes hit/render counts, phase totals, and scratch cleanup;
job and run totals include orchestration overhead but exclude Python startup/imports.
On a hit, rendering is skipped, but hashing, verification, copying, and publication
still occur. Use these timings to distinguish remote/metadata delays from cache
disk I/O before changing cache policy. Engine/script edits invalidate cache keys,
so the first run after a code update may rebuild even with an unchanged job.

Cache keys include full SHA-256 input-content hashes, effective parameters after
preset/CLI expansion, output format, preview mode, resolved font variants, engine
source and registered handler implementations, Python/platform/package versions,
and FFmpeg/ffprobe binary fingerprints. Resolved remote paths and marker values are
refreshed during compilation; a cache hit does not enable offline remote resolution.
Random scratch paths and output destinations do not affect keys. Changing only a
later step reuses unchanged earlier results. Hashing large videos adds disk I/O.

Entries contain a checksum manifest, the result, and generated overlay/panel PNGs.
Checksums are verified on reuse; missing or damaged entries are rebuilt. Results
are copied, never hard-linked, so editing an output cannot modify its cache entry.
Completed steps remain cached even when a later step fails. The cache is local,
trusted data; custom handlers must be source-inspectable and deterministic from
their declared parameters/dependencies, or callers must use `--no-cache`.

Operations render into this run's scratch workspace. Nonempty declared results are
published through a temporary file beside the destination followed by an atomic
replace. A failed render/copy/replace preserves the previous final output; an
interrupted process may leave temporary files, but does not publish partial output.
This is per-file atomic visibility, not a transaction across the whole job or a
guarantee against power loss. Direct low-level engine calls do not use this executor.

`--release` deletes this run's owned scratch directory after success; failed jobs
also clean their scratch directory. Without release, successful runs retain
intermediates under `<output-directory>/.meme-scratch/` for inspection, including on
cache hits. Other runs' scratch directories are never deleted automatically.
The persistent cache survives release and has no automatic eviction yet; remove
its directory to reclaim space when no jobs are running. Concurrent execution,
interprocess cache locking, and concurrent writes to the same output are not yet
supported. Do not reuse the output path as an input.

The catalog can also be run directly:

```powershell
python .github/scripts/run_meme_job.py config/mockups/compact-examples.json --example video_concat_two_trimmed --release
```

## Implementation Priority

This project is in alpha with essentially no user base. Prioritize a clear new API,
correct rendering, and maintainable implementation over backward compatibility.
Breaking changes to existing configs and handlers are acceptable when they simplify
the design. Do not add compatibility switches, adapters, or parallel execution paths
solely to preserve old behavior. Update affected examples, tests, and documentation
together when implementing a change.

The current full configs are useful feature references, not a frozen internal API.
Compact jobs should compile to a typed execution plan whose shape can evolve with
the engine. Keep version checking for clear errors, not as a promise to support
every historical format indefinitely.

The companion [catalog](../config/mockups/compact-examples.json) contains a compact
counterpart for each of the 23 original example configs, plus built-in preset values.
Use `--example` to select one job, not the entire catalog as a batch. Each value under
`examples` is a standalone job; `presets` documents the built-ins. Runtime presets
live in the compiler and are checked against the catalog by tests.
`additional_examples` holds new workflows without a corresponding legacy example,
including plain concatenation and concatenation of two independently trimmed clips.

## Everyday Shape

```json
{
  "format": "meme/v1",
  "input": "media/examples/video.mp4",
  "output": "render/examples/trim_captioned.mp4",
  "steps": [
    {"op": "trim", "start": 1, "end": 5},
    {"op": "caption", "text": "**When the build passes**", "at": "bottom", "font": "C:\\Windows\\Fonts\\ARIAL.ttf"}
  ]
}
```

Keep one shape for single-step and multi-step jobs: always `steps`, always `op`.
Do not introduce one-key shorthands, natural-language commands, implicit operations,
or a second YAML syntax. Short, predictable keys help constrained local models.

Required job fields: `format`, `input`, `output`, nonempty `steps`.
Optional job fields: `font`, `quality`, `encode`, `duration`.
`duration` supplies `output_duration_sec` to caption/panel operations and
`duration_sec` to stack operations; it does not trim or extend an existing video.
Output extensions remain explicit: quality must never silently change a file type.

## Step Vocabulary

| Step | Compact fields | Expansion target |
| --- | --- | --- |
| `trim` | `start`, `end`, optional `boomerang`; or `marker` | `trim_video` |
| `scale` | `max_long_side`, optional `max_short_side`, `upscale` | `scale_media` |
| `crop` | `left`, `right`, `top`, `bottom` in pixels, omitted edges are zero | `crop_media` |
| `panel` | `text`, `side`, text appearance, optional `ratio`, `pixels`, `auto_size` | `add_text_side_box` |
| `caption` | `text`, text appearance, optional `start`, `end` | Single-item `apply_multi_text_overlays`, or `generate_text_overlay` for a still-image result |
| `captions` | `items` array of text/timing entries; shared text appearance on the step | `apply_multi_text_overlays` |
| `stack` | `with` media reference or `{input, steps}` branch, optional `direction`, `duration` | `stack_media` |
| `concat` | Nonempty `with` array of media references or `{input, steps}` branches | `concatenate_clips` with normalized dimensions |

All steps accept `encode` for applicable encoding fields; steps that support a
duration accept `duration`. `intermediate_format` is an advanced, nonfinal-step
override such as `jpeg` or `mp4`. There are no input/output paths on ordinary steps.
`scale` requires at least one bound and defaults to `upscale: false`.
`panel` defaults to top, automatic sizing, and a minimum size ratio of 0.22.
`pixels` is fixed sizing and cannot be combined with `ratio` or `auto_size: true`.
`stack` defaults to horizontal; its first input is the current pipeline media.
`with` accepts a plain media reference or a branch, exactly like `concat`'s `with`
entries: `{input, steps}` with the same branch step restrictions and marker rules.
Other stack behavior, including mixed-media duration, stays with the existing handler.

Map panel `ratio` / `pixels` to `box_size_ratio` / `box_size_px`; keep `auto_size`.
Map crop edge names to the corresponding `*_px` fields. Map stack `with` to `path2`,
the current input to `path1`, and `direction` to `orientation`.

`caption` on a still image with an image result expands to `generate_text_overlay`
with `compose_on_media: true` and source-sized dimensions. Timings are invalid in
that case. On video or for an animated result it expands to single-item `apply_multi_text_overlays`.
`captions` is explicitly a timed composition, even with one item; its result is video
in v1. Multiple static captions on an image use successive `caption` steps.
PNG output from video requires the existing CLI preview mode; it is not an implicit
frame-extraction operation. Animated GIF export is outside this proposal.

## Concatenation

`stack` places media beside or above one another. `concat` places clips one after
another: the current pipeline result first, then each `with` entry in array order.
Always use an array, even for one appended clip:

```json
{"op": "concat", "with": ["media/examples/vertical_video.mp4"]}
```

An entry can instead be `{input, steps}` to process another source independently.
This branch has a required media `input` and nonempty `steps`; it is not a separate
job and has no `format`, `output`, `quality`, or other job-level fields. For v1,
branch steps are limited to `trim`, `scale`, and `crop`, with their existing compact
fields and validation. Nested concatenation and arbitrary graph references are out
of scope. Unmodified media uses a plain reference, not a branch with empty steps.
Existing Stash/Hydrus media objects remain distinguishable from branches by `input`.

### Two Independently Trimmed Clips

```json
{
  "format": "meme/v1",
  "input": "media/examples/video.mp4",
  "output": "render/examples/two_trimmed_clips.mp4",
  "steps": [
    {"op": "trim", "start": 2, "end": 6},
    {"op": "concat", "with": [
      {"input": "media/examples/vertical_video.mp4", "steps": [
        {"op": "trim", "start": 10, "end": 13}
      ]}
    ]}
  ]
}
```

This plays seconds 2 through 6 of the first source, then seconds 10 through 13 of
the second source: a nominal seven-second result. Both ranges must exist in their
respective sources. Trim intervals include the start and exclude the end; encoded
duration is subject to output-frame quantization. A following caption's timestamps
refer to the combined timeline: the second segment starts at approximately second 4.

### Default Canvas Policy

Use **largest long edge, first aspect ratio, contain, centered black padding**.
Measure inputs after their branch processing, including crops and scaling, using
display dimensions after rotation and pixel-aspect normalization.

1. Let `long_edge` be the maximum of every processed input's width and height.
2. Keep the first processed input's width-to-height ratio. Set its longer canvas
   dimension to `long_edge` and derive the shorter dimension from that ratio.
3. Round each canvas dimension up to an even integer for common video encoders.
   This may introduce a tiny aspect-ratio rounding difference.
4. Scale every clip proportionally by `min(canvas_width / width, canvas_height / height)`.
   Upscaling is allowed here, unlike the default standalone `scale` operation.
   Round fitted dimensions to the nearest positive integer within the canvas.
5. Center the fitted clip with opaque black (`#000000`) filling unused space.
   Never stretch or crop. For odd padding, put the extra pixel on the right/bottom.

Examples:
- First 1280x720, second 1920x1080: output 1920x1080; both fill the canvas.
- First 1280x720, second 1080x1920: output 1920x1080; the portrait clip is about
  608x1080 with black bars on the left and right.
- First 720x1280, second 1920x1080: output 1080x1920; the landscape clip is about
  1080x608 with black bars above and below.

"Largest resolution" thus means the largest **long-edge dimension**, not the
largest pixel area or independent maximum width/height. It avoids creating a
1920x1920 canvas for mixed 1080p orientations. Opposite-orientation media will be
downscaled to fit; preserving all original pixels would require a much larger
canvas. There is no implicit resolution cap: explicitly scale the result when needed.

These are fixed v1 defaults, so everyday jobs need no extra layout settings. A future
explicit canvas/fit option can be added separately instead of burdening this syntax.

### Playback And Expansion

- Hard cuts with no overlap, fades, gaps, or transitions. Sum the processed clip
  durations; job-level `duration` does not override or truncate concatenation.
- Use the first processed clip's frame rate; if unavailable, use 24 fps. Resample
  subsequent clips in time by dropping/repeating frames, without changing playback
  speed. Do not interpolate motion or take the highest source frame rate implicitly.
- Keep each clip's audio aligned with its segment. Audio-less segments are silent;
  trim/pad each audio track to its segment duration. If all inputs lack audio, omit
  the audio track. No normalization or crossfades. Output encoding unifies formats.
- Accept video and animated GIF sources; reject still images in v1 because they
  need an explicit hold duration. Missing/unreadable inputs fail the job, not skip a
  segment. A concat result is video, except for the CLI preview described below.
- A branch inherits job encoding defaults. Its own step overrides win. Encoding
  on the enclosing `concat` applies only to the combined write, not branch writes;
  CLI overrides still win throughout. A marker trim infers identity from its own
  branch input and must precede any transformation in that branch.
- Compile branch operations into uniquely owned scratch paths before the concat.
  Preserve the incoming main result in an explicit path: after rendering a branch,
  `$last_output` points to that branch, not the main result. Emit `clip_paths` as
  `[saved_main_path, branch_0_path, branch_1_path, ...]` in the original order.
  A subsequent top-level step can resume ordinary `$last_output` wiring.
- Preview produces one PNG contact sheet with one normalized first-frame tile per
  processed segment in order, arranged vertically, with black padding inside each
  tile. Compute the target dimensions from the processed media metadata, not the
  contact sheet. Treat this sheet as a terminal review artifact: reject subsequent
  steps in preview mode until temporal preview chaining is supported.

The handler normalizes dimensions before MoviePy composition, and preview uses
the same canvas policy. There is no legacy layout mode. Direct concat inputs use
ffprobe sample-aspect metadata and MoviePy's rotation handling. Branches are
materialized before concatenation; metadata discarded by a preceding encoder is
not recovered by concat. Square-pixel branch intermediates are recommended.

## Text And Timing

| Compact field | Existing parameter |
| --- | --- |
| `text` | `text`, or `text_data` for panel/static overlay |
| `font`, `size` | `font_path`, `font_size` |
| `at` | Text vertical alignment: `top`, `center`, `bottom` |
| `align` | Text horizontal alignment: `left`, `center`, `right` |
| `padding`, `background` | `text_padding`, `background_color` |
| `stroke`, `stroke_color`, `shadow` | `stroke_width`, `stroke_fill`, `shadow_enabled` |
| `line_height`, `paragraph_spacing`, `indent` | `line_height`, `paragraph_spacing`, `paragraph_indent_px` |
| `start`, `end` | `start_time`, `end_time` for captions; `start_sec`, `end_sec` for trim |

For static overlays translate alignment/padding to `horizontal_align`,
`vertical_align`, and `padding` instead. Panel `side` locates the panel outside the
media; panel `at` locates text inside it. Caption `at` aligns text within a full-frame
canvas (`match_base_size: true`), not a separately positioned rectangle.

Text markup and newlines pass through unchanged. No implicit capitalization, color
wrapping, font substitution, auto-fit, or markup conversion. Built-in style values
are fixed in the catalog: `meme`, `headline`, `meme-compact`, and `panel`.
The default style is `meme` for captions and `panel` for panels.
Styles control appearance only; they never supply text, panel side, time, or encoding.

For a caption/panel: built-in style < explicit step appearance.
For each `captions` item: start from the item's named style, else the step's named
style, else `meme`; then apply explicit shared step appearance, then item appearance.
The job font fills missing font values; a step/item font takes precedence.
Styles do not inherit other styles. Use the runner's `--presets` option for shared
custom presets; jobs do not import preset files themselves.

Times are numeric seconds relative to the current step's input, not the original
source. Caption `start` defaults to 0; omitted `end` means the composition duration.
Simultaneous captions belong in one `captions` step to avoid another encode for each
caption. Array order determines drawing order. Do not automatically clamp explicit
end times; retain existing semantics and warn when metadata reveals suspicious timing.

## Sources And Markers

Local paths and existing reference strings remain valid, for example
`stash:image:425270`, `stash:scene:1141`, and `hydrus:file_id:21602506`.
Existing reference objects also remain valid, including `$hydrus_search_path` with
tags, selection index, and service filters. They are accepted only in media fields;
text that happens to begin with `media/` or `stash:` must remain text.
Do not create another general-purpose reference syntax.

The one convenience addition is a trim marker:

```json
{"op": "trim", "marker": {"id": 878, "fallback_duration": 2}}
```

For input `stash:scene:1141`, expand this into the existing two
`$stash_marker_time` objects with `scene_id: 1141`, `marker_id: 878`, and `time`
equal to `start` / `end`. Only the end reference receives `default_duration_sec: 2`.
`marker.title` may replace `marker.id`; exactly one is required. An explicit
`marker.scene` is allowed for a local-file source. Without it, infer the scene only
when this trim directly consumes the original Stash scene. Reject marker trimming
after transformations: source marker timestamps no longer identify the same timeline.
`marker` cannot coexist with `start` / `end`.

## Quality Without Hidden Resizing

The catalog proposes `good`, `balanced`, `crunchy`, and `super_crunchy` presets.
Image quality values match the existing JPEG examples. `crunchy` has only an image
profile in this draft: reject it for a video encode rather than inventing values.
Video profiles are common settings extracted from the existing quality pipelines;
step overrides retain the differences between trimming, scaling, and final encoding.

`encode` keys: `codec`, `crf`, `preset`, `bitrate`, `audio_bitrate`, `threads`,
`image_quality`, `png_compress_level`, `optimize`. Map the first four to
`video_codec`, `video_crf`, `video_preset`, `video_bitrate`; the others retain names.
Only apply the image/video profile matching a step's actual write format.
JPEG/WebP quality is not PNG quality; PNG compression is lossless. An applicable
image preset may supply `optimize` to PNG but must not imply JPEG degradation.

Precedence per encoding field: existing handler defaults < named job quality profile
< job `encode` < step `encode` < explicit CLI override.
Omitted quality leaves encoding values unset except for the portable `libx264`
codec default. Quality never
changes dimensions, font sizes, caption text, or output suffixes. That is why the
catalog keeps scale bounds and typography explicit in each quality variant.

Preset names are validated for `libx264` and `h264_nvenc`. When using NVENC, a
quality profile's `slow`, `fast`, or `veryfast` maps to `p6`, `p4`, or `p2` respectively.
An explicitly supplied preset is not translated and must match the encoder.
Other encoders and their preset/rate-control capabilities are validated by FFmpeg
at render time; hardware availability is not checked by offline validation.

## Expansion And Artifact Ownership

1. Recognize `format: meme/v1`; reject unknown versions and mixed compact/full roots.
  Maintaining execution of the old `operation` / `pipeline` format is not a gate.
  Prefer a clear migration error over a compatibility subsystem if it is removed.
2. Validate structural fields, operations, presets, and value types before API calls.
3. Resolve media references and inspect metadata only where media kind/duration is
   needed. Preserve original Stash identity until marker references have expanded.
4. Expand ordinary steps to one existing operation with explicit effective parameters.
  All inputs use explicit resolved paths, including previous-step results.
  A concat with branches expands to branch operations followed by concatenation,
  using explicit saved input paths as described above.
5. Allocate a job-owned scratch directory beside the final output. Nonfinal steps
   receive numbered paths; PNG for still images and MP4 for video by default.
   An explicit `intermediate_format: jpeg` retains a legacy lossy intermediate.
6. Give each caption/panel step its own overlay directory and generated extensionless
   artifact names. Only the final step receives the requested final output path.
7. Apply CLI overrides and execute through the existing job service. Preserve actual
  returned paths in preview mode. No encoding fusion; concatenation requires the
  normalized handler described above.

Scratch paths use a normalized-job hash plus a per-run identifier to avoid
collisions between concurrent runs. Example displays can use `<scratch>` as a
placeholder. The compiled plan reports its owned scratch directory and outputs; never infer cleanup
targets from user source names. Changing config shape alone does not make cleanup safe.

Conceptual routing for the everyday job (abbreviated; `--expand` prints the full
typed plan with explicit paths, source-field labels, presets, and artifact ownership):

```json
{
  "pipeline": [
    {"operation": "trim_video", "params": {"input_path": "media/examples/video.mp4", "start_sec": 1, "end_sec": 5, "output_path": "<scratch>/000-trim.mp4"}},
    {"operation": "apply_text_overlay", "params": {"input_path": "$last_output", "output_path": "render/examples/trim_captioned.mp4", "overlay_dir": "<scratch>/001-caption", "text": "**When the build passes**", "match_base_size": true, "text_vertical_align": "bottom", "font_path": "C:\\Windows\\Fonts\\ARIAL.ttf"}}
  ]
}
```

Paths resolve against an explicit project root, consistently with the existing
`media/` and `render/` examples; they are not relative to the mockup catalog.
Custom handlers, positioned rectangles, standalone transparent overlays, and
arbitrary graph wiring are outside this compact v1 scope. Add typed capabilities
when needed rather than retaining the old format solely as an escape hatch.
Do not add an unvalidated `raw` dictionary to every compact step.

## Coverage And Deliberate Differences

The catalog's `examples` keys exactly match the current 23 basenames. It covers crop,
static-image text, local/Stash/Hydrus panels, JPEG quality variants, GIF-to-MP4,
image/video scaling, marker trimming, timed multi-caption pipelines, side panels,
mixed-media stacking, and plain trimming without a raw-operation escape hatch.

Keep all final paths, text/markup, explicit timings, dimensions, fonts, and explicit
encoding settings. Drop user-chosen intermediate and overlay names. The image-scale
example explicitly retains its JPEG intermediate rather than silently claiming
equivalence after switching to PNG. Single-caption defaults are expanded explicitly
from the chosen style so adapter defaults cannot alter appearance.

This is intended semantic coverage, not proven pixel/bitstream equivalence. The
current renderer may produce different containers, durations, or encodes around
media-type boundaries; expansion and rendering tests must establish those contracts.

Mockup checks: all 23 names, final paths, text strings, and effective explicit encoding
settings match the originals. Using the same PowerShell minified JSON serializer,
the standalone job payloads total 7,601 UTF-8 bytes versus 15,259 for the originals:
50.2% smaller. This excludes shared preset definitions and catalog metadata and is
not a model-specific token count. The longest text strings remain unchanged.
These measurements exclude the new `additional_examples` concatenation workflows.

## Verification And Limits

Available commands: `--validate` for offline structural validation;
`--expand` for the effective execution plan and artifact ownership. Expansion may need
external services and media metadata, especially for extensionless/Stash/Hydrus
assets; it must not render video or create scratch files. CLI overrides appear in
expanded output, while credentials never do.

The compiler generates a discriminated JSON Schema from its Pydantic models.
Validation rejects unknown keys, coercion of strings to booleans/numbers, invalid presets, empty
steps/items, contradictory sizing, and invalid time ranges. Errors should name the
source field, for example `steps[2].items[1].size: expected a positive integer`.
Provide an LLM with the relevant step schemas and one small matching example, not
the whole catalog. The catalog is for review and future golden tests.

Automated coverage in `tests/test_compact_jobs.py`:
- Verify one compact counterpart per original basename and valid JSON throughout.
- Compile every entry using deterministic media-info/reference test doubles.
- Verify effective parameters and override precedence against the new specification.
  Use old examples to identify missing features, not to freeze historical defaults
  or incidental output behavior. Document intentional differences.
- Test precedence, multi-caption timing, marker fallback, codec errors, preview paths,
  mixed-media results, nonfinal image formats, and concurrent artifact isolation.
- For concat, test independent trims (4 + 3 seconds), ordered explicit input paths,
  first-clip aspect ratio, largest long edge, even dimensions, centered black bars,
  different frame rates, silent segments, audio boundaries, branch marker identity,
  missing inputs, and preview contact sheets with no following steps.
- Render representative static, video, GIF-source, and mixed-media jobs; compare
  dimensions, text placement, timing, and audio with the corresponding legacy jobs.
- Standalone examples match the catalog. Serialized size measurements above are
  historical comparisons; whitespace savings are not model-specific token savings.

Tests use deterministic Stash/Hydrus reference doubles, not the user's live library.
Image, video, GIF conversion, mixed-media stack, timed captions, and trimmed concat
are exercised with generated media. Codec-specific hardware rendering is not tested.
Dynamic panel/stack dimensions are resolved by the handlers, so some downstream
geometry checks necessarily occur at execution rather than offline validation.
Preview collapses time to still frames: a trim after a prior preview-producing
transformation is rejected, and concat contact sheets must be terminal.