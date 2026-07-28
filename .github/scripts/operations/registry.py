from __future__ import annotations

from typing import Dict, List, Optional

from .base import OperationHandler

try:
    from operations.trim_video import TrimVideoOperation
    from operations.crop_media import CropMediaOperation
    from operations.scale_media import ScaleMediaOperation
    from operations.stack_media import StackMediaOperation
    from operations.concatenate_clips import ConcatenateClipsOperation
    from operations.generate_text_overlay import GenerateTextOverlayOperation
    from operations.apply_text_overlay import ApplyTextOverlayOperation
    from operations.add_text_side_box import AddTextSideBoxOperation
    from operations.apply_multi_text_overlays import ApplyMultiTextOverlaysOperation
except ImportError:
    from .trim_video import TrimVideoOperation
    from .crop_media import CropMediaOperation
    from .scale_media import ScaleMediaOperation
    from .stack_media import StackMediaOperation
    from .concatenate_clips import ConcatenateClipsOperation
    from .generate_text_overlay import GenerateTextOverlayOperation
    from .apply_text_overlay import ApplyTextOverlayOperation
    from .add_text_side_box import AddTextSideBoxOperation
    from .apply_multi_text_overlays import ApplyMultiTextOverlaysOperation


class OperationRegistry:
    def __init__(self) -> None:
        self._handlers: Dict[str, OperationHandler] = {}

    def register(self, handler: OperationHandler) -> None:
        if not getattr(handler, "name", None):
            raise ValueError("Handlers must define a non-empty name")
        self._handlers[handler.name] = handler

    def get(self, name: str) -> Optional[OperationHandler]:
        return self._handlers.get(name)

    def list(self) -> List[str]:
        return sorted(self._handlers.keys())


def build_default_registry() -> OperationRegistry:
    registry = OperationRegistry()
    registry.register(TrimVideoOperation())
    registry.register(CropMediaOperation())
    registry.register(ScaleMediaOperation())
    registry.register(StackMediaOperation())
    registry.register(ConcatenateClipsOperation())
    registry.register(GenerateTextOverlayOperation())
    registry.register(ApplyTextOverlayOperation())
    registry.register(AddTextSideBoxOperation())
    registry.register(ApplyMultiTextOverlaysOperation())
    return registry
