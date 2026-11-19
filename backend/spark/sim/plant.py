"""Writes each planted problem into the world and records its answer.

Each kind of problem is generic. What it applies to (which site, item,
supplier, role, model) comes from the organisation's problems.yaml.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from statistics import median
from typing import Any, cast

from spark.sim.common import add_months, days, month_end, month_start, months_between
from spark.sim.world import (
    Activity,
    Asset,
    Incident,
    Order,
    World,
    add_certificates,
    add_person,
    contract_no,
    schedule_work,
    supplier_code,
    worker_id,
)

Answer = dict[str, Any]


def plant_all(world: World) -> list[Answer]:
    answers: list[Answer] = []
    for problem in world.config.problems:
        kind = str(problem["kind"])
        if kind not in PLANTERS:
            raise ValueError(f"Unknown problem kind {kind!r} in {problem['id']}.")
        finding = PLANTERS[kind](world, problem)
        answers.append(
            {
                "id": problem["id"],
                "harness": problem["harness"],
                "kind": kind,
                "story": problem.get("story", ""),
                "check": problem.get("check", {}),
                "finding": finding,
            }
        )
    return answers


def _consumption_runout(world: World, p: dict[str, Any]) -> Answer:
    site = world.select_site(cast(dict[str, Any], p["site"]))
    item = next(i for i in world.items if i["name"] == p["item"])
    series = next(
        s for s in world.stock if s.site == site.code and s.item == item["code"]
    )
    as_of = world.config.as_of
    months = months_between(add_months(as_of, -12), as_of - days(1))
    base = median(list(series.issues.values())[:-12] or [10])
    for step, month in enumerate(months):
        series.issues[month] = round(base * (1 + step * 0.2))
    last3 = months[-3:]
    rate = sum(series.issues[m] for m in last3) / sum(
        (month_end(m) - m).days + 1 for m in last3
    )
    target = round(rate * int(p["days_to_runout"]))
    cutoff = months[-6]
    world.orders = [
        o
        for o in world.orders
        if not (
            o.site == site.code
            and o.item == series.item
            and o.received is not None
            and o.received >= months[0]
        )
    ]
    # Months -12 to -7: normal reordering against the new, rising use.
    before = series.month_end_stock[add_months(months[0], -1)]
    for month in months[:-6]:
        series.receipts.pop(month, None)
        if before - series.issues[month] < series.issues[month] * 2:
            quantity = series.issues[month] * 4
            series.receipts[month] = quantity
            received = month_end(month)
            world.orders.append(
                Order(
                    990000 + len(world.orders),
                    series.supplier,
                    series.item,
                    site.code,
                    received - days(14),
                    received,
                    received,
                    quantity,
                    42.0,
                )
            )
        before += series.receipts.get(month, 0) - series.issues[month]
        series.month_end_stock[month] = before
    # Months -6 to now: one delivery, then nothing; stock runs down.
    for month in months[-6:]:
        series.receipts.pop(month, None)
    need = target - before + sum(series.issues[m] for m in months[-6:])
    if need < 0:
        series.issues[cutoff] += -need
        need = 0
    if need > 0:
        series.receipts[cutoff] = need
        received = month_end(cutoff)
        world.orders.append(
            Order(
                999000 + len(world.orders),
                series.supplier,
                series.item,
                site.code,
                received - days(14),
                received,
                received,
                need,
                42.0,
            )
        )
    stock = before
    for month in months[-6:]:
        stock += series.receipts.get(month, 0) - series.issues[month]
        series.month_end_stock[month] = stock
    runout = as_of + days(round(stock / rate))
    return {
        "site_code": site.code,
        "item_code": series.item,
        "item": p["item"],
        "stock_on_hand": stock,
        "runout_date": runout.isoformat(),
        "runout_window": [
            (runout - days(7)).isoformat(),
            (runout + days(7)).isoformat(),
        ],
    }


def _lead_time_drift(world: World, p: dict[str, Any]) -> Answer:
    name = str(p["supplier"])
    if name not in world.suppliers:
        raise ValueError(f"Planted supplier {name!r} is not in the supplier list.")
    as_of = world.config.as_of
    start = add_months(as_of, -12)
    base, end = int(p["base_days"]), int(p["end_days"])
    changed = 0
    for order in world.orders:
        if order.supplier != name or order.received is None:
            continue
        lead = base + world.r("drift", str(order.number)).randint(-1, 1)
        if order.received >= start:
            frac = (order.received - start).days / (as_of - start).days
            lead = round(base + (end - base) * frac)
            changed += 1
        order.ordered = order.received - days(lead)
        order.promised = order.ordered + days(base)
    if changed < 6:
        raise ValueError("Too few orders from the planted supplier to show a trend.")
    return {
        "supplier_code": supplier_code(world, name),
        "supplier": name,
        "base_days": base,
        "end_days": end,
    }


def _expiry_cluster(world: World, p: dict[str, Any]) -> Answer:
    site = world.select_site(cast(dict[str, Any], p["site"]))
    skill = str(p["skill"])
    spec = cast(dict[str, Any], p["activity"])
    as_of = world.config.as_of
    start = as_of + days(int(spec["starts_in_days"]))
    activity = Activity(
        f"ACT-P{len(world.activities) + 1:04d}",
        str(spec["name"]),
        site.code,
        str(spec["kind"]),
        start,
        start + days(int(spec["days"])),
    )
    world.activities.append(activity)
    roles = sorted(world.holders_of(skill))
    holders = [
        x
        for x in world.people
        if x.site == site.code and x.left is None and x.role in roles
    ]
    r = world.r("plant", str(p["id"]))
    while len(holders) < int(p["min_holders"]):
        person = add_person(
            world,
            site,
            roles[len(holders) % len(roles)],
            as_of - days(r.randint(200, 1500)),
        )
        add_certificates(world, person)
        holders.append(person)
    chosen = sorted(
        r.sample(holders, round(float(p["expiring_share"]) * len(holders))),
        key=lambda x: x.pid,
    )
    for person in chosen:
        expiry = as_of + days(r.randint(10, (start - as_of).days - 1))
        certs = [
            c for c in world.certificates if c.pid == person.pid and c.skill == skill
        ]
        latest = max(certs, key=lambda c: c.expires)
        for cert in certs:
            if cert is not latest and cert.expires > expiry:
                world.certificates.remove(cert)
        latest.expires = expiry
        if latest.issued >= expiry:
            latest.issued = add_months(expiry, -12)
    return {
        "site_code": site.code,
        "skill": skill,
        "activity_code": activity.code,
        "activity_start": start.isoformat(),
        "worker_ids": [worker_id(x.pid) for x in chosen],
        "valid_share_at_start": round(1 - len(chosen) / len(holders), 3),
    }


def _turnover_rise(world: World, p: dict[str, Any]) -> Answer:
    role, trait = str(p["role"]), str(p["trait"])
    as_of = world.config.as_of
    start = as_of - days(365)
    sites = {s.code: s for s in world.sites if trait in s.traits}
    group = [
        x
        for x in world.people
        if x.role == role
        and x.site in sites
        and x.hired < start
        and (x.left is None or x.left >= start)
    ]
    rate = float(world.config.org["annual_leaver_rate"])
    extra = round((float(p["factor"]) - 1) * rate * len(group))
    r = world.r("plant", str(p["id"]))
    stayers = sorted((x for x in group if x.left is None), key=lambda x: x.pid)
    chosen = r.sample(stayers, min(extra, len(stayers)))
    for person in chosen:
        person.left = start + days(r.randint(1, 360))
        world.certificates = [
            c
            for c in world.certificates
            if not (c.pid == person.pid and c.issued > person.left)
        ]
        hired = person.left + days(r.randint(14, 45))
        if hired < as_of:
            add_certificates(world, add_person(world, sites[person.site], role, hired))
    leavers = sum(1 for x in group if x.left is not None and start <= x.left < as_of)
    return {
        "role": role,
        "trait": trait,
        "group_size": len(group),
        "leavers_last_12_months": leavers,
        "extra_leavers": [
            worker_id(x.pid) for x in sorted(chosen, key=lambda x: x.pid)
        ],
    }


def _resource_double_booking(world: World, p: dict[str, Any]) -> Answer:
    site = world.select_site(cast(dict[str, Any], p["site"]))
    spec = cast(dict[str, Any], p["activity"])
    as_of = world.config.as_of
    start = as_of + days(int(spec["starts_in_days"]))
    end = start + days(int(spec["days"]))
    resources = [str(x) for x in cast(list[Any], p["resources"])]
    main = Activity(
        f"ACT-P{len(world.activities) + 1:04d}",
        str(spec["name"]),
        site.code,
        str(spec["kind"]),
        start,
        end,
        list(resources),
    )
    world.activities.append(main)
    others = [s for s in world.open_sites(as_of) if s.code != site.code]
    r = world.r("plant", str(p["id"]))
    competing: list[str] = []
    for i in range(int(p["competing"])):
        other = others[i % len(others)]
        s = start + days(r.randint(5, 40))
        act = Activity(
            f"ACT-P{len(world.activities) + 1:04d}",
            f"{r.choice(['Campaign', 'Shutdown'])} {other.name} {s.year}",
            other.code,
            "Campaign",
            s,
            s + days(r.randint(20, 40)),
            list(resources),
        )
        world.activities.append(act)
        competing.append(act.code)
    return {
        "activity_code": main.code,
        "activity": main.name,
        "resources": resources,
        "competing_activity_codes": competing,
    }


def _split_overspend(world: World, p: dict[str, Any]) -> Answer:
    contract = next(c for c in world.contracts if c.name == p["contract"])
    as_of = world.config.as_of
    year_start = date(as_of.year, 1, 1)
    r = world.r("plant", str(p["id"]))
    ratio = float(p["ratio"])
    for posting in world.postings:
        if posting.contract == contract.number and posting.day >= year_start:
            posting.amount = round(
                contract.annual_budget[posting.cost_centre]
                / 12
                * ratio
                * r.uniform(0.97, 1.03),
                2,
            )
    return {
        "contract_no": contract_no(contract.number),
        "contract": contract.name,
        "cost_centres": contract.cost_centres,
        "year": as_of.year,
        "ratio": ratio,
    }


def _failure_rate_by_trait(world: World, p: dict[str, Any]) -> Answer:
    model, trait = str(p["model"]), str(p["trait"])
    as_of = world.config.as_of
    start = date(as_of.year - int(p["years"]), as_of.month, 1)
    rate = float(world.config.org["annual_failure_rate"]) * (float(p["factor"]) - 1)
    affected = [
        a
        for a in world.assets
        if a.model == model and trait in world.site(a.site).traits
    ]
    if len(affected) < 3:
        raise ValueError("Too few assets of the planted model at sites with the trait.")
    for asset in affected:
        if asset.retired is None:
            begin = max(start, asset.commissioned)
            before = len(world.work_orders)
            schedule_work(world, asset, begin, as_of, rate)
            world.work_orders[before:] = [
                w for w in world.work_orders[before:] if w.corrective
            ]
    return {
        "model_no": model,
        "trait": trait,
        "factor": float(p["factor"]),
        "years": int(p["years"]),
        "since": start.isoformat(),
        "asset_count": len(affected),
    }


def _same_fault_reports(world: World, p: dict[str, Any]) -> Answer:
    model = str(p["model"])
    as_of = world.config.as_of
    r = world.r("plant", str(p["id"]))
    wording = [str(x) for x in cast(list[Any], p["wording"])]
    wanted = int(p["sites"])
    sites = sorted(
        {a.site for a in world.assets if a.model == model and a.retired is None}
    )
    open_codes = [s.code for s in world.open_sites(as_of)]
    for code in open_codes:
        if len(sites) >= wanted:
            break
        if code not in sites:
            site = world.site(code)
            tag = len(world.assets) + 1
            asset = Asset(tag, model, code, max(site.opened, as_of - days(900)))
            world.assets.append(asset)
            schedule_work(
                world,
                asset,
                asset.commissioned,
                as_of,
                float(world.config.org["annual_failure_rate"]),
            )
            sites.append(code)
    chosen = r.sample(sorted(sites), wanted)
    numbers: list[int] = []
    for i, code in enumerate(chosen):
        day = as_of - days(r.randint(5, int(p["within_days"])))
        number = len(world.incidents) + 1
        text = wording[i % len(wording)].format(model=model)
        world.incidents.append(Incident(number, code, day, text, model))
        numbers.append(number)
    return {
        "model_no": model,
        "site_codes": sorted(chosen),
        "incident_numbers": numbers,
    }


PLANTERS: dict[str, Callable[[World, dict[str, Any]], Answer]] = {
    "consumption_runout": _consumption_runout,
    "lead_time_drift": _lead_time_drift,
    "expiry_cluster": _expiry_cluster,
    "turnover_rise": _turnover_rise,
    "resource_double_booking": _resource_double_booking,
    "split_overspend": _split_overspend,
    "failure_rate_by_trait": _failure_rate_by_trait,
    "same_fault_reports": _same_fault_reports,
}

__all__ = ["plant_all", "PLANTERS", "month_start"]
