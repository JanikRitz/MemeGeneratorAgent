import sys
import unittest
from pathlib import Path

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
