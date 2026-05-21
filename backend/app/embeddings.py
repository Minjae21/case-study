import os
import time
from typing import List

from chromadb import EmbeddingFunction, Documents, Embeddings
from dotenv import load_dotenv
from google import genai

load_dotenv()


class GeminiEmbeddingFunction(EmbeddingFunction):
    def __init__(self, api_key: str, model_name: str = "models/gemini-embedding-001"):
        self._client = genai.Client(api_key=api_key)
        self._model = model_name

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = []
        for doc in input:
            for attempt in range(5):
                try:
                    result = self._client.models.embed_content(
                        model=self._model,
                        contents=[doc],
                    )
                    embeddings.append(result.embeddings[0].values)
                    break
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        wait = (attempt + 1) * 15
                        print(f"    [rate limit] waiting {wait}s (attempt {attempt+1})...")
                        time.sleep(wait)
                    else:
                        raise
        return embeddings


def get_embedding_function() -> GeminiEmbeddingFunction:
    return GeminiEmbeddingFunction(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model_name="models/gemini-embedding-001",
    )
