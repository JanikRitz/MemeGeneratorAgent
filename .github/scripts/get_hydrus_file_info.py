"""
Fetch Hydrus file metadata and resolved local media path.

Environment variables:
- HYDRUS_API_URL (optional, defaults to http://127.0.0.1:45869/)
- HYDRUS_ACCESS_KEY or HYDRUS_API_KEY (optional, depends on Hydrus API permissions)

Usage:
    uv run .github/scripts/get_hydrus_file_info.py --file-id 123
    uv run .github/scripts/get_hydrus_file_info.py --hash <sha256>
"""

import argparse
import json
import os

from hydrus_client import HydrusClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Query file metadata and media path from Hydrus")
    parser.add_argument("--file-id", type=int, help="Hydrus file ID")
    parser.add_argument("--hash", dest="hash_value", help="Hydrus SHA-256 hash")
    args = parser.parse_args()

    if args.file_id is None and not args.hash_value:
        parser.error("Provide either --file-id or --hash")

    endpoint = os.getenv("HYDRUS_API_URL") or os.getenv("HYDRUS_URL")
    access_key = os.getenv("HYDRUS_ACCESS_KEY") or os.getenv("HYDRUS_API_KEY")

    client = HydrusClient(endpoint=endpoint, access_key=access_key)
    payload = client.get_file_bundle(file_id=args.file_id, hash_=args.hash_value)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
