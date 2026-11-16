"""Write the API's OpenAPI document to web/openapi.json, the input of `make client`.

Building the app opens no database connection, so this runs without Docker.
"""

import json
import sys
from pathlib import Path

from home_base.api.app import create_app

OUT = Path(__file__).resolve().parent.parent / "web" / "openapi.json"


def main() -> int:
    document = create_app().openapi()
    OUT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
