"""
Unit tests for the four agent tools.
All ChromaDB and embedding calls are mocked — no network or disk I/O required.
"""
import json
from unittest.mock import MagicMock, patch

import pytest


MOCK_PART_META = {
    "part_number": "PS11752778",
    "title": "Ice Maker Assembly",
    "price": "$94.63",
    "image_url": "https://example.com/ps11752778.jpg",
    "appliance_type": "refrigerator",
    "url": "https://www.partselect.com/PS11752778-Whirlpool-W10884390-Ice-Maker-Assembly.htm",
    "compatible_models": json.dumps(["WRS325SDHZ00", "WDT780SAEM1", "WRS571CIHZ00"]),
}

MOCK_PART_META_2 = {
    "part_number": "PS11748892",
    "title": "Dishwasher Door Latch Assembly",
    "price": "$42.19",
    "image_url": "https://example.com/ps11748892.jpg",
    "appliance_type": "dishwasher",
    "url": "https://www.partselect.com/PS11748892.htm",
    "compatible_models": json.dumps(["WDT780SAEM1", "WDTA50SAHZ0"]),
}

MOCK_GUIDE_META = {
    "title": "Ice Maker Not Making Ice",
    "url": "https://www.partselect.com/Repair/Refrigerator/Ice-Maker-Not-Making-Ice/",
    "appliance_type": "refrigerator",
}

MOCK_GUIDE_DOC = (
    "If your refrigerator ice maker is not making ice, the most likely causes are: "
    "a faulty ice maker assembly, a broken water inlet valve, or a clogged water filter. "
    "Start by checking the ice maker switch is in the ON position."
)


class TestSearchParts:
    def _mock_collection(self, metas, distances=None):
        if distances is None:
            distances = [0.1 * (i + 1) for i in range(len(metas))]
        col = MagicMock()
        col.query.return_value = {
            "metadatas": [metas],
            "distances": [distances],
            "documents": [[""] * len(metas)],
        }
        return col

    def test_returns_parts_list(self):
        col = self._mock_collection([MOCK_PART_META])
        with patch("app.tools.search_parts.get_parts_collection", return_value=col):
            from app.tools.search_parts import search_parts
            result = search_parts("ice maker")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["part_number"] == "PS11752778"
        assert result[0]["title"] == "Ice Maker Assembly"
        assert result[0]["price"] == "$94.63"

    def test_deduplicates_same_part_number(self):
        col = self._mock_collection([MOCK_PART_META, MOCK_PART_META], [0.1, 0.15])
        with patch("app.tools.search_parts.get_parts_collection", return_value=col):
            from app.tools.search_parts import search_parts
            result = search_parts("ice maker")

        assert len(result) == 1

    def test_respects_n_results(self):
        metas = [MOCK_PART_META, MOCK_PART_META_2]
        distances = [0.1, 0.2]
        col = self._mock_collection(metas, distances)
        with patch("app.tools.search_parts.get_parts_collection", return_value=col):
            from app.tools.search_parts import search_parts
            result = search_parts("parts", n_results=1)

        assert len(result) == 1

    def test_appliance_type_filter_passed_to_chroma(self):
        col = self._mock_collection([MOCK_PART_META])
        with patch("app.tools.search_parts.get_parts_collection", return_value=col):
            from app.tools.search_parts import search_parts
            search_parts("ice maker", appliance_type="refrigerator")

        call_kwargs = col.query.call_args.kwargs
        assert call_kwargs["where"] == {"appliance_type": "refrigerator"}

    def test_no_filter_when_appliance_type_empty(self):
        col = self._mock_collection([MOCK_PART_META])
        with patch("app.tools.search_parts.get_parts_collection", return_value=col):
            from app.tools.search_parts import search_parts
            search_parts("ice maker", appliance_type="")

        call_kwargs = col.query.call_args.kwargs
        assert call_kwargs["where"] is None

    def test_returns_empty_list_on_exception(self):
        col = MagicMock()
        col.query.side_effect = Exception("DB error")
        with patch("app.tools.search_parts.get_parts_collection", return_value=col):
            from app.tools.search_parts import search_parts
            result = search_parts("ice maker")

        assert result == []

    def test_relevance_score_calculated(self):
        col = self._mock_collection([MOCK_PART_META], [0.25])
        with patch("app.tools.search_parts.get_parts_collection", return_value=col):
            from app.tools.search_parts import search_parts
            result = search_parts("ice maker")

        assert result[0]["relevance_score"] == pytest.approx(0.75, abs=1e-3)


