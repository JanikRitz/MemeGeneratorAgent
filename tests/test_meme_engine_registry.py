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


class DispatchingMediaInfoHandler(OperationHandler):
    name = "get_media_info"

    def validate(self, params):
        return True

    def execute(self, engine, params, context):
        return {"path": params["input_path"], "width": 1, "height": 2, "duration_sec": 3.0}


class DispatchingPathHandler(OperationHandler):
    name = "resolve_path"

    def validate(self, params):
        return True

    def execute(self, engine, params, context):
        return Path(params["path_value"])


class DispatchingCropImplHandler(OperationHandler):
    name = "crop_media_impl"

    def validate(self, params):
        return True

    def execute(self, engine, params, context):
        return "crop-dispatched"


class DispatchingStackImplHandler(OperationHandler):
    name = "stack_media_impl"

    def validate(self, params):
        return True

    def execute(self, engine, params, context):
        return "stack-dispatched"


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

    def test_engine_media_info_and_path_helpers_delegate_to_registry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = OperationRegistry()
            registry.register(DispatchingMediaInfoHandler())
            registry.register(DispatchingPathHandler())
            engine = MemeEngine(base_dir=tmpdir, logger=logging.getLogger("test"), registry=registry)

            self.assertEqual(
                engine.get_media_info("ignored.mp4"),
                {"path": "ignored.mp4", "width": 1, "height": 2, "duration_sec": 3.0},
            )
            self.assertEqual(engine.resolve_path("ignored.mp4"), Path("ignored.mp4"))

    def test_engine_crop_and_stack_helpers_delegate_to_registry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = OperationRegistry()
            registry.register(DispatchingCropImplHandler())
            registry.register(DispatchingStackImplHandler())
            engine = MemeEngine(base_dir=tmpdir, logger=logging.getLogger("test"), registry=registry)

            self.assertEqual(engine._crop_media_impl("input.mp4", "render/out.mp4"), "crop-dispatched")
            self.assertEqual(engine._stack_media_impl("one.mp4", "two.mp4", "render/out.mp4"), "stack-dispatched")


if __name__ == "__main__":
    unittest.main()
