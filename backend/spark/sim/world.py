"""Builds one organisation's 20-year history in memory, from its YAML.

The world holds clean facts. ``plant.py`` adds the planted problems and
``export.py`` writes the facts out as messy source-system files.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date
from typing import Any, cast

from spark.sim.common import (
    OrgConfig,
    add_months,
    days,
    month_end,
    months_between,
    rng,
    weighted,
)


@dataclass
class Country:
    name: str
    code: str
    currency: str
    opened: int
    acquired: bool


@dataclass
class Site:
    code: str
    name: str
    country: Country
    division: str
    kind: str
    opened: date
    traits: set[str] = field(default_factory=lambda: set[str]())
    closed: date | None = None
    old_name: str | None = None
    protected: bool = False


@dataclass
class Person:
    pid: int
    first: str
    last: str
    site: str
    role: str
    hired: date
    left: date | None = None


@dataclass
class Certificate:
    pid: int
    skill: str
    issued: date
    expires: date


@dataclass
class Asset:
    tag: int
    model: str
    site: str
    commissioned: date
    retired: date | None = None


@dataclass
class WorkOrder:
    tag: int
    raised: date
    corrective: bool
    cost: float


@dataclass
class StockSeries:
    site: str
    item: str
    supplier: str
    issues: dict[date, int]
    receipts: dict[date, int]
    month_end_stock: dict[date, int]


@dataclass
class Order:
    number: int
    supplier: str
    item: str
    site: str
    ordered: date
    promised: date
    received: date | None
    quantity: int
    unit_price: float


@dataclass
class Activity:
    code: str
    name: str
    site: str
    kind: str
    start: date
    end: date
    resources: list[str] = field(default_factory=lambda: list[str]())


@dataclass
class Contract:
    number: int
    name: str
    supplier: str
    cost_centres: list[str]
    annual_budget: dict[str, float]


@dataclass
class Posting:
    day: date
    cost_centre: str
    account: str
    amount: float
    currency: str
    contract: int | None = None


@dataclass
class Incident:
    number: int
    site: str
    day: date
    text: str
    model: str | None = None


@dataclass
class World:
    config: OrgConfig
    countries: list[Country]
    sites: list[Site]
    people: list[Person] = field(default_factory=lambda: list[Person]())
    certificates: list[Certificate] = field(default_factory=lambda: list[Certificate]())
    assets: list[Asset] = field(default_factory=lambda: list[Asset]())
    work_orders: list[WorkOrder] = field(default_factory=lambda: list[WorkOrder]())
    items: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    suppliers: list[str] = field(default_factory=lambda: list[str]())
    stock: list[StockSeries] = field(default_factory=lambda: list[StockSeries]())
    orders: list[Order] = field(default_factory=lambda: list[Order]())
    activities: list[Activity] = field(default_factory=lambda: list[Activity]())
    contracts: list[Contract] = field(default_factory=lambda: list[Contract]())
    postings: list[Posting] = field(default_factory=lambda: list[Posting]())
    incidents: list[Incident] = field(default_factory=lambda: list[Incident]())

    @property
    def seed(self) -> int:
        return int(self.config.org["seed"])

    def r(self, *parts: str) -> random.Random:
        return rng(self.seed, self.config.size, *parts)

    def site(self, code: str) -> Site:
        for site in self.sites:
            if site.code == code:
                return site
        raise KeyError(code)

    def open_sites(self, on: date) -> list[Site]:
        return [
            s
            for s in self.sites
            if s.opened <= on and (s.closed is None or s.closed > on)
        ]

    def select_site(self, selector: dict[str, Any]) -> Site:
        matches = [
            s
            for s in self.sites
            if s.closed is None
            and ("division" not in selector or s.division == selector["division"])
            and ("trait" not in selector or selector["trait"] in s.traits)
        ]
        index = int(selector.get("index", 0))
        if index >= len(matches):
            raise ValueError(f"No site matches {selector}.")
        return matches[index]

    def holders_of(self, skill: str) -> set[str]:
        roles = cast(list[dict[str, Any]], self.config.org["roles"])
        return {str(r["title"]) for r in roles if skill in r.get("skills", [])}


# ----------------------------------------------------------------------------
# Building


def build_world(config: OrgConfig) -> World:
    org = config.org
    counts = config.counts
    countries = [
        Country(
            name=str(c["name"]),
            code=str(c["code"]),
            currency=str(c["currency"]),
            opened=int(c["opened"]),
            acquired=bool(c.get("acquired", False)),
        )
        for c in cast(list[dict[str, Any]], org["countries"])[: counts["countries"]]
    ]
    world = World(config=config, countries=countries, sites=[])
    _build_sites(world)
    _ensure_problem_sites(world)
    _close_sites(world)
    _build_people(world)
    _build_assets(world)
    _build_stock(world)
    _build_activities(world)
    _build_finance(world)
    _build_incidents(world)
    return world


def _build_sites(world: World) -> None:
    org = world.config.org
    counts = world.config.counts
    r = world.r("sites")
    divisions = cast(list[dict[str, Any]], org["divisions"])
    prefixes = list(cast(list[str], org["place_prefixes"]))
    words = list(cast(list[str], org["place_words"]))
    names = [f"{p} {w}" for p in prefixes for w in words]
    r.shuffle(names)
    latest_open = add_months(world.config.as_of, -60)
    for index in range(counts["sites"]):
        country = world.countries[index % len(world.countries)]
        division = divisions[(index // len(world.countries)) % len(divisions)]
        earliest = max(
            world.config.start,
            date(country.opened, 1, 1),
            date(int(division["since"]), 1, 1),
        )
        span = max(1, (latest_open - earliest).days)
        opened = min(earliest + days(r.randint(0, min(span, 900))), latest_open)
        world.sites.append(
            Site(
                code=f"{country.code}{index + 1:03d}",
                name=names[index % len(names)],
                country=country,
                division=str(division["name"]),
                kind=r.choice(cast(list[str], division["kinds"])),
                opened=opened,
            )
        )
    for trait, share in cast(dict[str, float], org["traits"]).items():
        order = list(world.sites)
        world.r("trait", trait).shuffle(order)
        for site in order[: round(float(share) * len(order))]:
            site.traits.add(trait)
    restructure = world.config.when("restructure")
    renamed = list(world.sites)
    world.r("renames").shuffle(renamed)
    share = float(world.config.timeline["rename_share"])
    spare = names[len(world.sites) :]
    for i, site in enumerate(renamed[: round(share * len(renamed))]):
        if site.opened < restructure and i < len(spare):
            site.old_name, site.name = site.name, spare[i]


def _ensure_problem_sites(world: World) -> None:
    """Make sure every problem's site selector has a match; protect it."""
    for problem in world.config.problems:
        selector = problem.get("site")
        if not isinstance(selector, dict):
            continue
        sel = cast(dict[str, Any], selector)
        candidates = [
            s
            for s in world.sites
            if "division" not in sel or s.division == sel["division"]
        ]
        if not candidates:
            raise ValueError(f"No site in division for problem {problem['id']}.")
        needed = int(sel.get("index", 0)) + 1
        if "trait" in sel:
            matching = [s for s in candidates if sel["trait"] in s.traits]
            for site in candidates:
                if len(matching) >= needed:
                    break
                if site not in matching:
                    site.traits.add(str(sel["trait"]))
                    matching.append(site)
        world.select_site(sel).protected = True


