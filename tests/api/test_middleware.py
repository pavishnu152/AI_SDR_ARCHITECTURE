"""Tests for the request-ID middleware."""
import uuid


def test_response_includes_generated_request_id(client):
    response = client.get("/health")

    assert "X-Request-ID" in response.headers
    # Must be a valid UUID when we generated it ourselves.
    uuid.UUID(response.headers["X-Request-ID"])


def test_response_echoes_inbound_request_id(client):
    inbound_id = "test-fixed-request-id-123"

    response = client.get("/health", headers={"X-Request-ID": inbound_id})

    assert response.headers["X-Request-ID"] == inbound_id
