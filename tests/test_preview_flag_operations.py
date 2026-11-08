import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

from MemeEngine import MemeEngine
from operations.base import OperationContext


class PreviewFlagOperationTests(unittest.TestCase):
    def test_timed_caption_preview_shows_each_caption_state_in_a_separate_frame(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_path = tmp_path / "base.png"
            Image.new("RGBA", (4, 4), (0, 0, 0, 255)).save(base_path)
            output_path = tmp_path / "render" / "captions.mp4"
            engine = MemeEngine(base_dir=str(tmp_path), logger=logging.getLogger("test"))
            renderer = MagicMock()
            renderer.default_size = 12
            renderer.parse_tokens.side_effect = lambda text: [{"text": text}]

            def render_overlay(tokens, *args, **kwargs):
                color = (255, 0, 0, 255) if tokens[0]["text"] == "First Caption" else (0, 0, 255, 255)
                return Image.new("RGBA", (4, 4), color), {}

            renderer.generate_canvas.side_effect = render_overlay
            with patch.object(engine, "_get_renderer", return_value=renderer):
                result = engine.execute(
                    "apply_multi_text_overlays",
                    {
                        "base_media_path": str(base_path),
                        "output_path": str(output_path),
                        "preview_only": True,
                        "overlays": [
                            {"text": "First Caption", "start_time": 0, "end_time": 5},
                            {"text": "Second Caption", "start_time": 5, "end_time": 10},
                        ],
                    },
                )

            with Image.open(result) as preview:
                self.assertEqual(preview.size, (8, 4))
                self.assertEqual(preview.getpixel((1, 1)), (255, 0, 0, 255))
                self.assertEqual(preview.getpixel((5, 1)), (0, 0, 255, 255))
            self.assertEqual([call.args[0] for call in renderer.parse_tokens.call_args_list], ["First Caption", "Second Caption"])

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
