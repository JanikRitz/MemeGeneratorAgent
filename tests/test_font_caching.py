import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

from MemeEngine import MemeEngine
from RichTextRenderer import RichTextRenderer


class TestFontCaching(unittest.TestCase):
    def test_meme_engine_resolve_font_path_caching(self):
        # Clear cache info first
        MemeEngine._resolve_font_path.cache_clear()

        # Test resolving existing font path
        font_path = r"C:\Windows\Fonts\arial.ttf"
        if not Path(font_path).exists():
            font_path = r"C:\Windows\Fonts\COMIC.ttf"

        resolved_1 = MemeEngine._resolve_font_path(font_path)
        cache_info_1 = MemeEngine._resolve_font_path.cache_info()

        resolved_2 = MemeEngine._resolve_font_path(font_path)
        cache_info_2 = MemeEngine._resolve_font_path.cache_info()

        self.assertEqual(resolved_1, resolved_2)
        self.assertEqual(cache_info_2.hits, cache_info_1.hits + 1)

    def test_rich_text_renderer_font_caching(self):
        renderer = RichTextRenderer(default_size=40)
        renderer._load_font.cache_clear()
        renderer._font_path_for_style.cache_clear()

        # First call loads font
        font1 = renderer._load_font(bold=False, italic=False, size=40)
        font_info_1 = renderer._load_font.cache_info()

        # Second call returns cached font instance
        font2 = renderer._load_font(bold=False, italic=False, size=40)
        font_info_2 = renderer._load_font.cache_info()

        self.assertIs(font1, font2)
        self.assertEqual(font_info_2.hits, font_info_1.hits + 1)

        # Style path resolution caching test
        path1 = renderer._font_path_for_style(bold=True, italic=False)
        style_info_1 = renderer._font_path_for_style.cache_info()

        path2 = renderer._font_path_for_style(bold=True, italic=False)
        style_info_2 = renderer._font_path_for_style.cache_info()

        self.assertEqual(path1, path2)
        self.assertEqual(style_info_2.hits, style_info_1.hits + 1)

    def test_benchmark_generate_canvas_100_iterations(self):
        renderer = RichTextRenderer(default_size=32)
        complex_text = "<b>Hello</b> <i>World</i>! <span color='red'>Rich Text</span> test sequence with <b>bold</b> and <i>italic</i> words."

        renderer._load_font.cache_clear()
        renderer._font_path_for_style.cache_clear()

        tokens = renderer.parse_tokens(complex_text)
        start_time = time.perf_counter()
        for _ in range(100):
            canvas, metrics = renderer.generate_canvas(
                structured_text=tokens,
                container_width=400,
                container_height=300,
                return_metrics=True,
            )
            self.assertIsNotNone(canvas)
            self.assertFalse(metrics["overflowed"])
        elapsed = time.perf_counter() - start_time

        cache_info = renderer._load_font.cache_info()
        self.assertGreater(cache_info.hits, 0)
        # Verify 100 iterations of complex text rendering complete fast (< 2.0s)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
