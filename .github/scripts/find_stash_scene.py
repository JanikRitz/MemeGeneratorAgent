"""
Find scenes from Stash GraphQL.

Environment variables:
- STASH_GRAPHQL_ENDPOINT or STASH_URL
- STASH_API_KEY (optional)

Usage examples:
    uv run .github/scripts/find_stash_scene.py --title "massage"
    uv run .github/scripts/find_stash_scene.py --path "clips/2024"
    uv run .github/scripts/find_stash_scene.py --include-tags "outdoor,verified"
    uv run .github/scripts/find_stash_scene.py --exclude-tags "bad-lighting"
    uv run .github/scripts/find_stash_scene.py --performers "Jane Doe,John Doe"
"""

import argparse
import json
import os
from typing import List

from stash_client import StashClient


def _csv_list(values: List[str] | None) -> List[str]:
    if not values:
        return []
    items: List[str] = []
    for value in values:
        items.extend([part.strip() for part in value.split(",") if part.strip()])
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Find scenes by title/path/tags/performers from Stash")
    parser.add_argument("--title", help="Title contains")
    parser.add_argument("--path", help="Scene file path contains")
    parser.add_argument(
        "--include-tags",
        action="append",
        help="Whitelist tags (comma-separated, repeatable). Scene must include all provided tags.",
    )
    parser.add_argument(
        "--exclude-tags",
        action="append",
        help="Blacklist tags (comma-separated, repeatable). Scene must include none of these tags.",
    )
    parser.add_argument(
        "--performers",
        action="append",
        help="Performer names (comma-separated, repeatable). Scene must include all provided performers.",
    )
    parser.add_argument("--per-page", type=int, default=5, help="Max results pulled from Stash per page")
    parser.add_argument("--page", type=int, default=1, help="Stash page number")

    args = parser.parse_args()

    endpoint = os.getenv("STASH_GRAPHQL_ENDPOINT") or os.getenv("STASH_URL")
    api_key = os.getenv("STASH_API_KEY")
    if not endpoint:
        parser.error("Set STASH_GRAPHQL_ENDPOINT (or STASH_URL) before calling this script")

    client = StashClient(endpoint=endpoint, api_key=api_key)
    payload = client.find_stash_scenes(
        title=args.title,
        path=args.path,
        include_tags=_csv_list(args.include_tags),
        exclude_tags=_csv_list(args.exclude_tags),
        performers=_csv_list(args.performers),
        per_page=args.per_page,
        page=args.page,
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
