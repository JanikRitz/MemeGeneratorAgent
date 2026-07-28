from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Set


class ArtifactCleanupService:
    """Remove stale intermediate artifacts while preserving the final output."""

    def cleanup_files(self, paths: Set[Path], keep_path: Optional[Path] = None, logger: Optional[logging.Logger] = None) -> int:
        removed = 0
        keep_resolved = str(keep_path.resolve()) if keep_path is not None else None

        for path in sorted(paths, key=lambda p: str(p)):
            try:
                if keep_resolved is not None and str(path.resolve()) == keep_resolved:
                    continue
                if path.exists() and path.is_file():
                    path.unlink()
                    removed += 1
            except Exception as exc:
                if logger:
                    logger.warning("cleanup failed for %s: %s", path, exc)

        return removed
