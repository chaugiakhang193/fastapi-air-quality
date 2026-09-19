import logging

from fastapi.testclient import TestClient

from app.main import app


def test_request_id_middleware_wraps_outermost(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="airq.middleware"):
        with TestClient(app) as client:
            client.get("/health")

    messages = [record.message for record in caplog.records]
    # RequestIdMiddleware is added last in app/main.py, so it wraps outermost:
    # its "enter" is the very first log line, its "exit" the very last —
    # the onion nesting pattern.
    assert "request-id:enter" in messages[0]
    assert "request-id:exit" in messages[-1]
    assert "timing:enter" in messages[1]
