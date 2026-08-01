from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

try:
    from stash_client import StashClient
except ImportError:
    from .stash_client import StashClient

try:
    from hydrus_client import HydrusClient
except ImportError:
    from .hydrus_client import HydrusClient


class ConfigPreparationService:
    """Prepare a config by rewriting local paths and resolving external references."""

    def prepare_config(self, config: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
        rewritten = self.rewrite_media_paths(config, project_root)
        rewritten = self.maybe_resolve_stash_references(rewritten)
        rewritten = self.maybe_resolve_hydrus_references(rewritten)
        return rewritten

    def rewrite_media_paths(self, obj: Any, project_root: Path) -> Any:
        if isinstance(obj, dict):
            return {k: self.rewrite_media_paths(v, project_root) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.rewrite_media_paths(item, project_root) for item in obj]
        if isinstance(obj, str):
            for prefix in ("media/", "render/", "logs/", "config/"):
                if obj.startswith(prefix):
                    return str(project_root / obj)
            return obj
        return obj

    def contains_stash_references(self, obj: Any) -> bool:
        if isinstance(obj, dict):
            if "$stash_scene_path" in obj or "$stash_marker_time" in obj or "$stash_image_path" in obj:
                return True
            return any(self.contains_stash_references(value) for value in obj.values())
        if isinstance(obj, list):
            return any(self.contains_stash_references(item) for item in obj)
        if isinstance(obj, str):
            return obj.startswith("stash:scene:") or obj.startswith("stash:marker:") or obj.startswith("stash:image:")
        return False

    def contains_hydrus_references(self, obj: Any) -> bool:
        if isinstance(obj, dict):
            if "$hydrus_file_path" in obj or "$hydrus_search_path" in obj:
                return True
            return any(self.contains_hydrus_references(value) for value in obj.values())
        if isinstance(obj, list):
            return any(self.contains_hydrus_references(item) for item in obj)
        if isinstance(obj, str):
            return obj.startswith("hydrus:file_id:") or obj.startswith("hydrus:hash:")
        return False

    def _parse_stash_marker_token(self, token: str) -> Dict[str, Any]:
        parts = token.split(":", 5)
        if len(parts) != 5:
            raise ValueError(
                "Invalid stash marker token. Expected stash:marker:<scene_id>:<marker_id_or_title>:<start|end>"
            )

        scene_id = parts[2]
        marker_ref = parts[3]
        time_value = parts[4]

        spec: Dict[str, Any] = {"scene_id": scene_id, "time": time_value}
        if marker_ref.startswith("title="):
            spec["marker_title"] = marker_ref[len("title=") :]
        else:
            spec["marker_id"] = marker_ref
        return spec

    def resolve_stash_references(self, obj: Any, stash: StashClient) -> Any:
        if isinstance(obj, dict):
            if "$stash_scene_path" in obj:
                return stash.get_scene_path(obj["$stash_scene_path"])

            if "$stash_image_path" in obj:
                return stash.get_image_path(obj["$stash_image_path"])

            if "$stash_marker_time" in obj:
                spec = obj["$stash_marker_time"]
                if not isinstance(spec, dict):
                    raise ValueError("$stash_marker_time must be an object")

                default_duration = spec.get("default_duration_sec")
                return stash.resolve_marker_time(
                    scene_id=spec["scene_id"],
                    marker_id=spec.get("marker_id"),
                    marker_title=spec.get("marker_title"),
                    time_value=str(spec.get("time", "start")),
                    default_duration_sec=float(default_duration) if default_duration is not None else None,
                )

            return {key: self.resolve_stash_references(value, stash) for key, value in obj.items()}

        if isinstance(obj, list):
            return [self.resolve_stash_references(item, stash) for item in obj]

        if isinstance(obj, str):
            if obj.startswith("stash:scene:"):
                scene_id = obj[len("stash:scene:") :]
                return stash.get_scene_path(scene_id)

            if obj.startswith("stash:image:"):
                image_id = obj[len("stash:image:") :]
                return stash.get_image_path(image_id)

            if obj.startswith("stash:marker:"):
                spec = self._parse_stash_marker_token(obj)
                return stash.resolve_marker_time(
                    scene_id=spec["scene_id"],
                    marker_id=spec.get("marker_id"),
                    marker_title=spec.get("marker_title"),
                    time_value=str(spec.get("time", "start")),
                )

        return obj

    def _coerce_hydrus_tags(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return []

    def resolve_hydrus_references(self, obj: Any, hydrus: HydrusClient) -> Any:
        if isinstance(obj, dict):
            if "$hydrus_file_path" in obj:
                spec = obj["$hydrus_file_path"]
                if isinstance(spec, dict):
                    return hydrus.get_media_path(file_id=spec.get("file_id"), hash_=spec.get("hash"))
                return hydrus.get_media_path(file_id=spec)

            if "$hydrus_search_path" in obj:
                spec = obj["$hydrus_search_path"]
                if not isinstance(spec, dict):
                    raise ValueError("$hydrus_search_path must be an object")

                return hydrus.search_file_path(
                    tags=self._coerce_hydrus_tags(spec.get("tags")),
                    index=int(spec.get("index", 0)),
                    file_service_keys=spec.get("file_service_keys"),
                    tag_service_key=spec.get("tag_service_key"),
                )

            return {key: self.resolve_hydrus_references(value, hydrus) for key, value in obj.items()}

        if isinstance(obj, list):
            return [self.resolve_hydrus_references(item, hydrus) for item in obj]

        if isinstance(obj, str):
            if obj.startswith("hydrus:file_id:"):
                file_id = obj[len("hydrus:file_id:") :]
                return hydrus.get_media_path(file_id=file_id)

            if obj.startswith("hydrus:hash:"):
                hash_value = obj[len("hydrus:hash:") :]
                return hydrus.get_media_path(hash_=hash_value)

        return obj

    def maybe_resolve_stash_references(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if not self.contains_stash_references(config):
            return config

        endpoint = os.getenv("STASH_GRAPHQL_ENDPOINT") or os.getenv("STASH_URL")
        api_key = os.getenv("STASH_API_KEY")
        if not endpoint:
            raise ValueError(
                "Config contains Stash references but STASH_GRAPHQL_ENDPOINT (or STASH_URL) is not set"
            )

        try:
            stash = StashClient(endpoint=endpoint, api_key=api_key)
            return self.resolve_stash_references(config, stash)
        except Exception as exc:
            err_detail = str(exc).strip() or repr(exc)
            raise ValueError(
                f"Config contains Stash references but Stash API call failed: {err_detail}"
            ) from exc

    def maybe_resolve_hydrus_references(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if not self.contains_hydrus_references(config):
            return config

        endpoint = os.getenv("HYDRUS_API_URL") or os.getenv("HYDRUS_URL") or "http://127.0.0.1:45869/"
        access_key = os.getenv("HYDRUS_ACCESS_KEY") or os.getenv("HYDRUS_API_KEY")

        try:
            hydrus = HydrusClient(endpoint=endpoint, access_key=access_key)
            return self.resolve_hydrus_references(config, hydrus)
        except Exception as exc:
            err_detail = str(exc).strip() or repr(exc)
            raise ValueError(
                f"Config contains Hydrus references but failed to connect/query Hydrus API at {endpoint}: {err_detail}"
            ) from exc

