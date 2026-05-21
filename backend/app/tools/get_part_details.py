import json
from typing import Optional

from app.db import get_parts_collection


def get_part_details(part_number: str) -> Optional[dict]:
    collection = get_parts_collection()
    try:
        results = collection.get(
            where={"part_number": part_number},
            include=["documents", "metadatas"],
        )
    except Exception:
        return None

    if not results["ids"]:
        return None

    meta = results["metadatas"][0]
    return {
        "part_number": part_number,
        "title": meta.get("title", ""),
        "price": meta.get("price", ""),
        "image_url": meta.get("image_url", ""),
        "appliance_type": meta.get("appliance_type", ""),
        "url": meta.get("url", ""),
        "compatible_models": json.loads(meta.get("compatible_models", "[]")),
        "full_text": " ".join(results["documents"]),
    }
