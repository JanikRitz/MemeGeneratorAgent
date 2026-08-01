import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

from operations.base import OperationContext
from operations.utility_ops import WriteVideoOperation


class WriteVideoOperationTests(unittest.TestCase):
    def test_write_video_defaults_to_h264_nvenc(self):
        handler = WriteVideoOperation()
        mock_clip = MagicMock()
        mock_engine = MagicMock()
        mock_context = MagicMock(spec=OperationContext)

        params = {
            "clip": mock_clip,
            "output_path": "render/test.mp4",
        }
        handler.execute(mock_engine, params, mock_context)

        mock_clip.write_videofile.assert_called_once()
        _, kwargs = mock_clip.write_videofile.call_args
        self.assertEqual(kwargs["codec"], "h264_nvenc")
        self.assertEqual(kwargs["audio_codec"], "aac")

    def test_write_video_passes_threads_and_custom_codec(self):
        handler = WriteVideoOperation()
        mock_clip = MagicMock()
        mock_engine = MagicMock()
        mock_context = MagicMock(spec=OperationContext)

        params = {
            "clip": mock_clip,
            "output_path": "render/test.mp4",
            "video_codec": "h264_nvenc",
            "threads": 4,
            "video_crf": 23,
            "video_preset": "p4",
        }
        handler.execute(mock_engine, params, mock_context)

        mock_clip.write_videofile.assert_called_once()
        _, kwargs = mock_clip.write_videofile.call_args
        self.assertEqual(kwargs["codec"], "h264_nvenc")
        self.assertEqual(kwargs["threads"], 4)
        self.assertEqual(kwargs["ffmpeg_params"], ["-cq", "23", "-preset", "p4"])

    def test_build_ffmpeg_params_rate_control_mapping(self):
        handler = WriteVideoOperation()

        # NVENC mapping
        nvenc_params = handler._build_ffmpeg_params(20, "fast", video_codec="h264_nvenc")
        self.assertEqual(nvenc_params, ["-cq", "20", "-preset", "fast"])

        # QSV mapping
        qsv_params = handler._build_ffmpeg_params(20, "fast", video_codec="h264_qsv")
        self.assertEqual(qsv_params, ["-global_quality", "20", "-preset", "fast"])

        # Software libx264 mapping
        x264_params = handler._build_ffmpeg_params(20, "fast", video_codec="libx264")
        self.assertEqual(x264_params, ["-crf", "20", "-preset", "fast"])


if __name__ == "__main__":
    unittest.main()
