import copy
import json
import sys
import unittest
from pathlib import Path
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch
import contextlib
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

from compact_jobs import CompactJob, Presets, validate_job
from compact_compiler import CompactCompiler, QUALITY, STYLES
from operations.concatenate_clips import blurred_background, canvas_size, fitted_size


ROOT = Path(__file__).resolve().parents[1]


def catalog_jobs():
    with (ROOT / "config/mockups/compact-examples.json").open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    return {**catalog["examples"], **catalog["additional_examples"]}


class CompactValidationTests(unittest.TestCase):
    def test_standalone_examples_match_catalog(self):
        expected = catalog_jobs()
        files = list((ROOT / "config/examples").glob("*.json"))
        self.assertEqual({path.stem for path in files}, set(expected))
        for path in files:
            with self.subTest(path=path.name), path.open(encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), expected[path.stem])

    def test_entire_catalog_validates(self):
        for name, value in catalog_jobs().items():
            with self.subTest(name=name):
                self.assertIsInstance(validate_job(value), CompactJob)

    def test_invalid_values_are_rejected(self):
        template = catalog_jobs()["video_trim"]
        invalid_steps = [
            {"op": "trim", "start": 3, "end": 2},
            {"op": "trim", "start": "2", "end": 4},
            {"op": "trim", "start": True, "end": 4},
            {"op": "scale"},
            {"op": "scale", "max_long_side": 100, "upscale": "false"},
            {"op": "caption", "text": "hello", "size": -1},
            {"op": "caption", "text": "hello", "font_szie": 24},
            {"op": "captions", "items": []},
            {"op": "panel", "text": "hello", "pixels": 20, "auto_size": True},
            {"op": "concat", "with": []},
            {"op": "concat", "with": [{"input": "other.mp4", "steps": [{"op": "concat", "with": ["third.mp4"]}]}]},
        ]
        for step in invalid_steps:
            with self.subTest(step=step):
                value = copy.deepcopy(template)
                value["steps"] = [step]
                with self.assertRaises(ValueError):
                    validate_job(value)

    def test_schema_has_discriminated_operations(self):
        schema = CompactJob.model_json_schema()
        self.assertEqual(schema["properties"]["steps"]["items"]["discriminator"]["propertyName"], "op")


