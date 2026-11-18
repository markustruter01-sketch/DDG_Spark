from __future__ import annotations

import yaml

from omni.model.schema import build_metadata, load_schema, schema_counts
from omni.packs.loader import PACK_DIR, active_pack, active_pack_name, load_pack


def test_yaml_is_the_single_source_for_entities_and_tables() -> None:
    assert schema_counts() == {
        "entities": 21,
        "system_tables": 5,
        "support_tables": 2,
    }
    metadata = build_metadata()
    assert len(metadata.tables) == 28
    common = set(load_schema()["common_entity_fields"])
    for name in load_schema()["entities"]:
        assert common.issubset(metadata.tables[name].columns.keys())


def test_location_uses_postgis_geometry() -> None:
    geometry = build_metadata().tables["location"].columns["geometry"].type
    assert geometry.srid == 4326


def test_default_pack_has_six_harnesses_and_entity_labels(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OMNI_PACK", raising=False)
    load_pack.cache_clear()
    pack = active_pack()
    default_name = yaml.safe_load(
        (PACK_DIR / "pack-config.yaml").read_text(encoding="utf-8")
    )["default"]
    assert pack["name"] == default_name
    assert len(pack["harnesses"]) == 6
    assert len(pack["entities"]) == 5
    load_pack.cache_clear()


def test_pack_can_be_selected_by_environment(monkeypatch) -> None:
    available = {
        path.stem for path in PACK_DIR.glob("*.yaml") if path.name != "pack-config.yaml"
    }
    alternate = next(name for name in available if name != active_pack_name())
    monkeypatch.setenv("OMNI_PACK", alternate)
    load_pack.cache_clear()
    assert active_pack()["name"] == alternate
    load_pack.cache_clear()
