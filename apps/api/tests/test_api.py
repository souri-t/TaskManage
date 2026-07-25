from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from review_hub.database import SessionLocal
from review_hub.main import app
from review_hub.models import Finding, FindingOccurrence


client = TestClient(app)


def payload(code_context: str = "value = lookup(key)\nreturn value.name") -> dict:
    return {
        "repository": "example/repository",
        "base_branch": "main",
        "target_branch": "feature/example",
        "commit_sha": "0123456789abcdef",
        "reviewed_file_count": 1,
        "review_source": "Codex",
        "detected_at": "2026-07-25T12:00:00+09:00",
        "findings": [
            {
                "title": "Null dereference",
                "description": "A **problem** exists.",
                "remediation": "Check the result.",
                "severity": "High",
                "category": "Correctness",
                "rule_id": "CORRECTNESS-NULL-001",
                "file_path": "src/example.py",
                "symbol": "Example.run",
                "line_number": 42,
                "code_context": code_context,
                "code_language": "python",
                "ai_confidence": 90,
            }
        ],
    }


def test_health_and_ready():
    assert client.get("/healthz").json() == {"status": "ok"}
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["database"] == "sqlite"


def test_dry_run_has_no_database_writes():
    response = client.post("/api/v1/reconciliations/dry-run", json=payload())
    assert response.status_code == 200
    assert response.json()["results"][0]["action"] == "would_create"
    with SessionLocal() as session:
        assert session.scalar(select(func.count(Finding.id))) == 0


def test_apply_is_idempotent_and_reopens_fixed():
    headers = {"Idempotency-Key": "run-1"}
    first = client.post("/api/v1/reconciliations", json=payload(), headers=headers)
    assert first.status_code == 200
    assert first.json()["summary"]["created"] == 1
    second = client.post("/api/v1/reconciliations", json=payload(), headers=headers)
    assert second.json() == first.json()

    finding_id = first.json()["results"][0]["finding_id"]
    with SessionLocal() as session, session.begin():
        finding = session.get(Finding, finding_id)
        assert finding is not None
        finding.status = "修正済み"

    changed_payload = payload()
    changed_payload["commit_sha"] = "fedcba9876543210"
    changed_payload["detected_at"] = "2026-07-26T12:00:00+09:00"
    reopened = client.post(
        "/api/v1/reconciliations",
        json=changed_payload,
        headers={"Idempotency-Key": "run-2"},
    )
    assert reopened.json()["results"][0]["action"] == "reopened"
    with SessionLocal() as session:
        finding = session.get(Finding, finding_id)
        assert finding.status == "確認中"
        assert finding.recurrence_count == 1
        assert session.scalar(select(func.count(FindingOccurrence.id))) == 2


def test_human_candidate_suppresses_automation():
    manual = {
        **payload()["findings"][0],
        "repository": "example/repository",
        "detected_at": "2026-07-25T10:00:00+09:00",
    }
    manual_response = client.post("/api/v1/findings", json=manual)
    assert manual_response.status_code == 201
    automated = client.post(
        "/api/v1/reconciliations",
        json=payload("different context"),
        headers={"Idempotency-Key": "run-human"},
    )
    assert automated.json()["results"][0]["action"] == "suppressed_human"


def test_repository_scopes_duplicate_candidates():
    manual = {
        **payload()["findings"][0],
        "repository": "other/repository",
        "detected_at": "2026-07-25T10:00:00+09:00",
    }
    assert client.post("/api/v1/findings", json=manual).status_code == 201
    automated = client.post(
        "/api/v1/reconciliations",
        json=payload("different context"),
        headers={"Idempotency-Key": "run-repo-scope"},
    )
    assert automated.json()["results"][0]["action"] == "created"


def test_transition_and_duplicate_cycle_protection():
    first = client.post("/api/v1/findings", json={
        **payload()["findings"][0],
        "repository": "repo",
    }).json()
    second_input = {
        **payload()["findings"][0],
        "repository": "repo",
        "title": "Other",
        "rule_id": "R2",
        "symbol": "Other.run",
    }
    second = client.post("/api/v1/findings", json=second_input).json()

    transition = client.post(
        f"/api/v1/findings/{first['id']}/transitions",
        json={"status": "確認中", "reason": "triage"},
    )
    assert transition.status_code == 200
    assert transition.json()["status"] == "確認中"

    duplicate = client.post(
        f"/api/v1/findings/{first['id']}/duplicate",
        json={"target_finding_id": second["id"], "reason": "same problem"},
    )
    assert duplicate.status_code == 200
    cycle = client.post(
        f"/api/v1/findings/{second['id']}/duplicate",
        json={"target_finding_id": first["id"], "reason": "cycle"},
    )
    assert cycle.status_code == 409


def test_concurrent_apply_creates_one_finding():
    def apply(index: int):
        return client.post(
            "/api/v1/reconciliations",
            json=payload(),
            headers={"Idempotency-Key": f"concurrent-{index}"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(apply, range(2)))
    assert all(response.status_code == 200 for response in responses)
    with SessionLocal() as session:
        assert session.scalar(select(func.count(Finding.id))) == 1


def test_apply_stores_only_redacted_bounded_code_excerpt():
    secret = "password = supersecret\n"
    long_context = secret + "\n".join(f"line-{index}" for index in range(80))
    response = client.post(
        "/api/v1/reconciliations",
        json=payload(long_context),
        headers={"Idempotency-Key": "bounded-code"},
    )
    assert response.status_code == 200
    finding_id = response.json()["results"][0]["finding_id"]
    with SessionLocal() as session:
        finding = session.get(Finding, finding_id)
        assert finding is not None
        assert "supersecret" not in finding.code_excerpt
        assert "[REDACTED]" in finding.code_excerpt
        assert len(finding.code_excerpt.splitlines()) <= 50
        assert len(finding.code_excerpt.encode("utf-8")) <= 16 * 1024
