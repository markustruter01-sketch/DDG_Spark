from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PACK_DIR = Path(__file__).parent


@lru_cache(maxsize=4)
def load_pack(name: str) -> dict[str, Any]:
    available = {
        path.stem for path in PACK_DIR.glob("*.yaml") if path.name != "pack-config.yaml"
    }
    if name not in available:
        raise ValueError("OMNI_PACK must name an available sector pack.")
    path = PACK_DIR / f"{name}.yaml"
    pack = yaml.safe_load(path.read_text(encoding="utf-8"))
    if len(pack.get("harnesses", {})) != 6:
        raise ValueError(f"Pack {name} must define six harnesses.")
    return pack


def active_pack_name() -> str:
    config = yaml.safe_load((PACK_DIR / "pack-config.yaml").read_text(encoding="utf-8"))
    chosen = os.getenv("OMNI_PACK", config["default"]).strip().lower()
    return chosen or config["default"]


def active_pack() -> dict[str, Any]:
    return load_pack(active_pack_name())


def public_pack() -> dict[str, Any]:
    pack = active_pack()
    return {
        "name": pack["name"],
        "harnesses": [
            {"key": key, "label": label} for key, label in pack["harnesses"].items()
        ],
        "entities": pack["entities"],
        "rules": pack.get("rules", {}),
    }