class CompactCompilerTests(unittest.TestCase):
    def test_missing_video_does_not_fall_back_to_old_preview(self):
        import logging
        from PIL import Image
        from MemeEngine import MemeEngine
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (20, 20)).save(root / "source.png")
            job = validate_job({"format": "meme/v1", "input": "source.mp4", "output": "out.mp4", "steps": [{"op": "trim", "start": 0, "end": 1}]})
            with self.assertRaisesRegex(ValueError, "Asset not found"):
                CompactCompiler(root, MemeEngine(str(root), logging.getLogger("test"))).compile(job)

    def compiler(self, root):
        engine = MagicMock()
        engine.resolve_path.side_effect = lambda path: root / path

        def resolve(value):
            if isinstance(value, dict) and "$stash_marker_time" in value:
                return 1.0 if value["$stash_marker_time"]["time"] == "start" else 3.0
            if isinstance(value, str) and value.startswith(("stash:", "hydrus:")):
                return "source.mp4" if any(token in value for token in ("scene:", "430765", "189566595")) else "source.png"
            return value

        def probe(path):
            video = Path(path).suffix == ".mp4"
            return dict(is_video=video, width=1280, height=720, duration_sec=20 if video else None)

        return CompactCompiler(root, engine, resolve=resolve, probe=probe)

    def test_catalog_compiles_without_creating_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in catalog_jobs().items():
                with self.subTest(name=name):
                    compiler = self.compiler(root)
                    if name == "video_stack_concatenate":
                        compiler.probe = lambda path: dict(is_video=True, width=1280, height=720, duration_sec=4000)
                    plan = compiler.compile(validate_job(value))
                    self.assertEqual(plan.steps[-1].params["output_path"], str((root / value["output"]).resolve()))
                    self.assertFalse(Path(plan.scratch).exists())
            self.assertEqual(list(root.iterdir()), [])

    def test_presets_match_catalog(self):
        with (ROOT / "config/mockups/compact-examples.json").open() as handle:
            presets = json.load(handle)["presets"]
        self.assertEqual(STYLES, presets["styles"])
        self.assertEqual(QUALITY, presets["quality"])

    def test_user_presets_override_built_ins_and_add_names(self):
        presets = Presets.model_validate({
            "styles": {"meme": {"size": 31}, "quiet": {"size": 17, "shadow": False}},
            "quality": {"good": {"video": {"crf": 18}}, "archive": {"image": {"image_quality": 96}}},
        })
        with tempfile.TemporaryDirectory() as directory:
            compiler = self.compiler(Path(directory))
            video = validate_job({"format": "meme/v1", "input": "source.mp4", "output": "out.mp4", "quality": "good", "steps": [{"op": "caption", "text": "Hi", "style": "meme"}]})
            plan = CompactCompiler(Path(directory), compiler.engine, resolve=compiler.resolve, probe=compiler.probe, presets=presets).compile(video)
            self.assertEqual(plan.steps[0].params["overlays"][0]["font_size"], 31)
            self.assertEqual(plan.steps[0].params["video_crf"], 18)
            self.assertEqual(plan.steps[0].params["video_bitrate"], "3000k")
            image = validate_job({"format": "meme/v1", "input": "source.png", "output": "out.jpg", "quality": "archive", "steps": [{"op": "caption", "text": "Hi", "style": "quiet"}]})
            plan = CompactCompiler(Path(directory), compiler.engine, resolve=compiler.resolve, probe=compiler.probe, presets=presets).compile(image)
            self.assertEqual(plan.steps[0].params["font_size"], 17)
            self.assertEqual(plan.steps[0].params["image_quality"], 96)

    def test_concat_preserves_main_result_and_branch_order(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.compiler(Path(directory)).compile(validate_job(catalog_jobs()["video_concat_two_trimmed"]))
            self.assertEqual([step.operation for step in plan.steps], ["trim_video", "trim_video", "concatenate_clips"])
            self.assertEqual(plan.steps[-1].params["clip_paths"], [step.params["output_path"] for step in plan.steps[:2]])
            self.assertEqual(plan.steps[1].params["start_sec"], 10)

    def test_video_stack_concatenate_example_orders_captioned_clip_before_stacked_branch(self):
        with (ROOT / "config/examples/video_stack_concatenate.json").open() as handle:
            job = validate_job(json.load(handle))
        with tempfile.TemporaryDirectory() as directory:
            compiler = self.compiler(Path(directory))
            compiler.probe = lambda path: dict(is_video=True, width=1280, height=720, duration_sec=4000)
            plan = compiler.compile(job)
        self.assertEqual([step.operation for step in plan.steps], [
            "trim_video", "scale_media", "apply_multi_text_overlays",
            "trim_video", "scale_media", "trim_video", "scale_media",
            "stack_media", "apply_multi_text_overlays", "concatenate_clips",
        ])
        self.assertEqual(plan.steps[3].params["start_sec"], 2700)
        self.assertEqual(plan.steps[5].params["start_sec"], 3360)
        self.assertEqual(plan.steps[7].params["orientation"], "vertical")
        self.assertEqual(plan.steps[-1].params["clip_paths"], [
            plan.steps[2].params["output_path"], plan.steps[8].params["output_path"],
        ])

    def test_text_is_never_resolved_as_a_source(self):
        value = catalog_jobs()["image_text_overlay"]
        value["steps"][0]["text"] = "stash:scene:123"
        with tempfile.TemporaryDirectory() as directory:
            plan = self.compiler(Path(directory)).compile(validate_job(value))
            self.assertEqual(plan.steps[0].params["text_data"], "stash:scene:123")

    def test_cli_encoding_wins_and_preview_paths_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.compiler(Path(directory)).compile(validate_job(catalog_jobs()["pipeline_video_trim_scale_multi_overlay_quality_good"]), preview=True, overrides={"crf": 12, "codec": "h264_nvenc"})
            for step in plan.steps:
                self.assertEqual(step.params["video_crf"], 12)
                self.assertEqual(step.params["video_preset"], "p6")
                self.assertTrue(step.params["output_path"].endswith(".png"))

    def test_preflight_rejects_bad_media_contracts(self):
        cases = [
            {"input": "source.mp4", "output": "out.mp4", "steps": [{"op": "trim", "start": 0, "end": 100}]},
            {"input": "source.png", "output": "out.mp4", "steps": [{"op": "concat", "with": ["other.mp4"]}]},
            {"input": "source.png", "output": "out.png", "steps": [{"op": "caption", "text": "hi", "end": 3}]},
            {"input": "source.mp4", "output": "source.mp4", "steps": [{"op": "trim", "start": 0, "end": 2}]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValueError):
                    self.compiler(Path(directory)).compile(validate_job({"format": "meme/v1", **case}))

    def test_plan_cleans_owned_scratch_on_failure_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            compiler = self.compiler(Path(directory))
            for failure in (False, True):
                plan = compiler.compile(validate_job(catalog_jobs()["video_trim"]))
                engine = MagicMock()
                def render(operation, params, context):
                    Path(params["output_path"]).write_bytes(b"rendered")
                    return params["output_path"]
                engine.execute.side_effect = render
                if failure:
                    engine.execute.side_effect = RuntimeError("render failed")
                    with self.assertRaisesRegex(ValueError, "steps\\[0\\].*render failed"):
                        plan.execute(engine, no_cache=True)
                else:
                    self.assertEqual(plan.execute(engine, release=True, no_cache=True), plan.output)
                self.assertFalse(Path(plan.scratch).exists())


class PlanExecutionTests(unittest.TestCase):
    def test_failed_render_preserves_existing_output(self):
        from compact_compiler import ExecutionPlan, PlannedStep
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out.png"
            output.write_bytes(b"previous")
            plan = ExecutionPlan(output=str(output), scratch=str(root / "scratch"), steps=[
                PlannedStep(source="steps[0]", operation="scale_media", params={"output_path": str(output)})
            ])
            engine = MagicMock()
            def fail(operation, params, context):
                Path(params["output_path"]).write_bytes(b"partial")
                raise RuntimeError("render interrupted")
            engine.execute.side_effect = fail
            with self.assertRaisesRegex(ValueError, "render interrupted"):
                plan.execute(engine, no_cache=True)
            self.assertEqual(output.read_bytes(), b"previous")
            self.assertFalse(Path(plan.scratch).exists())

    def test_failed_replace_preserves_output_and_removes_temporary(self):
        from plan_executor import atomic_publish
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "source.png", root / "out.png"
            source.write_bytes(b"new")
            destination.write_bytes(b"previous")
            with patch("plan_executor.os.replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    atomic_publish(source, destination)
            self.assertEqual(destination.read_bytes(), b"previous")
            self.assertEqual(set(root.iterdir()), {source, destination})

    def test_persistent_cache_reuses_steps_and_invalidates_changed_inputs(self):
        import logging
        import os
        from PIL import Image
        from MemeEngine import MemeEngine
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (32, 24), "red").save(source)
            job = validate_job({"format": "meme/v1", "input": "source.png", "output": "out.png", "steps": [
                {"op": "scale", "max_long_side": 16}, {"op": "crop", "left": 2}
            ]})
            def run(current_job, expected_calls, **options):
                engine = MemeEngine(str(root), logging.getLogger("test"))
                plan = CompactCompiler(root, engine).compile(current_job, preview=options.get("preview", False))
                original = engine.execute
                operations = []
                def execute(operation, params, context=None):
                    if operation in {"scale_media", "crop_media"}:
                        operations.append(operation)
                    return original(operation, params, context)
                with patch.object(engine, "execute", side_effect=execute):
                    plan.execute(engine, release=True, **options)
                self.assertEqual(operations, expected_calls)
                return plan
            run(job, ["scale_media", "crop_media"])
            (root / "out.png").write_bytes(b"user modified")
            run(job, [])
            with Image.open(root / "out.png") as image:
                self.assertEqual(image.size, (14, 12))
            run(job, ["scale_media", "crop_media"], preview=True)
            run(job, [], preview=True)
            job.steps[1].left = 4
            run(job, ["crop_media"])
            job.output = "elsewhere.png"
            run(job, [])
            run(job, ["scale_media", "crop_media"], force=True)
            run(job, ["scale_media", "crop_media"], no_cache=True)
            timestamps = source.stat()
            Image.new("RGB", (32, 24), "blue").save(source)
            os.utime(source, ns=(timestamps.st_atime_ns, timestamps.st_mtime_ns))
            run(job, ["scale_media", "crop_media"])
            for artifact in (root / ".meme-cache").glob("*/artifacts/result.png"):
                artifact.write_bytes(b"corrupt")
            run(job, ["scale_media", "crop_media"])

    def test_cache_key_tracks_fonts_encoding_runtime_and_input_order(self):
        from plan_executor import PlanExecutor
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, other, font = root / "source.png", root / "other.png", root / "font.ttf"
            source.write_bytes(b"source")
            other.write_bytes(b"other")
            font.write_bytes(b"font version one")
            engine = MagicMock()
            renderer = engine._get_renderer.return_value
            renderer._font_path_for_style.return_value = font
            renderer.default_size = 40
            executor = PlanExecutor(root / "cache")
            params = {"base_media_path": str(source), "output_path": str(root / "out.mp4"),
                      "overlays": [{"text": "hello"}], "video_crf": 20}
            def key(values=params, runtime="runtime-one"):
                return executor._key("apply_multi_text_overlays", values, engine, False, runtime)
            original = key()
            self.assertNotEqual(original, key({**params, "video_crf": 30}))
            self.assertNotEqual(original, key(runtime="runtime-two"))
            self.assertNotEqual(original, key({**params, "output_path": str(root / "out.webm")}))
            font.write_bytes(b"font version two")
            self.assertNotEqual(original, key())
            concat = {"clip_paths": [str(source), str(other)], "output_path": str(root / "out.mp4")}
            first = executor._key("concatenate_clips", concat, engine, False, "runtime")
            concat["clip_paths"].reverse()
            self.assertNotEqual(first, executor._key("concatenate_clips", concat, engine, False, "runtime"))

    def test_completed_step_cache_survives_later_failure(self):
        import logging
        from PIL import Image
        from MemeEngine import MemeEngine
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (32, 24), "red").save(root / "source.png")
            output = root / "out.png"
            output.write_bytes(b"previous output")
            job = validate_job({"format": "meme/v1", "input": "source.png", "output": "out.png", "steps": [
                {"op": "scale", "max_long_side": 16}, {"op": "crop", "left": 2}
            ]})
            engine = MemeEngine(str(root), logging.getLogger("test"))
            plan = CompactCompiler(root, engine).compile(job)
            original = engine.execute
            def fail_crop(operation, params, context=None):
                if operation == "crop_media":
                    Path(params["output_path"]).write_bytes(b"partial")
                    raise RuntimeError("crop failed")
                return original(operation, params, context)
            with patch.object(engine, "execute", side_effect=fail_crop), self.assertRaisesRegex(ValueError, "steps\\[1\\].*crop failed"):
                plan.execute(engine)
            self.assertEqual(output.read_bytes(), b"previous output")
            self.assertFalse(Path(plan.scratch).exists())
            self.assertEqual(len(list((root / ".meme-cache").glob("*/manifest.json"))), 1)
            retry = CompactCompiler(root, engine).compile(job)
            def reject_scale(operation, params, context=None):
                if operation == "scale_media":
                    raise AssertionError("completed scale should be cached")
                return original(operation, params, context)
            with patch.object(engine, "execute", side_effect=reject_scale):
                retry.execute(engine, release=True)
            with Image.open(output) as image:
                self.assertEqual(image.size, (14, 12))

    def test_empty_output_is_not_published_or_cached(self):
        from compact_compiler import ExecutionPlan, PlannedStep
        from plan_executor import PlanExecutor
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out.png"
            output.write_bytes(b"previous")
            plan = ExecutionPlan(output=str(output), scratch=str(root / "scratch"), steps=[
                PlannedStep(source="steps[0]", operation="scale_media", params={"output_path": str(output)})
            ])
            engine = MagicMock()
            def render_empty(operation, params, context):
                Path(params["output_path"]).touch()
                return params["output_path"]
            engine.execute.side_effect = render_empty
            with patch("plan_executor.runtime_fingerprint", return_value="runtime"), self.assertRaisesRegex(ValueError, "nonempty output"):
                PlanExecutor(root / "cache").execute(plan, engine)
            self.assertEqual(output.read_bytes(), b"previous")
            self.assertFalse((root / "cache").exists())


class CompactCliTests(unittest.TestCase):
    def test_representative_image_gif_caption_and_stack_plans_render(self):
        import logging
        from PIL import Image
        from moviepy import ColorClip, VideoFileClip
        from MemeEngine import MemeEngine

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (96, 64), (30, 140, 90)).save(root / "image.png")
            frames = [Image.new("RGB", (96, 64), color) for color in ((30, 140, 90), (140, 30, 90))]
            frames[0].save(root / "source.gif", save_all=True, append_images=frames[1:], duration=200, loop=0)
            with ColorClip((96, 64), color=(30, 140, 90), duration=0.4) as clip:
                clip.write_videofile(str(root / "source.mp4"), fps=10, codec="libx264", audio=False, logger=None)
            cases = [
                ("image.png", "caption.png", [{"op": "caption", "text": "Hello", "size": 16}]),
                ("image.png", "panel.jpg", [{"op": "scale", "max_long_side": 80}, {"op": "panel", "text": "Hello", "size": 16}]),
                ("source.gif", "gif.mp4", [{"op": "scale", "max_long_side": 80}, {"op": "panel", "text": "Hello", "size": 16}]),
                ("source.mp4", "captions.mp4", [{"op": "crop", "left": 2}, {"op": "captions", "size": 16, "items": [{"text": "Hi", "at": "top", "end": 0.4}]}]),
                ("source.mp4", "stack.mp4", [{"op": "stack", "with": "image.png", "duration": 0.4}]),
                ("image.png", "stack.png", [{"op": "stack", "with": "image.png"}]),
            ]
            engine = MemeEngine(str(root), logging.getLogger("test"))
            for source, output, steps in cases:
                with self.subTest(output=output):
                    job = validate_job(dict(format="meme/v1", input=source, output=output, font="Arial", encode={"threads": 1}, steps=steps))
                    plan = CompactCompiler(root, engine).compile(job)
                    result = plan.execute(engine, release=True)
                    self.assertTrue(Path(result).is_file())
                    self.assertFalse(Path(plan.scratch).exists())
                    if output.endswith(".mp4"):
                        with VideoFileClip(result) as clip:
                            self.assertGreater(clip.duration, 0)
                            self.assertGreater(clip.get_frame(0).var(), 0)
                    else:
                        with Image.open(result) as image:
                            self.assertGreater(image.width, 0)
                    cached = CompactCompiler(root, engine).compile(job)
                    with patch.object(engine, "execute", side_effect=AssertionError("warm plan must not render")):
                        self.assertEqual(cached.execute(engine), result)
                    for step in cached.steps:
                        if "overlay_dir" in step.params:
                            self.assertTrue(list(Path(step.params["overlay_dir"]).glob("*.png")))

    def test_validate_is_offline_and_supports_catalog_selection(self):
        import run_meme_job
        args = ["run_meme_job.py", str(ROOT / "config/mockups/compact-examples.json"), "--example", "video_concat_two_trimmed", "--validate"]
        with patch.object(sys, "argv", args), patch.object(run_meme_job, "MemeEngine", side_effect=AssertionError("must be offline")), contextlib.redirect_stdout(io.StringIO()) as output:
            run_meme_job.main()
        self.assertIn("Valid:", output.getvalue())

    def test_schema_does_not_require_config(self):
        import run_meme_job
        with patch.object(sys, "argv", ["run_meme_job.py", "--schema"]), contextlib.redirect_stdout(io.StringIO()) as output:
            run_meme_job.main()
        self.assertIn("steps", json.loads(output.getvalue())["properties"])

    def test_cli_expands_and_renders_trimmed_concat(self):
        import run_meme_job
        from moviepy import ColorClip, VideoFileClip
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, color, size in (("first.mp4", (240, 0, 0), (80, 40)), ("second.mp4", (0, 240, 0), (40, 80))):
                with ColorClip(size, color=color, duration=0.6) as clip:
                    clip.write_videofile(str(root / name), fps=10, codec="libx264", audio=False, logger=None)
            job = {"format": "meme/v1", "input": "first.mp4", "output": "out.mp4", "steps": [
                {"op": "trim", "start": 0.1, "end": 0.5},
                {"op": "concat", "with": [{"input": "second.mp4", "steps": [{"op": "trim", "start": 0.2, "end": 0.5}]}]},
            ]}
            config = root / "job.json"
            config.write_text(json.dumps(job), encoding="utf-8")
            args = ["run_meme_job.py", str(config), "--project-root", str(root), "--threads", "1"]
            with patch.object(sys, "argv", [*args, "--expand"]), contextlib.redirect_stdout(io.StringIO()) as output:
                run_meme_job.main()
            plan = json.loads(output.getvalue())
            self.assertFalse(Path(plan["scratch"]).exists())
            self.assertFalse((root / "out.mp4").exists())
            with patch.object(sys, "argv", [*args, "--release"]):
                run_meme_job.main()
            with VideoFileClip(str(root / "out.mp4")) as clip:
                self.assertAlmostEqual(clip.duration, 0.7, places=1)
                self.assertGreater(clip.get_frame(0.1)[20, 40, 0], 200)
                self.assertGreater(clip.get_frame(0.5)[20, 40, 1], 200)
            self.assertEqual(list((root / ".meme-scratch").iterdir()), [])
            with patch.object(sys, "argv", [*args, "--preview-only", "--release"]):
                run_meme_job.main()
            from PIL import Image
            with Image.open(root / "out.png") as image:
                self.assertEqual(image.size, (80, 80))