def _close_sites(world: World) -> None:
    share = float(world.config.timeline["closed_site_share"])
    order = [s for s in world.sites if not s.protected]
    world.r("closures").shuffle(order)
    for site in order[: round(share * len(world.sites))]:
        earliest = site.opened + days(5 * 365)
        latest = world.config.as_of - days(365)
        if earliest < latest:
            site.closed = earliest + days(
                world.r("close", site.code).randint(0, (latest - earliest).days)
            )


def _role_counts(world: World, headcount: int) -> list[tuple[str, int]]:
    roles = cast(list[dict[str, Any]], world.config.org["roles"])
    total = sum(float(r["weight"]) for r in roles)
    raw = [(str(r["title"]), headcount * float(r["weight"]) / total) for r in roles]
    counts = [(title, int(value)) for title, value in raw]
    remainder = headcount - sum(c for _, c in counts)
    by_fraction = sorted(
        range(len(raw)), key=lambda i: raw[i][1] - counts[i][1], reverse=True
    )
    for i in by_fraction[:remainder]:
        counts[i] = (counts[i][0], counts[i][1] + 1)
    return counts


def add_person(world: World, site: Site, role: str, hired: date) -> Person:
    """Hire one person and give them the certificates their role needs."""
    org = world.config.org
    pid = len(world.people) + 1
    r = world.r("person", str(pid))
    person = Person(
        pid,
        r.choice(cast(list[str], org["first_names"])),
        r.choice(cast(list[str], org["last_names"])),
        site.code,
        role,
        hired,
    )
    world.people.append(person)
    return person


