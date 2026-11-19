from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from spark.sim.build import build
from spark.sim.common import ArchiveWriter, load_org
from spark.sim.export import export_world
from spark.sim.recover import CHECKS, Archive
from spark.sim.world import build_world

SIM_DIR = Path(__file__).resolve().parents[1] / "spark" / "sim"


ORGS = ("corvane", "blue_team")


@pytest.mark.parametrize("org", ORGS)
def test_same_seed_gives_identical_files(tmp_path: Path, org: str) -> None:
    first = build(org, "small", tmp_path / "one")
    second = build(org, "small", tmp_path / "two")
    assert first["checksum"] == second["checksum"]
    assert first["files"] == second["files"] > 100


@pytest.mark.parametrize("org", ORGS)
def test_every_planted_problem_is_recovered_with_no_extras(
    tmp_path: Path, org: str
) -> None:
    report = build(org, "small", tmp_path)
    results = report["results"]
    assert len(results) == len(load_org(org, "small").problems)
    assert [r["id"] for r in results if not r["recovered"]] == []
    assert [r["id"] for r in results if r["extras"]] == []


@pytest.mark.parametrize("org", ORGS)
def test_checks_flag_nothing_when_no_problem_is_planted(
    tmp_path: Path, org: str
) -> None:
    config = load_org(org, "small")
    clean = replace(config, problems=[])
    world = build_world(clean)
    export_world(world, ArchiveWriter(tmp_path))
    archive = Archive(tmp_path, config.as_of)
    for problem in config.problems:
        check = dict(problem["check"])
        for field in ("trait", "years"):
            if field in problem:
                check[field] = problem[field]
        flagged = CHECKS[str(problem["kind"])](archive, check)
        assert flagged == [], f"{problem['id']} flagged {flagged}"


def test_answer_key_is_outside_the_archive(tmp_path: Path) -> None:
    report = build("corvane", "small", tmp_path)
    archive = Path(report["archive"])
    key = Path(report["answer_key"])
    assert key.is_file()
    assert archive not in key.parents


def test_generator_code_has_no_organisation_or_sector_words() -> None:
    banned = re.compile(
        r"corvane|blue team|aldmark|brigade|barracks|defence|military|"
        r"\bmining\b|\bmine\b|pipeline|\btruck\b|\bhaul\b|\bcrane\b|\bpump\b|\blogistics\b|\bsupply\b",
        re.I,
    )
    hits = [
        f"{path.name}:{number}"
        for path in sorted(SIM_DIR.glob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if banned.search(line)
    ]
    assert hits == []


def test_both_organisations_use_the_same_problem_kinds() -> None:
    kinds = {org: {p["kind"] for p in load_org(org, "small").problems} for org in ORGS}
    assert kinds["corvane"] == kinds["blue_team"]