class ConcatRenderingTests(unittest.TestCase):
    def test_pixel_aspect_ratio_and_rotation(self):
        from operations.concatenate_clips import display_size
        clip = MagicMock(filename="source.mp4", size=(720, 576))
        clip.reader.rotation = 0
        with patch("operations.concatenate_clips.subprocess.run", return_value=MagicMock(stdout='{"streams":[{"sample_aspect_ratio":"16:15"}]}')):
            self.assertEqual(display_size(clip), (768, 576))
            clip.size = (576, 720)
            clip.reader.rotation = 90
            self.assertEqual(display_size(clip), (576, 768))

    def test_canvas_and_fit(self):
        self.assertEqual(canvas_size([(1280, 720), (1080, 1920)]), (1920, 1080))
        self.assertEqual(canvas_size([(720, 1280), (1920, 1080)]), (1080, 1920))
        self.assertEqual(fitted_size((1080, 1920), (1920, 1080)), (608, 1080))

    def test_blurred_background_covers_canvas_and_softens_detail(self):
        import numpy as np
        from PIL import Image, ImageOps

        for size, canvas in [((40, 80), (80, 40)), ((80, 40), (40, 80))]:
            with self.subTest(size=size):
                pixels = np.zeros((size[1], size[0], 3), dtype=np.uint8)
                pixels[::2] = 240
                frame = Image.fromarray(pixels)
                background = blurred_background(frame, canvas)
                sharp = ImageOps.fit(frame, canvas, method=Image.Resampling.LANCZOS)
                self.assertEqual(background.size, canvas)
                self.assertLess(np.asarray(background).std(), np.asarray(sharp).std() / 2)

    def test_real_concat_preserves_order_blurred_padding_fps_and_audio(self):
        import logging
        import numpy as np
        from moviepy import AudioClip, ColorClip, VideoClip, VideoFileClip
        from MemeEngine import MemeEngine

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, output = root / "first.mp4", root / "second.mp4", root / "out.mp4"
            with ColorClip((80, 40), color=(240, 0, 0), duration=0.5) as clip:
                clip.write_videofile(str(first), fps=10, codec="libx264", audio=False, logger=None)
            with AudioClip(lambda time: 0.2 * np.sin(440 * 2 * np.pi * time), duration=0.5, fps=44100) as audio:
                def second_frame(time):
                    color = (0, 240, 0) if time < 0.25 else (0, 0, 240)
                    return np.full((80, 40, 3), color, dtype=np.uint8)

                with VideoClip(second_frame, duration=0.5).with_audio(audio) as clip:
                    clip.write_videofile(str(second), fps=20, codec="libx264", audio_codec="aac", logger=None)
            engine = MemeEngine(str(root), logging.getLogger("test"))
            params = dict(clip_paths=[str(first), str(second)], output_path=str(output), video_codec="libx264", threads=1)
            engine.execute("concatenate_clips", params)
            with VideoFileClip(str(output)) as clip:
                self.assertEqual(tuple(clip.size), (80, 40))
                self.assertEqual(clip.fps, 10)
                self.assertAlmostEqual(clip.duration, 1.0, places=1)
                self.assertGreater(clip.get_frame(0.2)[20, 40, 0], 200)
                frame = clip.get_frame(0.7)
                self.assertGreater(frame[20, 2, 1], 200)
                self.assertGreater(frame[20, 40, 1], 200)
                later = clip.get_frame(0.9)
                self.assertGreater(later[20, 2, 2], 200)
                self.assertGreater(later[20, 40, 2], 200)
                self.assertIsNotNone(clip.audio)
                self.assertLess(np.abs(clip.audio.get_frame(0.2)).max(), 0.02)
                self.assertGreater(np.abs(clip.audio.get_frame(np.linspace(0.65, 0.75, 100))).max(), 0.05)
            from PIL import Image
            params["preview_only"] = True
            result = engine.execute("concatenate_clips", params)
            with Image.open(result) as image:
                self.assertEqual(image.size, (80, 80))
                self.assertGreater(image.getpixel((2, 60))[1], 200)
            first.unlink()
            second.unlink()