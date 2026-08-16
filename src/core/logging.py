"""
Structured JSON logging.

Why JSON instead of plain text logs: this is the explainability backbone of
the whole system. Every agent decision (research summary, score + reasoning,
draft, guardrail verdict) gets logged as structured data, not just printed —
so it can be queried, filtered by lead_id, and fed into the eval harness
(Milestone 8) instead of being grep'd out of a text file.

`request_id_var` is a contextvar (not a global/thread-local dict) set by
RequestIDMiddleware (src/api/middleware.py) at the top of every HTTP
request and automatically stamped onto every log line emitted during that
request — including inside the orchestrator's four agent calls, which run
synchronously deep in the call stack. This is what lets you grep one
request_id and see the entire Research -> Score -> Draft -> Guardrail
trace for a single lead, across every agent's log lines, without threading
a request_id parameter through every function signature in the codebase.
contextvars propagate correctly across the threadpool FastAPI uses for
sync route handlers (anyio copies context into worker threads), so this
works even though the pipeline itself is synchronous code.
"""
import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "message": record.getMessage(),
        }
        # Extra structured fields passed via logger.info(msg, extra={...})
        for key, value in record.__dict__.items():
            if key in ("args", "msg", "levelname", "levelno", "pathname", "filename",
                       "module", "exc_info", "exc_text", "stack_info", "lineno",
                       "funcName", "created", "msecs", "relativeCreated", "thread",
                       "threadName", "processName", "process", "name"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(log_level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root.handlers.clear()
    root.addHandler(handler)


def get_agent_logger(agent_name: str) -> logging.Logger:
    """
    Every agent gets its own named logger (e.g. 'agent.research') so log
    output can be filtered per-agent, which matters once the orchestrator
    is running four agents concurrently per lead.
    """
    return logging.getLogger(f"agent.{agent_name}")
