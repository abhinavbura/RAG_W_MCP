# Phase 3 — Retrieval & LLM Layer

**Estimated time:** 2–3 days  
**Status:** 🟢 Done  
**Dependencies:** Phase 1 + Phase 2 complete

---

## Goal

Build the full 7-stage `retrieve()` pipeline, the `LLMRouter`, all embedding helpers, and wire `ConversationHistory` into the conversational intent path. At the end of this phase, the system can answer queries end-to-end without API or frontend.

---

## Tasks

### 3.1 Embedding Helpers

- [x] `embed_query(query, state)` — applies `query_prefix` if `requires_prefix=True`, single `model.encode()` call
- [x] `embed_documents(texts, state)` — applies `doc_prefix` if `requires_prefix=True`, batched encode
- [x] Both read model from `state._model_instance`
- [x] nomic prefix: `"search_query: "` (query) / `"search_document: "` (doc)
- [x] bge-large: no prefix (empty string)

### 3.2 Intent Classification — `_classify_intent()`

- [x] Regex patterns (already done — verify):
  - `fact` — specific question words: who, what, when, where, how much, how many, etc.
  - `summary` — summarise, overview, explain, what is, describe
  - `comparison` — compare, difference, vs, versus, better, contrast
  - `conversational` — you, your, that, it, this (pronoun-heavy → follow-up)
- [x] LLM fallback (DeepSeek) for ambiguous — returns one of 4 intent strings
- [x] Returns intent string, never raises

### 3.3 Scope Detection — `_detect_scope()`

- [x] Tokenise each `source_doc` stem from `state.files_metadata` (e.g. `"ml_textbook"` → `["ml","textbook"]`)
- [x] Match against query words
- [x] Confident match → return `source_doc` string
- [x] No match → return `None` (search whole collection)

### 3.4 Section Extraction — `_extract_sections_llm()`

- [x] Only called for `comparison` intent
- [x] Input: query + list of known section names from ChromaDB metadata
- [x] DeepSeek call with system prompt enforcing JSON `{section_a, section_b}`
- [x] Both values must exist in known section list
- [x] If JSON parse fails or sections not in list → return `None` (fall back to no filter)

### 3.5 Re-ranker — `_rerank()`

- [x] Input: list of candidate chunks with cosine similarity scores from ChromaDB
- [x] Apply 5 signals per chunk:
  - `+0.15` if any query word in `section` or `subsection`
  - `+0.05` if `chunk_type = "headed"`
  - `+0.05` if `heading_confidence = "high"`
  - `-0.05` if `position_ratio < 0.05` or `> 0.95`
  - `-0.10` if `token_count > model_ctx_tokens` (from state)
- [x] Sort descending by adjusted score
- [x] Return sorted list

### 3.6 MMR — `_mmr()`

- [x] Used only for `summary` intent
- [x] Redundancy proxy: section name overlap (no extra embed calls)
- [x] `mmr_lambda` from ChunkingConfig (0.7 small → 0.5 large)
- [x] `mmr_lambda` controls precision/diversity trade-off
- [x] Deduplicates by section after MMR

### 3.7 retrieve() — 7 stages

- [x] **Stage 0** — `embed_query()` once, reuse vector everywhere
- [x] **Stage 1** — `_classify_intent()` → `intent` string
- [x] **Stage 2** — `_detect_scope()` → `source_doc` or `None`
- [x] **Stage 3** — Build ChromaDB `where` clause:
  - Scope match → `source_doc` filter
  - Comparison → call `_extract_sections_llm()` → two section filters
  - Conversational → collect `excluded_ids` from history
- [x] **Stage 4** — ChromaDB cosine search:
  - summary: fetch k×3 (MMR needs headroom)
  - all others: fetch k×2
  - comparison: two separate queries, merge results
- [x] **Stage 5** — `_rerank()` on candidates
- [x] **Stage 6** — Intent-specific post-processing:
  - fact: top-k by score, no MMR
  - summary: `_mmr()` → deduplicate by section
  - comparison: interleave results from both section queries
  - conversational: drop `excluded_ids`, prepend `recent_chunks(n=2)`, trim to token budget
- [x] Return `RetrievalResult` with all 13 fields populated
- [x] Start/end timestamps for `latency_ms`

### 3.8 LLMRouter

