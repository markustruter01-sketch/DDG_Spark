"""Writes the world out as the files each source system would export.

The mess is deliberate and driven by the organisation's timeline settings:
two finance systems with different account codes, old and new HR systems
with duplicate people, three maintenance systems with three coding schemes,
emailed stock counts that disagree with the system, late and missing shift
reports, and inconsistently named incident documents.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, cast

from spark.sim.common import ArchiveWriter, Row, add_months, days, dmy, month_end
from spark.sim.world import (
    ACCOUNTS,
    Site,
    World,
    contract_no,
    legacy_contract_ref,
    legacy_employee_no,
    maintenance_system,
    supplier_code,
    worker_id,
)

LEGACY_ACCOUNT = {name: str(5100 + 100 * i) for i, name in enumerate(ACCOUNTS)}
ERP_ACCOUNT = {
    name: f"6{i + 1}00-{name[:3].upper()}" for i, name in enumerate(ACCOUNTS)
}


def name_on(site: Site, day: date, restructure: date) -> str:
    """The site name people used on a given day."""
    return site.old_name if site.old_name and day < restructure else site.name


def incident_filename(world: World, number: int) -> str:
    """Incident documents were never named consistently."""
    incident = world.incidents[number - 1]
    site = world.site(incident.site)
    style = number % 4
    if style == 0:
        return f"INC-{incident.day.year}-{number:04d}.txt"
    if style == 1:
        return f"incident report {incident.day.strftime('%d %B %Y')} {site.name}.txt"
    if style == 2:
        return f"IR_{site.code}_{incident.day.strftime('%Y%m%d')}_{number}.txt"
    return f"{site.name.replace(' ', '_')}-{number}-final v2.txt"


def export_world(world: World, out: ArchiveWriter) -> None:
    _site_register(world, out)
    _hr(world, out)
    _finance(world, out)
    _maintenance(world, out)
    _inventory(world, out)
    _operations(world, out)
    _legal_risk(world, out)


def _yn(flag: bool) -> str:
    return "Y" if flag else "N"


def _site_register(world: World, out: ArchiveWriter) -> None:
    out.csv(
        "site_register/sites.csv",
        [
            "site_code",
            "site_name",
            "country",
            "division",
            "site_type",
            "opened",
            "status",
            "closed",
            "remote_area",
            "coastal",
        ],
        (
            {
                "site_code": s.code,
                "site_name": s.name,
                "country": s.country.name,
                "division": s.division,
                "site_type": s.kind,
                "opened": s.opened.isoformat(),
                "status": "Closed" if s.closed else "Open",
                "closed": s.closed.isoformat() if s.closed else "",
                "remote_area": _yn("remote" in s.traits),
                "coastal": _yn("coastal" in s.traits),
            }
            for s in world.sites
        ),
    )
    restructure = world.config.when("restructure")
    rows: list[Row] = []
    for s in world.sites:
        if s.old_name:
            rows.append(
                {
                    "site_code": s.code,
                    "name": s.old_name,
                    "valid_from": s.opened.isoformat(),
                    "valid_to": (restructure - days(1)).isoformat(),
                }
            )
            rows.append(
                {
                    "site_code": s.code,
                    "name": s.name,
                    "valid_from": restructure.isoformat(),
                    "valid_to": "",
                }
            )
        else:
            rows.append(
                {
                    "site_code": s.code,
                    "name": s.name,
                    "valid_from": s.opened.isoformat(),
                    "valid_to": "",
                }
            )
    out.csv(
        "site_register/name_history.csv",
        ["site_code", "name", "valid_from", "valid_to"],
        rows,
    )


def _hr(world: World, out: ArchiveWriter) -> None:
    merge = world.config.when("hr_merge")
    restructure = world.config.when("restructure")
    timeline = world.config.timeline
    legacy = [p for p in world.people if p.hired < merge]
    out.csv(
        "hr_legacy/employees.csv",
        [
            "emp_no",
            "surname",
            "given_names",
            "site",
            "position",
            "start_date",
            "end_date",
        ],
        (
            {
                "emp_no": legacy_employee_no(p.pid),
                "surname": p.last.upper(),
                "given_names": p.first,
                "site": name_on(world.site(p.site), merge - days(1), restructure),
                "position": p.role,
                "start_date": dmy(p.hired),
                "end_date": dmy(p.left) if p.left and p.left < merge else "",
            }
            for p in legacy
        ),
    )
    current = [p for p in world.people if p.left is None or p.left >= merge]
    r = world.r("hr-export")
    rows: list[Row] = []
    duplicates: list[Row] = []
    for p in current:
        migrated = p.hired < merge
        rows.append(
            {
                "worker_id": worker_id(p.pid),
                "full_name": f"{p.first} {p.last}",
                "site_code": p.site,
                "job_title": p.role,
                "hire_date": (merge if migrated else p.hired).isoformat(),
                "termination_date": p.left.isoformat() if p.left else "",
                "legacy_ref": legacy_employee_no(p.pid)
                if migrated and r.random() >= float(timeline["hr_missing_legacy_ref"])
                else "",
            }
        )
        if migrated and r.random() < float(timeline["hr_duplicate_share"]):
            duplicates.append(
                {
                    "worker_id": f"W-9{p.pid:05d}",
                    "full_name": f"{p.last.upper()}, {p.first}",
                    "site_code": p.site,
                    "job_title": p.role.lower(),
                    "hire_date": merge.isoformat(),
                    "termination_date": "",
                    "legacy_ref": "",
                }
            )
    out.csv("hr_current/workers.csv", list(rows[0]), [*rows, *duplicates])
    current_ids = {p.pid for p in current}
    out.csv(
        "hr_current/certifications.csv",
        ["worker_id", "certification", "issued", "expires"],
        (
            {
                "worker_id": worker_id(c.pid),
                "certification": c.skill,
                "issued": c.issued.isoformat(),
                "expires": c.expires.isoformat(),
            }
            for c in sorted(
                world.certificates, key=lambda c: (c.pid, c.skill, c.issued)
            )
            if c.pid in current_ids and c.expires >= merge
        ),
    )


def _finance(world: World, out: ArchiveWriter) -> None:
    cutover = world.config.when("erp_cutover")
    legacy: list[Row] = []
    erp: list[Row] = []
    for p in sorted(world.postings, key=lambda x: (x.day, x.cost_centre, x.account)):
        company = p.cost_centre[:2]
        if p.day < cutover:
            legacy.append(
                {
                    "Date": dmy(p.day),
                    "Entity": company,
                    "CostCentre": p.cost_centre,
                    "Account": LEGACY_ACCOUNT[p.account],
                    "ContractRef": legacy_contract_ref(p.contract)
                    if p.contract
                    else "",
                    "Currency": p.currency,
                    "Amount": f"{p.amount:.2f}",
                }
            )
        else:
            erp.append(
                {
                    "posting_date": p.day.isoformat(),
                    "company": company,
                    "cost_centre": p.cost_centre,
                    "gl_account": ERP_ACCOUNT[p.account],
                    "contract_no": contract_no(p.contract) if p.contract else "",
                    "currency": p.currency,
                    "amount": f"{p.amount:.2f}",
                }
            )
    out.csv("finance_legacy/gl_export.csv", list(legacy[0]), legacy)
    out.csv("finance_erp/journal.csv", list(erp[0]), erp)
    budgets: list[Row] = []
    for contract in world.contracts:
        for year in range(cutover.year, world.config.as_of.year + 1):
            for cc in contract.cost_centres:
                budgets.append(
                    {
                        "fiscal_year": str(year),
                        "cost_centre": cc,
                        "contract_no": contract_no(contract.number),
                        "budget_amount": f"{contract.annual_budget[cc]:.2f}",
                        "currency": "AUD",
                    }
                )
    out.csv("finance_erp/budgets.csv", list(budgets[0]), budgets)
    out.csv(
        "finance_erp/contracts.csv",
        ["contract_no", "description", "supplier_code"],
        (
            {
                "contract_no": contract_no(c.number),
                "description": c.name,
                "supplier_code": supplier_code(world, c.supplier),
            }
            for c in world.contracts
        ),
    )


def _maintenance(world: World, out: ArchiveWriter) -> None:
    descriptions = {
        str(m["model_no"]): str(m["description"])
        for m in cast(list[dict[str, Any]], world.config.org["asset_models"])
    }
    starts = {
        str(s["name"]): int(s["from"])
        for s in cast(list[dict[str, Any]], world.config.org["maintenance_systems"])
    }
    holder = {
        a.tag: maintenance_system(world, world.site(a.site)) for a in world.assets
    }
    orders: defaultdict[int, list[Any]] = defaultdict(list)
    for w in sorted(world.work_orders, key=lambda w: (w.raised, w.tag)):
        if w.raised.year >= starts[holder[w.tag]]:
            orders[w.tag].append(w)
    sys_a = [a for a in world.assets if holder[a.tag] == "maint_a"]
    sys_b = [a for a in world.assets if holder[a.tag] == "maint_b"]
    sys_c = [a for a in world.assets if holder[a.tag] == "maint_c"]
    if sys_a:
        out.csv(
            "maint_a/assets.csv",
            [
                "asset_id",
                "description",
                "oem_model",
                "site_code",
                "commissioned",
                "status",
            ],
            (
                {
                    "asset_id": f"A{a.tag:05d}",
                    "description": descriptions[a.model],
                    "oem_model": a.model,
                    "site_code": a.site,
                    "commissioned": a.commissioned.isoformat(),
                    "status": "Retired" if a.retired else "In service",
                }
                for a in sys_a
            ),
        )
        out.csv(
            "maint_a/work_orders.csv",
            ["wo_number", "asset_id", "wo_type", "raised", "cost"],
            (
                {
                    "wo_number": f"WO{i:07d}",
                    "asset_id": f"A{w.tag:05d}",
                    "wo_type": "CM" if w.corrective else "PM",
                    "raised": w.raised.isoformat(),
                    "cost": f"{w.cost:.2f}",
                }
                for i, w in enumerate(
                    (w for a in sys_a for w in orders[a.tag]), start=1
                )
            ),
        )
    if sys_b:
        out.csv(
            "maint_b/equipment.csv",
            [
                "equipment_no",
                "equip_class",
                "manufacturer_model",
                "functional_location",
                "install_date",
                "status",
            ],
            (
                {
                    "equipment_no": f"EQ-{a.tag:06d}",
                    "equip_class": descriptions[a.model][:4].upper(),
                    "manufacturer_model": a.model.replace("-", " "),
                    "functional_location": world.site(a.site).name,
                    "install_date": dmy(a.commissioned),
                    "status": "INAC" if a.retired else "ACTV",
                }
                for a in sys_b
            ),
        )
        out.csv(
            "maint_b/notifications.csv",
            ["notification", "equipment_no", "notif_type", "created", "cost"],
            (
                {
                    "notification": f"{40000000 + i}",
                    "equipment_no": f"EQ-{w.tag:06d}",
                    "notif_type": "M1" if w.corrective else "M2",
                    "created": dmy(w.raised),
                    "cost": f"{w.cost:.2f}",
                }
                for i, w in enumerate(
                    (w for a in sys_b for w in orders[a.tag]), start=1
                )
            ),
        )
    if sys_c:
        out.csv(
            "maint_c/tags.csv",
            ["tag", "oem", "site_code", "in_service", "out_of_service"],
            (
                {
                    "tag": f"C/{a.tag:04d}",
                    "oem": a.model.replace("-", "").lower(),
                    "site_code": a.site,
                    "in_service": a.commissioned.isoformat(),
                    "out_of_service": a.retired.isoformat() if a.retired else "",
                }
                for a in sys_c
            ),
        )
        out.csv(
            "maint_c/jobs.csv",
            ["job_id", "tag", "job_type", "date", "amount", "currency"],
            (
                {
                    "job_id": f"J{i:06d}",
                    "tag": f"C/{w.tag:04d}",
                    "job_type": "breakdown" if w.corrective else "service",
                    "date": w.raised.isoformat(),
                    "amount": f"{w.cost * 0.62:.2f}",
                    "currency": "EUR",
                }
                for i, w in enumerate(
                    (w for a in sys_c for w in orders[a.tag]), start=1
                )
            ),
        )


def _inventory(world: World, out: ArchiveWriter) -> None:
    out.csv(
        "inventory/items.csv",
        ["item_code", "description", "unit"],
        (
            {
                "item_code": str(i["code"]),
                "description": str(i["name"]),
                "unit": str(i["unit"]),
            }
            for i in world.items
        ),
    )
    counts: list[Row] = []
    moves: list[Row] = []
    for s in world.stock:
        for month, quantity in s.month_end_stock.items():
            counts.append(
                {
                    "count_date": month_end(month).isoformat(),
                    "site_code": s.site,
                    "item_code": s.item,
                    "quantity": str(quantity),
                }
            )
        for month, quantity in s.issues.items():
            moves.append(
                {
                    "date": (month_end(month) - days(1)).isoformat(),
                    "site_code": s.site,
                    "item_code": s.item,
                    "movement": "ISSUE",
                    "quantity": str(quantity),
                }
            )
        for month, quantity in s.receipts.items():
            moves.append(
                {
                    "date": month_end(month).isoformat(),
                    "site_code": s.site,
                    "item_code": s.item,
                    "movement": "RECEIPT",
                    "quantity": str(quantity),
                }
            )
    out.csv(
        "inventory/stock_counts.csv",
        list(counts[0]),
        sorted(counts, key=lambda r: (r["count_date"], r["site_code"], r["item_code"])),
    )
    out.csv(
        "inventory/movements.csv",
        list(moves[0]),
        sorted(
            moves,
            key=lambda r: (r["date"], r["site_code"], r["item_code"], r["movement"]),
        ),
    )
    # Quarterly counts emailed in by sites as spreadsheets; some disagree.
    share = float(world.config.timeline["stock_count_conflict_share"])
    names = {str(i["code"]): str(i["name"]) for i in world.items}
    emailed: defaultdict[tuple[str, int], list[Row]] = defaultdict(list)
    for s in world.stock:
        r = world.r("emailed", s.site, s.item)
        for month, quantity in s.month_end_stock.items():
            if (
                month.month % 3 == 0
                and month.year >= world.config.when("restructure").year
            ):
                shown = (
                    quantity
                    if r.random() >= share
                    else max(0, round(quantity * r.uniform(0.8, 1.2)))
                )
                emailed[(s.site, month.year)].append(
                    {
                        "Site": s.site,
                        "Item": s.item,
                        "Description": names[s.item],
                        "Qty on hand": str(shown),
                        "Counted": dmy(month_end(month)),
                    }
                )
    for (site, year), rows in sorted(emailed.items()):
        out.csv(f"inventory/emailed_counts/{site}_{year}.csv", list(rows[0]), rows)
    out.csv(
        "procurement/suppliers.csv",
        ["supplier_code", "name"],
        (
            {"supplier_code": supplier_code(world, n), "name": n}
            for n in world.suppliers
        ),
    )
    out.csv(
        "procurement/purchase_orders.csv",
        [
            "po_number",
            "supplier_code",
            "item_code",
            "site_code",
            "order_date",
            "promised_date",
            "received_date",
            "quantity",
            "unit_price",
            "currency",
        ],
        (
            {
                "po_number": f"PO{o.number}",
                "supplier_code": supplier_code(world, o.supplier),
                "item_code": o.item,
                "site_code": o.site,
                "order_date": o.ordered.isoformat(),
                "promised_date": o.promised.isoformat(),
                "received_date": o.received.isoformat() if o.received else "",
                "quantity": str(o.quantity),
                "unit_price": f"{o.unit_price:.2f}",
                "currency": "AUD",
            }
            for o in sorted(world.orders, key=lambda o: (o.ordered, o.number))
        ),
    )


def _operations(world: World, out: ArchiveWriter) -> None:
    acts = sorted(world.activities, key=lambda a: (a.start, a.code))
    out.csv(
        "operations/project_plans.csv",
        [
            "activity_code",
            "activity_name",
            "site_code",
            "activity_type",
            "planned_start",
            "planned_finish",
        ],
        (
            {
                "activity_code": a.code,
                "activity_name": a.name,
                "site_code": a.site,
                "activity_type": a.kind,
                "planned_start": a.start.isoformat(),
                "planned_finish": a.end.isoformat(),
            }
            for a in acts
        ),
    )
    out.csv(
        "operations/resource_bookings.csv",
        ["activity_code", "resource", "booked_from", "booked_to"],
        (
            {
                "activity_code": a.code,
                "resource": res,
                "booked_from": a.start.isoformat(),
                "booked_to": a.end.isoformat(),
            }
            for a in acts
            for res in a.resources
        ),
    )
    phrases = cast(list[str], world.config.org["shift_phrases"])
    crews = cast(list[str], world.config.org["crews"])
    timeline = world.config.timeline
    disruption = cast(dict[str, Any], timeline["disruption"])
    gap_start, gap_end = (
        date.fromisoformat(str(disruption["start"])),
        date.fromisoformat(str(disruption["end"])),
    )
    as_of = world.config.as_of
    restructure = world.config.when("restructure")
    for site in world.sites:
        r = world.r("shifts", site.code)
        models = sorted({a.model for a in world.assets if a.site == site.code}) or [
            "equipment"
        ]
        skip_gap = r.random() < float(disruption["missing_share"])
        end = site.closed or as_of
        by_year: defaultdict[int, list[str]] = defaultdict(list)
        week = site.opened
        while week < end:
            if not (skip_gap and gap_start <= week <= gap_end):
                text = " ".join(
                    r.choice(phrases).format(
                        crew=r.choice(crews),
                        item=str(r.choice(world.items)["name"]),
                        model=r.choice(models),
                    )
                    for _ in range(2)
                )
                late = r.random() < float(timeline["late_report_share"])
                header = f"Week of {dmy(week)} | {name_on(site, week, restructure)}"
                if late:
                    header += f" | entered {dmy(week + days(r.randint(15, 40)))}"
                by_year[week.year].append(f"{header}\n{text}\n")
            week = week + days(7)
        for year, entries in sorted(by_year.items()):
            out.text(
                f"operations/shift_reports/{site.code}/{year}.txt", "\n".join(entries)
            )


def _legal_risk(world: World, out: ArchiveWriter) -> None:
    restructure = world.config.when("restructure")
    for incident in world.incidents:
        site = world.site(incident.site)
        body = (
            f"Site: {name_on(site, incident.day, restructure)}\n"
            f"Date: {dmy(incident.day)}\nReported by: shift supervisor\n\n"
            f"{incident.text}\n"
        )
        out.text(
            f"legal_risk/incidents/{incident_filename(world, incident.number)}", body
        )
    r = world.r("audit")
    areas = cast(list[str], world.config.org["audit_areas"])
    rows: list[Row] = []
    for site in world.sites:
        for year in range(
            site.opened.year + 1,
            ((site.closed or world.config.as_of) - days(1)).year + 1,
        ):
            for _ in range(r.randint(0, 3)):
                raised = date(year, 1, 1) + days(r.randint(0, 364))
                rows.append(
                    {
                        "finding_id": f"AF-{len(rows) + 1:05d}",
                        "site_code": site.code,
                        "raised": raised.isoformat(),
                        "area": r.choice(areas),
                        "severity": r.choice(["Low", "Medium", "High"]),
                        "status": "Closed"
                        if raised < add_months(world.config.as_of, -6)
                        else "Open",
                    }
                )
    out.csv(
        "legal_risk/audit_findings.csv",
        ["finding_id", "site_code", "raised", "area", "severity", "status"],
        rows,
    )
