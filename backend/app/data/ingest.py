import json
import os
import time
from pathlib import Path

import chromadb
from dotenv import load_dotenv

from app.embeddings import get_embedding_function

load_dotenv()

RAW_DIR = Path(__file__).parent / "raw"
CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")


def get_chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=CHROMA_PATH)


def chunk_text(text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
    if len(text) <= max_chars:
        return [text] if text.strip() else []
    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start:start + max_chars].strip()
        if chunk:
            chunks.append(chunk)
        start += max_chars - overlap
    return chunks


def build_part_document(part: dict) -> str:
    lines = [
        f"Part Number: {part.get('part_number', '')}",
        f"Title: {part.get('title', '')}",
        f"Appliance Type: {part.get('appliance_type', '')}",
        f"Price: {part.get('price', '')}",
        f"Description: {part.get('description', '')}",
    ]
    models = part.get("compatible_models", [])
    if models:
        lines.append(f"Compatible Models: {', '.join(models[:30])}")
    symptoms = part.get("symptoms", [])
    if symptoms:
        lines.append(f"Fixes/Symptoms: {' | '.join(symptoms)}")
    return "\n".join(lines)


def ingest_parts(client: chromadb.PersistentClient) -> int:
    parts_path = RAW_DIR / "parts.json"
    if not parts_path.exists():
        print(f"[warn] {parts_path} not found — run scraper first")
        return 0

    with open(parts_path) as f:
        parts: list[dict] = json.load(f)

    ef = get_embedding_function()
    collection = client.get_or_create_collection(
        name="parts",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    ids, docs, metas = [], [], []
    for part in parts:
        pn = part.get("part_number", "")
        if not pn:
            continue
        doc = build_part_document(part)
        for i, chunk in enumerate(chunk_text(doc)):
            ids.append(f"{pn}_{i}")
            docs.append(chunk)
            metas.append({
                "part_number": pn,
                "title": part.get("title", ""),
                "price": part.get("price", ""),
                "image_url": part.get("image_url", ""),
                "appliance_type": part.get("appliance_type", ""),
                "url": part.get("url", ""),
                "compatible_models": json.dumps(part.get("compatible_models", [])[:20]),
            })

    if ids:
        batch_size = 20
        for i in range(0, len(ids), batch_size):
            collection.upsert(
                ids=ids[i:i+batch_size],
                documents=docs[i:i+batch_size],
                metadatas=metas[i:i+batch_size],
            )
            print(f"    upserted {min(i+batch_size, len(ids))}/{len(ids)} chunks...")
            if i + batch_size < len(ids):
                time.sleep(12)  # Gemini free tier: ~100 embed RPM, 20 chunks/batch = 5 batches/min
    print(f"  Parts collection: {len(ids)} chunks from {len(parts)} parts")
    return len(ids)


def ingest_repair_guides(client: chromadb.PersistentClient) -> int:
    guides_path = RAW_DIR / "repair_guides.json"
    if not guides_path.exists():
        print(f"[warn] {guides_path} not found — run scraper first")
        return 0

    with open(guides_path) as f:
        guides: list[dict] = json.load(f)

    ef = get_embedding_function()
    collection = client.get_or_create_collection(
        name="repair_guides",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    ids, docs, metas = [], [], []
    for gi, guide in enumerate(guides):
        content = guide.get("content", "").strip()
        if not content:
            continue
        for ci, chunk in enumerate(chunk_text(content)):
            ids.append(f"guide_{gi}_{ci}")
            docs.append(chunk)
            metas.append({
                "title": guide.get("title", ""),
                "url": guide.get("url", ""),
                "appliance_type": guide.get("appliance_type", ""),
            })

    if ids:
        batch_size = 20
        for i in range(0, len(ids), batch_size):
            collection.upsert(
                ids=ids[i:i+batch_size],
                documents=docs[i:i+batch_size],
                metadatas=metas[i:i+batch_size],
            )
            print(f"    upserted {min(i+batch_size, len(ids))}/{len(ids)} chunks...")
            if i + batch_size < len(ids):
                time.sleep(12)
    print(f"  Repair guides collection: {len(ids)} chunks from {len(guides)} guides")
    return len(ids)


def main():
    print("=== Ingesting into Chroma with Gemini embeddings ===")
    client = get_chroma_client()
    n_parts = ingest_parts(client)
    n_guides = ingest_repair_guides(client)
    print(f"\nDone. {n_parts + n_guides} total chunks stored at '{CHROMA_PATH}'")


if __name__ == "__main__":
    main()
