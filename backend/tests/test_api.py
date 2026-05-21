"""
Integration tests for the FastAPI /api/chat endpoint.
The agent (run_agent) is mocked so no LLM or DB calls are made.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


MOCK_TEXT_REPLY = {
    "role": "assistant",
    "content": "The ice maker assembly PS11752778 costs $94.63.",
    "products": [],
}

MOCK_REPLY_WITH_PRODUCTS = {
    "role": "assistant",
    "content": "Here are some matching parts.",
    "products": [
        {
            "part_number": "PS11752778",
            "title": "Ice Maker Assembly",
            "price": "$94.63",
            "image_url": "https://example.com/img.jpg",
            "url": "https://www.partselect.com/PS11752778.htm",
            "appliance_type": "refrigerator",
        }
    ],
}


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class TestChatEndpointHappyPath:
    def test_basic_user_message(self):
        with patch("app.main.run_agent", return_value=MOCK_TEXT_REPLY):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "How much is PS11752778?"}]},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "assistant"
        assert "PS11752778" in data["content"]
        assert data["products"] == []

    def test_response_includes_product_cards(self):
        with patch("app.main.run_agent", return_value=MOCK_REPLY_WITH_PRODUCTS):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Find ice maker parts"}]},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["products"]) == 1
        product = data["products"][0]
        assert product["part_number"] == "PS11752778"
        assert product["title"] == "Ice Maker Assembly"
        assert product["price"] == "$94.63"

    def test_multi_turn_conversation(self):
        with patch("app.main.run_agent", return_value=MOCK_TEXT_REPLY) as mock_agent:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [
                        {"role": "user", "content": "What is PS11752778?"},
                        {"role": "assistant", "content": "It is an ice maker assembly."},
                        {"role": "user", "content": "How much does it cost?"},
                    ]
                },
            )

        assert response.status_code == 200
        # Agent receives all three messages
        called_messages = mock_agent.call_args[0][0]
        assert len(called_messages) == 3

    def test_session_id_accepted(self):
        with patch("app.main.run_agent", return_value=MOCK_TEXT_REPLY):
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                    "session_id": "abc123",
                },
            )

        assert response.status_code == 200

    def test_compatibility_query(self):
        mock_reply = {
            "role": "assistant",
            "content": "Yes, PS11752778 is compatible with WDT780SAEM1.",
            "products": [],
        }
        with patch("app.main.run_agent", return_value=mock_reply):
            response = client.post(
                "/api/chat",
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": "Is PS11752778 compatible with WDT780SAEM1?",
                        }
                    ]
                },
            )

        assert response.status_code == 200
        assert "compatible" in response.json()["content"].lower()

    def test_troubleshoot_query(self):
        mock_reply = {
            "role": "assistant",
            "content": "Your ice maker may need a new assembly or water inlet valve.",
            "products": [],
        }
        with patch("app.main.run_agent", return_value=mock_reply):
            response = client.post(
                "/api/chat",
                json={
                    "messages": [
                        {"role": "user", "content": "Ice maker on my Whirlpool fridge not working"}
                    ]
                },
            )

        assert response.status_code == 200
        assert "ice maker" in response.json()["content"].lower()


class TestChatEndpointValidation:
    def test_empty_messages_returns_400(self):
        response = client.post("/api/chat", json={"messages": []})
        assert response.status_code == 400

    def test_first_message_not_user_returns_400(self):
        response = client.post(
            "/api/chat",
            json={
                "messages": [
                    {"role": "assistant", "content": "I started first!"},
                    {"role": "user", "content": "Hello"},
                ]
            },
        )
        assert response.status_code == 400

    def test_assistant_only_messages_returns_400(self):
        response = client.post(
            "/api/chat",
            json={"messages": [{"role": "assistant", "content": "Hello"}]},
        )
        assert response.status_code == 400

    def test_whitespace_only_content_filtered(self):
        """Messages with only whitespace should be filtered out."""
        with patch("app.main.run_agent", return_value=MOCK_TEXT_REPLY) as mock_agent:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [
                        {"role": "user", "content": "   "},
                        {"role": "user", "content": "Hello"},
                    ]
                },
            )

        assert response.status_code == 200
        called_messages = mock_agent.call_args[0][0]
        assert all(m["content"].strip() for m in called_messages)

    def test_missing_messages_field_returns_422(self):
        response = client.post("/api/chat", json={"session_id": "abc"})
        assert response.status_code == 422


class TestChatEndpointErrorHandling:
    def test_rate_limit_error_returns_friendly_message(self):
        with patch(
            "app.main.run_agent",
            side_effect=Exception("429 RESOURCE_EXHAUSTED"),
        ):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hello"}]},
            )

        assert response.status_code == 200
        assert "try again" in response.json()["content"].lower()

    def test_unexpected_exception_propagates(self):
        safe_client = TestClient(app, raise_server_exceptions=False)
        with patch(
            "app.main.run_agent",
            side_effect=RuntimeError("unexpected crash"),
        ):
            response = safe_client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hello"}]},
            )

        assert response.status_code == 500
