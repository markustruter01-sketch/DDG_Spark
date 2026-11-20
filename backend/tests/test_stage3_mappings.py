from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from spark.api.auth import ensure_admin_account, require_session
from spark.api.ingest import router
from spark.db.owner import owner_engine
from spark.db.platform import platform_engine
from spark.ingest.registry import register_archive
from spark.model.schema import build_metadata
from spark.sim.build import build


@pytest.fixture(scope="module")
def admin_id() -> str:
    ensure_admin_account()
    with platform_engine().connect() as connection:
        return str(
            connection.execute(
                text("SELECT id FROM auth_user WHERE role = 'administrator' LIMIT 1")
            ).scalar_one()
        )


@pytest.fixture(scope="module")
def archive(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    report = build("corvane", "small", tmp_path_factory.mktemp("corvane"))
    name = f"test-{uuid4().hex[:8]}"
    return Path(report["archive"]), name


def client_for(user_id: str, role: str = "administrator") -> TestClient:
    app = FastAPI()
    app.include_router(router)
    user: dict[str, Any] = {
        "user_id": user_id,
        "email": "test@spark.local",
        "role": role,
        "clearance": "restricted",
    }
    app.dependency_overrides[require_session] = lambda: user
    return TestClient(app)


def _files(client: TestClient, archive: str) -> list[dict[str, Any]]:
    response = client.get("/api/ingest/files")
    assert response.status_code == 200
    return [f for f in response.json() if f["archive"] == archive]


def test_register_stores_every_file_once_with_a_proposal(
    archive: tuple[Path, str], admin_id: str
) -> None:
    root, name = archive
    total = sum(1 for p in root.rglob("*") if p.is_file())
    assert register_archive(root, name) == {"files": total, "added": total}
    assert register_archive(root, name) == {"files": total, "added": 0}
    files = _files(client_for(admin_id), name)
    assert len(files) == total
    assert all(f["mapping"]["status"] == "proposed" for f in files)
    assert all(f["mapping"]["version"] == 1 for f in files)


def test_approving_the_proposal_keeps_who_proposed_it(
    archive: tuple[Path, str], admin_id: str
) -> None:
    client = client_for(admin_id)
    target = next(
        f for f in _files(client, archive[1]) if f["path"] == "inventory/items.csv"
    )
    proposal = target["mapping"]
    response = client.post(
        f"/api/ingest/files/{target['id']}/mapping",
        json={k: proposal[k] for k in ("entity", "fields", "refs")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mapping"]["status"] == "approved"
    assert body["mapping"]["proposed_by"] == "rules"
    assert [v["status"] for v in body["history"]] == ["superseded", "approved"]


def test_a_correction_is_a_new_version_and_only_one_is_approved(
    archive: tuple[Path, str], admin_id: str
) -> None:
    client = client_for(admin_id)
    target = next(
        f for f in _files(client, archive[1]) if f["path"] == "inventory/items.csv"
    )
    fields = dict(target["mapping"]["fields"])
    fields.popitem()
    response = client.post(
        f"/api/ingest/files/{target['id']}/mapping",
        json={"entity": "item", "fields": fields, "refs": target["mapping"]["refs"]},
    )
    assert response.status_code == 200, response.text
    history = response.json()["history"]
    assert [v["status"] for v in history] == ["superseded", "superseded", "approved"]
    assert history[-1]["proposed_by"] == "person"
    assert history[-1]["version"] == 3


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"entity": "nonsense"}, "not an entity"),
        ({"entity": "item", "fields": {"no_such_field": "x"}}, "Not fields of item"),
        ({"entity": "item", "refs": {"no_such_entity": "x"}}, "Not entities"),
        ({"entity": "item", "fields": {"name": "no such column"}}, "Not columns"),
    ],
)
def test_bad_mappings_are_refused(
    archive: tuple[Path, str], admin_id: str, body: dict[str, Any], message: str
) -> None:
    client = client_for(admin_id)
    target = next(
        f for f in _files(client, archive[1]) if f["path"] == "inventory/items.csv"
    )
    response = client.post(f"/api/ingest/files/{target['id']}/mapping", json=body)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_only_an_administrator_approves(
    archive: tuple[Path, str], admin_id: str
) -> None:
    client = client_for(admin_id, role="analyst")
    target = _files(client, archive[1])[0]
    response = client.post(
        f"/api/ingest/files/{target['id']}/mapping", json={"entity": "item"}
    )
    assert response.status_code == 403


def test_unknown_file_is_404(admin_id: str) -> None:
    response = client_for(admin_id).get(f"/api/ingest/files/{UUID(int=0)}")
    assert response.status_code == 404


def test_the_database_allows_one_approved_mapping_per_file(
    archive: tuple[Path, str], admin_id: str
) -> None:
    client = client_for(admin_id)
    target = next(
        f for f in _files(client, archive[1]) if f["path"] == "inventory/items.csv"
    )
    with pytest.raises(Exception, match="uq_ingest_mapping_one_approved"):
        with owner_engine().begin() as connection:
            connection.execute(
                text(
                    "UPDATE ingest_mapping SET status = 'approved' "
                    "WHERE file_id = :id AND version = 1"
                ),
                {"id": target["id"]},
            )


@pytest.mark.parametrize("table", ["ingest_file", "ingest_mapping"])
def test_live_schema_matches_the_migration(table: str) -> None:
    in_database = {c["name"] for c in inspect(owner_engine()).get_columns(table)}
    assert in_database == set(build_metadata().tables[table].columns.keys())


def test_one_approval_can_cover_a_folder_of_identical_files(
    archive: tuple[Path, str], admin_id: str
) -> None:
    client = client_for(admin_id)
    folder = "inventory/emailed_counts/"
    in_folder = [f for f in _files(client, archive[1]) if f["path"].startswith(folder)]
    assert len(in_folder) > 1
    first = in_folder[0]
    detail = client.get(f"/api/ingest/files/{first['id']}").json()
    assert detail["same_folder_files"] == len(in_folder) - 1
    response = client.post(
        f"/api/ingest/files/{first['id']}/mapping",
        json={
            **{k: first["mapping"][k] for k in ("entity", "fields", "refs")},
            "same_folder": True,
        },
    )
    assert response.status_code == 200, response.text
    after = [f for f in _files(client, archive[1]) if f["path"].startswith(folder)]
    assert all(f["mapping"]["status"] == "approved" for f in after)
    others = [f for f in _files(client, archive[1]) if not f["path"].startswith(folder)]
    assert any(f["mapping"]["status"] == "proposed" for f in others)


def test_loader_fields_cannot_be_mapped(
    archive: tuple[Path, str], admin_id: str
) -> None:
    client = client_for(admin_id)
    target = next(
        f for f in _files(client, archive[1]) if f["path"] == "inventory/items.csv"
    )
    response = client.post(
        f"/api/ingest/files/{target['id']}/mapping",
        json={"entity": "item", "fields": {"confidence": "unit"}},
    )
    assert response.status_code == 422
