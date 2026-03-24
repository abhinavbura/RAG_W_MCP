# Phase 1 — Data Models

**Estimated time:** 1–2 days  
**Status:** � Done  
**Dependencies:** None — start here  
**Completed:** March 24, 2026

---

## Goal

Build all 6 dataclasses that form the backbone of the pipeline. All must be JSON-serialisable. Private runtime fields (prefixed `_`) are never serialised.

---

## Tasks

### 1.1 FileMetadata
- [x] Define dataclass fields: `path`, `file_type`, `size_chars`, `hash`, `status`, `chunks_added`, `error`
- [x] Implement `to_dict()` and `from_dict()`
- [x] Status enum values: `"new"` | `"changed"` | `"unchanged"` | `"failed"` | `"ingested"`

### 1.2 ChunkingConfig
- [x] Define dataclass fields: `max_chars`, `overlap_chars`, `min_tokens`, `max_tokens`, `overlap_sentences`, `drop_percentile`, `k_fact`, `k_summary`, `k_compare`, `k_conversational`, `mmr_lambda`
- [x] Implement `get_config(text, chunk_count)` factory function
  - Small doc: < 100K chars
  - Medium doc: < 500K chars
  - Large doc: 500K+ chars
  - Small collection: < 200 chunks
  - Medium collection: < 1000 chunks
  - Large collection: 1000+ chunks

### 1.3 ConversationTurn
- [x] Define fields: `query`, `intent`, `chunks`, `token_count`, `timestamp`
- [x] Implement `to_dict()` and `from_dict()`

### 1.4 ConversationHistory
- [x] Define fields: list of `ConversationTurn`, `max_tokens` (default 1500)
- [x] Implement `add_turn(turn)` → appends then calls `_trim()`
- [x] Implement `_trim()`:
  - If total tokens > budget → try LLM compression of oldest turn (DeepSeek, ~100 tokens)
  - If still over → drop oldest turn entirely
- [x] Implement `excluded_ids()` → all chunk IDs across all turns
- [x] Implement `recent_chunks(n=2)` → chunks from last N turns

### 1.5 RetrievalResult
- [x] Define 13 fields: `chunks`, `query`, `intent`, `scope`, `sections`, `k`, `model_key`, `filter_applied`, `total_tokens`, `total_fetched`, `scores_before`, `scores_after`, `latency_ms`
- [x] Implement `to_dict()`
- [x] Implement `strip_debug()` → removes `scores_before`, `scores_after`, `latency_ms` for production

### 1.6 PipelineState
- [x] Define all 35 fields across 6 groups: Folder, Model, ChromaDB, Current File, Session, LLM Budget, BM25
- [x] Implement `to_dict()` — exclude private fields (`_model_instance`, `_collection`)
- [x] Implement `from_dict()` — reconstruct from JSON, private fields = None
- [x] Implement `save(path)` → serialise to `.rag_state.json`
- [x] Implement `load(path)` → deserialise from `.rag_state.json`
- [x] Implement `set_current_file(file_metadata)` → refreshes all `current_*` fields
- [x] Implement `record_ingested(filename, chunks_added)`
- [x] Implement `record_failed(filename, reason)`
- [x] Implement `record_skipped(filename)`
- [x] Implement `update_collection_count(collection)` → calls `collection.count()`

---

## File Structure

```
pipeline/
  state/
    pipeline_state.py     # PipelineState + FileMetadata
    chunking_config.py    # ChunkingConfig + get_config()
    conversation.py       # ConversationTurn + ConversationHistory
    retrieval_result.py   # RetrievalResult
```

---

## Testing

### Unit tests

| Test | What to verify | Status |
|---|---|---|
| `FileMetadata.to_dict()` / `from_dict()` | Round-trip serialisation, all fields preserved | ✓ Pass |
| `get_config()` small doc | Returns max_chars=1000, k_fact=3, mmr_lambda=0.7 | ✓ Pass |
| `get_config()` large doc | Returns max_chars=2000, k_fact=5, mmr_lambda=0.5 | ✓ Pass |
| `ConversationHistory.add_turn()` | token_count accumulates, `_trim()` fires when over budget | ✓ Pass |
| `ConversationHistory.excluded_ids()` | Returns flat list of all chunk IDs across all turns | ✓ Pass |
| `ConversationHistory.recent_chunks(n=2)` | Returns only last 2 turns' chunks | ✓ Pass |
| `PipelineState.save()` / `load()` | Round-trip to JSON, private fields are None after load | ✓ Pass |
| `PipelineState.record_failed()` | Appends to `failed_files`, does NOT update hash store | ✓ Pass |
| `RetrievalResult.strip_debug()` | `scores_before`, `scores_after`, `latency_ms` absent in output | ✓ Pass |

### Quick smoke test ✓ PASSED

```python
from pipeline.state.pipeline_state import PipelineState, FileMetadata
from pipeline.state.chunking_config import get_config
from pipeline.state.conversation import ConversationTurn, ConversationHistory
from pipeline.state.retrieval_result import RetrievalResult

# All 6 dataclasses imported and instantiated successfully
state = PipelineState(folder_path="./dataset")
config = get_config(text="x" * 50000, chunk_count=100)
turn = ConversationTurn(query="test", intent="fact", token_count=50)
history = ConversationHistory(max_tokens=500)
result = RetrievalResult(query="test", intent="fact", k=5, model_key="nomic")

# Serialization round-trips verified
state_dict = state.to_dict()
loaded_state = PipelineState.from_dict(state_dict)
assert loaded_state.folder_path == state.folder_path

# Smoke test result: PASS - All Phase 1 dataclasses working correctly
```

---

## Done criteria

- [x] All 6 dataclasses importable with no errors
- [x] `PipelineState.save()` + `load()` round-trip passes
- [x] `get_config()` returns correct bands for all 3 doc sizes
- [x] `ConversationHistory._trim()` correctly drops oldest turn when over budget
- [x] All unit tests pass

## Implementation Notes

**Files created:**
- [pipeline/state/pipeline_state.py](pipeline/state/pipeline_state.py) — FileMetadata + PipelineState (35 fields, 8 methods)
- [pipeline/state/chunking_config.py](pipeline/state/chunking_config.py) — ChunkingConfig dataclass + get_config() factory (9x9 configuration matrix)
- [pipeline/state/conversation.py](pipeline/state/conversation.py) — ConversationTurn + ConversationHistory with token budgeting
- [pipeline/state/retrieval_result.py](pipeline/state/retrieval_result.py) — RetrievalResult with strip_debug() for production

**Key design decisions:**
- All dataclasses use `@dataclass` decorator with `field(default_factory=...)` for mutable defaults
- JSON serialization excludes private fields (`_model_instance`, `_collection`) — reloaded from state on startup
- ChunkingConfig uses 9x9 matrix: 3 doc bands × 3 collection bands = 9 configurations
- ConversationHistory._trim() strategy: compress oldest turn first (via LLM in production), then drop if needed
- RetrievalResult.to_dict() accepts include_debug flag for dev/prod modes
