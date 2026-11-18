from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any, cast

import yaml

HARNESS_ROOT = Path(__file__).parent


def load_harness(key: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        raise ValueError("Harness key is invalid.")
    root = (HARNESS_ROOT / key).resolve()
    if not root.is_relative_to(HARNESS_ROOT.resolve()):
        raise ValueError("Harness path is invalid.")
    manifest_path = root / "manifest.yaml"
    if not manifest_path.is_file():
        raise ValueError("Harness is not available.")
    raw_manifest: Any = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw_manifest, dict):
        raise ValueError("Harness manifest is malformed.")
    manifest = cast(dict[str, Any], raw_manifest)
    if manifest.get("key") != key:
        raise ValueError("Harness manifest is malformed.")
    instructions_path = (root / manifest["instructions"]).resolve()
    template_path = (root / manifest["output_template"]).resolve()
    if not instructions_path.is_relative_to(root) or not template_path.is_relative_to(
        root
    ):
        raise ValueError("Harness resource path is invalid.")
    manifest["instructions_text"] = instructions_path.read_text(encoding="utf-8")
    manifest["output_template_value"] = json.loads(
        template_path.read_text(encoding="utf-8")
    )
    mock_script = root / "mock_script.py"
    if mock_script.is_file():
        module = importlib.import_module(f"omni.harness.{key}.mock_script")
        manifest["mock_reply_factory"] = module.__dict__["scripted_reply"]
        manifest["mock_tool_call_factory"] = module.__dict__["scripted_tool_calls"]
    if not isinstance(manifest.get("tools"), list) or not isinstance(
        manifest.get("scope"), list
    ):
        raise ValueError("Harness manifest is missing its declared scope or tools.")
    return manifest
