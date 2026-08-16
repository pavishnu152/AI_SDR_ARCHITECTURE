"""Tests for the structured JSON log formatter and request_id propagation."""
import json
import logging

from src.core.logging import JSONFormatter, get_agent_logger, request_id_var


def _format_record(logger_name: str, level: int, msg: str, exc_info=None) -> dict:
    record = logging.LogRecord(
        name=logger_name, level=level, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=exc_info,
    )
    return json.loads(JSONFormatter().format(record))


def test_format_includes_core_fields():
    payload = _format_record("agent.research", logging.INFO, "research started")

    assert payload["level"] == "INFO"
    assert payload["logger"] == "agent.research"
    assert payload["message"] == "research started"
    assert "timestamp" in payload


def test_format_includes_current_request_id():
    token = request_id_var.set("test-request-id-abc")
    try:
        payload = _format_record("agent.scoring", logging.INFO, "scoring started")
    finally:
        request_id_var.reset(token)

    assert payload["request_id"] == "test-request-id-abc"


def test_format_defaults_request_id_when_not_set():
    payload = _format_record("agent.scoring", logging.INFO, "no request context")

    assert payload["request_id"] == "-"


def test_format_includes_exception_traceback_when_present():
    try:
        raise ValueError("something broke")
    except ValueError:
        import sys

        payload = _format_record(
            "agent.guardrail", logging.ERROR, "guardrail crashed", exc_info=sys.exc_info()
        )

    assert "exception" in payload
    assert "ValueError" in payload["exception"]
    assert "something broke" in payload["exception"]


def test_get_agent_logger_namespaces_by_agent_name():
    logger = get_agent_logger("drafting")

    assert logger.name == "agent.drafting"
