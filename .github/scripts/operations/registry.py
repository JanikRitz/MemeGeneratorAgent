from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

from .base import OperationHandler

_REGISTERED_HANDLER_CLASSES: Dict[str, Type[OperationHandler]] = {}


def register_operation(
    target: Optional[Union[Type[OperationHandler], str]] = None,
    name: Optional[str] = None,
) -> Any:
    """
    Decorator to register an OperationHandler class.

    Can be used as:
        @register_operation
        class MyOp(OperationHandler):
            name = "my_op"

        @register_operation("custom_name")
        class MyOp(OperationHandler): ...

        @register_operation(name="custom_name")
        class MyOp(OperationHandler): ...
    """
    def decorator(cls: Type[OperationHandler]) -> Type[OperationHandler]:
        op_name = name or (target if isinstance(target, str) else None) or getattr(cls, "name", None)
        if not op_name:
            raise ValueError("OperationHandler classes must define a non-empty 'name' or pass a name to @register_operation")
        _REGISTERED_HANDLER_CLASSES[op_name] = cls
        return cls

    if isinstance(target, type):
        cls = target
        target = None
        return decorator(cls)

    return decorator


class OperationRegistry:
    def __init__(self) -> None:
        self._handlers: Dict[str, OperationHandler] = {}

    def register(
        self,
        handler: Union[OperationHandler, Type[OperationHandler], str],
        name: Optional[str] = None,
    ) -> Any:
        if isinstance(handler, str):
            custom_name = handler

            def decorator(cls: Type[OperationHandler]) -> Type[OperationHandler]:
                self.register(cls, name=custom_name)
                return cls

            return decorator

        if isinstance(handler, type):
            instance = handler()
            op_name = name or getattr(instance, "name", None) or getattr(handler, "name", None)
            if not op_name:
                raise ValueError("Handlers must define a non-empty name")
            self._handlers[op_name] = instance
            return handler

        op_name = name or getattr(handler, "name", None)
        if not op_name:
            raise ValueError("Handlers must define a non-empty name")
        self._handlers[op_name] = handler
        return handler

    def get(self, name: str) -> Optional[OperationHandler]:
        return self._handlers.get(name)

    def list(self) -> List[str]:
        return sorted(self._handlers.keys())


def auto_discover_operations() -> None:
    """Dynamically discover and import all operation modules in operations package."""
    operations_dir = Path(__file__).parent
    for file_path in operations_dir.glob("*.py"):
        if file_path.name in ("__init__.py", "base.py", "registry.py"):
            continue
        module_name = file_path.stem
        try:
            importlib.import_module(f"operations.{module_name}")
        except ImportError:
            try:
                importlib.import_module(f".{module_name}", package=__package__ or "operations")
            except Exception:
                pass
        except Exception:
            pass


def build_default_registry() -> OperationRegistry:
    auto_discover_operations()
    registry = OperationRegistry()
    for name, handler_cls in _REGISTERED_HANDLER_CLASSES.items():
        registry.register(handler_cls(), name=name)
    return registry

