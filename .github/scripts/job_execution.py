from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set

from MemeEngine import MemeEngine

from operations.base import OperationContext
from operations.registry import OperationRegistry, build_default_registry

try:
    from artifact_cleanup import ArtifactCleanupService
except ImportError:
    from .artifact_cleanup import ArtifactCleanupService


class JobExecutionService:
    """Execute config steps using dependency injection for the operation registry."""

    def __init__(
        self,
        registry: Optional[OperationRegistry] = None,
        engine_factory: Optional[Callable[[str, logging.Logger], MemeEngine]] = None,
        cleanup_service: Optional[ArtifactCleanupService] = None,
    ) -> None:
        self.registry = registry or build_default_registry()
        self.engine_factory = engine_factory or (lambda base_dir, logger: MemeEngine(base_dir=base_dir, logger=logger))
        self.cleanup_service = cleanup_service or ArtifactCleanupService()

    def _replace_last_output(self, value: Any, last_output: str) -> Any:
        if isinstance(value, str):
            return last_output if value == "$last_output" else value
        if isinstance(value, list):
            return [self._replace_last_output(item, last_output) for item in value]
        if isinstance(value, dict):
            return {k: self._replace_last_output(v, last_output) for k, v in value.items()}
        return value

    def execute_step(
        self,
        engine: MemeEngine,
        step: Dict[str, Any],
        last_output: str = "",
        preview_only_override: Optional[bool] = None,
        default_font_path: Optional[str] = None,
        cli_overrides: Optional[Dict[str, Any]] = None,
    ) -> str:
        operation = step.get("operation")
        params = dict(step.get("params", {}))
        if last_output:
            params = self._replace_last_output(params, last_output)

        if cli_overrides:
            for key, val in cli_overrides.items():
                if val is not None:
                    params[key] = val

        if not operation:
            raise ValueError("Each step must define an operation")

        context = OperationContext(
            engine=engine,
            logger=engine.logger,
            preview_only_override=preview_only_override,
            default_font_path=default_font_path,
            last_output=last_output,
        )

        handler = self.registry.get(operation)
        if handler is None:
            raise ValueError(f"Unsupported operation: {operation}")

        return handler.execute(engine, params, context)

    def execute_config(
        self,
        config: Dict[str, Any],
        engine: MemeEngine,
        args: argparse.Namespace,
        logger: logging.Logger,
    ) -> str:
        cli_overrides: Dict[str, Any] = {}
        if getattr(args, "video_codec", None) is not None:
            cli_overrides["video_codec"] = args.video_codec
        if getattr(args, "threads", None) is not None:
            cli_overrides["threads"] = args.threads
        if getattr(args, "video_crf", None) is not None:
            cli_overrides["video_crf"] = args.video_crf
        if getattr(args, "video_preset", None) is not None:
            cli_overrides["video_preset"] = args.video_preset

        if "pipeline" in config:
            logger.info("Running pipeline with %s steps", len(config["pipeline"]))
            last_output = ""
            for index, step in enumerate(config["pipeline"]):
                logger.info("Executing step %s: %s", index, step.get("operation"))
                last_output = self.execute_step(
                    engine,
                    step,
                    last_output=last_output,
                    preview_only_override=args.preview_only or None,
                    default_font_path=config.get("font_path"),
                    cli_overrides=cli_overrides,
                )
                logger.info("Step %s output: %s", index, last_output)
            return last_output

        logger.info("Running single operation: %s", config.get("operation"))
        output = self.execute_step(
            engine,
            config,
            preview_only_override=args.preview_only or None,
            default_font_path=config.get("font_path"),
            cli_overrides=cli_overrides,
        )
        logger.info("Operation output: %s", output)
        return output

    def run_config_file(
        self,
        config_path: Path,
        config: Dict[str, Any],
        project_root: Path,
        args: argparse.Namespace,
        logger: Optional[logging.Logger] = None,
        output_path_resolver: Optional[Callable[[Dict[str, Any]], Optional[Path]]] = None,
        generated_path_collector: Optional[Callable[[Dict[str, Any]], Set[Path]]] = None,
    ) -> bool:
        effective_logger = logger or logging.getLogger("meme_engine")
        engine = self.engine_factory(str(project_root), effective_logger)

        generated_files = generated_path_collector(config) if generated_path_collector else set()
        output_path = output_path_resolver(config) if output_path_resolver else None

        if output_path and output_path.exists() and output_path.stat().st_mtime > config_path.stat().st_mtime:
            if args.release:
                removed = self.cleanup_service.cleanup_files(generated_files, keep_path=output_path, logger=effective_logger)
                if removed:
                    print(f"Release cleanup for {config_path}: removed {removed} stale intermediates/previews")
            print(f"Skipping {config_path} (output newer than config)")
            return True

        if args.release:
            removed = self.cleanup_service.cleanup_files(generated_files, keep_path=output_path, logger=effective_logger)
            if removed:
                print(f"Release pre-cleanup for {config_path}: removed {removed} stale intermediates/previews")

        print(f"Running config: {config_path}")
        try:
            run_result = self.execute_config(config, engine, args, effective_logger)
            if args.release and run_result:
                removed = self.cleanup_service.cleanup_files(generated_files, keep_path=Path(run_result), logger=effective_logger)
                if removed:
                    print(f"Release post-cleanup for {config_path}: removed {removed} intermediate/preview files")
            print(run_result)
            return True
        except Exception as exc:
            print(f"Error running {config_path}: {exc}")
            return False
