from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import yaml
from geoalchemy2 import Geometry
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

SCHEMA_FILE = Path(__file__).with_name("schema.yaml")


def load_schema(path: Path = SCHEMA_FILE) -> dict[str, Any]:
    raw_data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, dict):
        raise ValueError("The universal schema file is malformed.")
    data = cast(dict[str, Any], raw_data)
    if not isinstance(data.get("entities"), dict):
        raise ValueError("The universal schema file is malformed.")
    return data


def _sql_type(type_name: str) -> Any:
    types: dict[str, Any] = {
        "uuid": UUID(as_uuid=True),
        "text": Text(),
        "integer": Integer(),
        "numeric": Numeric(),
        "float": Float(),
        "boolean": Boolean(),
        "date": Date(),
        "timestamp": DateTime(timezone=True),
        "json": JSONB(),
        "sensitivity": String(16),
        "confidence": Float(),
        "geometry": Geometry(geometry_type="GEOMETRY", srid=4326),
        "text_array": ARRAY(Text()),
    }
    try:
        return types[type_name]
    except KeyError as error:
        raise ValueError(f"Unsupported YAML field type: {type_name}") from error


@lru_cache(maxsize=1)
def build_metadata(path: Path = SCHEMA_FILE) -> MetaData:
    definition = load_schema(path)
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    common = definition["common_entity_fields"]
    table_groups = [
        ("system_tables", definition.get("system_tables", {})),
        ("support_tables", definition.get("support_tables", {})),
        ("entities", definition["entities"]),
    ]

    for group_name, tables in table_groups:
        for table_name, table_definition in tables.items():
            fields: dict[str, Any] = {}
            if group_name == "entities":
                fields.update(common)
            fields.update(table_definition.get("fields", {}))
            columns: list[Column[Any]] = []
            checks: list[CheckConstraint] = []
            for column_name, field in fields.items():
                type_name = field["type"]
                nullable = bool(field.get("nullable", False))
                kwargs: dict[str, Any] = {
                    "nullable": nullable,
                    "primary_key": bool(field.get("primary_key", False)),
                    "unique": bool(field.get("unique", False)),
                }
                if "references" in field:
                    kwargs["foreign_key"] = ForeignKey(field["references"])
                column = Column(
                    column_name,
                    _sql_type(type_name),
                    *([kwargs.pop("foreign_key")] if "foreign_key" in kwargs else []),
                    **kwargs,
                )
                columns.append(column)
                if type_name == "sensitivity":
                    checks.append(
                        CheckConstraint(
                            f"{column_name} IN ('public', 'internal', 'restricted')",
                            name=f"{column_name}_sensitivity_values",
                        )
                    )
                if type_name == "confidence":
                    checks.append(
                        CheckConstraint(
                            "confidence >= 0 AND confidence <= 1",
                            name="confidence_range",
                        )
                    )
                if field.get("allowed"):
                    allowed_values = ", ".join(
                        "'" + str(value).replace("'", "''") + "'"
                        for value in field["allowed"]
                    )
                    checks.append(
                        CheckConstraint(
                            f"{column_name} IN ({allowed_values})",
                            name=f"{column_name}_allowed",
                        )
                    )
            Table(table_name, metadata, *columns, *checks)
    return metadata


def schema_counts() -> dict[str, int]:
    schema = load_schema()
    return {
        "entities": len(schema["entities"]),
        "system_tables": len(schema["system_tables"]),
        "support_tables": len(schema.get("support_tables", {})),
    }
