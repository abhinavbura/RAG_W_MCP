# RAG Pipeline — Build Plan

**Total estimated time: 10–16 days (including testing)**  
**Last updated:** Mar 24 2026

---

## Phase Overview

| Phase | Name | Est. Days | Dependencies | Status |
|---|---|---|---|---|
| [Phase 1](./phase1_data_models.md) | Data Models | 1–2 days | None | 🔴 Not Started |
| [Phase 2](./phase2_chunkers_ingestion.md) | Chunkers & Ingestion | 2–3 days | Phase 1 | 🔴 Not Started |
| [Phase 3](./phase3_retrieval_llm.md) | Retrieval & LLM Layer | 2–3 days | Phase 1 + 2 | 🔴 Not Started |
| [Phase 4](./phase4_api_frontend.md) | API & Frontend | 3–4 days | Phase 1–3 | 🔴 Not Started |
| [Phase 5](./phase5_future_extensions.md) | Future Extensions | 2–4 days | Phase 4 live | 🔴 Not Started |

---

## What each phase delivers

### Phase 1 — Data Models (1–2 days)
6 Python dataclasses that every other layer depends on:
- `PipelineState` (35 fields, JSON save/load, Redis-ready)
- `FileMetadata`, `ChunkingConfig`, `ConversationTurn`, `ConversationHistory`, `RetrievalResult`

✅ **Phase 1 done =** state round-trip pass, `get_config()` correct for all bands, ConversationHistory trim works.

---

### Phase 2 — Chunkers & Ingestion (2–3 days)
File readers + structure detection + 3 chunkers + ingest pipeline:
- `read_md()`, `read_txt()`, `read_pdf()` (image-page skipping)
- `detect_structure()` (already done — verify integration)
- Wire `ChunkingConfig` into `chunk_markdown()` (currently in progress)
- `_hash_file()`, `_archive_file()`, `ingest_folder()` (4-phase entry point)

✅ **Phase 2 done =** full folder ingest to ChromaDB, re-ingest on changed file, hash store + archive correct.

---

### Phase 3 — Retrieval & LLM Layer (2–3 days)
7-stage `retrieve()` + `LLMRouter`:
- `embed_query()` / `embed_documents()` with nomic prefix logic
- `_classify_intent()`, `_detect_scope()`, `_extract_sections_llm()`
- `_rerank()` (5 signals), `_mmr()` (section overlap proxy)
- `LLMRouter` (DeepSeek + GPT-4o mini, 3 routing triggers, fallback on 429)
- `ConversationHistory` wired into conversational intent path

✅ **Phase 3 done =** `retrieve()` returns correct `RetrievalResult` for all 4 intents, LLMRouter fallback tested.

---

### Phase 4 — API & Frontend (3–4 days)
Full usable system:
- **FastAPI** — 4 endpoints: `/ingest`, `/query`, `/state`, `/ingest/progress` (SSE)
- **React + Vite** — upload UI with drag/drop + SSE progress, chat with source chunks panel
- **MCP server** — 3 tools: `search_documents`, `get_document_sections`, `get_collection_stats`

✅ **Phase 4 done =** upload → ingest → query → answer end-to-end in browser, all 3 MCP tools working.

---

### Phase 5 — Future Extensions (2–4 days, non-sequential)
Add only when real usage reveals the need:
- **BM25 + RRF fusion** — for exact-term fact lookups (legal, clause numbers)
- **Redis state store** — for multi-user deployment
- **Model upgrade path** — wipe-and-reingest script for bge-large migration
- **Large collection optimisation** — pre-filter when > 5000 chunks
- **Auth middleware** — API key gating for public deployment

---

## Build order within phases

Each phase must be fully tested before starting the next. Phases 1–4 are strictly sequential (each depends on the previous). Phase 5 extensions are independent of each other.

Components already done (from architecture build status):
- `detect_structure()`, `_is_heading_line()`, `_heading_level()`, `_clean_heading()`
- `chunk_txt_structured()`, `chunk_txt_semantic()`, `chunk_document()`
- `get_config()`, `_classify_intent()`, `_rerank()`, `_mmr()`

Components in progress:
- `chunk_markdown()` — needs ChunkingConfig wired in
- `retrieve()` — needs RetrievalResult + LLMRouter wired in
