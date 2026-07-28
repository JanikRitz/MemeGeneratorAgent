from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class OperationContext:
    engine: Any
    logger: Any
    preview_only_override: Optional[bool] = None
    default_font_path: Optional[str] = None
    last_output: str = ""


class OperationHandler:
    name: str = ""

    def validate(self, params: Dict[str, Any]) -> None:
        return None

    def execute(self, engine: Any, params: Dict[str, Any], context: OperationContext) -> str:
        raise NotImplementedError