- [x] `LLMRouter(state)` class — reads budget from `state.llm_budget_gpt`
- [x] `route(task)` → returns primary + fallback model name
  - Low complexity tasks (classify, extract, compress) → OpenRouter (DeepSeek R1) primary, OpenRouter (GPT-4o mini) fallback
  - High complexity (answer generation) → OpenRouter (GPT-4o mini) primary, OpenRouter (DeepSeek R1) fallback
- [x] `call(task, prompt, system_prompt=None)` → orchestrates routing + fallback
- [x] `_call_deepseek(prompt, system_prompt)` — calls OpenRouter API for `deepseek/deepseek-r1`
- [x] `_call_gpt(prompt, system_prompt)` — calls OpenRouter API for `openai/gpt-4o-mini`
- [x] `_handle_fallback(task, prompt, system_prompt)` — retries on 429 or timeout
- [x] Budget check: if `llm_tokens_used_gpt >= llm_budget_gpt` → route all to DeepSeek
- [x] On both models fail → raise `LLMUnavailableError`
- [x] Update `state.llm_tokens_used_deepseek` / `state.llm_tokens_used_gpt` after every call
- [x] Log to `state.llm_calls_by_task`

### 3.9 Wire ConversationHistory into retrieve()

- [x] `retrieve(query, state, history: ConversationHistory = None)`
- [x] Conversational intent: `history.excluded_ids()` → passed to ChromaDB exclude filter
- [x] Conversational intent: `history.recent_chunks(n=2)` → prepended to result
- [x] After retrieve: caller responsible for calling `history.add_turn(turn)`

---

## File Structure

```
pipeline/
  retrieval/
    retrieve.py            # retrieve() — 7-stage entry point
    intent.py              # _classify_intent()
    scope.py               # _detect_scope()
    rerank.py              # _rerank()
    mmr.py                 # _mmr()
    section_extract.py     # _extract_sections_llm()
  llm/
    router.py              # LLMRouter
    errors.py              # LLMUnavailableError
  embeddings/
    helpers.py             # embed_query(), embed_documents()
```

---

## Testing

### Unit tests

| Test | What to verify |
|---|---|
| `embed_query()` with nomic | Prefix `"search_query: "` applied |
| `embed_query()` with bge-large | No prefix — raw query encoded |
| `_classify_intent("what is X")` | Returns `"fact"` |
| `_classify_intent("compare A and B")` | Returns `"comparison"` |
| `_classify_intent("summarise X")` | Returns `"summary"` |
| `_rerank()` heading match | Chunk with matching heading word scores higher |
| `_rerank()` token gate | Oversized chunk gets -0.10 penalty |
| `_mmr()` lambda=0.7 | Less diversity (more precision) than lambda=0.5 |
| `LLMRouter.route("answer")` | Returns GPT-4o mini as primary |
| `LLMRouter.route("classify")` | Returns DeepSeek as primary |
| `LLMRouter` budget exceeded | Routes to DeepSeek even for answer task |
| `LLMRouter` 429 on primary | Retries on fallback without raising |

### Integration test — full query run

```python
from pipeline.ingestion.ingest_folder import ingest_folder
from pipeline.retrieval.retrieve import retrieve
from pipeline.state.conversation import ConversationHistory

state = ingest_folder("./dataset")
history = ConversationHistory()

result = retrieve("What is the refund policy?", state, history)
assert result.intent == "fact"
assert len(result.chunks) > 0
assert result.latency_ms > 0

print(f"Intent: {result.intent}")
print(f"Chunks: {len(result.chunks)}")
print(f"Top chunk: {result.chunks[0]['anchor']}")
print("Phase 3 integration test passed")
```

### Conversational multi-turn test

```python
# Turn 1
result1 = retrieve("What is the refund policy?", state, history)
history.add_turn(ConversationTurn(...))

# Turn 2 — uses excluded_ids and recent_chunks
result2 = retrieve("What about the 7-day window?", state, history)
assert not any(c["id"] in [c2["id"] for c2 in result1.chunks] for c2 in result2.chunks)
print("Multi-turn excluded_ids test passed")
```

---

## Done criteria

- [x] `retrieve()` returns `RetrievalResult` with all 13 fields for all 4 intents
- [x] `_rerank()` scores differ correctly across 5 signals
- [x] `_mmr()` produces more diverse results at lower lambda
- [x] `LLMRouter` falls back to secondary without raising on 429
- [x] Budget exhaustion routes all calls to DeepSeek
- [x] Conversational path excludes previously seen chunk IDs
- [x] `latency_ms` populated on every result
