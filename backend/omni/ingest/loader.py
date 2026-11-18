from __future__ import annotations

import csv
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection
from sqlalchemy.dialects.postgresql import insert as pg_insert

from omni.db.owner import owner_engine
from omni.model.schema import build_metadata

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
INPUT_DIR = WORKSPACE_ROOT / "generated-artifacts" / "stage1" / "input"
RAW_DIR = WORKSPACE_ROOT / "generated-artifacts" / "stage1" / "raw"


def _stable_id(namespace: str, value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"omni:{namespace}:{value}")


def _date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def _write_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as output:
            output.write(content)
    except FileExistsError as error:
        if path.read_bytes() != content:
            raise RuntimeError(
                "A content-addressed landed file does not match its hash."
            ) from error


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _span(rows: list[dict[str, str]]) -> dict[str, str] | None:
    dates = [
        date_value
        for row in rows
        for key, value in row.items()
        if value and (key.endswith("_on") or key == "as_of")
        if (date_value := _date(value)) is not None
    ]
    if not dates:
        return None
    return {"start": min(dates).isoformat(), "end": max(dates).isoformat()}


def _insert(connection: Connection, table_name: str, values: dict[str, Any]) -> int:
    table = build_metadata().tables[table_name]
    statement = (
        pg_insert(table).values(**values).on_conflict_do_nothing().returning(table.c.id)
    )
    result = connection.execute(statement)
    return len(result.fetchall())


def _entity(
    connection: Connection,
    *,
    table_name: str,
    natural_key: str,
    raw_record_id: UUID,
    valid_from: date,
    fields: dict[str, Any],
) -> int:
    return _insert(
        connection,
        table_name,
        {
            "id": _stable_id(table_name, natural_key),
            "source_id": raw_record_id,
            "sensitivity": "internal",
            "valid_from": valid_from,
            "valid_to": None,
            "confidence": 0.98,
            **fields,
        },
    )


