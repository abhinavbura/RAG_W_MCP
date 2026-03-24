# Phase 5 — Future Extensions

**Estimated time:** 2–4 days (spread over time, not sequential)  
**Status:** 🔴 Not Started  
**Dependencies:** Phase 4 complete and live-tested

---

## Goal

Incremental improvements added only when real usage reveals the need. These are not required for a working system — Phase 4 is the complete baseline.

---

## Extensions (tackle independently, in any order)

### 5.1 BM25 Hybrid Search

**Trigger:** Exact-term fact lookups test poorly (legal clauses, clause numbers, proper nouns).

- [ ] Install `rank-bm25`
- [ ] Build in-memory BM25 index from all `text` fields in ChromaDB on startup
- [ ] Store index in `state.bm25_index`
- [ ] Set `state.enable_bm25 = True`
- [ ] Wire into `retrieve()` for `fact` intent only
- [ ] Fusion: Reciprocal Rank Fusion (RRF) → `score = 1/(k + bm25_rank) + 1/(k + vector_rank)` where k=60
- [ ] No score normalisation needed with RRF

**Testing:**
- Query exact clause text → verify BM25 chunk ranks higher than pure cosine
- Query paraphrase → verify cosine chunks still competitive
- Measure retrieval quality before/after on 10 exact-term test queries

---

### 5.2 Redis State Store

**Trigger:** Moving from single-user local to multi-user API deployment.

- [ ] Install `redis-py`
- [ ] Replace `PipelineState.save()` — serialise to JSON, write to Redis key `rag_state:{session_id}`
- [ ] Replace `PipelineState.load()` — read from Redis key, deserialise
- [ ] Replace hash store `_save_hash_store()` / `_load_hash_store()` — Redis hash key `rag_hashes`
- [ ] Move `ConversationHistory` store from FastAPI in-memory dict → Redis per `conversation_id`
- [ ] All other pipeline code unchanged — only these 2 methods change

**Testing:**
- Start pipeline, kill process, restart → verify state restored from Redis
- Two concurrent POST /query requests → verify separate conversation histories

---

### 5.3 Model Upgrade Path (bge-large)

**Trigger:** Folder size crosses 500K chars but collection is locked to nomic.

- [ ] Build `wipe_and_reingest.py` script:
  - Delete ChromaDB collection
  - Clear `.rag_hashes.json`
  - Move all files from `dataset/processed/` back to `dataset/`
  - Run `ingest_folder()` fresh — will select bge-large on new collection
- [ ] Surface `model_upgrade_warning` prominently in React state panel
- [ ] Add "Upgrade Model" button in UI → calls wipe_and_reingest endpoint

**Testing:**
- Add enough files to cross 500K threshold
- Verify `model_upgrade_warning` appears in GET /state
- Run wipe_and_reingest → verify collection rebuilt with bge-large
- Re-query → verify retrieval still works

---

### 5.4 Large Collection Optimisation (5000+ chunks)

**Trigger:** Collection exceeds 5000 chunks (several full books ingested).

- [ ] Add `source_doc` pre-filter as default on all `retrieve()` calls when `collection.count() > 5000`
  - Only if `_detect_scope()` found a confident match
  - No filter if scope is ambiguous
- [ ] Consider adding `chapter_num` and `chapter_title` fields to chunk schema for book navigation
- [ ] Evaluate ChromaDB HNSW index tuning parameters (`ef_construction`, `M`)

**Testing:**
- Ingest 5+ large PDFs (collection > 5000 chunks)
- Compare retrieval precision with and without `source_doc` pre-filter
- Measure latency at scale

---

### 5.5 Auth Middleware (if exposing API publicly)

- [ ] Add FastAPI dependency for API key validation
- [ ] Read allowed keys from env variable `RAG_API_KEYS`
- [ ] Apply to all endpoints except GET /state (public)
- [ ] Rate limiting per key (slowapi or similar)

---

## Done criteria per extension

| Extension | Done when |
|---|---|
| BM25 | RRF scores tested on 10 exact-term queries, improvement measurable |
| Redis | Restart-recovery test passes, concurrent conversation test passes |
| Model upgrade | `wipe_and_reingest` tested end-to-end, bge-large collection working |
| Large collection | Pre-filter logic tested at 5000+ chunks, no regressions |
| Auth | API key rejection tested, valid key grants access |