def _build_people(world: World) -> None:
    rate = float(world.config.org["annual_leaver_rate"])
    as_of = world.config.as_of
    per_site = max(
        8, world.config.counts["people"] // max(1, len(world.open_sites(as_of)))
    )
    by_site: dict[str, list[Person]] = {s.code: [] for s in world.sites}
    for site in world.sites:
        for role, n in _role_counts(world, per_site):
            for _ in range(n):
                hired = site.opened + days(
                    world.r("hire", site.code, role).randint(0, 120)
                )
                by_site[site.code].append(add_person(world, site, role, hired))
    for year in range(world.config.start.year, as_of.year + 1):
        year_start = date(year, 1, 1)
        year_end = min(date(year, 12, 31), as_of - days(1))
        fraction = ((year_end - year_start).days + 1) / 365
        for site in world.sites:
            active = [
                p for p in by_site[site.code] if p.left is None and p.hired <= year_end
            ]
            if site.closed is not None and year_start <= site.closed <= year_end:
                for person in active:
                    person.left = site.closed
                continue
            if site.closed is not None and site.closed < year_start:
                continue
            groups: dict[str, list[Person]] = {}
            for person in active:
                groups.setdefault(person.role, []).append(person)
            for role in sorted(groups):
                members = sorted(groups[role], key=lambda p: p.pid)
                r = world.r("leave", site.code, role, str(year))
                quota = round(rate * fraction * len(members) + r.random() - 0.5)
                for leaver in r.sample(members, min(max(0, quota), len(members))):
                    span = (year_end - max(year_start, leaver.hired)).days
                    if span <= 0:
                        continue
                    leaver.left = max(year_start, leaver.hired) + days(
                        r.randint(1, span)
                    )
                    start = leaver.left + days(r.randint(14, 60))
                    if start < as_of:
                        by_site[site.code].append(add_person(world, site, role, start))
    for person in world.people:
        add_certificates(world, person)


def add_certificates(world: World, person: Person) -> None:
    roles = {
        str(r["title"]): r
        for r in cast(list[dict[str, Any]], world.config.org["roles"])
    }
    validity = {
        str(s["name"]): int(s["validity_months"])
        for s in cast(list[dict[str, Any]], world.config.org["skills"])
    }
    as_of = world.config.as_of
    end = person.left or as_of
    for skill in cast(list[str], roles[person.role].get("skills", [])):
        r = world.r("cert", str(person.pid), skill)
        issued = person.hired - days(r.randint(0, 20))
        expires = add_months(issued, validity[skill])
        while True:
            expires = add_months(issued, validity[skill])
            world.certificates.append(Certificate(person.pid, skill, issued, expires))
            if expires >= end:
                break
            issued = expires - days(r.randint(0, 45))
        if person.left is None and expires <= as_of + days(240):
            # Renewed ahead of time: active people hold at least eight months
            # of validity unless a planted problem says otherwise.
            issued = as_of - days(r.randint(5, 60))
            world.certificates.append(
                Certificate(
                    person.pid, skill, issued, add_months(issued, validity[skill])
                )
            )


def _build_assets(world: World) -> None:
    org = world.config.org
    models = cast(list[dict[str, Any]], org["asset_models"])
    rate = float(org["annual_failure_rate"])
    as_of = world.config.as_of
    r = world.r("assets")
    for tag in range(1, world.config.counts["assets"] + 1):
        model = weighted(r, models)
        site = world.sites[(tag - 1) % len(world.sites)]
        commissioned = site.opened + days(r.randint(0, 400))
        if commissioned >= as_of:
            commissioned = site.opened
        world.assets.append(
            Asset(tag, str(model["model_no"]), site.code, commissioned, site.closed)
        )
    for asset in world.assets:
        schedule_work(world, asset, asset.commissioned, asset.retired or as_of, rate)


def schedule_work(
    world: World, asset: Asset, start: date, end: date, rate: float
) -> None:
    r = world.r("work", str(asset.tag), start.isoformat())
    interval = 365 / rate
    current = start + days(r.randint(0, int(interval)))
    while current < end:
        world.work_orders.append(
            WorkOrder(asset.tag, current, True, round(r.uniform(800, 6000), 2))
        )
        current = current + days(int(interval * r.uniform(0.85, 1.15)))
    service = start + days(180)
    while service < end:
        world.work_orders.append(
            WorkOrder(asset.tag, service, False, round(r.uniform(300, 1500), 2))
        )
        service = service + days(182)


