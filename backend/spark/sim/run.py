from __future__ import annotations

from typing import Any

import yaml

from spark.ingest.loader import ingest_dataset
from spark.sim.generate import CONFIG_FILE, generate_dataset


def main() -> None:
    config: Any = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    paths = generate_dataset()
    inserted = ingest_dataset(source_owner=config["organisation"]["source_owner"])
    print(f"Generated {len(paths)} source files.")
    print(
        "Inserted: " + ", ".join(f"{name}={count}" for name, count in inserted.items())
    )


if __name__ == "__main__":
    main()
