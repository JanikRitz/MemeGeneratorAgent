"""
Find Hydrus files by tags and return resolved local media paths.

Environment variables:
- HYDRUS_API_URL (optional, defaults to http://127.0.0.1:45869/)
- HYDRUS_ACCESS_KEY or HYDRUS_API_KEY (optional, depends on Hydrus API permissions)

Usage:
    uv run .github/scripts/find_hydrus_file.py --tags "series:foo,character:bar"
"""

import argparse
import json
import os
from typing import List

from hydrus_client import HydrusClient


def _csv_list(values: List[str] | None) -> List[str]:
    if not values:
        return []
    items: List[str] = []
    for value in values:
        items.extend([part.strip() for part in value.split(",") if part.strip()])
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Find Hydrus files by tags")
    parser.add_argument(
        "--tags",
        action="append",
        required=True,
        help="Hydrus tags (comma-separated, repeatable).",
    )
    parser.add_argument("--index", type=int, default=0, help="Select a specific match index")
    args = parser.parse_args()

    endpoint = os.getenv("HYDRUS_API_URL") or os.getenv("HYDRUS_URL")
    access_key = os.getenv("HYDRUS_ACCESS_KEY") or os.getenv("HYDRUS_API_KEY")

    client = HydrusClient(endpoint=endpoint, access_key=access_key)
    tags = _csv_list(args.tags)
    all_paths = client.search_file_paths(tags)
    selected_path = ""
    if all_paths and 0 <= int(args.index) < len(all_paths):
        selected_path = all_paths[int(args.index)]

    print(
        json.dumps(
            {
                "tags": tags,
                "count": len(all_paths),
                "selected_index": int(args.index),
                "selected_path": selected_path,
                "paths": all_paths,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
