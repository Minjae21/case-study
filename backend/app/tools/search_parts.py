import json

from app.db import get_parts_collection


def search_parts(query: str, appliance_type: str = "", n_results: int = 5) -> list[dict]:
    collection = get_parts_collection()
    where = {"appliance_type": appliance_type} if appliance_type in ("refrigerator", "dishwasher") else None

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results * 2, 20),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    seen: set[str] = set()
    parts: list[dict] = []
    for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
        pn = meta.get("part_number", "")
        if pn in seen:
            continue
        seen.add(pn)
        parts.append({
            "part_number": pn,
            "title": meta.get("title", ""),
            "price": meta.get("price", ""),
            "image_url": meta.get("image_url", ""),
            "appliance_type": meta.get("appliance_type", ""),
            "url": meta.get("url", ""),
            "compatible_models": json.loads(meta.get("compatible_models", "[]")),
            "relevance_score": round(1 - dist, 3),
        })
        if len(parts) >= n_results:
            break

    return parts
