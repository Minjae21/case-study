"""
Unit tests for the Gemini agent loop (agent.py).
The Gemini SDK client and all tool functions are fully mocked.
"""
import json
from unittest.mock import MagicMock, patch, call

import pytest


def _make_text_response(text: str):
    """Fake Gemini response with only a text part (no function calls)."""
    part = MagicMock()
    part.text = text
    part.function_call = None
    candidate = MagicMock()
    candidate.content.parts = [part]
    response = MagicMock()
    response.candidates = [candidate]
    return response


def _make_tool_call_response(tool_name: str, tool_args: dict):
    """Fake Gemini response requesting one function call."""
    fn_call = MagicMock()
    fn_call.name = tool_name
    fn_call.args = tool_args

    part = MagicMock()
    part.function_call = fn_call
    # Make hasattr(part, 'text') falsy so text extraction skips it
    part.text = ""

    candidate = MagicMock()
    candidate.content.parts = [part]
    response = MagicMock()
    response.candidates = [candidate]
    return response


@pytest.fixture(autouse=True)
def mock_gemini_client():
    """Replace genai.Client with a MagicMock for every test in this module."""
    with patch("app.agent._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        yield mock_client


def _setup_chat(mock_client, responses: list):
    """
    Wire mock_client.chats.create() to return a chat whose send_message()
    returns responses in order.
    """
    chat = MagicMock()
    chat.send_message.side_effect = responses
    mock_client.chats.create.return_value = chat
    return chat


class TestAgentNoTools:
    def test_returns_text_response(self, mock_gemini_client):
        text = "The ice maker assembly PS11752778 costs $94.63."
        _setup_chat(mock_gemini_client, [_make_text_response(text)])

        from app.agent import run_agent
        result = run_agent([{"role": "user", "content": "How much does PS11752778 cost?"}])

        assert result["role"] == "assistant"
        assert result["content"] == text
        assert result["products"] == []

    def test_multi_turn_history_passed(self, mock_gemini_client):
        _setup_chat(mock_gemini_client, [_make_text_response("Sure!")])

        from app.agent import run_agent
        messages = [
            {"role": "user", "content": "What is the ice maker part number?"},
            {"role": "assistant", "content": "It is PS11752778."},
            {"role": "user", "content": "How much does it cost?"},
        ]
        run_agent(messages)

        # History passed to chats.create should contain first two turns
        create_kwargs = mock_gemini_client.chats.create.call_args.kwargs
        history = create_kwargs["history"]
        assert len(history) == 2

    def test_returns_empty_products_without_tool_calls(self, mock_gemini_client):
        _setup_chat(mock_gemini_client, [_make_text_response("Hello!")])

        from app.agent import run_agent
        result = run_agent([{"role": "user", "content": "Hi"}])

        assert result["products"] == []


class TestAgentWithToolCalls:
    def test_search_parts_tool_invoked(self, mock_gemini_client):
        tool_response = _make_tool_call_response(
            "search_parts", {"query": "ice maker", "appliance_type": "refrigerator"}
        )
        final_response = _make_text_response("I found some ice maker parts for you.")
        _setup_chat(mock_gemini_client, [tool_response, final_response])

        mock_parts = [
            {
                "part_number": "PS11752778",
                "title": "Ice Maker Assembly",
                "price": "$94.63",
                "image_url": "https://example.com/img.jpg",
                "url": "https://www.partselect.com/PS11752778.htm",
                "appliance_type": "refrigerator",
            }
        ]

        with patch("app.agent.search_parts", return_value=mock_parts) as mock_fn:
            from app.agent import run_agent
            result = run_agent([{"role": "user", "content": "Find ice maker parts"}])

        mock_fn.assert_called_once_with(
            query="ice maker",
            appliance_type="refrigerator",
            n_results=5,
        )
        assert result["content"] == "I found some ice maker parts for you."
        assert len(result["products"]) == 1
        assert result["products"][0]["part_number"] == "PS11752778"

    def test_get_part_details_tool_invoked(self, mock_gemini_client):
        tool_response = _make_tool_call_response(
            "get_part_details", {"part_number": "PS11752778"}
        )
        final_response = _make_text_response("Here are the details for PS11752778.")
        _setup_chat(mock_gemini_client, [tool_response, final_response])

        mock_detail = {
            "part_number": "PS11752778",
            "title": "Ice Maker Assembly",
            "price": "$94.63",
            "image_url": "https://example.com/img.jpg",
            "url": "https://www.partselect.com/PS11752778.htm",
            "appliance_type": "refrigerator",
            "compatible_models": ["WRS325SDHZ00"],
            "full_text": "Installation: unplug refrigerator first.",
        }

        with patch("app.agent.get_part_details", return_value=mock_detail):
            from app.agent import run_agent
            result = run_agent([{"role": "user", "content": "Tell me about PS11752778"}])

        assert "PS11752778" in result["content"]
        assert result["products"][0]["part_number"] == "PS11752778"

    def test_check_compatibility_tool_invoked(self, mock_gemini_client):
        tool_response = _make_tool_call_response(
            "check_compatibility",
            {"model_number": "WDT780SAEM1", "part_number": "PS11752778"},
        )
        final_response = _make_text_response("Yes, PS11752778 is compatible with WDT780SAEM1.")
        _setup_chat(mock_gemini_client, [tool_response, final_response])

        mock_compat = {
            "compatible": True,
            "part_number": "PS11752778",
            "model_number": "WDT780SAEM1",
            "compatible_models": ["WDT780SAEM1"],
            "note": "Part PS11752778 is compatible with model WDT780SAEM1.",
        }

        with patch("app.agent.check_compatibility", return_value=mock_compat):
            from app.agent import run_agent
            result = run_agent([
                {"role": "user", "content": "Is PS11752778 compatible with WDT780SAEM1?"}
            ])

        assert "compatible" in result["content"].lower()

    def test_troubleshoot_tool_invoked(self, mock_gemini_client):
        tool_response = _make_tool_call_response(
            "troubleshoot",
            {"symptom": "ice maker not making ice", "appliance_type": "refrigerator"},
        )
        final_response = _make_text_response(
            "The most likely cause is a faulty ice maker assembly."
        )
        _setup_chat(mock_gemini_client, [tool_response, final_response])

        mock_guides = [
            {
                "title": "Ice Maker Not Making Ice",
                "url": "https://www.partselect.com/repair/ice-maker/",
                "appliance_type": "refrigerator",
                "excerpt": "Check the ice maker switch first.",
                "relevance_score": 0.9,
            }
        ]

        with patch("app.agent.troubleshoot", return_value=mock_guides):
            from app.agent import run_agent
            result = run_agent([
                {"role": "user", "content": "My ice maker is not making ice"}
            ])

        assert "ice maker" in result["content"].lower()

    def test_part_not_found_returns_error_in_content(self, mock_gemini_client):
        tool_response = _make_tool_call_response(
            "get_part_details", {"part_number": "DOESNOTEXIST"}
        )
        final_response = _make_text_response(
            "I could not find any part with that number."
        )
        _setup_chat(mock_gemini_client, [tool_response, final_response])

        with patch("app.agent.get_part_details", return_value=None):
            from app.agent import run_agent
            result = run_agent([{"role": "user", "content": "Tell me about DOESNOTEXIST"}])

        assert result["role"] == "assistant"
        # Agent should still return a reply (error handled gracefully)
        assert len(result["content"]) > 0


class TestAgentToolLoop:
    def test_two_tool_rounds_before_final_text(self, mock_gemini_client):
        round1 = _make_tool_call_response("search_parts", {"query": "water inlet valve"})
        round2 = _make_tool_call_response(
            "get_part_details", {"part_number": "PS11748892"}
        )
        final = _make_text_response("Here is everything about the water inlet valve.")
        _setup_chat(mock_gemini_client, [round1, round2, final])

        mock_part = {
            "part_number": "PS11748892",
            "title": "Water Inlet Valve",
            "price": "$55.00",
            "image_url": "",
            "url": "",
            "appliance_type": "refrigerator",
        }

        with (
            patch("app.agent.search_parts", return_value=[mock_part]),
            patch("app.agent.get_part_details", return_value={**mock_part, "full_text": ""}),
        ):
            from app.agent import run_agent
            result = run_agent([{"role": "user", "content": "Tell me about water inlet valves"}])

        assert result["content"] == "Here is everything about the water inlet valve."

    def test_max_tool_rounds_returns_last_text(self, mock_gemini_client):
        """When every response is a tool call, stop at MAX_TOOL_ROUNDS and return last text."""
        from app import agent as agent_module
        tool_resp = _make_tool_call_response("search_parts", {"query": "part"})
        # Return a text-less tool-call response for all rounds
        _setup_chat(mock_gemini_client, [tool_resp] * (agent_module.MAX_TOOL_ROUNDS + 1))

        with patch("app.agent.search_parts", return_value=[]):
            result = agent_module.run_agent([{"role": "user", "content": "find parts"}])

        # Should not raise; should return a dict
        assert "role" in result
        assert result["role"] == "assistant"

class TestProductExtraction:
    """Test _extract_products in isolation."""

    def test_extracts_from_list_result(self):
        from app.agent import _extract_products
        tool_results = [
            {
                "tool": "search_parts",
                "data": [
                    {
                        "part_number": "PS11752778",
                        "title": "Ice Maker Assembly",
                        "price": "$94.63",
                        "image_url": "",
                        "url": "",
                        "appliance_type": "refrigerator",
                    }
                ],
            }
        ]
        products = _extract_products(tool_results)
        assert len(products) == 1
        assert products[0]["part_number"] == "PS11752778"

    def test_extracts_from_dict_result(self):
        from app.agent import _extract_products
        tool_results = [
            {
                "tool": "get_part_details",
                "data": {
                    "part_number": "PS11748892",
                    "title": "Door Latch",
                    "price": "$42.00",
                    "image_url": "",
                    "url": "",
                    "appliance_type": "dishwasher",
                },
            }
        ]
        products = _extract_products(tool_results)
        assert len(products) == 1
        assert products[0]["part_number"] == "PS11748892"

    def test_deduplicates_across_rounds(self):
        from app.agent import _extract_products
        part = {
            "part_number": "PS11752778",
            "title": "Ice Maker Assembly",
            "price": "$94.63",
            "image_url": "",
            "url": "",
            "appliance_type": "refrigerator",
        }
        tool_results = [
            {"tool": "search_parts", "data": [part]},
            {"tool": "get_part_details", "data": part},
        ]
        products = _extract_products(tool_results)
        assert len(products) == 1

    def test_skips_items_without_title(self):
        from app.agent import _extract_products
        tool_results = [
            {
                "tool": "search_parts",
                "data": [{"part_number": "PS11752778", "title": ""}],
            }
        ]
        products = _extract_products(tool_results)
        assert len(products) == 0

    def test_empty_input_returns_empty_list(self):
        from app.agent import _extract_products
        assert _extract_products([]) == []
