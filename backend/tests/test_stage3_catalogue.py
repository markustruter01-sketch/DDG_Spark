from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

import pytest

from spark.ingest.catalogue import catalogue
from spark.ingest.mapping import propose
from spark.ingest.parse import parse_date, parse_number, passages
from spark.sim.build import build

INGEST_DIR = Path(__file__).resolve().parents[1] / "spark" / "ingest"

# Which entity each source file feeds. Written by hand from the source
# systems in the world briefs; the proposals must reach the same answer.
EXPECTED = {
    "site_register/sites.csv": "org_unit",
    "site_register/name_history.csv": "org_unit",
    "hr_legacy/employees.csv": "person",
    "hr_current/workers.csv": "person",
    "hr_current/certifications.csv": "person_skill",
    "finance_legacy/gl_export.csv": "transaction",
    "finance_erp/journal.csv": "transaction",
    "finance_erp/budgets.csv": "budget_line",
    "finance_erp/contracts.csv": "contract",
    "maint_a/assets.csv": "asset",
    "maint_b/equipment.csv": "asset",
    "maint_c/tags.csv": "asset",
    "maint_a/work_orders.csv": "maintenance_job",
    "maint_b/notifications.csv": "maintenance_job",
    "maint_c/jobs.csv": "maintenance_job",
    "inventory/items.csv": "item",
    "inventory/stock_counts.csv": "stock_level",
    "inventory/movements.csv": "stock_movement",
    "inventory/emailed_counts/": "stock_level",
    "procurement/suppliers.csv": "supplier",
    "procurement/purchase_orders.csv": "purchase_order",
    "operations/project_plans.csv": "activity",
    "operations/resource_bookings.csv": "activity_requirement",
    "legal_risk/audit_findings.csv": "risk",
    "operations/shift_reports/": "document",
    "legal_risk/incidents/": "document",
}


def expected_entity(path: str) -> str:
    for key, entity in EXPECTED.items():
        if path == key or (key.endswith("/") and path.startswith(key)):
            return entity
    raise AssertionError(f"No expected entity for {path}")


@pytest.fixture(scope="module", params=["corvane", "blue_team"])
def archive(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    report = build(
        str(request.param), "small", tmp_path_factory.mktemp(str(request.param))
    )
    return Path(report["archive"])


def test_dates_in_both_styles_and_numbers() -> None:
    assert parse_date("2026-11-01") == date(2026, 11, 1)
    assert parse_date("01/11/2026") == date(2026, 11, 1)
    assert parse_date("31/02/2026") is None
    assert parse_date("next week") is None
    assert parse_number("1,234.50") == 1234.5
    assert parse_number("") is None


def test_catalogue_counts_every_row_and_passage(archive: Path) -> None:
    entries = catalogue(archive)
    assert len(entries) == sum(1 for p in archive.rglob("*") if p.is_file())
    for entry in entries:
        path = archive / entry.path
        if entry.format == "table":
            with path.open(encoding="utf-8", newline="") as handle:
                assert entry.records == sum(1 for _ in csv.DictReader(handle))
        else:
            assert entry.format == "document"
            assert entry.records == len(passages(path)) > 0
    assert all(e.format != "unknown" for e in entries)


def test_every_file_gets_the_right_entity(archive: Path) -> None:
    wrong = [
        (e.path, p.entity)
        for e in catalogue(archive)
        if (p := propose(e)).entity != expected_entity(e.path)
    ]
    assert wrong == []


def test_proposals_link_files_to_each_other(archive: Path) -> None:
    proposals = {p.path: p for p in map(propose, catalogue(archive))}
    assert proposals["hr_current/certifications.csv"].refs["person"] == "worker_id"
    assert (
        proposals["procurement/purchase_orders.csv"].refs["supplier"] == "supplier_code"
    )
    assert proposals["maint_b/notifications.csv"].refs["asset"] == "equipment_no"
    assert proposals["finance_legacy/gl_export.csv"].refs["contract"] == "ContractRef"


def test_passages_keep_line_numbers(tmp_path: Path) -> None:
    doc = tmp_path / "d.txt"
    doc.write_text(
        "Site: A\nDate: 01/02/2026\n\nSomething happened.\nMore.\n", encoding="utf-8"
    )
    found = passages(doc)
    assert [(p.start_line, p.end_line) for p in found] == [(1, 2), (4, 5)]


def test_ingest_code_has_no_organisation_or_sector_words() -> None:
    banned = re.compile(
        r"corvane|blue team|aldmark|brigade|defence|military|\bmining\b|"
        r"pipeline|\btruck\b|\bpump\b|\blogistics\b",
        re.I,
    )
    files = [*INGEST_DIR.glob("*.py"), INGEST_DIR / "mapping_hints.yaml"]
    hits = [
        f"{path.name}:{n}"
        for path in files
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if banned.search(line)
    ]
    assert hits == []
