"""
API tests for the /leads endpoints. `run_pipeline` is mocked at the
lead_service import site — these tests verify the API/DB/auth wiring, not
agent behavior (that's covered by tests/agents/test_orchestrator.py and
each agent's own tests). No real Gemini API calls happen here.
"""
from unittest.mock import patch

from src.agents.orchestrator import AgentInvocationRecord, PipelineResult
from src.db.models import LeadStatus
from src.schemas.lead import DraftOutput, GuardrailVerdict, ResearchOutput, ScoreOutput, Signal


def _fake_ready_pipeline_result(company_name: str) -> PipelineResult:
    return PipelineResult(
        company_name=company_name,
        domain=None,
        status=LeadStatus.READY,
        research_output=ResearchOutput(
            summary="Acme AI raised a Series A and markets an AI copilot.",
            signals=[
                Signal(label="recent_funding", detail="$12M Series A", source_url="https://x")
            ],
            sources=["https://x"],
        ),
        score_output=ScoreOutput(score=85, confidence=0.8, reasoning="Strong fit."),
        draft_output=DraftOutput(channel="email", message="Congrats on your Series A!"),
        guardrail_output=GuardrailVerdict(approved=True, unsupported_claims=[], notes="ok"),
        invocation_log=[
            AgentInvocationRecord(
                agent_name="research", model="openai/gpt-oss-20b", latency_ms=100,
                success=True, error=None, attempt=1,
            ),
        ],
        total_latency_ms=500,
    )


def test_create_lead_requires_auth(client):
    response = client.post("/leads", json={"company_name": "Acme AI"})

    assert response.status_code == 401


@patch("src.services.lead_service.run_pipeline")
def test_create_lead_happy_path(mock_run_pipeline, client, auth_headers):
    mock_run_pipeline.return_value = _fake_ready_pipeline_result("Acme AI")

    response = client.post("/leads", json={"company_name": "Acme AI"}, headers=auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["company_name"] == "Acme AI"
    assert body["status"] == "ready"
    assert body["profile"]["summary"].startswith("Acme AI")
    assert body["score"]["score"] == 85
    assert body["draft"]["guardrail_approved"] is True


@patch("src.services.lead_service.run_pipeline")
def test_get_lead_returns_created_lead(mock_run_pipeline, client, auth_headers):
    mock_run_pipeline.return_value = _fake_ready_pipeline_result("Acme AI")
    create_response = client.post(
        "/leads", json={"company_name": "Acme AI"}, headers=auth_headers
    )
    lead_id = create_response.json()["id"]

    response = client.get(f"/leads/{lead_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == lead_id


def test_get_lead_not_found(client, auth_headers):
    response = client.get(
        "/leads/00000000-0000-0000-0000-000000000000", headers=auth_headers
    )

    assert response.status_code == 404


@patch("src.services.lead_service.run_pipeline")
def test_list_leads_returns_created_leads(mock_run_pipeline, client, auth_headers):
    mock_run_pipeline.side_effect = [
        _fake_ready_pipeline_result("Acme AI"),
        _fake_ready_pipeline_result("Beta AI"),
    ]
    client.post("/leads", json={"company_name": "Acme AI"}, headers=auth_headers)
    client.post("/leads", json={"company_name": "Beta AI"}, headers=auth_headers)

    response = client.get("/leads", headers=auth_headers)

    assert response.status_code == 200
    names = {lead["company_name"] for lead in response.json()}
    assert names == {"Acme AI", "Beta AI"}


@patch("src.services.lead_service.run_pipeline")
def test_list_leads_respects_limit_and_skip(mock_run_pipeline, client, auth_headers):
    mock_run_pipeline.side_effect = [
        _fake_ready_pipeline_result("Alpha"),
        _fake_ready_pipeline_result("Beta"),
        _fake_ready_pipeline_result("Gamma"),
    ]
    for name in ("Alpha", "Beta", "Gamma"):
        client.post("/leads", json={"company_name": name}, headers=auth_headers)

    limited = client.get("/leads?limit=2", headers=auth_headers)
    assert len(limited.json()) == 2

    skipped = client.get("/leads?skip=2&limit=2", headers=auth_headers)
    assert len(skipped.json()) == 1  # only 1 left after skipping 2 of 3


def test_get_lead_rejects_malformed_uuid(client, auth_headers):
    response = client.get("/leads/not-a-valid-uuid", headers=auth_headers)

    assert response.status_code == 422  # FastAPI validates the path param before the handler runs


def test_protected_route_rejects_garbage_bearer_token(client):
    response = client.get("/leads", headers={"Authorization": "Bearer not.a.real.token"})

    assert response.status_code == 401


@patch("src.services.lead_service.run_pipeline")
def test_get_lead_logs_returns_invocation_trail(mock_run_pipeline, client, auth_headers):
    mock_run_pipeline.return_value = _fake_ready_pipeline_result("Acme AI")
    create_response = client.post(
        "/leads", json={"company_name": "Acme AI"}, headers=auth_headers
    )
    lead_id = create_response.json()["id"]

    response = client.get(f"/leads/{lead_id}/logs", headers=auth_headers)

    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 1
    assert logs[0]["agent_name"] == "research"
    assert logs[0]["model_used"] == "openai/gpt-oss-20b"
    assert logs[0]["success"] is True


def test_get_lead_logs_not_found(client, auth_headers):
    response = client.get(
        "/leads/00000000-0000-0000-0000-000000000000/logs", headers=auth_headers
    )

    assert response.status_code == 404


def test_get_lead_logs_requires_auth(client):
    response = client.get("/leads/00000000-0000-0000-0000-000000000000/logs")

    assert response.status_code == 401


def test_protected_route_rejects_token_for_deleted_or_unknown_user(client):
    # A validly-signed token, but for a user that was never registered (or
    # was deleted after the token was issued) — exercises the "token is
    # valid but the user lookup fails" branch in get_current_user.
    from src.core.security import create_access_token

    token = create_access_token(subject="ghost@example.com")

    response = client.get("/leads", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
