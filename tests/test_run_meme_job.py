import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

import run_meme_job
from config_preparation import ConfigPreparationService


class ConfigPreparationServiceTests(unittest.TestCase):
    def test_prepare_config_rewrites_media_paths(self):
        root = Path("/tmp/project")
        config = {"params": {"input_path": "media/example.mp4", "output_path": "render/out.mp4"},
                  "nested": ["logs/job.log", {"path": "config/example.json"}]}
        prepared = ConfigPreparationService().prepare_config(config, root)
        self.assertEqual(prepared["params"]["input_path"], str(root / "media/example.mp4"))
        self.assertEqual(prepared["params"]["output_path"], str(root / "render/out.mp4"))
        self.assertEqual(prepared["nested"][0], str(root / "logs/job.log"))
        self.assertEqual(prepared["nested"][1]["path"], str(root / "config/example.json"))


class RunMemeJobScriptTests(unittest.TestCase):
    def test_tty_progress_counts_completed_operations_and_closes_on_failure(self):
        from PIL import Image

        class TerminalOutput(io.StringIO):
            def isatty(self):
                return True

        bars = []
        progress_factory = run_meme_job.tqdm
        execute_operation = run_meme_job.MemeEngine.execute

        def fail_scale(engine, operation, params, context=None):
            if operation == "scale_media":
                raise RuntimeError("test render failure")
            return execute_operation(engine, operation, params, context)

        def record_bar(*args, **kwargs):
            bar = progress_factory(*args, **kwargs)
            bars.append(bar)
            return bar

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (16, 16), "red").save(root / "source.png")
            config = root / "job.json"
            config.write_text(json.dumps({"format": "meme/v1", "input": "source.png", "output": "out.png", "steps": [
                {"op": "scale", "max_long_side": 8}, {"op": "crop", "left": 2}
            ]}), encoding="utf-8")
            args = ["run_meme_job.py", str(config), "--project-root", str(root), "--release"]
            for status in ("miss", "hit"):
                with self.subTest(status=status), patch.object(sys, "argv", args), \
                        contextlib.redirect_stderr(TerminalOutput()) as errors, contextlib.redirect_stdout(io.StringIO()) as output, \
                        patch.object(run_meme_job, "tqdm", side_effect=record_bar):
                    run_meme_job.main()
                self.assertEqual(bars[-1].n, 2)
                self.assertEqual(bars[-1].total, 2)
                self.assertTrue(bars[-1].disable)
                self.assertIn("\r", errors.getvalue())
                self.assertIn("2/2 ops", errors.getvalue())
                for label in ("[1/2] steps[0] (scale_media)", "[2/2] steps[1] (crop_media)"):
                    self.assertIn(f"INFO | {label}: cache {status}", errors.getvalue())
                self.assertNotIn("INFO | scale_media resolved", errors.getvalue())
                self.assertEqual(output.getvalue().strip(), str(root / "out.png"))
            with patch.object(sys, "argv", [*args, "--no-cache"]), \
                    contextlib.redirect_stderr(TerminalOutput()) as errors, contextlib.redirect_stdout(io.StringIO()) as output, \
                    patch.object(run_meme_job, "tqdm", side_effect=record_bar), \
                    patch.object(run_meme_job.MemeEngine, "execute", new=fail_scale):
                with self.assertRaises(SystemExit) as raised:
                    run_meme_job.main()
            self.assertEqual(raised.exception.code, 1)
            self.assertEqual(bars[-1].n, 0)
            self.assertTrue(bars[-1].disable)
            self.assertIn("test render failure", errors.getvalue())
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(list((root / ".meme-scratch").iterdir()), [])

    def test_progress_timings_and_cache_modes_are_reported_on_stderr(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (16, 16), "red").save(root / "source.png")
            config = root / "job.json"
            config.write_text(json.dumps({"format": "meme/v1", "input": "source.png", "output": "out.png", "steps": [
                {"op": "scale", "max_long_side": 8}, {"op": "crop", "left": 2}
            ]}), encoding="utf-8")
            args = ["run_meme_job.py", str(config), "--project-root", str(root), "--release"]
            for flags, status, counts in (([], "miss", "0 cache hits, 2 rendered"),
                                           ([], "hit", "2 cache hits, 0 rendered"),
                                           (["--force", "--verbose"], "forced rebuild", "0 cache hits, 2 rendered"),
                                           (["--no-cache"], "disabled", "0 cache hits, 2 rendered")):
                with self.subTest(flags=flags, status=status), patch.object(sys, "argv", [*args, *flags]), \
                        contextlib.redirect_stderr(io.StringIO()) as errors, contextlib.redirect_stdout(io.StringIO()) as output:
                    run_meme_job.main()
                logs = errors.getvalue()
                self.assertNotIn("\r", logs)
                self.assertEqual(output.getvalue().strip(), str(root / "out.png"))
                self.assertIn("[1/2] steps[0] (scale_media)", logs)
                self.assertIn("[2/2] steps[1] (crop_media)", logs)
                self.assertIn(f"cache {status}", logs)
                self.assertIn(counts, logs)
                self.assertIn("Compile (engine, sources, metadata):", logs)
                self.assertIn("Run total:", logs)
                if "--verbose" in flags:
                    self.assertIn("cache key", logs)
                else:
                    self.assertNotIn("cache key", logs)
                for phase in ("fingerprint", "key", "restore", "render", "store", "publish", "cleanup"):
                    self.assertRegex(logs, rf"{phase} \d+\.\d{{3}}s")
                if status == "hit":
                    self.assertIn("rendering skipped", logs)
                    self.assertIn("render 0.000s", logs)
                else:
                    self.assertLess(logs.index(f"cache {status}"), logs.index("publishing output"))
            with patch.object(sys, "argv", [*args, "--expand"]), contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                run_meme_job.main()
            self.assertEqual(len(json.loads(output.getvalue())["steps"]), 2)
            self.assertEqual(errors.getvalue(), "")

    def test_legacy_configs_are_rejected_without_engine_creation(self):
        for config in ({"operation": "trim_video", "params": {}}, {"pipeline": []}):
            with self.subTest(config=config), tempfile.TemporaryDirectory() as directory:
                config_path = Path(directory) / "job.json"
                config_path.write_text(json.dumps(config), encoding="utf-8")
                with patch.object(sys, "argv", ["run_meme_job.py", str(config_path)]), patch.object(run_meme_job, "MemeEngine") as factory, contextlib.redirect_stderr(io.StringIO()) as errors:
                    with self.assertRaises(SystemExit) as raised:
                        run_meme_job.main()
                self.assertEqual(raised.exception.code, 1)
                self.assertIn("Legacy configs are no longer supported", errors.getvalue())
                factory.assert_not_called()

    def test_cli_forwards_cache_controls_and_keeps_other_scratch(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (16, 16), "red").save(root / "source.png")
            config = root / "job.json"
            config.write_text(json.dumps({"format": "meme/v1", "input": "source.png", "output": "out.png", "steps": [{"op": "scale", "max_long_side": 8}]}), encoding="utf-8")
            sibling = root / ".meme-scratch" / "other-job"
            sibling.mkdir(parents=True)
            marker = sibling / "active"
            marker.touch()
            args = ["run_meme_job.py", str(config), "--project-root", str(root), "--cache-dir", "cache", "--release"]
            for flags, expected_force, expected_cache in (([], False, root / "cache"), (["--force"], True, root / "cache"), (["--no-cache"], False, None)):
                with self.subTest(flags=flags), patch.object(sys, "argv", [*args, *flags]), patch.object(run_meme_job, "PlanExecutor") as executor, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    run_meme_job.main()
                    executor.assert_called_once_with(expected_cache)
                    self.assertEqual(executor.return_value.execute.call_args.kwargs, {"preview": False, "release": True, "force": expected_force})
            with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
                run_meme_job.main()
            self.assertTrue((root / "cache").is_dir())
            self.assertTrue(marker.exists())
            self.assertEqual(list((root / ".meme-scratch").iterdir()), [sibling])

    def test_arg_parser_supports_hardware_and_thread_overrides(self):
        args = run_meme_job.build_arg_parser().parse_args(["config.json", "--video-codec", "h264_nvenc", "--threads", "8", "--video-crf", "18", "--video-preset", "p6"])
        self.assertEqual(args.video_codec, "h264_nvenc")
        self.assertEqual(args.threads, 8)
        self.assertEqual(args.video_crf, 18)
        self.assertEqual(args.video_preset, "p6")