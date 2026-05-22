"""
Find performers by name from Stash GraphQL.

Environment variables:
- STASH_GRAPHQL_ENDPOINT or STASH_URL
- STASH_API_KEY (optional)

Usage:
    uv run .github/scripts/find_stash_performer.py --name "Jane Doe"
"""

import argparse
import json
import os

from stash_client import StashClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Find performers by name from Stash")
    parser.add_argument("--name", required=True, help="Performer name")
    args = parser.parse_args()

    endpoint = os.getenv("STASH_GRAPHQL_ENDPOINT") or os.getenv("STASH_URL")
    api_key = os.getenv("STASH_API_KEY")
    if not endpoint:
        parser.error("Set STASH_GRAPHQL_ENDPOINT (or STASH_URL) before calling this script")

    client = StashClient(endpoint=endpoint, api_key=api_key)
    payload = client.find_stash_performer(args.name)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
