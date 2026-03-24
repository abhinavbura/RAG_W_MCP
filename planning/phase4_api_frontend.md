# Phase 4 — API & Frontend

**Estimated time:** 3–4 days  
**Status:** 🔴 Not Started  
**Dependencies:** Phase 1 + 2 + 3 complete

---

## Goal

Build the FastAPI backend (4 endpoints + SSE), React frontend (upload UI + chat), and MCP server (3 tools). At the end of this phase, the full system is usable end-to-end from a browser.

---

## Tasks

### 4.1 FastAPI Backend

#### Setup
- [ ] `FastAPI()` app with CORS middleware (allow localhost:5173)
- [ ] `DATASET_PATH` env variable, default `./dataset`
- [ ] `PROCESSED_PATH` = `{DATASET_PATH}/processed/`
- [ ] ConversationHistory store: `Dict[str, ConversationHistory]` in memory, keyed by `conversation_id`
- [ ] Load PipelineState on startup if `.rag_state.json` exists

#### POST /ingest
- [ ] Accept `List[UploadFile]`
- [ ] Validate extensions — reject non .md/.txt/.pdf with HTTP 400
- [ ] Stream save to `dataset/` with `shutil.copyfileobj` (never loads full file into memory)
- [ ] Kick off `ingest_folder()` as background task (`BackgroundTasks`)
- [ ] Return `{status: "accepted", files_received: [...]}`

#### POST /query
- [ ] Body: `{query: str, conversation_id: str}`
- [ ] Load or create `ConversationHistory` for `conversation_id`
- [ ] Call `retrieve(query, state, history)`
- [ ] Call `LLMRouter.call("answer", prompt)` — prompt includes chunks as context
- [ ] Append `ConversationTurn` to history
- [ ] Return `{answer, chunks, intent, scope, total_tokens}`

#### GET /state
- [ ] Return serialised `PipelineState`:
  - `collection_count`, `model_key`, `ingested_files`, `skipped_files`, `failed_files`
  - `total_chunks_added`, `model_upgrade_warning` (if set)
  - `llm_tokens_used_deepseek`, `llm_tokens_used_gpt`

#### GET /ingest/progress (SSE)
- [ ] Server-Sent Events stream
- [ ] Yield one event per file during ingestion: `{filename, status, chunks_added, error}`
- [ ] Yield final summary event on completion: `{total_ingested, total_skipped, total_failed, collection_count}`
- [ ] Use `EventSourceResponse` from `sse-starlette`

### 4.2 React Frontend

#### Upload UI
- [ ] Drag-and-drop file zone (accept .md, .txt, .pdf only)
- [ ] POST to `/ingest` as `multipart/form-data`
- [ ] Connect to `/ingest/progress` SSE stream after upload
- [ ] Display per-file status in real time: filename, status icon, chunk count
- [ ] Final summary: "X files ingested, Y skipped, Z failed"

#### Chat Interface
- [ ] Query input (text box + submit button)
- [ ] Sends POST to `/query` with `conversation_id` (persist in localStorage or session)
- [ ] Displays streamed / returned answer
- [ ] Source chunks panel below answer: shows `anchor`, `source_doc`, `text` snippet per chunk
- [ ] Intent badge display (Fact / Summary / Comparison / Conversational)

#### State Monitor (optional panel)
- [ ] Polls GET `/state` on load
- [ ] Shows collection count, model key, `model_upgrade_warning` if present

### 4.3 MCP Server — 3 tools

#### Setup
- [ ] `FastMCP` or `mcp.server` app on `:8001`
- [ ] Import and reuse pipeline internals (same PipelineState, same `retrieve()`)

#### search_documents
- [ ] Signature: `search_documents(query: str, source_doc: str = None, section: str = None) -> list[dict]`
- [ ] Calls `retrieve()` internally
- [ ] Passes optional `source_doc` / `section` as scope override
- [ ] Returns list of chunk dicts (without debug fields)

#### get_document_sections
- [ ] Signature: `get_document_sections(source_doc: str = None) -> list[dict]`
- [ ] Queries ChromaDB metadata for distinct `section` values
- [ ] Returns `[{source_doc, section, chunk_count}]`
- [ ] Optional `source_doc` filter

#### get_collection_stats
- [ ] Signature: `get_collection_stats() -> dict`
- [ ] Returns `{total_chunks, model_key, model_dims, docs_ingested, collection_name}`

---

## File Structure

```
backend/
  main.py               # FastAPI app, all 4 endpoints
  conversation_store.py # Dict[str, ConversationHistory] manager

frontend/
  src/
    components/
      UploadZone.jsx
      ProgressMonitor.jsx
      ChatInterface.jsx
      SourceChunksPanel.jsx
      StateBadge.jsx
    App.jsx
    main.jsx
  index.html
  package.json
  vite.config.js

mcp_server/
  server.py             # MCP app + 3 tool definitions
```

---

## Testing

### FastAPI unit tests (pytest + httpx)

| Test | What to verify |
|---|---|
| POST /ingest with valid files | Returns 200, `files_received` count matches |
| POST /ingest with .exe file | Returns HTTP 400 |
| POST /query with new `conversation_id` | Creates new history, returns answer |
| POST /query same `conversation_id` | Reuses existing history, excluded_ids active |
| GET /state | Returns dict with `collection_count`, `model_key` |
| GET /ingest/progress | SSE stream emits per-file events |

```bash
# Run FastAPI tests
pytest backend/tests/ -v
```

### MCP tool smoke tests

```python
from mcp_server.server import search_documents, get_collection_stats, get_document_sections

stats = get_collection_stats()
assert stats["total_chunks"] > 0

sections = get_document_sections()
assert len(sections) > 0

results = search_documents("refund policy")
assert len(results) > 0
assert "text" in results[0]
print("MCP tools smoke test passed")
```

### End-to-end browser test

1. Start backend: `uvicorn backend.main:app --reload --port 8000`
2. Start frontend: `npm run dev` (port 5173)
3. Upload `test.md` via drag-and-drop
4. Watch SSE progress stream in UI — verify file appears as "ingested"
5. Query: "What is the refund policy?" — verify answer + source chunks panel
6. Second query in same session: "What about the 7-day window?" — verify conversational context
7. GET /state — verify `collection_count` increased, `ingested_files` list populated

---

## Done criteria

- [ ] POST /ingest rejects non-allowed extensions with HTTP 400
- [ ] SSE progress stream emits per-file events during ingestion
- [ ] POST /query returns answer + chunk context for all 4 intent types
- [ ] `conversation_id` maintains turn history across multiple queries
- [ ] React upload UI shows real-time SSE status per file
- [ ] React chat shows source chunks panel with anchor + snippet
- [ ] All 3 MCP tools return correctly structured responses
- [ ] End-to-end: upload → ingest → query → answer fully working in browser
