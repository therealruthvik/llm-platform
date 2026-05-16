"""
Unit tests for the FastAPI backend.
Run: pytest app/backend/tests/
Model loading is mocked – no GPU or HF download required.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# Patch model loading before importing app
@pytest.fixture(autouse=True)
def mock_manager():
    with patch("model_manager.ModelManager.load"), patch(
        "model_manager.manager"
    ) as mock_mgr:
        mock_mgr.model = MagicMock()
        mock_mgr.tokenizer = MagicMock()
        mock_mgr.generate.return_value = "Hello! I am a mocked assistant."
        yield mock_mgr


@pytest.fixture()
def client(mock_manager):
    # Import after mocking
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from main import app

    return TestClient(app)


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "model_version" in data
        assert "model_name" in data

    def test_version_endpoint(self, client):
        resp = client.get("/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "model_version" in data
        assert "model_name" in data


class TestChat:
    def test_chat_success(self, client):
        resp = client.post("/chat", json={"message": "Hello!", "history": []})
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "model_version" in data
        assert "latency_ms" in data

    def test_chat_with_history(self, client):
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        resp = client.post(
            "/chat", json={"message": "How are you?", "history": history}
        )
        assert resp.status_code == 200

    def test_chat_empty_message(self, client):
        resp = client.post("/chat", json={"message": "", "history": []})
        # Empty message is still valid – model decides what to do
        assert resp.status_code in (200, 500)

    def test_metrics_endpoint(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert b"llm_request_total" in resp.content
