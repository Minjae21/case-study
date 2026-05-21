# Design Decisions

Every significant technology choice, and the reasoning behind it.

---

## LLM: Gemini 2.5 Flash

**Chosen over:** GPT-4o, Claude Sonnet, Llama 3 (self-hosted)

Gemini 2.5 Flash was chosen for three reasons:

1. **Native function calling.** The Gemini API supports structured function declarations with JSON Schema parameters. The agent loop relies on this — Gemini decides which tools to call and with what arguments, without any prompt engineering to produce parseable output.
2. **Free tier availability.** The assignment is a demo/submission, not a production deployment. Gemini's free tier (20 req/day on 2.5 Flash) is sufficient for development and a recorded walkthrough without requiring billing setup.
3. **Single vendor.** Using Gemini for both generation (`gemini-2.5-flash`) and embeddings (`gemini-embedding-001`) keeps the dependency surface small — one API key, one SDK, one billing account.

**Trade-off:** The free tier daily limit of 20 requests is tight for extended testing. Switching to a paid key or a higher-quota model (e.g. `gemini-2.0-flash` with billing) removes this constraint entirely with minimal code change — only `MODEL` in `agent.py` needs updating.

---

## Why RAG (Retrieval-Augmented Generation)?

The agent needs to answer questions about specific part numbers, prices, compatibility lists, and installation steps. This information is:

- **Highly specific** — part numbers like PS11765620 are not in any LLM's training data with reliable accuracy
- **Frequently wrong when hallucinated** — a wrong price or compatibility answer is worse than no answer
- **Structured** — it lives naturally in a vector store with metadata filters

RAG solves all three: the LLM never invents part data because it always calls a tool that queries the ground-truth database. The system prompt explicitly instructs the agent to "never make up part numbers, prices, or compatibility data — always use your tools."

**Alternative considered:** Fine-tuning a model on PartSelect data. Rejected because fine-tuning bakes a snapshot in time — any new part requires retraining. RAG lets us add new parts by running the ingest script.

---

## Vector Database: ChromaDB (local) over Pinecone / Weaviate

**Chosen over:** Pinecone, Weaviate, pgvector, Qdrant

| | ChromaDB | Pinecone |
|---|---|---|
| Setup | Zero — runs in-process | Account + API key + index creation |
| Cost | Free | Free tier, then paid |
| Latency | Sub-millisecond (in-process) | ~50–200ms network round-trip |
| Scale | Single machine, ~millions of vectors | Distributed, billions of vectors |
| Persistence | Local SQLite + binary files | Managed cloud |

For a case-study submission with ~350 chunks, ChromaDB's in-process persistence is strictly better: zero external dependencies, instant queries, and the entire vector store is committed to the repo so reviewers can run the project without any setup beyond `pip install`.

**When to switch:** At production scale (millions of parts, multi-instance backend), Pinecone or Weaviate would be appropriate. See [scalability.md](scalability.md) for the migration path.

---

## Embedding Model: Gemini Embedding 001

**Chosen over:** OpenAI `text-embedding-3-small`, `sentence-transformers` (local)

- Same vendor as the generation model — one API key, no additional billing setup
- 3072-dimensional embeddings with strong semantic quality for product/technical text
- Free tier available (with rate limits handled in `embeddings.py` with retry/backoff)

**Trade-off:** Rate limits during ingest required a 12-second sleep between batches of 20. A paid OpenAI embedding key would have been faster to ingest with, but adds a second vendor dependency.

---

## Backend: FastAPI over Django / Flask / Express

**Chosen over:** Django REST Framework, Flask, Node/Express

- **Async-native.** FastAPI is built on Starlette/asyncio, matching well with async LLM calls (though the Gemini SDK used here is synchronous, the architecture is ready for async upgrades)
- **Auto-generated OpenAPI docs.** `/docs` at `localhost:8000/docs` provides an interactive Swagger UI — useful for demonstrating the API to reviewers
- **Pydantic validation.** Request and response schemas are enforced with zero boilerplate via `BaseModel`, which catches malformed inputs before they reach the agent

---

## Frontend: Next.js 16 (App Router) over Create React App

**Chosen over:** Create React App, Vite + React, Vue

The assignment specifically calls out Next.js as the recommended framework. Practically:

- **App Router + Server Components.** The header and layout render as Server Components (zero JS sent for static content); only `ChatWindow.tsx` is marked `"use client"`, minimizing client bundle size
- **`NEXT_PUBLIC_` environment variables** work natively without CRA's `REACT_APP_` prefix and support `.env.local` out of the box
- **Production-ready.** Next.js compiles, optimizes, and can deploy to Vercel with a single command — CRA's production story requires additional configuration

The migration from the original CRA implementation was minimal: add `"use client"`, rename env vars, and move files into `app/`.

---

## Agentic Pattern: Tool-Calling Loop over Chain-of-Thought / ReAct

**Chosen over:** LangChain agents, raw ReAct prompting, hardcoded intent routing

The agent loop in `agent.py` is a direct implementation of the tool-use pattern:

1. Send user message + tool declarations to Gemini
2. If Gemini returns function calls, execute them and send results back
3. Repeat until Gemini returns plain text (or 5 rounds are exhausted)

**Why not LangChain?** LangChain adds significant abstraction overhead — its agent executors, memory modules, and chain primitives are powerful but introduce hidden behavior that is hard to debug and explain in an interview context. A hand-rolled 50-line loop is transparent, testable, and demonstrates understanding of the underlying pattern.

**Why not hardcoded intent routing?** A router (e.g. "if message contains 'install' → call `get_part_details`") is brittle and doesn't compose. The LLM-driven approach handles ambiguous queries ("what's wrong with my ice maker and where can I buy the fix?") that would require multiple tools and fail under rigid routing.

---

## Data: Playwright Scraper over PartSelect Public API

PartSelect does not expose a public REST API for part data. The scraper uses Playwright (non-headless Chromium) to:

1. Bypass Akamai bot detection (which blocks `requests`/`httpx` with a 403)
2. Parse product pages for part numbers, prices, compatible models, symptoms, and installation text
3. Follow repair guide index pages to collect troubleshooting content

The scraped data is committed to the repo as `data/raw/parts.json` and `data/raw/repair_guides.json` so reviewers do not need to re-run the scraper (which requires a display and ~10 minutes).
