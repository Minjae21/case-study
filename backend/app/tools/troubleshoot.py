from app.db import get_guides_collection


def troubleshoot(symptom: str, appliance_type: str = "") -> list[dict]:
    collection = get_guides_collection()
    where = {"appliance_type": appliance_type} if appliance_type in ("refrigerator", "dishwasher") else None

    try:
        results = collection.query(
            query_texts=[symptom],
            n_results=4,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    return [
        {
            "title": meta.get("title", ""),
            "url": meta.get("url", ""),
            "appliance_type": meta.get("appliance_type", ""),
            "excerpt": doc[:600],
            "relevance_score": round(1 - dist, 3),
        }
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]
