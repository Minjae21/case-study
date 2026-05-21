# Scalability

## Current State (Case Study)

| Component | Current implementation |
|---|---|
| Frontend | Next.js dev server, single instance |
| Backend | FastAPI + uvicorn, single process |
| Vector DB | ChromaDB, local persistent files |
| LLM | Gemini 2.5 Flash, free tier (20 req/day) |
| Data | 110 parts, 80 repair guides, ~350 chunks |

This is sufficient for a demo but not for production traffic.

---

## Scaling the Backend

### Phase 1 — Multiple workers (low effort)

Replace the single uvicorn process with Gunicorn + multiple uvicorn workers:

```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

This handles ~4x concurrent requests with zero code changes. The constraint becomes the ChromaDB client, which is not safe to share across processes.

**Fix:** Move ChromaDB to a dedicated process using the [ChromaDB HTTP server](https://docs.trychroma.com/usage-guide#running-chroma-in-clientserver-mode):

```bash
chroma run --path ./chroma_db --port 8001
```

Then change `db.py` to use `chromadb.HttpClient` instead of `PersistentClient`.

### Phase 2 — Async Gemini calls (medium effort)

The current Gemini SDK calls are synchronous, blocking a thread per request. Switch to the async SDK client:

```python
response = await client.aio.chats.create(...)
```

This allows FastAPI to handle many concurrent in-flight LLM requests on a single process.

### Phase 3 — Horizontal scaling (production)

Deploy multiple backend instances behind a load balancer (e.g. AWS ALB, GCP Cloud Run). Requirements:

- **Shared vector DB:** Replace local ChromaDB with a managed service — Pinecone, Weaviate Cloud, or Qdrant Cloud. All expose an HTTP API that works across instances.
- **Session state:** If conversation history persistence is added, store it in Redis or a managed database (not in-process), so any instance can serve any user's session.
- **LLM quota:** Move from the free tier to a paid Gemini API key. At scale, consider a quota-aware request queue (e.g. Celery + Redis) to smooth out burst traffic without hitting rate limits.

---

## Scaling the Data

The current dataset of 110 parts is a manually curated sample. To cover PartSelect's full catalog (~1M+ parts):

### Option A — Full catalog scrape

Run the existing scraper at scale with a pool of Playwright workers. Rate-limit scraping to ~1 req/sec to avoid being blocked. This produces a large `parts.json` that feeds the same ingest pipeline.

**Estimated DB size:** 1M parts × 2 chunks average × 3072 floats × 4 bytes ≈ ~24 GB. Still manageable in Pinecone's free tier for this vector count.

### Option B — Real-time tool with live API

Replace ChromaDB lookups with direct HTTP calls to an internal PartSelect API (if one exists). Tools like `get_part_details` become thin wrappers around API calls rather than DB lookups. This eliminates the data freshness problem entirely — prices and availability are always current.

### Option C — Hybrid

Keep ChromaDB for semantic search (where a vector index is essential) but call a live API for `get_part_details` and `check_compatibility` (where exact lookups on structured data are better served by a relational DB or API).

---

## Scaling the LLM Layer

| Concern | Solution |
|---|---|
| Daily quota (20 req/day free tier) | Enable billing on Google AI Studio |
| Per-minute rate limits | Implement request queue with backoff (current retry logic is a partial solution) |
| Latency (1–3s per LLM call) | Stream responses using `stream=True` in the Gemini SDK; return chunks via SSE to the frontend |
| Cost at scale | Switch to `gemini-2.0-flash` (cheaper per token) for high-volume production; reserve 2.5 Flash for complex queries |
| Vendor lock-in | The tool-calling pattern is standard across providers (OpenAI, Anthropic, Google). Migrating means swapping `agent.py` while keeping all tools, routes, and frontend unchanged |

---

## Production Deployment Sketch

```
                    ┌──────────────────────┐
Users ──────────────► Vercel (Next.js)      │
                    └──────────┬───────────┘
                               │ HTTPS
                    ┌──────────▼───────────┐
                    │  Cloud Run / ECS      │
                    │  FastAPI (N instances)│
                    └──────┬────────┬───────┘
                           │        │
               ┌───────────▼─┐  ┌───▼────────────┐
               │  Pinecone   │  │  Redis (sessions│
               │  (vectors)  │  │  + rate limits) │
               └─────────────┘  └─────────────────┘
```

All three backing services (Pinecone, Redis, and the Gemini API) are fully managed — no infrastructure to operate.
