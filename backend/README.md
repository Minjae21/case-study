# Backend

FastAPI server for the PartSelect chat agent.

## Stack

- **FastAPI** — HTTP API (`/api/chat`, `/health`)
- **Gemini 2.5 Flash** — LLM with native function calling
- **ChromaDB** — local vector store for parts and repair guides
- **Gemini Embedding 001** — text embeddings for semantic search

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set GOOGLE_API_KEY in .env
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000/api/chat
- Swagger: http://localhost:8000/docs

## Tests

```bash
pip install pytest httpx
pytest tests/ -v
```

## Data pipeline (one-time)

The `chroma_db/` directory is pre-built. To rebuild:

```bash
python -m app.data.scraper   # scrape PartSelect
python -m app.data.ingest    # embed and load into chroma_db/
```
