import html
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageColor, ImageDraw, ImageFont

class RichTextRenderer:
    def __init__(self, default_font_path=r"C:\\Windows\\Fonts\\impact.ttf", default_size=40):
        self.default_font_path = Path(default_font_path)
        self.default_size = default_size
        self.logger = logging.getLogger("rich_text_renderer")
        self._missing_variant_warned: set = set()

    def _font_path_for_style(self, bold: bool, italic: bool) -> Path:
        if not bold and not italic:
            return self.default_font_path

        # Try to find a variant of the same font family by common filename suffixes.
        # This keeps Impact as Impact (no variants exist → falls back to Impact itself)
        # while Arial correctly resolves to arialbd/ariali/arialbi.
        stem = self.default_font_path.stem.lower()
        folder = self.default_font_path.parent
        suffix = self.default_font_path.suffix

        if bold and italic:
            variant_suffixes = ["bi", "z", "bolditalic"]
        elif bold:
            variant_suffixes = ["bd", "b", "bold"]
        else:
            variant_suffixes = ["i", "italic"]

        for s in variant_suffixes:
            candidate = folder / (stem + s + suffix)
            if candidate.exists():
                return candidate

        style_label = "bold+italic" if bold and italic else ("bold" if bold else "italic")
        warn_key = (self.default_font_path.name, style_label)
        if warn_key not in self._missing_variant_warned:
            self._missing_variant_warned.add(warn_key)
            self.logger.warning(
                "No %s variant found for font '%s' -- falling back to default font. "
                "Bold/italic will not be visually distinct. "
                "To enable styled variants, use a font that ships with variant files (e.g. arial.ttf).",
                style_label,
                self.default_font_path.name,
            )
        # No variant found for this font family — stay consistent with the default font.
        return self.default_font_path

    def _load_font(self, bold: bool, italic: bool, size: int):
        font_path = self._font_path_for_style(bold, italic)
        try:
            return ImageFont.truetype(str(font_path), size)
        except OSError:
            return ImageFont.load_default()

    def _split_words(self, text: str) -> List[str]:
        # [ \t]* on BOTH sides: optional leading whitespace (preserves inter-token boundary
        # spaces), optional trailing whitespace (consumed so the next word starts clean).
        # Newlines are captured as standalone tokens and never consumed by \s*.
        return re.findall(r"[ \t]*\S+[ \t]*|\n", text)

    def _to_rgba(self, color: Any, default: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
        if isinstance(color, str):
            value = color.strip().lower()
            if value == "transparent":
                return 0, 0, 0, 0
            try:
                parsed = ImageColor.getcolor(color.strip(), "RGBA")
                return int(parsed[0]), int(parsed[1]), int(parsed[2]), int(parsed[3])
            except ValueError:
                return default
        if isinstance(color, (tuple, list)):
            if len(color) == 4:
                return int(color[0]), int(color[1]), int(color[2]), int(color[3])
            if len(color) == 3:
                return int(color[0]), int(color[1]), int(color[2]), 255
        return default

    def _markdown_tokens(self, text_string: str) -> List[Dict]:
        tokens: List[Dict] = []
        current = {"bold": False, "italic": False, "color": "#FFFFFF"}
        i = 0
        buffer = []

        def flush_buffer():
            if buffer:
                tokens.append(
                    {
                        "text": "".join(buffer),
                        "bold": current["bold"],
                        "italic": current["italic"],
                        "color": current["color"],
                    }
                )
                buffer.clear()

        while i < len(text_string):
            if text_string[i : i + 2] == "**":
                flush_buffer()
                current["bold"] = not current["bold"]
                i += 2
                continue
            if text_string[i] == "*":
                flush_buffer()
                current["italic"] = not current["italic"]
                i += 1
                continue

            color_open = re.match(
                r"\[color\s*=\s*(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)\]",
                text_string[i:],
            )
            if color_open:
                flush_buffer()
                current["color"] = color_open.group(1)
                i += len(color_open.group(0))
                continue

            if text_string[i : i + 8].lower() == "[/color]":
                flush_buffer()
                current["color"] = "#FFFFFF"
                i += 8
                continue

            buffer.append(text_string[i])
            i += 1

        flush_buffer()
        return tokens

    def _html_tokens(self, text_string: str) -> List[Dict]:
        class _InlineHTMLParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tokens: List[Dict] = []
                self.stack = [{"bold": False, "italic": False, "color": "#FFFFFF"}]

            def _style(self):
                return self.stack[-1].copy()

            def handle_starttag(self, tag, attrs):
                style = self._style()
                attrs_map = {k.lower(): v for k, v in attrs}
                tag = tag.lower()
                if tag in {"b", "strong"}:
                    style["bold"] = True
                if tag in {"i", "em"}:
                    style["italic"] = True
                if tag == "span":
                    inline_style = attrs_map.get("style", "")
                    color_match = re.search(r"color\s*:\s*([^;]+)", inline_style, re.IGNORECASE)
                    if color_match:
                        style["color"] = color_match.group(1).strip()
                self.stack.append(style)

            def handle_endtag(self, _tag):
                if len(self.stack) > 1:
                    self.stack.pop()

            def handle_data(self, data):
                if not data:
                    return
                style = self._style()
                self.tokens.append(
                    {
                        "text": html.unescape(data),
                        "bold": style["bold"],
                        "italic": style["italic"],
                        "color": style["color"],
                    }
                )

        parser = _InlineHTMLParser()
        parser.feed(text_string)
        return parser.tokens

    def parse_tokens(self, text_string):
        if "<" in text_string and ">" in text_string:
            return self._html_tokens(text_string)
        return self._markdown_tokens(text_string)

    def generate_canvas(
        self,
        structured_text,
        container_width,
        container_height,
        horizontal_align: str = "center",
        vertical_align: str = "center",
        padding: int = 24,
        line_spacing: int = None,
        paragraph_spacing: int = None,
        line_height: float = 1.0,
        stroke_width: int = 3,
        stroke_fill: str = "#000000",
        shadow_enabled: bool = True,
        shadow_offset: Tuple[int, int] = (2, 2),
        shadow_fill: Any = (0, 0, 0, 180),
        background_fill: Any = (0, 0, 0, 0),
        return_metrics: bool = False,
    ):
        canvas = Image.new(
            "RGBA",
            (container_width, container_height),
            self._to_rgba(background_fill, (0, 0, 0, 0)),
        )
        draw = ImageDraw.Draw(canvas)

        shadow_rgba = self._to_rgba(shadow_fill, (0, 0, 0, 180))
        max_width = max(1, int(container_width - (padding * 2)))
        line_height = max(0.6, float(line_height))

        font_sizes = [int(token.get("size", self.default_size)) for token in structured_text if token.get("text")]
        avg_font_size = max(8, int(sum(font_sizes) / len(font_sizes))) if font_sizes else self.default_size
        if line_spacing is None:
            line_spacing = max(2, int(round(avg_font_size * 0.16)))
        if paragraph_spacing is None:
            paragraph_spacing = max(line_spacing + 2, int(round(avg_font_size * 0.34)))

        segments = []
        for token in structured_text:
            text = token.get("text", "")
            if not text:
                continue

            style = {
                "color": token.get("color", "#FFFFFF"),
                "bold": bool(token.get("bold", False)),
                "italic": bool(token.get("italic", False)),
                "size": int(token.get("size", self.default_size)),
            }

            for part in self._split_words(text):
                if part == "\n":
                    segments.append({"newline": True})
                else:
                    segments.append({"text": part, "style": style})

        lines: List[List[Dict]] = [[]]
        line_widths: List[int] = [0]
        line_heights: List[int] = [self.default_size]
        line_break_after: List[str] = ["end"]
        explicit_break_count = 0
        wrap_break_count = 0

        for segment in segments:
            if segment.get("newline"):
                explicit_break_count += 1
                line_break_after[-1] = "explicit"
                lines.append([])
                line_widths.append(0)
                line_heights.append(self.default_size)
                line_break_after.append("end")
                continue

            style = segment["style"]
            font = self._load_font(style["bold"], style["italic"], style["size"])
            seg_text = segment["text"]
            bbox = draw.textbbox((0, 0), seg_text, font=font)
            # Use advance-based length (not ink bbox) so leading/trailing spaces
            # between styled spans contribute correct horizontal advance.
            seg_w = int(draw.textlength(seg_text, font=font))
            seg_h = bbox[3] - bbox[1]

            current_idx = len(lines) - 1
            if line_widths[current_idx] + seg_w > max_width and line_widths[current_idx] > 0:
                wrap_break_count += 1
                line_break_after[-1] = "wrap"
                lines.append([])
                line_widths.append(0)
                line_heights.append(self.default_size)
                line_break_after.append("end")
                current_idx += 1
                # Strip leading space from a segment that begins a new wrapped line.
                seg_text = seg_text.lstrip(" \t")
                seg_w = int(draw.textlength(seg_text, font=font)) if seg_text else 0

            # Also strip leading space when this segment is the very first on any line.
            if line_widths[current_idx] == 0 and seg_text and seg_text[0] in (" ", "\t"):
                seg_text = seg_text.lstrip(" \t")
                seg_w = int(draw.textlength(seg_text, font=font)) if seg_text else 0

            if not seg_text:
                continue

            lines[current_idx].append({"text": seg_text, "style": style, "font": font, "w": seg_w, "h": seg_h})
            line_widths[current_idx] += seg_w
            line_heights[current_idx] = max(line_heights[current_idx], seg_h)

        total_text_height = 0
        for idx, line_h in enumerate(line_heights):
            total_text_height += max(1, int(round(line_h * line_height)))
            if idx < len(lines) - 1:
                gap = paragraph_spacing if line_break_after[idx] == "explicit" else line_spacing
                total_text_height += gap

        if vertical_align == "bottom":
            y = max(padding, container_height - padding - total_text_height)
        elif vertical_align == "top":
            y = padding
        else:
            y = max(padding, int((container_height - total_text_height) / 2))

        overflowed = False
        rendered_lines = 0

        for idx, line in enumerate(lines):
            line_w = line_widths[idx]
            line_h = line_heights[idx]

            if horizontal_align == "right":
                x = max(padding, container_width - padding - line_w)
            elif horizontal_align == "left":
                x = padding
            else:
                x = max(padding, int((container_width - line_w) / 2))

            for chunk in line:
                text = chunk["text"]
                font = chunk["font"]
                style = chunk["style"]
                color = style["color"]

                if shadow_enabled:
                    draw.text(
                        (x + int(shadow_offset[0]), y + int(shadow_offset[1])),
                        text,
                        font=font,
                        fill=shadow_rgba,
                    )

                draw.text(
                    (x, y),
                    text,
                    font=font,
                    fill=color,
                    stroke_width=max(0, int(stroke_width)),
                    stroke_fill=stroke_fill,
                )
                x += chunk["w"]

            rendered_lines += 1

            if idx == len(lines) - 1:
                continue

            gap = paragraph_spacing if line_break_after[idx] == "explicit" else line_spacing
            next_y = y + max(1, int(round(line_h * line_height))) + gap
            if next_y > container_height - padding:
                overflowed = True
                break
            y = next_y

        if rendered_lines < len(lines):
            overflowed = True

        metrics = {
            "overflowed": overflowed,
            "rendered_lines": rendered_lines,
            "total_lines": len(lines),
            "truncated_lines": max(0, len(lines) - rendered_lines),
            "line_spacing": int(line_spacing),
            "paragraph_spacing": int(paragraph_spacing),
            "line_height": float(line_height),
            "wrap_break_count": int(wrap_break_count),
            "explicit_break_count": int(explicit_break_count),
        }

        if return_metrics:
            return canvas, metrics
        return canvas