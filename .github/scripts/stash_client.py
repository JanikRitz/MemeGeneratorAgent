import sys
from typing import Any, List, Dict, Optional
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport

class StashClient:
    def __init__(self, endpoint: str = "http://localhost:9999/graphql", api_key: Optional[str] = None):
        """
        Initializes the Stash GraphQL client.
        Default Stash endpoint is http://localhost:9999/graphql
        """
        headers = {}
        if api_key:
            headers["ApiKey"] = api_key  # Stash uses 'ApiKey' header if security is enabled

        self.transport = RequestsHTTPTransport(
            url=endpoint,
            headers=headers,
            verify=True,
            retries=3
        )
        # Disable schema introspection fetch to avoid startup failures on imperfect server schemas.
        self.client = Client(transport=self.transport, fetch_schema_from_transport=False)

    def get_scene_path(self, scene_id: Any) -> str:
        """
        Retrieves the primary local file path for a given scene ID.
        """
        query = gql(
            """
            query FindScenePath($id: ID!) {
              findScene(id: $id) {
                files {
                  path
                }
              }
            }
            """
        )
        result = self.client.execute(query, variable_values={"id": str(scene_id)})
        scene = result.get("findScene")
        if scene and scene.get("files"):
            # Return the first available file path associated with the scene
            return scene["files"][0]["path"]
        return ""

    def get_scene_markers(self, scene_id: Any) -> List[Dict[str, Any]]:
        """
        Retrieves all markers associated with a scene.
        """
        query = gql(
            """
            query FindSceneMarkers($id: ID!) {
              findScene(id: $id) {
                scene_markers {
                  id
                  title
                  seconds
                  end_seconds
                  primary_tag {
                    id
                    name
                  }
                }
              }
            }
            """
        )
        result = self.client.execute(query, variable_values={"id": str(scene_id)})
        scene = result.get("findScene")
        if scene and "scene_markers" in scene:
            return scene["scene_markers"]
        return []

    def resolve_marker_time(
        self,
        scene_id: Any,
        marker_id: Optional[Any] = None,
        marker_title: Optional[str] = None,
        time_value: str = "start",
        default_duration_sec: Optional[float] = None,
    ) -> float:
        """
        Finds a marker inside a scene by ID or title and resolves its timestamp.
        time_value options: 'start' (default) or 'end'.
        If 'end' is chosen but no end_seconds exists, it falls back to start + default_duration_sec (or 0.0).
        """
        markers = self.get_scene_markers(scene_id)
        target_marker = None

        # 1. Match the marker
        if marker_id is not None:
            target_marker = next((m for m in markers if str(m.get("id")) == str(marker_id)), None)
        elif marker_title is not None:
            target_marker = next((m for m in markers if m.get("title", "").lower() == marker_title.lower()), None)

        if not target_marker:
            return 0.0

        # 2. Resolve the timestamp
        start_time = float(target_marker.get("seconds", 0.0))
        
        if time_value.lower() == "end":
            end_time = target_marker.get("end_seconds")
            if end_time is not None:
                return float(end_time)
            elif default_duration_sec is not None:
                return start_time + float(default_duration_sec)
            
        return start_time

    def get_image_path(self, image_id: Any) -> str:
        """
        Retrieves the primary local file path for a given image ID.
        """
        query = gql(
            """
            query FindImagePath($id: ID!) {
              findImage(id: $id) {
                files {
                  path
                }
              }
            }
            """
        )
        result = self.client.execute(query, variable_values={"id": str(image_id)})
        image = result.get("findImage")
        if image and image.get("files"):
            return image["files"][0]["path"]
        return ""

    def get_scene_bundle(self, scene_id: Any) -> Dict[str, Any]:
        """
        Retrieves a complete data bundle for a scene, matching relationships.
        """
        query = gql(
            """
            query GetSceneBundle($id: ID!) {
              findScene(id: $id) {
                id
                title
                details
                date
                rating100
                files {
                  path
                }
                performers {
                  name
                }
                tags {
                  name
                }
                studio {
                  id
                  name
                }
              }
            }
            """
        )
        result = self.client.execute(query, variable_values={"id": str(scene_id)})
        scene = result.get("findScene")
        if not scene:
            return {}
        scene["files"] = [f["path"] for f in scene.get("files") or []]
        scene["performers"] = [p["name"] for p in scene.get("performers") or []]
        scene["tags"] = [t["name"] for t in scene.get("tags") or []]
        return scene

    def get_image_bundle(self, image_id: Any) -> Dict[str, Any]:
        """
        Retrieves a complete data bundle for an image.
        """
        query = gql(
            """
            query GetImageBundle($id: ID!) {
              findImage(id: $id) {
                id
                title
                rating100
                date
                organized
                files {
                  id
                  path
                  size
                  width
                  height
                }
                performers {
                  id
                  name
                }
                tags {
                  id
                  name
                }
                studio {
                  id
                  name
                }
              }
            }
            """
        )
        result = self.client.execute(query, variable_values={"id": str(image_id)})
        return result.get("findImage") or {}

    def get_performer_bundle(self, performer_id: Any) -> Dict[str, Any]:
        """
        Retrieves a complete profile bundle for a performer.
        """
        query = gql(
            """
            query GetPerformerBundle($id: ID!) {
              findPerformer(id: $id) {
                id
                name
                disambiguation
                gender
                birthdate
                ethnicity
                country
                eye_color
                hair_color
                height_cm
                measurements
                fake_tits
                career_length_start
                career_length_end
                details
                rating100
                tags {
                  id
                  name
                }
              }
            }
            """
        )
        result = self.client.execute(query, variable_values={"id": str(performer_id)})
        return result.get("findPerformer") or {}

    def find_stash_performer(self, name: str, per_page: int = 25) -> Dict[str, Any]:
        """
      Finds performers by name and returns the first performer as a flat dict.
        """
        query = gql(
            """
            query FindPerformersByName($name: String!, $per_page: Int!) {
              findPerformers(
                performer_filter: { name: { value: $name, modifier: EQUALS } }
                filter: { per_page: $per_page }
              ) {
                count
                performers {
                  id
                  name
                  disambiguation
                  gender
                  ethnicity
                  country
                  rating100
                  height_cm
                  weight
                  eye_color
                  hair_color
                  tattoos
                  piercings
                  tags {name}
                  
                }
              }
            }
            """
        )
        result = self.client.execute(
            query,
            variable_values={"name": name, "per_page": int(per_page)},
        )
        performers = (result.get("findPerformers") or {}).get("performers") or []
        if not performers:
          return {}

        performer = dict(performers[0])
        # Flatten tags from [{"name": "..."}] to ["..."] for easier downstream use.
        performer["tags"] = [
          tag.get("name") if isinstance(tag, dict) else str(tag)
          for tag in performer.get("tags") or []
        ]
        return performer

    def find_tag_ids_by_names(self, names: List[str]) -> List[str]:
        """
        Resolves a list of tag names to their Stash IDs.
        Queries each name individually with an EQUALS filter and returns the first match per name.
        """
        query = gql(
            """
            query FindTagByName($name: String!) {
              findTags(
                tag_filter: { name: { value: $name, modifier: EQUALS } }
                filter: { per_page: 1 }
              ) {
                tags {
                  id
                }
              }
            }
            """
        )
        ids: List[str] = []
        for name in names:
            result = self.client.execute(query, variable_values={"name": name})
            tags = (result.get("findTags") or {}).get("tags") or []
            if tags:
                ids.append(str(tags[0]["id"]))
        return ids

    def find_performer_ids_by_names(self, names: List[str]) -> List[str]:
        """
        Resolves a list of performer names to their Stash IDs.
        Queries each name individually with an EQUALS filter and returns the first match per name.
        """
        query = gql(
            """
            query FindPerformerIdByName($name: String!) {
              findPerformers(
                performer_filter: { name: { value: $name, modifier: EQUALS } }
                filter: { per_page: 1 }
              ) {
                performers {
                  id
                }
              }
            }
            """
        )
        ids: List[str] = []
        for name in names:
            result = self.client.execute(query, variable_values={"name": name})
            performers = (result.get("findPerformers") or {}).get("performers") or []
            if performers:
                ids.append(str(performers[0]["id"]))
        return ids

    def find_stash_scenes(
        self,
        title: Optional[str] = None,
        path: Optional[str] = None,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        performers: Optional[List[str]] = None,
        per_page: int = 5,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Finds scenes using a single GraphQL query with proper SceneFilterType fields.

        - title / path use StringCriterionInput (INCLUDES).
        - include_tags / exclude_tags are resolved to IDs and applied via
          HierarchicalMultiCriterionInput (INCLUDES_ALL / NOT … INCLUDES).
        - performers are resolved to IDs and applied via MultiCriterionInput (INCLUDES_ALL).

        Returns a list of {"id": ..., "title": ...}.
        """
        query = gql(
            """
            query FindScenesByFilter($scene_filter: SceneFilterType!, $filter: FindFilterType!) {
              findScenes(
                scene_filter: $scene_filter
                filter: $filter
              ) {
                scenes {
                  id
                  title
                }
              }
            }
            """
        )

        def _normalized_list(items: Optional[List[str]]) -> List[str]:
            return [item.strip() for item in (items or []) if item and item.strip()]

        include_tag_names = _normalized_list(include_tags)
        exclude_tag_names = _normalized_list(exclude_tags)
        performer_names = _normalized_list(performers)

        include_tag_ids = self.find_tag_ids_by_names(include_tag_names)
        exclude_tag_ids = self.find_tag_ids_by_names(exclude_tag_names)
        performer_ids = self.find_performer_ids_by_names(performer_names)

        scene_filter: Dict[str, Any] = {}

        if title and title.strip():
            scene_filter["title"] = {"value": title.strip(), "modifier": "INCLUDES"}

        if path and path.strip():
            scene_filter["path"] = {"value": path.strip(), "modifier": "INCLUDES"}

        if include_tag_ids:
            scene_filter["tags"] = {
                "value": include_tag_ids,
                "modifier": "INCLUDES_ALL",
            }

        if exclude_tag_ids:
            scene_filter["NOT"] = {
                "tags": {
                    "value": exclude_tag_ids,
                    "modifier": "INCLUDES",
                }
            }

        if performer_ids:
            scene_filter["performers"] = {
                "value": performer_ids,
                "modifier": "INCLUDES_ALL",
            }

        result = self.client.execute(
            query,
            variable_values={
                "scene_filter": scene_filter,
                "filter": {"per_page": int(per_page), "page": int(page)},
            },
        )
        scenes = (result.get("findScenes") or {}).get("scenes") or []
        rows = [{"id": s.get("id"), "title": s.get("title") or ""} for s in scenes]
        rows.sort(key=lambda row: (str(row.get("title") or "").lower(), str(row.get("id") or "")))
        return rows