class TestGetPartDetails:
    def _mock_collection(self, metas, ids=None, docs=None):
        col = MagicMock()
        col.get.return_value = {
            "ids": ids if ids is not None else (["id1"] if metas else []),
            "metadatas": metas,
            "documents": docs if docs is not None else ["Installation: turn off power first."],
        }
        return col

    def test_returns_part_dict(self):
        col = self._mock_collection([MOCK_PART_META])
        with patch("app.tools.get_part_details.get_parts_collection", return_value=col):
            from app.tools.get_part_details import get_part_details
            result = get_part_details("PS11752778")

        assert result is not None
        assert result["part_number"] == "PS11752778"
        assert result["title"] == "Ice Maker Assembly"
        assert isinstance(result["compatible_models"], list)
        assert "WRS325SDHZ00" in result["compatible_models"]

    def test_returns_none_when_not_found(self):
        col = self._mock_collection([], ids=[], docs=[])
        with patch("app.tools.get_part_details.get_parts_collection", return_value=col):
            from app.tools.get_part_details import get_part_details
            result = get_part_details("DOESNOTEXIST")

        assert result is None

    def test_returns_none_on_exception(self):
        col = MagicMock()
        col.get.side_effect = Exception("DB error")
        with patch("app.tools.get_part_details.get_parts_collection", return_value=col):
            from app.tools.get_part_details import get_part_details
            result = get_part_details("PS11752778")

        assert result is None

    def test_full_text_joined_from_documents(self):
        col = self._mock_collection(
            [MOCK_PART_META],
            docs=["Part A description.", "Installation steps here."],
        )
        with patch("app.tools.get_part_details.get_parts_collection", return_value=col):
            from app.tools.get_part_details import get_part_details
            result = get_part_details("PS11752778")

        assert "Part A description." in result["full_text"]
        assert "Installation steps here." in result["full_text"]

class TestCheckCompatibility:
    def _mock_collection(self, meta=None):
        col = MagicMock()
        if meta is None:
            col.get.return_value = {"ids": [], "metadatas": []}
        else:
            col.get.return_value = {"ids": ["id1"], "metadatas": [meta]}
        return col

    def test_compatible_exact_match(self):
        col = self._mock_collection(MOCK_PART_META)
        with patch("app.tools.check_compatibility.get_parts_collection", return_value=col):
            from app.tools.check_compatibility import check_compatibility
            result = check_compatibility("WDT780SAEM1", "PS11752778")

        assert result["compatible"] is True
        assert result["part_number"] == "PS11752778"
        assert result["model_number"] == "WDT780SAEM1"

    def test_incompatible_model(self):
        col = self._mock_collection(MOCK_PART_META)
        with patch("app.tools.check_compatibility.get_parts_collection", return_value=col):
            from app.tools.check_compatibility import check_compatibility
            result = check_compatibility("WDF520PADM7", "PS11752778")

        assert result["compatible"] is False

    def test_part_not_found(self):
        col = self._mock_collection(None)
        with patch("app.tools.check_compatibility.get_parts_collection", return_value=col):
            from app.tools.check_compatibility import check_compatibility
            result = check_compatibility("WDT780SAEM1", "UNKNOWN999")

        assert result["compatible"] is False
        assert "not found" in result["note"].lower()

    def test_case_insensitive_model_matching(self):
        col = self._mock_collection(MOCK_PART_META)
        with patch("app.tools.check_compatibility.get_parts_collection", return_value=col):
            from app.tools.check_compatibility import check_compatibility
            result = check_compatibility("wdt780saem1", "PS11752778")

        assert result["compatible"] is True

    def test_model_with_spaces_normalized(self):
        col = self._mock_collection(MOCK_PART_META)
        with patch("app.tools.check_compatibility.get_parts_collection", return_value=col):
            from app.tools.check_compatibility import check_compatibility
            result = check_compatibility("WDT780 SAEM1", "PS11752778")

        assert result["compatible"] is True

    def test_compatible_models_truncated_to_20(self):
        long_meta = dict(MOCK_PART_META)
        long_meta["compatible_models"] = json.dumps([f"MODEL{i:03d}" for i in range(30)])
        col = self._mock_collection(long_meta)
        with patch("app.tools.check_compatibility.get_parts_collection", return_value=col):
            from app.tools.check_compatibility import check_compatibility
            result = check_compatibility("MODEL000", "PS11752778")

        assert len(result["compatible_models"]) <= 20

    def test_returns_note_with_compatibility_status(self):
        col = self._mock_collection(MOCK_PART_META)
        with patch("app.tools.check_compatibility.get_parts_collection", return_value=col):
            from app.tools.check_compatibility import check_compatibility
            result = check_compatibility("WDT780SAEM1", "PS11752778")

        assert "compatible" in result["note"].lower()
        assert "PS11752778" in result["note"]

