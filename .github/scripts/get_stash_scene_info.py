"""
Fetch scene media path and markers from Stash GraphQL.

Environment variables:
- STASH_GRAPHQL_ENDPOINT or STASH_URL
- STASH_API_KEY (optional)

Usage:
    uv run .github/scripts/get_stash_scene_info.py --scene-id 123
"""

import argparse
import json
import os

from stash_client import StashClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Query scene media path and markers from Stash")
    parser.add_argument("--scene-id", required=True, help="Stash scene ID")
    args = parser.parse_args()

    endpoint = os.getenv("STASH_GRAPHQL_ENDPOINT") or os.getenv("STASH_URL")
    api_key = os.getenv("STASH_API_KEY")
    if not endpoint:
        parser.error("Set STASH_GRAPHQL_ENDPOINT (or STASH_URL) before calling this script")

    client = StashClient(endpoint=endpoint, api_key=api_key)
    payload = client.get_scene_bundle(args.scene_id)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
