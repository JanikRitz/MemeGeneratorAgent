import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

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
