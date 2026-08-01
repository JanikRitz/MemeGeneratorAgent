import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

import run_meme_job
from artifact_cleanup import ArtifactCleanupService
from config_preparation import ConfigPreparationService


class ConfigPreparationServiceTests(unittest.TestCase):
    def test_prepare_config_rewrites_media_paths(self):
        service = ConfigPreparationService()
        project_root = Path("/tmp/project")
        config = {
            "params": {"input_path": "media/example.mp4", "output_path": "render/out.mp4"},
            "nested": ["logs/job.log", {"path": "config/example.json"}],
        }

        prepared = service.prepare_config(config, project_root)

        self.assertEqual(prepared["params"]["input_path"], str(project_root / "media/example.mp4"))
        self.assertEqual(prepared["params"]["output_path"], str(project_root / "render/out.mp4"))
        self.assertEqual(prepared["nested"][0], str(project_root / "logs/job.log"))
        self.assertEqual(prepared["nested"][1]["path"], str(project_root / "config/example.json"))


class ArtifactCleanupServiceTests(unittest.TestCase):
    def test_cleanup_files_removes_generated_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            keep_file = tmp_path / "keep.png"
            keep_file.write_bytes(b"keep")
            stale_file = tmp_path / "stale.png"
            stale_file.write_bytes(b"stale")

            service = ArtifactCleanupService()
            removed = service.cleanup_files({stale_file}, keep_path=keep_file)

            self.assertEqual(removed, 1)
            self.assertTrue(keep_file.exists())
            self.assertFalse(stale_file.exists())


class RunMemeJobScriptTests(unittest.TestCase):
    def test_main_passes_release_cleanup_hooks_to_runner(self):
        class FakeJobExecutionService:
            def __init__(self):
                self.calls = []

            def run_config_file(
                self,
                config_path,
                config,
                project_root,
                args,
                logger=None,
                output_path_resolver=None,
                generated_path_collector=None,
            ):
                self.calls.append(
                    {
                        "output_path_resolver": output_path_resolver,
                        "generated_path_collector": generated_path_collector,
                    }
                )
                return True

        fake_service = FakeJobExecutionService()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_path = tmp_path / "config.json"
            config_path.write_text(json.dumps({"params": {"output_path": str(tmp_path / "out.png")}}), encoding="utf-8")

            with patch.object(run_meme_job, "JOB_EXECUTION_SERVICE", fake_service), patch.object(
                run_meme_job,
                "prepare_config_for_run",
                return_value={"params": {"output_path": str(tmp_path / "out.png")}},
            ), patch.object(run_meme_job, "load_config_file", return_value={"params": {"output_path": str(tmp_path / "out.png")}}), patch.object(
                sys,
                "argv",
                ["run_meme_job.py", str(config_path), "--release"],
            ):
                run_meme_job.main()

            self.assertEqual(len(fake_service.calls), 1)
            self.assertIsNotNone(fake_service.calls[0]["output_path_resolver"])
            self.assertIsNotNone(fake_service.calls[0]["generated_path_collector"])

    def test_arg_parser_supports_hardware_and_thread_overrides(self):
        parser = run_meme_job.build_arg_parser()
        args = parser.parse_args(["config.json", "--video-codec", "h264_nvenc", "--threads", "8", "--video-crf", "18", "--video-preset", "p6"])

        self.assertEqual(args.video_codec, "h264_nvenc")
        self.assertEqual(args.threads, 8)
        self.assertEqual(args.video_crf, 18)
        self.assertEqual(args.video_preset, "p6")

    def test_job_execution_service_applies_cli_overrides(self):
        from unittest.mock import MagicMock
        from job_execution import JobExecutionService

        service = JobExecutionService()
        mock_engine = MagicMock()
        mock_logger = MagicMock()
        mock_handler = MagicMock()
        mock_handler.execute.return_value = "render/out.mp4"

        service.registry.get = MagicMock(return_value=mock_handler)

        args = run_meme_job.build_arg_parser().parse_args(
            ["config.json", "--video-codec", "h264_nvenc", "--threads", "4"]
        )

        config = {
            "operation": "trim_video",
            "params": {
                "input_path": "media/in.mp4",
                "output_path": "render/out.mp4",
            },
        }

        service.execute_config(config, mock_engine, args, mock_logger)

        self.assertTrue(mock_handler.execute.called)
        (engine, params, context), _ = mock_handler.execute.call_args
        self.assertEqual(params["video_codec"], "h264_nvenc")
        self.assertEqual(params["threads"], 4)

