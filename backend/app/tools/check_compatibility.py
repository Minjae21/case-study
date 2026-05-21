import json
import re

from app.db import get_parts_collection


def _normalize(model: str) -> str:
    return re.sub(r"[\s\-]", "", model).upper()


def check_compatibility(model_number: str, part_number: str) -> dict:
    collection = get_parts_collection()
    try:
        results = collection.get(
            where={"part_number": part_number},
            include=["metadatas"],
        )
    except Exception:
        return {
            "compatible": False,
            "part_number": part_number,
            "model_number": model_number,
            "compatible_models": [],
            "note": "Part not found in database.",
        }

    if not results["ids"]:
        return {
            "compatible": False,
            "part_number": part_number,
            "model_number": model_number,
            "compatible_models": [],
            "note": "Part not found in database.",
        }

    meta = results["metadatas"][0]
    compatible_models: list[str] = json.loads(meta.get("compatible_models", "[]"))
    norm_query = _normalize(model_number)

    compatible = any(_normalize(m) == norm_query for m in compatible_models)
    if not compatible:
        # Partial prefix match handles model variants (e.g. "WRS325" matches "WRS325SDHZ00")
        compatible = any(
            _normalize(m).startswith(norm_query) or norm_query.startswith(_normalize(m))
            for m in compatible_models
        )

    return {
        "compatible": compatible,
        "part_number": part_number,
        "model_number": model_number,
        "compatible_models": compatible_models[:20],
        "part_title": meta.get("title", ""),
        "note": (
            f"Part {part_number} is {'compatible' if compatible else 'NOT listed as compatible'} "
            f"with model {model_number}."
        ),
    }
