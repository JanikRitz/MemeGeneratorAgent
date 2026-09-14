from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import hydrus_api


_SUPPORTED_MEDIA_SUFFIXES = {
    ".avi",
    ".gif",
    ".jpeg",
    ".jpg",
    ".mkv",
    ".mov",
    ".mp4",
    ".png",
    ".webm",
    ".webp",
}


def _normalize_tags(tags: Iterable[str] | None) -> List[str]:
    normalized: List[str] = []
    for tag in tags or []:
        value = str(tag).strip()
        if value:
            normalized.append(value)
    return normalized


def _normalize_ext(value: Any) -> str:
    ext = str(value or "").strip().lower()
    if not ext:
        return ""
    return ext if ext.startswith(".") else f".{ext}"


class HydrusClient:
    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
    ) -> None:
        """Initialize the Hydrus API client."""
        api_url = endpoint or "http://127.0.0.1:45869/"
        self.client = hydrus_api.Client(access_key=access_key, api_url=api_url)

    def get_file_path(self, file_id: Any = None, hash_: Optional[str] = None) -> str:
        """Resolve a Hydrus file to its local path by file_id or hash."""
        if file_id is None and not hash_:
            raise ValueError("Hydrus file path lookup requires file_id or hash")

        args: Dict[str, Any] = {}
        if file_id is not None:
            args["file_id"] = int(file_id)
        if hash_:
            args["hash_"] = str(hash_)

        payload = self.client.get_file_path(**args)
        return str(payload.get("path") or "")

    def _get_metadata_entry(self, file_id: Any = None, hash_: Optional[str] = None) -> Dict[str, Any]:
        metadata = self.client.get_file_metadata(
            file_ids=[int(file_id)] if file_id is not None else None,
            hashes=[str(hash_)] if hash_ else None,
            include_notes=True,
        )
        entries = metadata.get("metadata") or []
        if not entries:
            raise ValueError("Hydrus metadata lookup returned no results")
        return dict(entries[0])

    def get_media_path(self, file_id: Any = None, hash_: Optional[str] = None) -> str:
        """Resolve a Hydrus file to a supported local media path for rendering."""
        if file_id is None and not hash_:
            raise ValueError("Hydrus media path lookup requires file_id or hash")

        args: Dict[str, Any] = {}
        if file_id is not None:
            args["file_id"] = int(file_id)
        if hash_:
            args["hash_"] = str(hash_)

        payload = self.client.get_file_path(**args)
        path = str(payload.get("path") or "")
        path_obj = Path(path) if path else None
        if path_obj is not None and path_obj.suffix.lower() in _SUPPORTED_MEDIA_SUFFIXES:
            return path

        metadata_entry = self._get_metadata_entry(file_id=file_id, hash_=hash_)
        metadata_ext = _normalize_ext(metadata_entry.get("ext"))
        metadata_mime = str(metadata_entry.get("mime") or payload.get("filetype") or "").strip().lower()

        if path_obj is not None and metadata_ext in _SUPPORTED_MEDIA_SUFFIXES and not path_obj.suffix:
            candidate = Path(f"{path}{metadata_ext}")
            if candidate.exists():
                return str(candidate)

        if metadata_mime.startswith("image/"):
            return path

        raise ValueError(
            "Hydrus reference did not resolve to supported renderable media "
            f"(file_id={file_id!r}, hash={hash_!r}, mime={metadata_mime or 'unknown'}, path={path!r})"
        )

    def search_file_paths(
        self,
        tags: Iterable[str],
        *,
        file_service_keys: Optional[Iterable[str | Iterable[str]]] = None,
        tag_service_key: Optional[str] = None,
    ) -> List[str]:
        """Search Hydrus files by tag list and return all resolvable local paths."""
        tag_list = _normalize_tags(tags)
        if not tag_list:
            raise ValueError("Hydrus file search requires at least one tag")

        search_payload = self.client.search_files(
            tags=tag_list,
            file_service_keys=file_service_keys,
            tag_service_key=tag_service_key,
            return_hashes=True,
            return_file_ids=True,
        )

        paths: List[str] = []
        seen: set[str] = set()

        for hash_value in search_payload.get("hashes") or []:
            try:
                path = self.get_media_path(hash_=str(hash_value))
            except Exception:
                continue
            if path and path not in seen:
                paths.append(path)
                seen.add(path)

        for file_id in search_payload.get("file_ids") or []:
            try:
                path = self.get_media_path(file_id=file_id)
            except Exception:
                continue
            if path and path not in seen:
                paths.append(path)
                seen.add(path)

        return paths

    def search_file_path(
        self,
        tags: Iterable[str],
        *,
        index: int = 0,
        file_service_keys: Optional[Iterable[str | Iterable[str]]] = None,
        tag_service_key: Optional[str] = None,
    ) -> str:
        """Search Hydrus files by tags and return one path by index."""
        paths = self.search_file_paths(
            tags,
            file_service_keys=file_service_keys,
            tag_service_key=tag_service_key,
        )
        if not paths:
            return ""

        index_value = int(index)
        if index_value < 0 or index_value >= len(paths):
            raise ValueError(f"Hydrus search index {index_value} out of range for {len(paths)} result(s)")

        return paths[index_value]

    def get_file_bundle(self, file_id: Any = None, hash_: Optional[str] = None) -> Dict[str, Any]:
        """Return a combined metadata bundle and resolved media path for debugging."""
        if file_id is None and not hash_:
            raise ValueError("Hydrus file bundle lookup requires file_id or hash")

        metadata = self.client.get_file_metadata(
            file_ids=[int(file_id)] if file_id is not None else None,
            hashes=[str(hash_)] if hash_ else None,
            include_notes=True,
        )
        return {
            "file_id": int(file_id) if file_id is not None else None,
            "hash": str(hash_) if hash_ else None,
            "resolved_media_path": self.get_file_path(file_id=file_id, hash_=hash_),
            "metadata": metadata,
        }