def ingest_dataset(
    input_dir: Path = INPUT_DIR,
    raw_dir: Path = RAW_DIR,
    source_owner: str | None = None,
) -> dict[str, int]:
    files = sorted(input_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError("No generated dataset files were found.")

    records: dict[str, list[tuple[UUID, dict[str, str]]]] = {}
    inserted = {"sources": 0, "raw_records": 0, "entities": 0}
    with owner_engine().begin() as connection:
        for path in files:
            content = path.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()
            _write_once(raw_dir / f"{checksum}.{path.suffix.lstrip('.')}", content)
            rows = _read_csv(path)
            source_id = _stable_id("source", checksum)
            inserted["sources"] += _insert(
                connection,
                "source",
                {
                    "id": source_id,
                    "owner": source_owner
                    or (rows[0].get("source_owner") if rows else None)
                    or "Synthetic organisation",
                    "format": "csv",
                    "time_span": _span(rows),
                    "sensitivity": "internal",
                    "checksum": checksum,
                    "landed_at": datetime.now(UTC),
                },
            )
            records[path.name] = []
            for index, row in enumerate(rows):
                record_key = f"{path.name}:{index:06d}"
                raw_id = _stable_id("raw_record", f"{checksum}:{record_key}")
                inserted["raw_records"] += _insert(
                    connection,
                    "raw_record",
                    {
                        "id": raw_id,
                        "source_id": source_id,
                        "record_key": record_key,
                        "payload": row,
                        "landed_at": datetime.now(UTC),
                    },
                )
                records[path.name].append((raw_id, row))

        location_name = records["stock_levels.csv"][0][1]["location_name"]
        first_stock = records["stock_levels.csv"][0][1]
        org_name = first_stock["org_unit_name"]
        as_of = _date(first_stock["as_of"]) or date.today()
        location_id = _stable_id("location", location_name)
        org_id = _stable_id("org_unit", org_name)
        first_raw = records["stock_levels.csv"][0][0]
        inserted["entities"] += _entity(
            connection,
            table_name="location",
            natural_key=location_name,
            raw_record_id=first_raw,
            valid_from=as_of,
            fields={
                "name": location_name,
                "kind": first_stock["location_kind"],
                "country": first_stock["country"],
                "geometry": None,
            },
        )
        inserted["entities"] += _entity(
            connection,
            table_name="org_unit",
            natural_key=org_name,
            raw_record_id=first_raw,
            valid_from=as_of,
            fields={
                "name": org_name,
                "kind": first_stock["org_unit_kind"],
                "parent_org_unit_id": None,
                "location_id": location_id,
            },
        )

        item_ids: dict[str, UUID] = {}
        for raw_id, row in records["stock_levels.csv"]:
            item_name = row["item_name"]
            item_ids[item_name] = _stable_id("item", item_name)
            inserted["entities"] += _entity(
                connection,
                table_name="item",
                natural_key=item_name,
                raw_record_id=raw_id,
                valid_from=_date(row["as_of"]) or as_of,
                fields={
                    "name": item_name,
                    "category": row["category"],
                    "unit": row["unit"],
                },
            )
            inserted["entities"] += _entity(
                connection,
                table_name="stock_level",
                natural_key=f"{item_name}:{row['location_name']}:{row['as_of']}",
                raw_record_id=raw_id,
                valid_from=_date(row["as_of"]) or as_of,
                fields={
                    "item_id": item_ids[item_name],
                    "location_id": location_id,
                    "quantity": float(row["quantity"]),
                    "as_of": _date(row["as_of"]),
                },
            )

        job_ids: dict[str, UUID] = {}
        for raw_id, row in records["maintenance_jobs.csv"]:
            asset_name = row["asset_name"]
            asset_id = _stable_id("asset", asset_name)
            opened_on = _date(row["opened_on"]) or as_of
            job_ids[asset_name] = _stable_id(
                "maintenance_job", f"{asset_name}:{opened_on}"
            )
            inserted["entities"] += _entity(
                connection,
                table_name="asset",
                natural_key=asset_name,
                raw_record_id=raw_id,
                valid_from=opened_on,
                fields={
                    "name": asset_name,
                    "asset_type": row["asset_type"],
                    "org_unit_id": org_id,
                    "location_id": location_id,
                    "commissioned_on": None,
                    "status": "active",
                },
            )
            inserted["entities"] += _entity(
                connection,
                table_name="maintenance_job",
                natural_key=f"{asset_name}:{opened_on}",
                raw_record_id=raw_id,
                valid_from=opened_on,
                fields={
                    "asset_id": asset_id,
                    "kind": row["kind"],
                    "opened_on": opened_on,
                    "closed_on": _date(row["closed_on"]),
                    "fault": row["fault"],
                },
            )

        for raw_id, row in records["stock_movements.csv"]:
            moved_on = _date(row["moved_on"]) or as_of
            inserted["entities"] += _entity(
                connection,
                table_name="stock_movement",
                natural_key=f"{row['item_name']}:{moved_on}:{row['quantity']}",
                raw_record_id=raw_id,
                valid_from=moved_on,
                fields={
                    "item_id": item_ids[row["item_name"]],
                    "from_location_id": location_id,
                    "to_location_id": None,
                    "quantity": float(row["quantity"]),
                    "moved_on": moved_on,
                    "maintenance_job_id": job_ids.get(row["maintenance_job_asset"]),
                },
            )

        for raw_id, row in records["supplier_orders.csv"]:
            supplier_name = row["supplier_name"]
            supplier_id = _stable_id("supplier", supplier_name)
            inserted["entities"] += _entity(
                connection,
                table_name="supplier",
                natural_key=supplier_name,
                raw_record_id=raw_id,
                valid_from=_date(row["ordered_on"]) or as_of,
                fields={
                    "name": supplier_name,
                    "country": row["supplier_country"],
                },
            )
            ordered_on = _date(row["ordered_on"]) or as_of
            inserted["entities"] += _entity(
                connection,
                table_name="purchase_order",
                natural_key=f"{supplier_name}:{row['item_name']}:{ordered_on}",
                raw_record_id=raw_id,
                valid_from=ordered_on,
                fields={
                    "supplier_id": supplier_id,
                    "item_id": item_ids[row["item_name"]],
                    "quantity": float(row["quantity"]),
                    "ordered_on": ordered_on,
                    "promised_on": _date(row["promised_on"]),
                    "received_on": _date(row["received_on"]),
                    "amount": float(row["amount"]),
                },
            )

        for raw_id, row in records["shift_reports.csv"]:
            authored_on = _date(row["authored_on"]) or as_of
            inserted["entities"] += _entity(
                connection,
                table_name="document",
                natural_key=f"{row['title']}:{authored_on}",
                raw_record_id=raw_id,
                valid_from=authored_on,
                fields={
                    "title": row["title"],
                    "kind": "report",
                    "authored_on": authored_on,
                    "org_unit_id": org_id,
                    "full_text": row["text"],
                },
            )

    return inserted
