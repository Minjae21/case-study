# Data Pipeline

## Overview

```
PartSelect website
      │
      │  Playwright (non-headless Chromium)
      ▼
app/data/scraper.py  →  data/raw/parts.json
                     →  data/raw/repair_guides.json
      │
      │  Gemini text-embedding-001
      ▼
app/data/ingest.py   →  chroma_db/  (ChromaDB persistent store)
      │
      ▼
 Two collections:
  "parts"          — 110 parts, ~220 chunks
  "repair_guides"  — ~80 guides, 243 chunks
```

---

## Scraping (`app/data/scraper.py`)

### Why Playwright, not requests/httpx?

PartSelect uses Akamai Bot Manager, which fingerprints HTTP clients and returns 403 for anything that looks automated. Playwright launches a real Chromium instance with:

- A real user-agent string
- `navigator.webdriver` spoofed to `undefined`
- Locale and timezone set to `en-US` / `America/New_York`
- Images and media blocked (speeds up loads without affecting DOM content)

This approach reliably bypasses the bot detection without needing rotating proxies.

### What is scraped

**Parts** (seeded from 48 curated URLs):
- Part number, title, price
- Product description
- Compatible model numbers (from the "Model Cross Reference" section)
- Symptoms the part fixes (from the "Troubleshooting" section)
- Installation story excerpts (from the "Installation Instructions" section)
- Image URL, product page URL, appliance type

**Repair guides** (crawled from the Repair index pages):
- Title, URL, appliance type
- Full page text content (up to 5,000 chars)
- Part numbers mentioned in the guide

### Why curated seed URLs instead of crawling category pages?

PartSelect's category listing pages are paginated but consistently return the same ~10 featured parts regardless of the page number, due to client-side rendering. Direct part URLs are reliable and deterministic.

---

## Ingestion (`app/data/ingest.py`)

### Text chunking

Each part is serialized into a document string:

```
Part Number: PS11765620
Title: Refrigerator Ice Maker Assembly W10884390
Appliance Type: refrigerator
Price: $104.39
Description: ...
Compatible Models: 10672002011, 10672002013, ...
Fixes/Symptoms: Ice maker not making ice | ...
```

This string is split into 800-character chunks with 100-character overlap. The overlap ensures that sentences spanning a chunk boundary are represented in both chunks, preventing search misses on split phrases.

### Why chunk rather than embed whole documents?

Embedding models have token limits and produce a single fixed-size vector per input. Long documents embedded as a whole lose fine-grained semantic information — a 2,000-character document about an ice maker will score similarly against any refrigerator query. Chunking lets the embedding capture specific sub-topics (installation vs. compatibility vs. symptoms) in separate vectors, improving retrieval precision.

### Metadata stored alongside each chunk

Each chunk stores metadata in ChromaDB that is never part of the embedding — it's retrieved at query time alongside the vector results:

| Field | Used for |
|---|---|
| `part_number` | Exact lookup in `get_part_details` and `check_compatibility` |
| `title`, `price`, `image_url`, `url` | Product card rendering in the frontend |
| `appliance_type` | Filter-by-appliance in `search_parts` and `troubleshoot` |
| `compatible_models` | JSON-encoded list, parsed in `check_compatibility` |

### Rate limiting during ingest

The Gemini embedding API on the free tier allows ~100 requests/minute. Each batch of 20 chunks is followed by a 12-second sleep, keeping throughput at ~100 embeddings/minute — within the limit. A paid key removes this constraint.

### HNSW index configuration

Collections are created with `{"hnsw:space": "cosine"}` — cosine similarity rather than L2 distance. For text embeddings, cosine similarity is directionally invariant (two documents about the same topic score high regardless of length differences), which is more appropriate than Euclidean distance for semantic search.

---

## Query Path

At query time, `search_parts` and `troubleshoot`:

1. Embed the user's query text using the same `GeminiEmbeddingFunction`
2. Issue a `collection.query()` call with `n_results * 2` (fetches extra to allow post-filtering)
3. Deduplicate by `part_number` (multiple chunks from the same part can rank highly)
4. Return up to `n_results` parts, sorted by relevance score (`1 - cosine_distance`)

`get_part_details` and `check_compatibility` bypass the embedding entirely — they use `collection.get(where={"part_number": pn})` for exact metadata lookup, which is an O(1) scan on the SQLite metadata store.
