"""Proves each planted problem can be found from the archive files alone.

Plain code, no AI. Each check reads only the generated source files, finds
every case of its kind of problem, and is compared with the answer key.
A planted problem counts as recovered when the check flags it; anything else
the check flags is reported as an extra finding.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any

from spark.sim.common import Row, normalise_code, read_csv

Finding = dict[str, Any]


def _d(value: str) -> date:
    """Read either ISO dates or day/month/year dates."""
    if "/" in value:
        return datetime.strptime(value, "%d/%m/%Y").date()
    return date.fromisoformat(value)


class Archive:
    def __init__(self, root: Path, as_of: date) -> None:
        self.root = root
        self.as_of = as_of
        self._cache: dict[str, list[Row]] = {}

    def rows(self, relative: str) -> list[Row]:
        if relative not in self._cache:
            path = self.root / relative
            self._cache[relative] = read_csv(path) if path.exists() else []
        return self._cache[relative]

    def sites(self) -> dict[str, Row]:
        return {r["site_code"]: r for r in self.rows("site_register/sites.csv")}

    def site_code_for_name(self) -> dict[str, str]:
        return {
            r["name"]: r["site_code"]
            for r in self.rows("site_register/name_history.csv")
        }

    def with_trait(self, trait: str) -> set[str]:
        column = {"remote": "remote_area", "coastal": "coastal"}.get(trait, trait)
        return {code for code, r in self.sites().items() if r.get(column) == "Y"}


def _consumption_runout(a: Archive, check: dict[str, Any]) -> list[Finding]:
    issues: defaultdict[tuple[str, str], dict[date, int]] = defaultdict(dict)
    for r in a.rows("inventory/movements.csv"):
        if r["movement"] == "ISSUE":
            issues[(r["site_code"], r["item_code"])][_d(r["date"]).replace(day=1)] = (
                int(r["quantity"])
            )
    latest: dict[tuple[str, str], tuple[date, int]] = {}
    for r in a.rows("inventory/stock_counts.csv"):
        key, day = (r["site_code"], r["item_code"]), _d(r["count_date"])
        if key not in latest or day > latest[key][0]:
            latest[key] = (day, int(r["quantity"]))
    open_sites = {c for c, r in a.sites().items() if r["status"] == "Open"}
    found: list[Finding] = []
    for key, (day, stock) in latest.items():
        if key[0] not in open_sites or (a.as_of - day).days > 45:
            continue
        months = sorted(issues[key])[-3:]
        span = sum((_month_days(m)) for m in months)
        rate = sum(issues[key][m] for m in months) / span if span else 0
        if rate <= 0:
            continue
        runout = a.as_of.toordinal() + round(stock / rate)
        if runout - a.as_of.toordinal() <= int(check["warning_days"]):
            found.append(
                {
                    "site_code": key[0],
                    "item_code": key[1],
                    "runout_date": date.fromordinal(runout).isoformat(),
                }
            )
    return found


def _month_days(month: date) -> int:
    nxt = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    return (nxt - month).days


def _lead_time_drift(a: Archive, check: dict[str, Any]) -> list[Finding]:
    leads: defaultdict[str, list[tuple[date, int]]] = defaultdict(list)
    for r in a.rows("procurement/purchase_orders.csv"):
        if r["received_date"]:
            received = _d(r["received_date"])
            leads[r["supplier_code"]].append(
                (received, (received - _d(r["order_date"])).days)
            )
    found: list[Finding] = []
    for supplier, values in sorted(leads.items()):
        recent = [v for day, v in values if (a.as_of - day).days <= 92]
        baseline = [v for day, v in values if 365 < (a.as_of - day).days <= 730]
        if len(recent) < 3 or len(baseline) < 3:
            continue
        ratio = median(recent) / median(baseline)
        if ratio >= float(check["ratio"]):
            found.append({"supplier_code": supplier, "ratio": round(ratio, 2)})
    return found


def _expiry_cluster(a: Archive, check: dict[str, Any]) -> list[Finding]:
    active = {
        r["worker_id"]: r["site_code"]
        for r in a.rows("hr_current/workers.csv")
        if not r["termination_date"]
    }
    latest: dict[tuple[str, str], date] = {}
    for r in a.rows("hr_current/certifications.csv"):
        key = (r["worker_id"], r["certification"])
        expires = _d(r["expires"])
        if key not in latest or expires > latest[key]:
            latest[key] = expires
    found: list[Finding] = []
    for act in a.rows("operations/project_plans.csv"):
        start = _d(act["planned_start"])
        if start <= a.as_of:
            continue
        site = act["site_code"]
        by_skill: defaultdict[str, list[tuple[str, date]]] = defaultdict(list)
        for (worker, skill), expires in latest.items():
            if active.get(worker) == site and expires >= a.as_of:
                by_skill[skill].append((worker, expires))
        for skill, holders in sorted(by_skill.items()):
            lapsing = sorted(w for w, e in holders if e < start)
            share = 1 - len(lapsing) / len(holders)
            if share < float(check["min_share"]):
                found.append(
                    {
                        "site_code": site,
                        "skill": skill,
                        "activity_code": act["activity_code"],
                        "worker_ids": lapsing,
                        "valid_share_at_start": round(share, 3),
                    }
                )
    return found


def _turnover_rise(a: Archive, check: dict[str, Any]) -> list[Finding]:
    found: list[Finding] = []
    for trait in [str(check["trait"])]:
        sites = a.with_trait(trait)
        recent: defaultdict[str, int] = defaultdict(int)
        prior: defaultdict[str, int] = defaultdict(int)
        for r in a.rows("hr_current/workers.csv"):
            if r["site_code"] not in sites or not r["termination_date"]:
                continue
            age = (a.as_of - _d(r["termination_date"])).days
            role = r["job_title"].lower()
            if 0 < age <= 365:
                recent[role] += 1
            elif 365 < age <= 4 * 365:
                prior[role] += 1
        for role, count in sorted(recent.items()):
            yearly = prior[role] / 3
            if count >= int(check["min_leavers"]) and count >= float(
                check["ratio"]
            ) * max(yearly, 1):
                found.append(
                    {
                        "role": role,
                        "trait": trait,
                        "leavers_last_12_months": count,
                        "prior_yearly_average": round(yearly, 1),
                    }
                )
    return found


def _resource_double_booking(a: Archive, check: dict[str, Any]) -> list[Finding]:
    bookings: defaultdict[str, list[tuple[date, date, str]]] = defaultdict(list)
    for r in a.rows("operations/resource_bookings.csv"):
        bookings[r["resource"]].append(
            (_d(r["booked_from"]), _d(r["booked_to"]), r["activity_code"])
        )
    found: list[Finding] = []
    for resource, spans in sorted(bookings.items()):
        for start, end, code in spans:
            overlapping = sorted({c for s, e, c in spans if s <= end and e >= start})
            if len(overlapping) > int(check["max_overlap"]) and code == overlapping[0]:
                found.append({"resource": resource, "activity_codes": overlapping})
    return found


def _split_overspend(a: Archive, check: dict[str, Any]) -> list[Finding]:
    year = a.as_of.year
    spent: defaultdict[str, float] = defaultdict(float)
    months: defaultdict[str, set[int]] = defaultdict(set)
    for r in a.rows("finance_erp/journal.csv"):
        day = _d(r["posting_date"])
        if r["contract_no"] and day.year == year:
            spent[r["contract_no"]] += float(r["amount"])
            months[r["contract_no"]].add(day.month)
    budget: defaultdict[str, float] = defaultdict(float)
    for r in a.rows("finance_erp/budgets.csv"):
        if int(r["fiscal_year"]) == year:
            budget[r["contract_no"]] += float(r["budget_amount"])
    found: list[Finding] = []
    for contract, amount in sorted(spent.items()):
        expected = budget[contract] * len(months[contract]) / 12
        if expected and amount / expected >= float(check["ratio"]):
            found.append(
                {"contract_no": contract, "ratio": round(amount / expected, 2)}
            )
    return found


def _failure_rate_by_trait(a: Archive, check: dict[str, Any]) -> list[Finding]:
    years = int(check.get("years", 5))
    since = date(a.as_of.year - years, a.as_of.month, 1)
    names = a.site_code_for_name()
    assets: dict[str, tuple[str, str, date]] = {}
    for r in a.rows("maint_a/assets.csv"):
        if r["status"] == "In service":
            assets["A:" + r["asset_id"]] = (
                normalise_code(r["oem_model"]),
                r["site_code"],
                _d(r["commissioned"]),
            )
    for r in a.rows("maint_b/equipment.csv"):
        if r["status"] == "ACTV":
            assets["B:" + r["equipment_no"]] = (
                normalise_code(r["manufacturer_model"]),
                names.get(r["functional_location"], ""),
                _d(r["install_date"]),
            )
    for r in a.rows("maint_c/tags.csv"):
        if not r["out_of_service"]:
            assets["C:" + r["tag"]] = (
                normalise_code(r["oem"]),
                r["site_code"],
                _d(r["in_service"]),
            )
    failures: defaultdict[str, int] = defaultdict(int)
    events = [
        ("A:", "maint_a/work_orders.csv", "asset_id", "wo_type", "CM", "raised"),
        (
            "B:",
            "maint_b/notifications.csv",
            "equipment_no",
            "notif_type",
            "M1",
            "created",
        ),
        ("C:", "maint_c/jobs.csv", "tag", "job_type", "breakdown", "date"),
    ]
    for prefix, path, key, kind, corrective, when in events:
        for r in a.rows(path):
            if r[kind] == corrective and _d(r[when]) >= since:
                failures[prefix + r[key]] += 1
    found: list[Finding] = []
    for trait in [str(check["trait"])]:
        sites = a.with_trait(trait)
        stats: defaultdict[tuple[str, bool], list[float]] = defaultdict(
            lambda: [0.0, 0.0]
        )
        for asset, (model, site, start) in assets.items():
            exposure = max(0, (a.as_of - max(start, since)).days) / 365
            cell = stats[(model, site in sites)]
            cell[0] += failures[asset]
            cell[1] += exposure
        for model in sorted({m for m, _ in stats}):
            inside, outside = stats[(model, True)], stats[(model, False)]
            if (
                inside[1] < 1
                or outside[1] < 1
                or inside[0] < int(check["min_failures"])
            ):
                continue
            ratio = (inside[0] / inside[1]) / max(outside[0] / outside[1], 1e-9)
            if ratio >= float(check["ratio"]):
                found.append({"model": model, "trait": trait, "ratio": round(ratio, 2)})
    return found


MODEL_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-[A-Z0-9-]+\b")


def _same_fault_reports(a: Archive, check: dict[str, Any]) -> list[Finding]:
    names = a.site_code_for_name()
    reports: defaultdict[str, list[tuple[date, str, str]]] = defaultdict(list)
    folder = a.root / "legal_risk" / "incidents"
    for path in sorted(folder.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        site = re.search(r"^Site: (.+)$", text, re.M)
        when = re.search(r"^Date: (.+)$", text, re.M)
        if not site or not when:
            continue
        body = text.split("\n\n", 1)[-1]
        for model in set(MODEL_PATTERN.findall(body)):
            reports[normalise_code(model)].append(
                (_d(when.group(1)), names.get(site.group(1), site.group(1)), path.name)
            )
    window = int(check["window_days"])
    found: list[Finding] = []
    for model, items in sorted(reports.items()):
        recent = [x for x in items if (a.as_of - x[0]).days <= window]
        sites = sorted({s for _, s, _ in recent})
        if len(sites) >= int(check["min_sites"]):
            found.append(
                {
                    "model": model,
                    "site_codes": sites,
                    "files": sorted(f for _, _, f in recent),
                }
            )
    return found


CHECKS: dict[str, Callable[[Archive, dict[str, Any]], list[Finding]]] = {
    "consumption_runout": _consumption_runout,
    "lead_time_drift": _lead_time_drift,
    "expiry_cluster": _expiry_cluster,
    "turnover_rise": _turnover_rise,
    "resource_double_booking": _resource_double_booking,
    "split_overspend": _split_overspend,
    "failure_rate_by_trait": _failure_rate_by_trait,
    "same_fault_reports": _same_fault_reports,
}


def matches(kind: str, expected: dict[str, Any], got: Finding) -> bool:
    """Does a flagged finding correspond to the planted answer?"""
    if kind == "consumption_runout":
        lo, hi = expected["runout_window"]
        return (
            got["site_code"] == expected["site_code"]
            and got["item_code"] == expected["item_code"]
            and lo <= got["runout_date"] <= hi
        )
    if kind == "lead_time_drift":
        return got["supplier_code"] == expected["supplier_code"]
    if kind == "expiry_cluster":
        return (got["site_code"], got["skill"], got["activity_code"]) == (
            expected["site_code"],
            expected["skill"],
            expected["activity_code"],
        ) and set(expected["worker_ids"]) <= set(got["worker_ids"])
    if kind == "turnover_rise":
        return (
            got["role"] == str(expected["role"]).lower()
            and got["trait"] == expected["trait"]
        )
    if kind == "resource_double_booking":
        return (
            got["resource"] in expected["resources"]
            and expected["activity_code"] in got["activity_codes"]
        )
    if kind == "split_overspend":
        return got["contract_no"] == expected["contract_no"]
    if kind == "failure_rate_by_trait":
        return (
            got["model"] == normalise_code(expected["model_no"])
            and got["trait"] == expected["trait"]
        )
    if kind == "same_fault_reports":
        return got["model"] == normalise_code(expected["model_no"]) and set(
            expected["site_codes"]
        ) <= set(got["site_codes"])
    raise ValueError(kind)


def explained_by(kind: str, expected: dict[str, Any], got: Finding) -> bool:
    """Is a flagged finding the planted problem itself or a direct effect of it?

    Lapsing certifications show up against every later activity at the same
    site, and a clash can pull in other bookings that overlap it. Those are
    the same problem, not extras.
    """
    if kind == "expiry_cluster":
        same_place = (got["site_code"], got["skill"]) == (
            expected["site_code"],
            expected["skill"],
        )
        return same_place and set(got["worker_ids"]) <= set(expected["worker_ids"])
    if kind == "resource_double_booking":
        planted = {expected["activity_code"], *expected["competing_activity_codes"]}
        return got["resource"] in expected["resources"] and bool(
            planted & set(got["activity_codes"])
        )
    return matches(kind, expected, got)


def recover(
    root: Path, as_of: date, answers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    archive = Archive(root, as_of)
    results: list[dict[str, Any]] = []
    flagged: dict[str, list[Finding]] = {}
    for answer in answers:
        kind = str(answer["kind"])
        check = dict(answer["check"])
        # Which site trait and period to compare comes from the problem
        # definition, as an analyst's question would.
        for field in ("trait", "years"):
            if field in answer["finding"]:
                check.setdefault(field, answer["finding"][field])
        key = f"{kind}:{sorted(check.items())}"
        if key not in flagged:
            flagged[key] = CHECKS[kind](archive, check)
        hits = [f for f in flagged[key] if matches(kind, answer["finding"], f)]
        results.append(
            {
                "id": answer["id"],
                "kind": kind,
                "recovered": bool(hits),
                "flagged": len(flagged[key]),
                "extras": [
                    f
                    for f in flagged[key]
                    if not explained_by(kind, answer["finding"], f)
                ],
            }
        )
    return results
