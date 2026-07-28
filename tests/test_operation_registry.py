import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

from operations.base import OperationHandler
from operations.registry import OperationRegistry, build_default_registry


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

    def test_default_registry_contains_core_operations(self):
        registry = build_default_registry()

        for operation_name in [
            "trim_video",
            "crop_media",
            "scale_media",
            "stack_media",
            "concatenate_clips",
            "generate_text_overlay",
            "apply_text_overlay",
            "add_text_side_box",
            "apply_multi_text_overlays",
        ]:
            with self.subTest(operation_name=operation_name):
                self.assertIsNotNone(registry.get(operation_name))


if __name__ == "__main__":
    unittest.main()
