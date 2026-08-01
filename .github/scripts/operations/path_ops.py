from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

try:
    from moviepy.editor import ImageClip, VideoFileClip
except ImportError:
    from moviepy import ImageClip, VideoFileClip

from .base import OperationContext, OperationHandler
from .registry import register_operation


@register_operation
class ResolvePathOperation(OperationHandler):
    name = "resolve_path"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["path_value"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> Path:
        self.validate(params)
        return engine._resolve_path_impl(params["path_value"])


@register_operation
class ResolveOutputPathOperation(OperationHandler):
    name = "resolve_output_path"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["path_value"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> Path:
        self.validate(params)
        return engine._resolve_output_path_impl(params["path_value"])


@register_operation
class GetMediaInfoOperation(OperationHandler):
    name = "get_media_info"

    def validate(self, params: Dict[str, Any]) -> None:
        required = ["input_path"]
        missing = [name for name in required if name not in params]
        if missing:
            raise ValueError(f"Missing required params: {', '.join(missing)}")

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> Dict[str, Any]:
        self.validate(params)
        return engine._get_media_info_impl(params["input_path"])
