"""Write the OpenAPI document for TS type generation: ``uv run python scripts/export_openapi.py [--check]``.

The app is built from in-memory settings, so no live dependency is contacted.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from api.apps import OPENAPI_PATH, create_app  # noqa: E402
from test.helpers.app import memory_settings  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "web" / "openapi" / "openapi.json"


async def render() -> str:
    app = create_app(memory_settings())
    response = await app.test_client().get(OPENAPI_PATH)
    if response.status_code != 200:
        raise SystemExit(f"openapi endpoint returned {response.status_code}")
    document = json.loads(await response.get_data(as_text=True))
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if the committed file differs")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    text = asyncio.run(render())
    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.is_file() else None
        if current != text:
            print(f"{args.out} is out of date; run scripts/export_openapi.py", file=sys.stderr)
            return 1
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
