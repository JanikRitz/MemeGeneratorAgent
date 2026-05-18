import json
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, request


class StashClient:
    def __init__(self, endpoint: str, api_key: Optional[str] = None, timeout_sec: int = 30):
        self.endpoint = self._normalize_endpoint(endpoint)
        self.api_key = api_key
        self.timeout_sec = int(timeout_sec)
        self._query_field_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._type_cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        endpoint = endpoint.strip()
        if not endpoint:
            raise ValueError("Stash GraphQL endpoint is empty")
        if endpoint.endswith("/graphql"):
            return endpoint
        return endpoint.rstrip("/") + "/graphql"

    @staticmethod
    def _unwrap_type_name(type_obj: Optional[Dict[str, Any]]) -> Optional[str]:
        current = type_obj or {}
        while current:
            name = current.get("name")
            if name:
                return str(name)
            current = current.get("ofType") or {}
        return None

    def execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "query": query,
            "variables": variables or {},
        }
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            # Stash commonly uses ApiKey; Authorization helps with reverse proxy setups.
            headers["ApiKey"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_sec) as resp:
                body = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Stash GraphQL HTTP {exc.code}: {raw}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Stash GraphQL request failed: {exc}") from exc

        decoded = json.loads(body)
        if decoded.get("errors"):
            raise RuntimeError(f"Stash GraphQL errors: {decoded['errors']}")

        data = decoded.get("data")
        if data is None:
            raise RuntimeError("Stash GraphQL response did not include a data object")
        return data

    def _get_query_fields(self) -> Dict[str, Dict[str, Any]]:
        if self._query_field_cache is not None:
            return self._query_field_cache

        query = """
        query IntrospectQueryType {
          __type(name: "Query") {
            fields {
              name
              args {
                name
              }
              type {
                kind
                name
                ofType {
                  kind
                  name
                  ofType {
                    kind
                    name
                    ofType {
                      kind
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = self.execute(query)
        fields = (data.get("__type") or {}).get("fields") or []
        self._query_field_cache = {f["name"]: f for f in fields if f.get("name")}
        return self._query_field_cache

    def _get_type_definition(self, type_name: str) -> Dict[str, Any]:
        if type_name in self._type_cache:
            return self._type_cache[type_name]

        query = """
        query IntrospectType($name: String!) {
          __type(name: $name) {
            name
            fields {
              name
              args {
                name
              }
              type {
                kind
                name
                ofType {
                  kind
                  name
                  ofType {
                    kind
                    name
                    ofType {
                      kind
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = self.execute(query, {"name": type_name})
        result = data.get("__type") or {}
        self._type_cache[type_name] = result
        return result

    def _pick_scene_lookup(self) -> Tuple[str, str, str]:
        query_fields = self._get_query_fields()
        for field_name in ("findScene", "scene", "sceneById"):
            field = query_fields.get(field_name)
            if not field:
                continue

            args = field.get("args") or []
            arg_name = None
            for candidate in ("id", "scene_id", "sceneId"):
                if any(arg.get("name") == candidate for arg in args):
                    arg_name = candidate
                    break
            if arg_name is None and args:
                arg_name = args[0].get("name")

            scene_type_name = self._unwrap_type_name(field.get("type"))
            if arg_name and scene_type_name:
                return field_name, arg_name, scene_type_name

        raise RuntimeError("Could not find a scene lookup query (findScene/scene/sceneById) in Stash GraphQL schema")

    def _query_scene(self, scene_id: Any, selection_set: str) -> Dict[str, Any]:
        query_field, arg_name, _scene_type = self._pick_scene_lookup()
        query = f"""
        query GetScene($id: ID!) {{
          {query_field}({arg_name}: $id) {{
            {selection_set}
          }}
        }}
        """
        data = self.execute(query, {"id": str(scene_id)})
        scene = data.get(query_field)
        if not scene:
            raise RuntimeError(f"Scene not found for id={scene_id}")
        return scene

    def get_scene_path(self, scene_id: Any) -> str:
        _query_field, _arg_name, scene_type_name = self._pick_scene_lookup()
        scene_type = self._get_type_definition(scene_type_name)
        scene_fields = {f["name"]: f for f in (scene_type.get("fields") or []) if f.get("name")}

        if "files" in scene_fields:
            files_type_name = self._unwrap_type_name(scene_fields["files"].get("type"))
            if files_type_name:
                file_type = self._get_type_definition(files_type_name)
                file_fields = {f["name"] for f in (file_type.get("fields") or []) if f.get("name")}
                for path_field in ("path", "file_path", "abs_path"):
                    if path_field in file_fields:
                        scene = self._query_scene(scene_id, f"files {{ {path_field} }}")
                        for item in (scene.get("files") or []):
                            value = item.get(path_field)
                            if value:
                                return str(value)

        if "paths" in scene_fields:
            paths_type_name = self._unwrap_type_name(scene_fields["paths"].get("type"))
            if paths_type_name:
                paths_type = self._get_type_definition(paths_type_name)
                path_fields = {f["name"] for f in (paths_type.get("fields") or []) if f.get("name")}
                for candidate in ("stream", "screenshot", "preview", "image"):
                    if candidate in path_fields:
                        scene = self._query_scene(scene_id, f"paths {{ {candidate} }}")
                        value = (scene.get("paths") or {}).get(candidate)
                        if value:
                            return str(value)

        raise RuntimeError(
            "Could not resolve a filesystem/media path for scene. Expected Scene.files.path or Scene.paths.* in schema"
        )

    def get_scene_markers(self, scene_id: Any) -> List[Dict[str, Any]]:
        _query_field, _arg_name, scene_type_name = self._pick_scene_lookup()
        scene_type = self._get_type_definition(scene_type_name)
        scene_fields = {f["name"]: f for f in (scene_type.get("fields") or []) if f.get("name")}

        marker_field_name = None
        for candidate in ("scene_markers", "sceneMarkers", "markers"):
            if candidate in scene_fields:
                marker_field_name = candidate
                break

        if marker_field_name is None:
            raise RuntimeError("Scene marker field not found on Scene type (expected scene_markers/sceneMarkers/markers)")

        marker_type_name = self._unwrap_type_name(scene_fields[marker_field_name].get("type"))
        if not marker_type_name:
            raise RuntimeError(f"Could not resolve marker type for field {marker_field_name}")

        marker_type = self._get_type_definition(marker_type_name)
        marker_fields = {f["name"] for f in (marker_type.get("fields") or []) if f.get("name")}

        id_field = "id" if "id" in marker_fields else None
        title_field = None
        for candidate in ("title", "name"):
            if candidate in marker_fields:
                title_field = candidate
                break

        start_field = None
        for candidate in ("seconds", "start_seconds", "start", "time"):
            if candidate in marker_fields:
                start_field = candidate
                break

        end_field = None
        for candidate in ("end_seconds", "end", "seconds_end"):
            if candidate in marker_fields:
                end_field = candidate
                break

        duration_field = None
        for candidate in ("duration", "duration_seconds", "length"):
            if candidate in marker_fields:
                duration_field = candidate
                break

        if start_field is None:
            raise RuntimeError(
                f"Could not identify marker start field on type {marker_type_name}. Available fields: {sorted(marker_fields)}"
            )

        selection_fields: List[str] = [start_field]
        if id_field:
            selection_fields.append(id_field)
        if title_field:
            selection_fields.append(title_field)
        if end_field:
            selection_fields.append(end_field)
        if duration_field and duration_field not in selection_fields:
            selection_fields.append(duration_field)

        selection = "\n".join(selection_fields)
        scene = self._query_scene(scene_id, f"{marker_field_name} {{\n{selection}\n}}")
        raw_markers = scene.get(marker_field_name) or []

        markers: List[Dict[str, Any]] = []
        for marker in raw_markers:
            start_value = marker.get(start_field)
            if start_value is None:
                continue
            start = float(start_value)
            end = None
            if end_field and marker.get(end_field) is not None:
                end = float(marker.get(end_field))
            elif duration_field and marker.get(duration_field) is not None:
                end = start + float(marker.get(duration_field))

            markers.append(
                {
                    "id": str(marker.get(id_field)) if id_field and marker.get(id_field) is not None else None,
                    "title": str(marker.get(title_field)) if title_field and marker.get(title_field) is not None else None,
                    "start_time": start,
                    "end_time": end,
                }
            )

        markers.sort(key=lambda item: item["start_time"])
        return markers

    def resolve_marker_time(
        self,
        scene_id: Any,
        marker_id: Optional[Any] = None,
        marker_title: Optional[str] = None,
        time_value: str = "start",
        default_duration_sec: Optional[float] = None,
    ) -> float:
        markers = self.get_scene_markers(scene_id)
        if not markers:
            raise RuntimeError(f"No markers found for scene id={scene_id}")

        selected = None
        if marker_id is not None:
            selected = next((m for m in markers if m.get("id") == str(marker_id)), None)
            if selected is None:
                raise RuntimeError(f"Marker id={marker_id} not found for scene id={scene_id}")
        elif marker_title:
            marker_title_lower = marker_title.lower().strip()
            selected = next(
                (m for m in markers if (m.get("title") or "").lower().strip() == marker_title_lower),
                None,
            )
            if selected is None:
                raise RuntimeError(
                    f"Marker title '{marker_title}' not found for scene id={scene_id}"
                )
        else:
            selected = markers[0]

        time_normalized = str(time_value).lower().strip()
        if time_normalized == "start":
            return float(selected["start_time"])
        if time_normalized != "end":
            raise ValueError("marker time must be 'start' or 'end'")

        if selected.get("end_time") is not None:
            return float(selected["end_time"])

        if default_duration_sec is not None:
            return float(selected["start_time"]) + float(default_duration_sec)

        raise RuntimeError(
            "Marker does not include an end time. Provide default_duration_sec to derive one"
        )

    def _pick_image_lookup(self) -> Tuple[str, str, str]:
        query_fields = self._get_query_fields()
        for field_name in ("findImage", "image", "imageById"):
            field = query_fields.get(field_name)
            if not field:
                continue

            args = field.get("args") or []
            arg_name = None
            for candidate in ("id", "image_id", "imageId"):
                if any(arg.get("name") == candidate for arg in args):
                    arg_name = candidate
                    break
            if arg_name is None and args:
                arg_name = args[0].get("name")

            image_type_name = self._unwrap_type_name(field.get("type"))
            if arg_name and image_type_name:
                return field_name, arg_name, image_type_name

        raise RuntimeError("Could not find an image lookup query (findImage/image/imageById) in Stash GraphQL schema")

    def _query_image(self, image_id: Any, selection_set: str) -> Dict[str, Any]:
        query_field, arg_name, _image_type = self._pick_image_lookup()
        query = f"""
        query GetImage($id: ID!) {{
          {query_field}({arg_name}: $id) {{
            {selection_set}
          }}
        }}
        """
        data = self.execute(query, {"id": str(image_id)})
        image = data.get(query_field)
        if not image:
            raise RuntimeError(f"Image not found for id={image_id}")
        return image

    def _get_union_possible_type_names(self, type_name: str) -> List[str]:
        query = """
        query IntrospectUnion($name: String!) {
          __type(name: $name) {
            kind
            possibleTypes {
              name
            }
          }
        }
        """
        data = self.execute(query, {"name": type_name})
        type_info = data.get("__type") or {}
        return [t["name"] for t in (type_info.get("possibleTypes") or []) if t.get("name")]

    def get_image_path(self, image_id: Any) -> str:
        _query_field, _arg_name, image_type_name = self._pick_image_lookup()
        image_type = self._get_type_definition(image_type_name)
        image_fields = {f["name"]: f for f in (image_type.get("fields") or []) if f.get("name")}

        # Prefer visual_files (non-deprecated). It is a union type, so we must use
        # inline fragments to access path — direct field introspection returns nothing.
        if "visual_files" in image_fields:
            vf_type_name = self._unwrap_type_name(image_fields["visual_files"].get("type"))
            if vf_type_name:
                member_names = self._get_union_possible_type_names(vf_type_name)
                path_fragments: List[str] = []
                for member in member_names:
                    member_type = self._get_type_definition(member)
                    member_fields = {f["name"] for f in (member_type.get("fields") or []) if f.get("name")}
                    for path_field in ("path", "file_path", "abs_path"):
                        if path_field in member_fields:
                            path_fragments.append(f"... on {member} {{ {path_field} }}")
                            break
                if path_fragments:
                    selection = "\n".join(path_fragments)
                    image = self._query_image(image_id, f"visual_files {{\n{selection}\n}}")
                    for item in (image.get("visual_files") or []):
                        value = item.get("path") or item.get("file_path") or item.get("abs_path")
                        if value:
                            return str(value)

        # Fall back to the deprecated files field (concrete ImageFile type with path).
        if "files" in image_fields:
            files_type_name = self._unwrap_type_name(image_fields["files"].get("type"))
            if files_type_name:
                file_type = self._get_type_definition(files_type_name)
                file_fields = {f["name"] for f in (file_type.get("fields") or []) if f.get("name")}
                for path_field in ("path", "file_path", "abs_path"):
                    if path_field in file_fields:
                        image = self._query_image(image_id, f"files {{ {path_field} }}")
                        for item in (image.get("files") or []):
                            value = item.get(path_field)
                            if value:
                                return str(value)

        # NOTE: Image.paths (ImagePathsType) intentionally not used here — its fields
        # (thumbnail, preview, image) are all HTTP URL resolvers, not filesystem paths.
        raise RuntimeError(
            "Could not resolve a filesystem path for image. "
            "Expected Image.visual_files or Image.files with a path field in schema"
        )

    def get_scene_bundle(self, scene_id: Any) -> Dict[str, Any]:
        # Query title and tags for the scene
        _query_field, _arg_name, scene_type_name = self._pick_scene_lookup()
        scene_type = self._get_type_definition(scene_type_name)
        scene_fields = {f["name"]: f for f in (scene_type.get("fields") or []) if f.get("name")}

        title_field = None
        for candidate in ("title", "name"):
            if candidate in scene_fields:
                title_field = candidate
                break

        tags_field = None
        for candidate in ("tags",):
            if candidate in scene_fields:
                tags_field = candidate
                break

        selection = []
        if title_field:
            selection.append(title_field)
        if tags_field:
            selection.append(f'{tags_field} {{ name }}')
        selection.append('files { path }')
        # Use correct marker fields: seconds (start), end_seconds (end)
        selection.append('scene_markers { id title seconds end_seconds tags { name } primary_tag { name } }')
        selection_set = '\n'.join(selection)
        scene = self._query_scene(scene_id, selection_set)

        # Scene tags
        scene_tags = [t["name"] for t in (scene.get(tags_field) or [])] if tags_field else []
        # Scene title
        scene_title = scene.get(title_field) if title_field else None
        # Scene path
        media_path = None
        if "files" in scene:
            for item in (scene["files"] or []):
                if item.get("path"):
                    media_path = item["path"]
                    break
        # Markers
        markers = []
        DEFAULT_MARKER_DURATION = 20.0
        for m in scene.get("scene_markers", []):
            start = m.get("seconds")
            end = m.get("end_seconds")
            if start is not None and end is not None:
                duration = float(end) - float(start)
            else:
                duration = DEFAULT_MARKER_DURATION
            marker = {
                "id": m.get("id"),
                "title": m.get("title"),
                "start_time": start,
                "end_time": end,
                "duration": duration,
                "tags": [t["name"] for t in (m.get("tags") or []) if t.get("name")],
                "primary_tag": m.get("primary_tag", {}).get("name") if m.get("primary_tag") else None,
            }
            markers.append(marker)
        return {
            "scene_id": str(scene_id),
            "title": scene_title,
            "tags": scene_tags,
            "media_path": media_path,
            "markers": markers,
        }