def _build_stock(world: World) -> None:
    org = world.config.org
    counts = world.config.counts
    listed = cast(list[dict[str, Any]], org["items"])
    items: list[dict[str, Any]] = []
    for i in range(counts["items"]):
        base = listed[i % len(listed)]
        variant = i // len(listed)
        name = str(base["name"]) + (f" type {variant + 1}" if variant else "")
        items.append({**base, "name": name})
    world.items = [{"code": f"IT{i + 1:05d}", **item} for i, item in enumerate(items)]
    names = list(cast(list[str], org["supplier_names"]))
    world.suppliers = [
        names[i % len(names)] + ("" if i < len(names) else f" {i // len(names) + 1}")
        for i in range(counts["suppliers"])
    ]
    supplier_of = {
        item["code"]: world.suppliers[i % len(world.suppliers)]
        for i, item in enumerate(world.items)
    }
    base_lead = {s: world.r("lead", s).randint(7, 21) for s in world.suppliers}
    as_of = world.config.as_of
    order_no = 100000
    required: dict[str, set[str]] = {}
    for problem in world.config.problems:
        if isinstance(problem.get("site"), dict) and "item" in problem:
            code = world.select_site(cast(dict[str, Any], problem["site"])).code
            required.setdefault(code, set()).add(str(problem["item"]))
    for site in world.sites:
        r = world.r("stocked", site.code)
        chosen = r.sample(world.items, min(counts["items_per_site"], len(world.items)))
        for name in sorted(required.get(site.code, set())):
            item_match = [i for i in world.items if i["name"] == name]
            if not item_match:
                raise ValueError(f"Planted item {name!r} is not in the item list.")
            if item_match[0] not in chosen:
                chosen[-1] = item_match[0]
        for item in sorted(chosen, key=lambda i: str(i["code"])):
            sr = world.r("stock", site.code, str(item["code"]))
            use = sr.randint(4, 60) * (10 if item["unit"] == "litre" else 1)
            end = site.closed or as_of
            series = StockSeries(
                site.code, str(item["code"]), supplier_of[str(item["code"])], {}, {}, {}
            )
            stock = use * 6
            for month in months_between(site.opened, end - days(1)):
                issued = max(0, round(use * sr.uniform(0.85, 1.15)))
                issued = min(issued, stock)
                series.issues[month] = issued
                stock -= issued
                if stock < use * 4:
                    quantity = use * 6
                    lead = base_lead[series.supplier] + sr.randint(-2, 2)
                    received = month_end(month)
                    ordered = received - days(lead)
                    if received < as_of:
                        series.receipts[month] = (
                            series.receipts.get(month, 0) + quantity
                        )
                        stock += quantity
                        order_no += 1
                        world.orders.append(
                            Order(
                                order_no,
                                series.supplier,
                                series.item,
                                site.code,
                                ordered,
                                ordered + days(base_lead[series.supplier]),
                                received,
                                quantity,
                                round(sr.uniform(5, 400), 2),
                            )
                        )
                series.month_end_stock[month] = stock
            world.stock.append(series)


def _build_activities(world: World) -> None:
    org = world.config.org
    as_of = world.config.as_of
    kinds = cast(list[str], org["activity_kinds"])
    resources = [*cast(list[str], org["crews"]), *cast(list[str], org["equipment"])]
    booked: dict[str, list[tuple[date, date]]] = {res: [] for res in resources}
    r = world.r("activities")
    total = world.config.counts["activities"]
    for index in range(total):
        site = world.sites[r.randrange(len(world.sites))]
        future = index >= total * 0.85
        if future:
            start = as_of + days(r.randint(10, 170))
        else:
            lo = site.opened
            hi = (site.closed or as_of) - days(90)
            if hi <= lo:
                continue
            start = lo + days(r.randint(0, (hi - lo).days))
        if site.closed is not None and start >= site.closed:
            continue
        end = start + days(r.randint(3, 60))
        kind = r.choice(kinds)
        activity = Activity(
            f"ACT-{index + 1:05d}",
            f"{kind} {site.name} {start.year}",
            site.code,
            kind,
            start,
            end,
        )
        for res in r.sample(resources, 2):
            if all(end < s or start > e for s, e in booked[res]):
                booked[res].append((start, end))
                activity.resources.append(res)
        world.activities.append(activity)


ACCOUNTS = ("Labour", "Materials", "Contract services", "Fuel", "Travel")


