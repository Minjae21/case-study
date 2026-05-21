# Scalability

## Scaling the Backend

### Async Gemini calls

The current Gemini SDK calls are synchronous, blocking a thread per request. Switch to the async SDK client:

```python
response = await client.aio.chats.create(...)
```

This allows FastAPI to handle many concurrent in-flight LLM requests on a single process.

### Phase 2 — Horizontal scaling (production)

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
