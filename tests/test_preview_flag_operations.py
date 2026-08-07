import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

from MemeEngine import MemeEngine
from operations.base import OperationContext


class PreviewFlagOperationTests(unittest.TestCase):
    def test_stack_media_preview_emits_png_without_writing_video(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            left_path = tmp_path / "left.png"
            right_path = tmp_path / "right.png"
            Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(left_path)
            Image.new("RGBA", (8, 8), (0, 0, 255, 255)).save(right_path)

            output_path = tmp_path / "render" / "out.mp4"
            engine = MemeEngine(base_dir=str(tmp_path), logger=logging.getLogger("test"))

            with patch.object(engine, "_write_video", side_effect=AssertionError("video write should not happen in preview")):
                result = engine.execute(
                    "stack_media",
                    {
                        "path1": str(left_path),
                        "path2": str(right_path),
                        "output_path": str(output_path),
                        "preview_only": True,
                    },
                )

            expected_preview = str(output_path.with_suffix(".png"))
            self.assertEqual(result, expected_preview)
            self.assertTrue(Path(expected_preview).exists())

    def test_stack_media_preview_uses_context_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            left_path = tmp_path / "left.png"
            right_path = tmp_path / "right.png"
            Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(left_path)
            Image.new("RGBA", (8, 8), (0, 0, 255, 255)).save(right_path)

            output_path = tmp_path / "render" / "out.mp4"
            engine = MemeEngine(base_dir=str(tmp_path), logger=logging.getLogger("test"))
            context = OperationContext(engine=engine, logger=engine.logger, preview_only_override=True)

            with patch.object(engine, "_write_video", side_effect=AssertionError("video write should not happen in preview")):
                result = engine.execute(
                    "stack_media",
                    {
                        "path1": str(left_path),
                        "path2": str(right_path),
                        "output_path": str(output_path),
                    },
                    context=context,
                )

            expected_preview = str(output_path.with_suffix(".png"))
            self.assertEqual(result, expected_preview)
            self.assertTrue(Path(expected_preview).exists())

    def test_resolve_path_uses_preview_png_when_video_path_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_image = tmp_path / "render" / "input.png"
            source_image.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (4, 4), (255, 255, 255, 255)).save(source_image)

            engine = MemeEngine(base_dir=str(tmp_path), logger=logging.getLogger("test"))
            context = OperationContext(engine=engine, logger=engine.logger, preview_only_override=True)

            resolved = engine.execute(
                "resolve_path",
                {"path_value": str(source_image.with_suffix(".mp4"))},
                context=context,
            )

            self.assertEqual(resolved, source_image)


if __name__ == "__main__":
    unittest.main()