class TestTroubleshoot:
    def _mock_collection(self, docs, metas, distances=None):
        if distances is None:
            distances = [0.1 * (i + 1) for i in range(len(docs))]
        col = MagicMock()
        col.query.return_value = {
            "documents": [docs],
            "metadatas": [metas],
            "distances": [distances],
        }
        return col

    def test_returns_guide_list(self):
        col = self._mock_collection([MOCK_GUIDE_DOC], [MOCK_GUIDE_META])
        with patch("app.tools.troubleshoot.get_guides_collection", return_value=col):
            from app.tools.troubleshoot import troubleshoot
            result = troubleshoot("ice maker not making ice")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["title"] == "Ice Maker Not Making Ice"
        assert "ice maker" in result[0]["excerpt"].lower()

    def test_excerpt_truncated_to_600_chars(self):
        long_doc = "x" * 800
        col = self._mock_collection([long_doc], [MOCK_GUIDE_META])
        with patch("app.tools.troubleshoot.get_guides_collection", return_value=col):
            from app.tools.troubleshoot import troubleshoot
            result = troubleshoot("ice maker not working")

        assert len(result[0]["excerpt"]) == 600

    def test_appliance_type_filter_dishwasher(self):
        col = self._mock_collection([MOCK_GUIDE_DOC], [MOCK_GUIDE_META])
        with patch("app.tools.troubleshoot.get_guides_collection", return_value=col):
            from app.tools.troubleshoot import troubleshoot
            troubleshoot("not draining", appliance_type="dishwasher")

        call_kwargs = col.query.call_args.kwargs
        assert call_kwargs["where"] == {"appliance_type": "dishwasher"}

    def test_no_filter_when_appliance_type_empty(self):
        col = self._mock_collection([MOCK_GUIDE_DOC], [MOCK_GUIDE_META])
        with patch("app.tools.troubleshoot.get_guides_collection", return_value=col):
            from app.tools.troubleshoot import troubleshoot
            troubleshoot("not draining", appliance_type="")

        call_kwargs = col.query.call_args.kwargs
        assert call_kwargs["where"] is None

    def test_returns_empty_list_on_exception(self):
        col = MagicMock()
        col.query.side_effect = Exception("DB error")
        with patch("app.tools.troubleshoot.get_guides_collection", return_value=col):
            from app.tools.troubleshoot import troubleshoot
            result = troubleshoot("ice maker broken")

        assert result == []

    def test_relevance_score_from_distance(self):
        col = self._mock_collection([MOCK_GUIDE_DOC], [MOCK_GUIDE_META], [0.3])
        with patch("app.tools.troubleshoot.get_guides_collection", return_value=col):
            from app.tools.troubleshoot import troubleshoot
            result = troubleshoot("ice maker not working")

        assert result[0]["relevance_score"] == pytest.approx(0.7, abs=1e-3)
