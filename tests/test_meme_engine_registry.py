import logging
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

from MemeEngine import MemeEngine
from operations.base import OperationContext, OperationHandler
from operations.registry import OperationRegistry


class DummyEngineHandler(OperationHandler):
    name = "dummy"

    def validate(self, params):
        return True

    def execute(self, engine, params, context):
        return params["value"]


class DispatchingTrimVideoHandler(OperationHandler):
    name = "trim_video"

    def validate(self, params):
        return True

    def execute(self, engine, params, context):
        return "registry-dispatched"


class MemeEngineRegistryTests(unittest.TestCase):
    def test_engine_execute_uses_registered_handler(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = OperationRegistry()
            registry.register(DummyEngineHandler())
            engine = MemeEngine(base_dir=tmpdir, logger=logging.getLogger("test"), registry=registry)

            self.assertEqual(engine.execute("dummy", {"value": "ok"}), "ok")

    def test_engine_execute_dispatches_registry_operations_without_wrapper_helpers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = OperationRegistry()
            registry.register(DispatchingTrimVideoHandler())
            engine = MemeEngine(base_dir=tmpdir, logger=logging.getLogger("test"), registry=registry)

            self.assertFalse(hasattr(engine, "trim_video"))
            self.assertEqual(
                engine.execute(
                    "trim_video",
                    {
                        "input_path": "input.mp4",
                        "start_sec": 0,
                        "end_sec": 1,
                        "output_path": "render/out.mp4",
                    },
                ),
                "registry-dispatched",
            )


if __name__ == "__main__":
    unittest.main()
