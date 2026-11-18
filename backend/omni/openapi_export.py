from __future__ import annotations

import argparse
import json
from pathlib import Path

from omni.main import app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    schema = app.openapi()
    schema["servers"] = [{"url": "/"}]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(schema, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