def _build_finance(world: World) -> None:
    org = world.config.org
    as_of = world.config.as_of
    multi_from = int(world.config.timeline["multi_currency_from"])
    for site in world.sites:
        r = world.r("ledger", site.code)
        scale = {
            a: r.uniform(5_000, 80_000) for a in ACCOUNTS if a != "Contract services"
        }
        for month in months_between(site.opened, (site.closed or as_of) - days(1)):
            currency = site.country.currency if month.year >= multi_from else "AUD"
            for account, base in scale.items():
                world.postings.append(
                    Posting(
                        month_end(month),
                        f"{site.code}-{ACCOUNTS.index(account) + 1}",
                        account,
                        round(base * r.uniform(0.8, 1.2), 2),
                        currency,
                    )
                )
    per = int(org["cost_centres_per_contract"])
    erp = world.config.when("erp_cutover")
    for number, name in enumerate(cast(list[str], org["contracts"]), start=1):
        r = world.r("contract", name)
        open_sites = world.open_sites(as_of)
        centres = [
            f"{s.code}-3" for s in r.sample(open_sites, min(per, len(open_sites)))
        ]
        contract = Contract(
            number,
            name,
            r.choice(world.suppliers),
            centres,
            {cc: round(r.uniform(120_000, 600_000), -3) for cc in centres},
        )
        world.contracts.append(contract)
        for cc in centres:
            for month in months_between(
                min(erp, add_months(as_of, -60)), as_of - days(1)
            ):
                ratio = r.uniform(0.85, 1.08)
                world.postings.append(
                    Posting(
                        month_end(month),
                        cc,
                        "Contract services",
                        round(contract.annual_budget[cc] / 12 * ratio, 2),
                        "AUD",
                        number,
                    )
                )


def model_sites_near(world: World, model: str, day: date) -> set[str]:
    return {
        i.site
        for i in world.incidents
        if i.model == model and abs((i.day - day).days) <= 365
    }


def _build_incidents(world: World) -> None:
    org = world.config.org
    as_of = world.config.as_of
    templates = cast(list[str], org["incident_templates"])
    plain = [t for t in templates if "{model}" not in t]
    surge = cast(dict[str, Any], world.config.timeline["document_surge"])
    r = world.r("incidents")
    total = world.config.counts["incidents"]
    for number in range(1, total + 1):
        site = world.sites[r.randrange(len(world.sites))]
        end = site.closed or as_of
        span = max(1, (end - site.opened).days - 1)
        day = site.opened + days(r.randint(0, span))
        if r.random() < 0.3:
            surge_day = date(int(surge["year"]), 1, 1) + days(r.randint(0, 364))
            if site.opened <= surge_day < end:
                day = surge_day
        template = r.choice(templates)
        at_site = sorted({a.model for a in world.assets if a.site == site.code})
        model: str | None = None
        if "{model}" in template:
            if at_site:
                model = r.choice(at_site)
                nearby = model_sites_near(world, model, day)
                if site.code not in nearby and len(nearby) >= 2:
                    model = None
            if model is None:
                template = r.choice(plain)
        item = str(r.choice(world.items)["name"])
        text = template.format(
            site=site.name, model=model or "", item=item, crew="", date=day.isoformat()
        )
        world.incidents.append(Incident(number, site.code, day, text, model))


# ----------------------------------------------------------------------------
# Identifiers as the source systems show them. One place, used by the
# exporter, the planter and the answer key.


def worker_id(pid: int) -> str:
    return f"W-{pid:06d}"


def legacy_employee_no(pid: int) -> str:
    return f"E{pid:05d}"


def supplier_code(world: World, name: str) -> str:
    return f"SUP{world.suppliers.index(name) + 1:03d}"


def contract_no(number: int) -> str:
    return f"CON{number:04d}"


def legacy_contract_ref(number: int) -> str:
    return f"C-{number:04d}"


def maintenance_system(world: World, site: Site) -> str:
    """Which maintenance system holds a site's assets (from the YAML)."""
    systems = cast(list[dict[str, Any]], world.config.org["maintenance_systems"])
    for system in systems:
        holds = system["holds"]
        if holds == "default":
            continue
        rule = cast(dict[str, Any], holds)
        if rule.get("acquired") and site.country.acquired:
            return str(system["name"])
        if "division" in rule and rule["division"] == site.division:
            return str(system["name"])
    return next(str(s["name"]) for s in systems if s["holds"] == "default")
