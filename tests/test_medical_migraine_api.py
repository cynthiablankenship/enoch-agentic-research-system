from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from enoch_control_plane.config import GateConfig
from enoch_control_plane.control_plane.router import create_control_plane_router


TOKEN = "test-token"


def _config(tmp_path: Path) -> GateConfig:
    project_root = tmp_path / "projects"
    project_root.mkdir(parents=True, exist_ok=True)
    return GateConfig(
        state_dir=str(tmp_path / "state"),
        project_root=str(project_root),
        dispatch_script_path=str(tmp_path / "dispatch.sh"),
        control_api_bearer_token=TOKEN,
        completion_callback_url="http://example.invalid/callback",
        completion_callback_token="unused",
    )


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    config = _config(tmp_path)

    def require(auth: str | None) -> None:
        if auth != f"Bearer {TOKEN}":
            raise HTTPException(status_code=401, detail="bad token")

    app.include_router(create_control_plane_router(config, require))
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def _record() -> dict[str, str]:
    return {
        "source_id": "pmid-1",
        "source_kind": "pubmed",
        "title": "Migraine sleep timing",
        "abstract": "Migraine headache literature discusses sleep disruption and circadian timing.",
        "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
        "year": "2026",
    }


def test_medical_sample_report_requires_auth_and_returns_cards(tmp_path: Path) -> None:
    client = _client(tmp_path)

    assert client.get("/control/api/medical/migraine/sample-report").status_code == 401

    response = client.get("/control/api/medical/migraine/sample-report", headers=_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "medical_enoch_migraine_workbench_v1"
    assert data["card_count"] >= 1
    assert data["cards"][0]["review_status"] == "needs_review"


def test_medical_fetch_writes_records_under_state_dir(tmp_path: Path) -> None:
    client = _client(tmp_path)

    with patch("scripts.fetch_pubmed_migraine.fetch_pubmed_records", return_value=[_record()]) as fetch:
        response = client.post(
            "/control/api/medical/migraine/fetch",
            headers=_headers(),
            json={"query": "migraine sleep", "limit": 500, "email": "research@example.com"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["record_count"] == 1
    assert data["limit"] == 200
    assert data["records_path"].startswith("migraine_records_")
    assert (tmp_path / "state" / "medical_workbench" / data["records_path"]).exists()
    fetch.assert_called_once()


def test_medical_generate_writes_report_and_review_updates_card(tmp_path: Path) -> None:
    client = _client(tmp_path)

    generated = client.post(
        "/control/api/medical/migraine/generate",
        headers=_headers(),
        json={"records": [_record()], "requested_by": "pytest"},
    )

    assert generated.status_code == 200
    report = generated.json()
    assert report["report_path"].startswith("migraine_report_")
    assert report["cards"][0]["review_status"] == "needs_review"
    card_id = report["cards"][0]["card_id"]

    reviewed = client.post(
        f"/control/api/medical/migraine/review/{card_id}",
        headers=_headers(),
        json={
            "report_path": report["report_path"],
            "review_status": "approved_for_research_planning",
            "reviewed_by": "researcher",
            "review_notes": "Good demo card.",
        },
    )

    assert reviewed.status_code == 200
    body = reviewed.json()
    assert body["review_status"] == "approved_for_research_planning"
    updated = body["report"]["cards"][0]
    assert updated["review_status"] == "approved_for_research_planning"
    assert updated["reviewed_by"] == "researcher"
    assert updated["review_notes"] == "Good demo card."


def test_medical_review_rejects_invalid_status(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/control/api/medical/migraine/review/missing",
        headers=_headers(),
        json={"review_status": "diagnose_patient"},
    )

    assert response.status_code == 400


def test_control_dashboard_contains_medical_research_page(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.get("/control/dashboard")

    assert response.status_code == 200
    assert "Medical Research" in response.text
    assert "/control/api/medical/migraine/sample-report" in response.text
