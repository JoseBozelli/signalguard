from fastapi.testclient import TestClient

from signalguard.api.app import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_baseline_qc_with_valid_records_returns_no_findings():
    response = client.post(
        "/qc/baseline",
        json={
            "records": [
                {"event_id": "e1", "account_id": "a1", "event_type": "task.required"},
                {"event_id": "e2", "account_id": "a1", "event_type": "task.completed"},
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["findings"] == []


def test_baseline_qc_detects_missing_account_id():
    response = client.post(
        "/qc/baseline",
        json={
            "records": [
                {"event_id": "e1", "account_id": None, "event_type": "task.required"},
            ]
        },
    )
    assert response.status_code == 200
    findings = response.json()["findings"]
    assert len(findings) == 1
    assert findings[0]["defect_type"] == "missing_account_id"
    assert findings[0]["source"] == "deterministic_qc"


def test_baseline_qc_detects_duplicate_event_id():
    response = client.post(
        "/qc/baseline",
        json={
            "records": [
                {"event_id": "dup", "account_id": "a1", "event_type": "task.required"},
                {"event_id": "dup", "account_id": "a1", "event_type": "task.completed"},
            ]
        },
    )
    assert response.status_code == 200
    findings = response.json()["findings"]
    assert len(findings) == 1
    assert findings[0]["defect_type"] == "duplicate_event_id"


def test_baseline_qc_empty_records_returns_empty_findings():
    response = client.post("/qc/baseline", json={"records": []})
    assert response.status_code == 200
    assert response.json()["findings"] == []


def test_baseline_qc_missing_records_field_is_a_validation_error():
    response = client.post("/qc/baseline", json={})
    assert response.status_code == 422