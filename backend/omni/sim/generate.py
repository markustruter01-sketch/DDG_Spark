from __future__ import annotations

import calendar
import csv
import random
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
CONFIG_FILE = Path(__file__).with_name("dataset.yaml")
OUTPUT_DIR = WORKSPACE_ROOT / "generated-artifacts" / "stage1" / "input"


def _shift_months(value: date, offset: int) -> date:
    absolute_month = value.year * 12 + value.month - 1 + offset
    year, month_index = divmod(absolute_month, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _month_end(value: date) -> date:
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def _read_config() -> dict[str, Any]:
    value = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Synthetic dataset configuration is malformed.")
    return cast(dict[str, Any], value)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to generate an empty data file: {path.name}")
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def generate_dataset(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    config = _read_config()
    as_of = date.fromisoformat(config["as_of"])
    randomizer = random.Random(int(config["seed"]))
    organisation = config["organisation"]
    items = [config["critical_item"], *config["items"]]
    months = [_shift_months(as_of.replace(day=1), index) for index in range(-11, 1)]
    asset_count = int(organisation["asset_count"])
    asset_names = [
        f"{organisation['asset_prefix']}-{index:02d}"
        for index in range(1, asset_count + 1)
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        output_dir / name
        for name in (
            "stock_levels.csv",
            "stock_movements.csv",
            "maintenance_jobs.csv",
            "supplier_orders.csv",
            "shift_reports.csv",
        )
    ]
    _write_csv(
        paths[0],
        [
            {
                "source_owner": organisation["source_owner"],
                "item_name": item["name"],
                "category": item["category"],
                "unit": item["unit"],
                "quantity": item["current_quantity"],
                "as_of": as_of.isoformat(),
                "location_name": organisation["location_name"],
                "location_kind": organisation["location_kind"],
                "country": organisation["country"],
                "org_unit_name": organisation["division_name"],
                "org_unit_kind": organisation["division_kind"],
            }
            for item in items
        ],
    )

    movements: list[dict[str, object]] = []
    for item_index, item in enumerate(items):
        monthly = item["monthly_consumption"]
        quantities: list[int]
        if isinstance(monthly, list):
            quantities = cast(list[int], monthly)
        else:
            quantities = [int(monthly)] * len(months)
        if len(quantities) != len(months):
            raise ValueError("Each item must define twelve monthly quantities.")
        for month_index, (month, quantity) in enumerate(
            zip(months, quantities, strict=True)
        ):
            moved_on = (
                as_of
                if month.year == as_of.year and month.month == as_of.month
                else _month_end(month)
            )
            movements.append(
                {
                    "source_owner": organisation["source_owner"],
                    "item_name": item["name"],
                    "quantity": quantity,
                    "moved_on": moved_on.isoformat(),
                    "from_location": organisation["location_name"],
                    "to_location": "",
                    "maintenance_job_asset": (
                        f"{organisation['asset_prefix']}-"
                        f"{((month_index + item_index) % asset_count) + 1:02d}"
                    ),
                }
            )
    _write_csv(paths[1], movements)

    job_rows: list[dict[str, object]] = []
    for asset_name in asset_names:
        opened = as_of - timedelta(days=randomizer.randint(15, 350))
        closed = opened + timedelta(days=randomizer.randint(1, 4))
        job_rows.append(
            {
                "source_owner": organisation["source_owner"],
                "asset_name": asset_name,
                "asset_type": organisation["asset_type"],
                "org_unit_name": organisation["division_name"],
                "opened_on": opened.isoformat(),
                "closed_on": closed.isoformat(),
                "kind": "scheduled inspection",
                "fault": "Routine inspection completed; asset returned to service.",
                "location_name": organisation["location_name"],
            }
        )
    _write_csv(paths[2], job_rows)

    supplier = config["supplier"]
    order_rows: list[dict[str, object]] = []
    for item in items:
        critical = item["name"] == config["critical_item"]["name"]
        monthly_plan = item["monthly_consumption"]
        if critical:
            quantity = 10
        elif isinstance(monthly_plan, list):
            quantity = max(80, int(cast(list[int], monthly_plan)[-1]) * 4)
        else:
            quantity = max(80, int(monthly_plan) * 4)
        order_rows.append(
            {
                "source_owner": organisation["source_owner"],
                "supplier_name": supplier["name"],
                "supplier_country": supplier["country"],
                "item_name": item["name"],
                "quantity": quantity,
                "ordered_on": (as_of - timedelta(days=5)).isoformat(),
                "promised_on": (as_of + timedelta(days=18)).isoformat(),
                "received_on": "",
                "amount": quantity * 25,
            }
        )
    _write_csv(paths[3], order_rows)

    report_rows: list[dict[str, Any]] = [
        {
            "source_owner": organisation["source_owner"],
            "authored_on": (as_of - timedelta(days=9 - index)).isoformat(),
            "title": report["title"],
            "text": report["text"],
            "org_unit_name": organisation["division_name"],
        }
        for index, report in enumerate(config["reports"])
    ]
    if len(report_rows) != 10:
        raise ValueError("The sample must contain exactly ten reports.")
    _write_csv(paths[4], report_rows)
    return paths
