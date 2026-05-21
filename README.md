# PartSelect Chat Agent

An AI-powered chat assistant for the [PartSelect](https://www.partselect.com) e-commerce platform, scoped to **refrigerator and dishwasher parts**. Users can find parts, check appliance compatibility, get installation guidance, and troubleshoot appliance problems — all through a conversational interface.

## Repository Structure

```
case-study/
├── frontend/          # Next.js 16 chat UI (App Router, TypeScript)
├── backend/           # FastAPI agent server (Python)
│   ├── app/
│   │   ├── agent.py           # Gemini tool-calling loop
│   │   ├── main.py            # FastAPI endpoints
│   │   ├── db.py              # ChromaDB collections
│   │   ├── embeddings.py      # Gemini embedding function
│   │   ├── tools/             # Four agent tools
│   │   └── data/              # Scraper + ingest pipeline
│   └── tests/                 # 53 unit tests (pytest)
└── docs/              # Architecture and design decisions
```

## Quick Start

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # add your GOOGLE_API_KEY
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

### Run Tests

```bash
cd backend && source venv/bin/activate
pip install pytest httpx
pytest tests/ -v
```

## Data Pipeline (one-time setup)

`chroma_db/` and `data/raw/*.json` are committed to the repo so the project runs without any rebuild step. In production these would be excluded from version control and rebuilt via a scheduled pipeline — see [docs/data-pipeline.md](docs/data-pipeline.md) for that discussion.

To rebuild from scratch:

```bash
cd backend && source venv/bin/activate
python -m app.data.scraper   # scrapes PartSelect → data/raw/*.json  (requires display for Playwright)
python -m app.data.ingest    # embeds and loads into chroma_db/       (takes ~10 min, burns API quota)
```

## Documentation

- [Architecture Overview](docs/architecture.md) — system design, data flow, agentic loop
- [Design Decisions](docs/design-decisions.md) — every major technology choice and why
- [Scalability](docs/scalability.md) — how to scale this to production
- [Data Pipeline](docs/data-pipeline.md) — scraping, chunking, and embedding strategy
