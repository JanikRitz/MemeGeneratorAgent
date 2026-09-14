import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

from operations.base import OperationHandler
from operations.registry import (
    OperationRegistry,
    auto_discover_operations,
    build_default_registry,
    register_operation,
)


class DummyHandler(OperationHandler):
    name = "dummy"

    def validate(self, params):
        return True

    def execute(self, engine, params, context):
        return "ok"


class OperationRegistryTests(unittest.TestCase):
    def test_duplicate_names_require_explicit_replacement(self):
        for as_class in (False, True):
            with self.subTest(as_class=as_class):
                registry = OperationRegistry()
                registry.register(DummyHandler())
                replacement = DummyHandler if as_class else DummyHandler()
                with self.assertRaisesRegex(ValueError, "already registered: dummy"):
                    registry.register(replacement)
                registry.register(replacement, replace=True)
                self.assertIsInstance(registry.get("dummy"), DummyHandler)

    def test_global_decorator_requires_explicit_replacement(self):
        with patch("operations.registry._REGISTERED_HANDLER_CLASSES", {}):
            register_operation(DummyHandler)
            with self.assertRaisesRegex(ValueError, "already registered: dummy"):
                register_operation(DummyHandler)
            self.assertIs(register_operation(DummyHandler, replace=True), DummyHandler)

    def test_named_registry_decorator_supports_explicit_replacement(self):
        registry = OperationRegistry()
        registry.register(DummyHandler())
        registry.register("dummy", replace=True)(DummyHandler)
        self.assertIsInstance(registry.get("dummy"), DummyHandler)

    def test_discovery_reports_module_import_failures(self):
        failure = RuntimeError("broken plugin")
        with patch("operations.registry.importlib.import_module", side_effect=failure):
            with self.assertRaisesRegex(ImportError, "Failed to load operation module .*broken plugin") as raised:
                auto_discover_operations()
        self.assertIs(raised.exception.__cause__, failure)

    def test_custom_registry_registers_and_resolves_handlers(self):
        registry = OperationRegistry()
        registry.register(DummyHandler())

        self.assertEqual(registry.get("dummy").name, "dummy")
        self.assertIn("dummy", registry.list())

    def test_register_operation_decorator(self):
        @register_operation
        class DecoratedOp(OperationHandler):
            name = "decorated_test_op"

        registry = build_default_registry()
        self.assertIsNotNone(registry.get("decorated_test_op"))

    def test_register_operation_decorator_custom_name(self):
        @register_operation("custom_op_name")
        class CustomNamedOp(OperationHandler):
            name = "original_name"

        registry = build_default_registry()
        self.assertIsNotNone(registry.get("custom_op_name"))

    def test_registry_instance_decorator(self):
        registry = OperationRegistry()

        @registry.register
        class InstanceDecoratedOp(OperationHandler):
            name = "inst_dec_op"

        self.assertIsNotNone(registry.get("inst_dec_op"))

    def test_default_registry_contains_core_operations(self):
        registry = build_default_registry()

        expected_operations = [
            "trim_video",
            "crop_media",
            "scale_media",
            "stack_media",
            "concatenate_clips",
            "generate_text_overlay",
            "apply_text_overlay",
            "add_text_side_box",
            "apply_multi_text_overlays",
            "resolve_path",
            "resolve_output_path",
            "get_media_info",
            "write_video",
            "save_image",
            "compute_scale_factor",
            "normalize_position",
            "position_to_pixels",
            "crop_media_impl",
            "stack_media_impl",
        ]

        for operation_name in expected_operations:
            with self.subTest(operation_name=operation_name):
                self.assertIsNotNone(registry.get(operation_name))


if __name__ == "__main__":
    unittest.main()
