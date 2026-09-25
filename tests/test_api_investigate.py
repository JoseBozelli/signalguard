from fastapi.testclient import TestClient

from signalguard.api.app import app, get_investigate_fn
from signalguard.schemas.finding import Finding

client = TestClient(app)


def _fake_finding():
    return Finding(
        source="ai_pipeline",
        tier="tier2",
        defect_type="prerequisite",
        affected_event_ids=["e1"],
        evidence="test evidence",
        reasoning_category="documented_rule",
        recommended_action="review",
    )


def test_investigate_returns_finding_when_pipeline_finds_violation():
    app.dependency_overrides[get_investigate_fn] = lambda: (lambda candidate, all_records: _fake_finding())
    try:
        response = client.post(
            "/qc/investigate",
            json={
                "candidate": {"event_type": "session.completed", "ref_id": "r1", "event_id": "e1"},
                "all_records": [],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["finding"] is not None
        assert body["finding"]["defect_type"] == "prerequisite"
    finally:
        app.dependency_overrides.clear()


def test_investigate_returns_null_finding_when_no_violation():
    app.dependency_overrides[get_investigate_fn] = lambda: (lambda candidate, all_records: None)
    try:
        response = client.post(
            "/qc/investigate",
            json={"candidate": {"event_type": "session.completed"}, "all_records": []},
        )
        assert response.status_code == 200
        assert response.json()["finding"] is None
    finally:
        app.dependency_overrides.clear()


def test_investigate_pipeline_error_returns_502():
    def _raise(candidate, all_records):
        raise RuntimeError("boom")

    app.dependency_overrides[get_investigate_fn] = lambda: _raise
    try:
        response = client.post("/qc/investigate", json={"candidate": {}, "all_records": []})
        assert response.status_code == 502
    finally:
        app.dependency_overrides.clear()


def test_investigate_missing_fields_is_validation_error():
    response = client.post("/qc/investigate", json={})
    assert response.status_code == 422