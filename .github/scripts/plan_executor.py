from __future__ import annotations

import hashlib
import inspect
import json
import os
import platform
import shutil
import tempfile
from importlib.metadata import version
from pathlib import Path

from operations.base import OperationContext


INPUT_KEYS = ("input_path", "base_media_path", "media_path", "path1", "path2")
TEXT_OPERATIONS = {"generate_text_overlay", "apply_multi_text_overlays", "add_text_side_box"}


def file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def object_digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def runtime_fingerprint(engine) -> str:
    from moviepy.config import FFMPEG_BINARY

    scripts = Path(__file__).parent
    implementation = {str(path.relative_to(scripts)): file_digest(path) for path in sorted(scripts.rglob("*.py"))}
    binaries = {}
    for name in (FFMPEG_BINARY, "ffprobe"):
        executable = shutil.which(name)
        binaries[name] = file_digest(Path(executable)) if executable else None
    handlers = {name: inspect.getsource(type(engine.registry.get(name))) for name in engine.registry.list()}
    return object_digest({
        "schema": 1, "implementation": implementation, "handlers": handlers,
        "engine": inspect.getsource(type(engine)), "binaries": binaries,
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {name: version(name) for name in ("moviepy", "Pillow", "numpy", "imageio", "imageio-ffmpeg")},
    })


class ArtifactCache:
    def __init__(self, root: Path):
        self.root = root

    def restore(self, key: str, workspace: Path) -> bool:
        entry = self.root / key
        try:
            manifest = json.loads((entry / "manifest.json").read_text(encoding="utf-8"))
            if manifest["key"] != key or manifest["version"] != 1 or not manifest["files"]:
                return False
            files = manifest["files"]
            for name, digest in files.items():
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name:
                    return False
                source = entry / "artifacts" / relative
                if not source.is_file() or source.is_symlink() or file_digest(source) != digest:
                    return False
            for name in files:
                destination = workspace / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(entry / "artifacts" / name, destination)
            return True
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return False

    def store(self, key: str, workspace: Path) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".entry-", dir=self.root) as temporary:
            staging = Path(temporary)
            artifacts = staging / "artifacts"
            shutil.copytree(workspace, artifacts)
            files = {path.relative_to(artifacts).as_posix(): file_digest(path) for path in sorted(artifacts.rglob("*")) if path.is_file()}
            (staging / "manifest.json").write_text(json.dumps({"version": 1, "key": key, "files": files}, sort_keys=True), encoding="utf-8")
            destination = self.root / key
            if destination.exists():
                shutil.rmtree(destination)
            os.replace(staging, destination)


def atomic_publish(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.stem}-", suffix=destination.suffix, dir=destination.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as target, source.open("rb") as origin:
            shutil.copyfileobj(origin, target)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


class PlanExecutor:
    def __init__(self, cache_dir: Path | None = None):
        self.cache = ArtifactCache(cache_dir) if cache_dir is not None else None

    def _key(self, operation: str, params: dict, engine, preview: bool, runtime: str) -> str:
        normalized = {key: value for key, value in params.items() if key not in {"output_path", "overlay_dir"}}
        for key in INPUT_KEYS:
            if key in normalized:
                path = Path(normalized[key])
                normalized[key] = {"sha256": file_digest(path), "suffix": path.suffix.lower()}
        if "clip_paths" in normalized:
            normalized["clip_paths"] = [{"sha256": file_digest(Path(path)), "suffix": Path(path).suffix.lower()} for path in normalized["clip_paths"]]
        fonts = []
        if operation in TEXT_OPERATIONS:
            entries = params.get("overlays", [params])
            for entry in entries:
                renderer = engine._get_renderer(entry.get("font_path") or params.get("font_path"))
                variants = []
                for bold, italic in ((False, False), (True, False), (False, True), (True, True)):
                    path = renderer._font_path_for_style(bold, italic)
                    variants.append(file_digest(path) if path.is_file() else "pillow-default")
                fonts.append({"variants": variants, "default_size": renderer.default_size})
        return object_digest({"operation": operation, "params": normalized, "fonts": fonts, "runtime": runtime,
                              "preview": preview, "suffix": Path(params["output_path"]).suffix.lower()})

    def execute(self, plan, engine, preview: bool = False, release: bool = False, force: bool = False) -> str:
        runtime = runtime_fingerprint(engine) if self.cache else ""
        if self.cache and any(step.operation in TEXT_OPERATIONS for step in plan.steps):
            engine._resolve_font_path.cache_clear()
            engine.renderer._font_path_for_style.cache_clear()
            engine.renderer._load_font.cache_clear()
        scratch = Path(plan.scratch)
        scratch.mkdir(parents=True, exist_ok=False)
        outputs: dict[str, str] = {}
        succeeded = False
        try:
            result = ""
            for index, step in enumerate(plan.steps):
                params = dict(step.params)
                for key in INPUT_KEYS:
                    if key in params:
                        params[key] = outputs.get(params[key], params[key])
                if "clip_paths" in params:
                    params["clip_paths"] = [outputs.get(path, path) for path in params["clip_paths"]]
                destination = Path(params["output_path"])
                workspace = scratch / f"work-{index:03d}"
                workspace.mkdir()
                staged = workspace / ("result" + destination.suffix)
                context = OperationContext(engine=engine, logger=engine.logger, preview_only_override=preview)
                try:
                    key = self._key(step.operation, params, engine, preview, runtime) if self.cache else ""
                    overlay_dir = params.get("overlay_dir")
                    params["output_path"] = str(staged)
                    if overlay_dir is not None:
                        params["overlay_dir"] = str(workspace / "overlays")
                    hit = bool(self.cache and not force and self.cache.restore(key, workspace))
                    if hit and (not staged.is_file() or staged.stat().st_size == 0):
                        hit = False
                    if not hit:
                        shutil.rmtree(workspace)
                        workspace.mkdir()
                        rendered = Path(engine.execute(step.operation, params, context))
                    else:
                        rendered = staged
                    if rendered.resolve() != staged.resolve() or not rendered.is_file() or rendered.stat().st_size == 0:
                        raise ValueError("Operation did not produce its declared nonempty output")
                    if self.cache:
                        engine.logger.info("Cache %s: %s (%s)", "hit" if hit else "miss", step.source, key)
                        if not hit:
                            self.cache.store(key, workspace)
                    if overlay_dir is not None and (workspace / "overlays").exists():
                        for artifact in (workspace / "overlays").rglob("*"):
                            if artifact.is_file():
                                atomic_publish(artifact, Path(overlay_dir) / artifact.relative_to(workspace / "overlays"))
                    atomic_publish(rendered, destination)
                except Exception as exc:
                    raise ValueError(f"{step.source}: {exc}") from exc
                finally:
                    shutil.rmtree(workspace)
                result = str(destination)
                outputs[step.params["output_path"]] = result
            succeeded = True
            return result
        finally:
            if release or not succeeded:
                shutil.rmtree(scratch)