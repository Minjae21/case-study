import os
from typing import Optional

import chromadb
from dotenv import load_dotenv

from app.embeddings import get_embedding_function

load_dotenv()

CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
_client: Optional[chromadb.PersistentClient] = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _client


def get_parts_collection():
    return _get_client().get_or_create_collection(
        name="parts",
        embedding_function=get_embedding_function(),
    )


def get_guides_collection():
    return _get_client().get_or_create_collection(
        name="repair_guides",
        embedding_function=get_embedding_function(),
    )
