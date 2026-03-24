# RAG Pipeline

Architecture & Design Document — Final Draft  
Last updated: Tue Mar 24 2026 · Status: Ready to Build

## Build Status

| Component                      | Status        | Notes                                                                 |
|--------------------------------|---------------|------------------------------------------------------------------------|
| PipelineState                  | **Planned**   | Full dataclass specced — 35 attrs across 6 groups, JSON/Redis-ready   |
| FileMetadata                   | **Planned**   | Per-file: path, type, size_chars, hash, status, chunks_added, error   |
| ChunkingConfig                 | **Planned**   | Dynamic dataclass — params driven by doc size band                     |
| ConversationTurn               | **Planned**   | query, intent, chunks, token_count, timestamp                          |
| ConversationHistory            | **Planned**   | Rolling window, token budget, LLM compression fallback                 |
| RetrievalResult                | **Planned**   | Typed return from retrieve() — 13 fields                               |
| LLMRouter                      | **Planned**   | DeepSeek + GPT-4o mini, 3 routing triggers, budget tracking            |
| detect_structure()             | **Done**      | Two-zone sampling, 5 heading heuristics, returns structured/flat       |
| _is_heading_line()             | **Done**      | Markdown markers, numbered, ALL CAPS, Title Case, colon-terminated     |
| _heading_level()               | **Done**      | Maps heuristic signals to level 1 (section) or level 2 (subsection)    |
| _clean_heading()               | **Done**      | Strips ## / numbering / trailing colons from heading text              |
| chunk_markdown()               | **In Progress** | Needs ChunkingConfig wired in + new metadata fields                  |
| chunk_txt_structured()         | **Done**      | Heuristic heading detection, shared schema output                      |
| chunk_txt_semantic()           | **Done**      | Sentence embeddings, percentile similarity drops, sentence overlap     |
| chunk_document()               | **Done**      | Dispatcher — routes by file_type + detect_structure result             |
| get_config()                   | **Done**      | Dynamic params from doc size (chunking) + collection size (retrieval)  |
| ingest_folder()                | **Planned**   | Four-phase entry point — scan, model select, per-file loop, finalise   |
| read_pdf()                     | **Planned**   | pymupdf text extraction, skip image pages < 20 chars                   |
| read_txt() / read_md()         | **Planned**   | UTF-8 read with error ignore                                           |
| _hash_file()                   | **Planned**   | MD5 per file, compared against .rag_hashes.json                        |
| _archive_file()                | **Planned**   | Move to dataset/processed/ after successful ingest                     |
| retrieve()                     | **In Progress** | 7-stage pipeline, needs RetrievalResult + LLMRouter wired in         |
| _classify_intent()             | **Done**      | Regex primary — fact/summary/comparison/conversational. LLM fallback.  |
| _detect_scope()                | **Planned**   | Keyword match on source_doc stems from state.files_metadata            |
| _extract_sections_llm()        | **Planned**   | DeepSeek call, JSON response {section_a, section_b}                    |
| _rerank()                      | **Done**      | 5 signals: heading match, chunk_type, confidence, position, token gate |
| _mmr()                         | **Done**      | Section-overlap redundancy proxy, lambda from config                   |
| FastAPI — POST /ingest         | **Planned**   | Multipart upload, saves to dataset/, triggers ingest_folder()          |
| FastAPI — POST /query          | **Planned**   | Query + conversation_id, returns answer + RetrievalResult              |
| FastAPI — GET /state           | **Planned**   | Returns PipelineState (collection count, model, ingested files)        |
| FastAPI — GET /ingest/progress | **Planned**   | SSE stream — per-file status during ingestion                          |
| MCP — search_documents         | **Planned**   | Tool wrapper around retrieve()                                         |
| MCP — get_document_sections    | **Planned**   | Returns known sections from ChromaDB metadata                          |
| MCP — get_collection_stats     | **Planned**   | chunk count, model_key, docs_ingested                                  |
| React — Upload UI              | **Planned**   | Drag/drop files, POST /ingest, progress monitor via SSE                |
| React — Chat interface         | **Planned**   | Query input, streamed answer, source chunks panel                      |

## 1. System Overview

A folder-ingestion RAG pipeline that auto-detects document structure, routes to the appropriate chunking strategy, selects the best embedding model based on cumulative folder size, and uses a dual-LLM routing layer for cost optimisation. A single ChromaDB collection holds all documents. A React frontend provides upload, chat, and monitoring. An MCP server exposes retrieval as LLM-callable tools.

### Design principles

- One schema everywhere — markdown, structured TXT, semantic TXT, and PDF all emit the same 11-field chunk dict. Retrieval is agnostic to source.
- Dynamic configuration — individual doc size drives chunk size and overlap. Live collection size drives k and MMR lambda at query time.
- One embedding model per collection — selected from cumulative folder size at first ingest, then locked to collection metadata. Prevents vector space mismatch.
- Crash recovery by design — PipelineState saved after every file. Hash store only updated after successful archive. Pipeline restarts exactly where it left off.
- LLM cost split — simple structured tasks (extraction, classification fallback, history compression) routed to DeepSeek R1 free. User-facing answer generation routed to GPT-4o mini.
- Expandable by layer — new capabilities added as MCP tools without touching FastAPI or React. Redis swapped in for JSON state without touching pipeline code.

## 2. Project Structure

All file-handling is rooted in `dataset/`. The pipeline scans it recursively — flat files and subfolders both supported. Uploaded files are archived to `dataset/processed/` after successful ingestion. Failed files stay in `dataset/` and are retried on the next run.

### Folder layout

> project/  
>   dataset/ ← UI uploads land here  
>   blinkit_tnc.md  
>   knowledge_base.txt  
>   books/ ← subfolders supported  
>   ml_textbook.pdf  
>   processed/ ← archived after successful ingest  
>   blinkit_tnc.md  
>   .rag_hashes.json ← auto-generated, tracks file hashes  
>   .rag_state.json ← auto-generated, full pipeline state  
>   chroma_db/ ← ChromaDB persistent storage  
>   backend/ ← FastAPI application  
>   frontend/ ← React application  
>   mcp_server/ ← MCP tool definitions  
>   pipeline/ ← all RAG pipeline code  
>     chunkers/  
>     retrieval/  
>     state/  
>     llm/

### File lifecycle

- Upload — React sends multipart POST /ingest. FastAPI validates extension (.md .txt .pdf only — reject others with HTTP 400). Saves to dataset/ using streaming write (`shutil.copyfileobj` — never loads full file into memory).
- Hash check — `ingest_folder()` scans dataset/ recursively. MD5 of each file compared against `.rag_hashes.json`. New and changed files proceed. Unchanged files skipped entirely.
- Ingest — read → detect structure → get_config → chunk → embed → store. State saved after each file. Progress streamed via SSE to frontend.
- Archive — file moved to `dataset/processed/` after successful ChromaDB store. Hash store entry written only after successful archive. Failed files stay in `dataset/` — retried next run.
- Re-upload — same filename, changed content → hash changes → re-ingest triggered → old chunks deleted from ChromaDB by `source_doc` filter → new chunks stored → file archived.
- `source_doc` field uses relative path (e.g. `books/ml_textbook.pdf`) not just filename — prevents collisions when two files share a name across subfolders.

### FastAPI file handling decisions

| Item                | Detail                                                                                     |
|---------------------|--------------------------------------------------------------------------------------------|
| DATASET_PATH        | Env variable, defaults to ./dataset — overridable for deployment                           |
| PROCESSED_PATH      | dataset/processed/ — mirrors subfolder structure of original                               |
| Allowed types       | .md .txt .pdf — rejected at upload with HTTP 400 before hitting pipeline                   |
| Duplicate uploads   | Overwrite in dataset/ — hash change triggers automatic re-ingest                           |
| Large file uploads  | Streaming save via shutil.copyfileobj — never loads file into memory                       |
| Failed file policy  | Stays in dataset/ — not archived, retried on next ingest run                               |
| Archive condition   | Only after successful ChromaDB store AND hash write — not on partial success               |

## 3. Data Models

Six dataclasses form the backbone of the pipeline. All are JSON-serialisable. Private runtime fields (prefixed `_`) are never serialised — reloaded on startup.

### 3.1 PipelineState

Single source of truth for all runtime state. Saved to `dataset/.rag_state.json` after every file ingest. Redis-ready — swap `save()` and `load()` methods only.

| Group        | Attribute                | Type                   | Description                                                                 |
|-------------|--------------------------|------------------------|-----------------------------------------------------------------------------|
| Folder      | folder_path              | str                    | Absolute path to input folder                                               |
| Folder      | total_files              | int                    | Total supported files found in folder                                       |
| Folder      | total_size_chars         | int                    | Cumulative chars across ALL files — drives model selection                  |
| Folder      | files_metadata           | list\[FileMetadata]    | One FileMetadata object per file in folder                                  |
| Folder      | files_to_ingest          | list\[str]             | Paths of new + changed files only                                           |
| Model       | model_key                | str                    | "nomic" or "bge-large" — one key for whole collection                       |
| Model       | model_name               | str                    | Full HuggingFace model identifier                                           |
| Model       | model_dims               | int                    | 768 for nomic, 1024 for bge-large                                           |
| Model       | model_ctx_tokens         | int                    | Max input tokens — 8192 nomic, 512 bge-large                                |
| Model       | requires_prefix          | bool                   | True for nomic, False for bge-large                                         |
| Model       | query_prefix             | str                    | "search_query: " for nomic, "" for bge-large                                |
| Model       | doc_prefix               | str                    | "search_document: " for nomic, "" for bge-large                             |
| Model       | model_source             | str                    | "computed" (new collection) or "collection_metadata" (existing)             |
| ChromaDB    | collection_name          | str                    | Defaults to "rag_pipeline"                                                  |
| ChromaDB    | db_path                  | str                    | Path to ChromaDB persistent storage                                         |
| ChromaDB    | collection_exists        | bool                   | Whether collection existed before this run                                  |
| ChromaDB    | collection_count         | int                    | Live chunk count — updated after every file ingest                          |
| Current file| current_doc              | str                    | Relative path of file being processed                                       |
| Current file| current_doc_size         | int                    | Char count of current file                                                  |
| Current file| current_doc_band         | str                    | "small" / "medium" / "large"                                               |
| Current file| current_structure        | str                    | "structured" or "flat"                                                     |
| Current file| current_chunker          | str                    | "markdown" / "structured" / "semantic"                                     |
| Current file| current_config           | dict                   | ChunkingConfig serialised as dict                                           |
| Session     | session_id               | str                    | 8-char MD5 hash — identifies this run for logging                           |
| Session     | session_started_at       | str                    | ISO 8601 timestamp                                                          |
| Session     | ingested_files           | list\[str]             | Filenames successfully ingested this session                                |
| Session     | skipped_files            | list\[str]             | Filenames skipped — unchanged hash                                          |
| Session     | failed_files             | list\[tuple]           | (filename, reason) for every errored file                                   |
| Session     | total_chunks_added       | int                    | Running total of chunks added this session                                  |
| Session     | model_upgrade_warning    | str                    | Non-empty if folder size now warrants bge-large but collection is locked    |
| LLM Budget  | llm_tokens_used_deepseek | int                    | Running token total for DeepSeek this session                               |
| LLM Budget  | llm_tokens_used_gpt      | int                    | Running token total for GPT-4o mini this session                            |
| LLM Budget  | llm_budget_gpt           | int                    | Max GPT tokens per session — configurable, default 50000                    |
| LLM Budget  | llm_calls_by_task        | dict                   | Call count per task type — for cost analysis and debugging                  |
| BM25        | enable_bm25              | bool                   | Feature flag — False until BM25 is implemented                              |
| BM25        | bm25_index               | Any                    | In-memory rank_bm25 index — None until built                                |

Private fields (never serialised): `_model_instance` (loaded SentenceTransformer), `_collection` (ChromaDB collection object). Both are reloaded from state fields on startup.

### 3.2 FileMetadata

One instance per file in the folder. Stored in `PipelineState.files_metadata`. Serialised as part of state JSON.

| Field         | Description                                         |
|---------------|-----------------------------------------------------|
| path          | Absolute file path                                  |
| file_type     | "md" \| "txt" \| "pdf"                              |
| size_chars    | Character count after text extraction               |
| hash          | MD5 of raw file bytes — used for change detection   |
| status        | "new" \| "changed" \| "unchanged" \| "failed" \| "ingested" |
| chunks_added  | Number of chunks successfully stored for this file  |
| error         | Error message string — populated when status="failed" |

### 3.3 ChunkingConfig

Returned by `get_config(text, chunk_count)`. Chunking parameters are driven by individual document size. Retrieval parameters are driven by live collection chunk count. Both are independent axes.

| Parameter            | Small doc / coll                | Medium doc / coll                | Large doc / coll                 |
|----------------------|----------------------------------|----------------------------------|----------------------------------|
| Doc size threshold   | < 100K chars (~10 pages)        | < 500K chars (~50 pages)         | 500K+ chars (400+ pages)         |
| Collection threshold | < 200 chunks                    | < 1000 chunks                    | 1000+ chunks                     |
| max_chars            | 1000                            | 1500                            | 2000                             |
| overlap_chars        | 100                             | 150                             | 200                              |
| min_tokens           | 60                              | 80                              | 100                              |
| max_tokens           | 300                             | 400                             | 500                              |
| overlap_sentences    | 1                               | 2                               | 3                                |
| drop_percentile      | 70                              | 75                              | 80                               |
| k_fact               | 3                               | 4                               | 5                                |
| k_summary            | 6                               | 8                               | 12                               |
| k_compare            | 4                               | 5                               | 8                                |
| k_conversational     | 3                               | 4                               | 5                                |
| mmr_lambda           | 0.7                             | 0.6                             | 0.5                              |

`drop_percentile` increases for larger docs because denser content has higher baseline sentence similarity — a higher bar is needed to identify genuine topic shifts. `mmr_lambda` decreases for larger collections because redundancy is a real problem in books — chapters revisit earlier ideas, and diversity must be pushed harder.

### 3.4 ConversationTurn and ConversationHistory

Separate from PipelineState — one ConversationHistory per user conversation, passed into `retrieve()` alongside state. Not stored in the pipeline state file.

**ConversationTurn fields**

| Field        | Description                                                                    |
|--------------|--------------------------------------------------------------------------------|
| query        | Original query string for this turn                                            |
| intent       | Classified intent — fact / summary / comparison / conversational              |
| chunks       | List of retrieved chunk dicts for this turn                                   |
| token_count  | Sum of chunk `token_count`s for this turn — used for budget tracking          |
| timestamp    | ISO 8601 timestamp                                                            |

**ConversationHistory behaviour**

- Maintains an ordered list of ConversationTurn objects.
- `max_tokens` budget (default 1500) — enforced as sum of all turn token_counts.
- `add_turn()` appends the new turn then immediately calls `_trim()`.
- `_trim()` strategy — if total tokens exceed budget: first attempt LLM compression of the oldest turn via DeepSeek (summarise to ~100 tokens). If still over budget after compression, drop the oldest turn entirely.
- `excluded_ids()` — returns all chunk IDs across all turns. Passed to retriever so already-seen chunks are never re-fetched in subsequent turns.
- `recent_chunks(n=2)` — returns all chunks from the last N turns. Injected as context for conversational queries so the LLM can resolve references like "that 7-day window you mentioned".
- Token budget uses `token_count` from chunk schema — no re-counting at retrieval time.

### 3.5 RetrievalResult

Typed return object from `retrieve()`. The LLM caller only needs chunks and total_tokens. All other fields support routing decisions and debugging. Debug fields (`scores_before`, `scores_after`, `latency_ms`) should be stripped in production.

| Field          | Description                                                                                                 |
|----------------|-------------------------------------------------------------------------------------------------------------|
| chunks         | Final ranked list of chunk dicts — what gets sent to the LLM as context                                     |
| query          | Original query string                                                                                       |
| intent         | Classified intent for this query                                                                            |
| scope          | Detected `source_doc` name if auto-detected, None if searched all docs                                      |
| sections       | \[section_a, section_b] for comparison intent, None for all others                                         |
| k              | Number of chunks requested                                                                                  |
| model_key      | Embedding model used — must match at query time                                                             |
| filter_applied | True if a ChromaDB where clause was used                                                                    |
| total_tokens   | Sum of `token_count` across all returned chunks — for LLM context budgeting                                 |
| total_fetched  | Candidate count before re-ranking (debug)                                                                  |
| scores_before  | Cosine similarity scores before re-rank adjustment (debug)                                                 |
| scores_after   | Final adjusted scores after re-rank (debug)                                                                |
| latency_ms     | Total wall-clock retrieval time in milliseconds (debug)                                                    |

## 4. Ingestion Pipeline

Entry point: `ingest_folder(folder_path)`. Four sequential phases. PipelineState is saved after every individual file — if the process crashes, the next run resumes exactly where it left off. Only successfully ingested and archived files are written to the hash store.

### 4.1 Phase 1 — Scan folder

- Walk dataset/ recursively using `rglob("*")`. Filter to .md, .txt, .pdf extensions only.
- Per file: extract text (type-specific reader), compute `len(text)` as `size_chars`, compute MD5 hash of raw bytes.
- Compare hash against `.rag_hashes.json` — classify each file as new, changed, or unchanged.
- Sum `size_chars` across ALL files including unchanged — cumulative total used for model selection in Phase 2.
- Populate `state.files_metadata` with one FileMetadata per file. Populate `state.files_to_ingest` with only new + changed paths.

### 4.2 Phase 2 — Model selection

- Check if ChromaDB collection already exists.
- If collection exists: read `model_key` from collection metadata. Existing model always wins — never recompute from folder size on re-ingest. This prevents vector space mismatch.
- If new collection: select model from cumulative `total_size_chars`. Under 500K chars → `nomic-ai/nomic-embed-text-v1.5`. Over 500K chars → `BAAI/bge-large-en-v1.5`.
- If folder now warrants bge-large but collection is locked to nomic: set `state.model_upgrade_warning` with message explaining the situation. Do not change the model.
- Load model via `_get_or_load_model()` — cached in module-level `_MODEL_CACHE` dict. Never reloaded across files in the same session.
- Store `model_key`, `model_name`, `model_dims` in ChromaDB collection metadata on first creation.
- Initialise ChromaDB `PersistentClient`. Get or create collection with `hnsw:space = "cosine"`.

### 4.3 Phase 3 — Per-file loop

Runs only for files in `files_to_ingest`. Each file is fully independent — failure of one does not affect others.

- Read file — `read_md()` or `read_txt()` (UTF-8, errors=ignore) / `read_pdf()` (pymupdf text layer only).
- `read_pdf()`: call `page.get_text("text")` per page. Skip pages where extracted text < 20 chars (image-only or scanned pages). Strip lines under 3 chars (image artifact noise). Raise `ValueError` if no pages yield text.
- Refresh all `current_*` fields on state via `set_current_file()`.
- Call `get_config(text=text)` → ChunkingConfig for this file based on its individual size.
- Call `detect_structure(text)` → "structured" or "flat".
- Call `chunk_document(text, source_doc, file_type)` → list of chunk dicts. `source_doc` is relative path from dataset/ root.
- Pop `text_for_embedding` from each chunk dict. This field is used only for embedding — never stored in ChromaDB.
- Batch embed all chunks via `embed_documents(embed_texts, state)`. Applies `doc_prefix` if `requires_prefix` is True.
- Delete old chunks: query ChromaDB with `where={"source_doc": {"$eq": source_doc}}`. Delete all returned IDs. This handles the re-ingest / update case cleanly.
- Call `collection.add(ids, embeddings, documents, metadatas)`.
- Archive: move file to `dataset/processed/` preserving subfolder structure.
- Update hash store entry for this file. Call `state.record_ingested()`. Call `state.save()`.
- On any exception: call `state.record_failed(filename, str(e))`. Log warning. Continue to next file. Do not update hash store for failed file.

### 4.4 Phase 4 — Finalise

- Save final `.rag_hashes.json` with all successfully archived files.
- Call `state.update_collection_count()` to get live chunk count from ChromaDB.
- Save final `.rag_state.json`.
- Log summary — ingested count, skipped count, failed count, total chunks added, collection total.
- Return PipelineState — used directly by `retrieve()` and FastAPI endpoints.

## 5. Chunking Strategy

### 5.1 Structure detection — detect_structure()

Samples two zones of the document rather than just the top — handles documents with long preambles before the first heading.

| Item              | Detail                                                                                   |
|-------------------|------------------------------------------------------------------------------------------|
| Zone 1            | First 50 non-empty lines                                                                 |
| Zone 2            | Middle 50 non-empty lines (centred at total_lines / 2)                                  |
| Heading score     | heading_lines / total_lines_sampled per zone                                            |
| Decision          | Take peak score across both zones. If ≥ 0.05 → "structured". Else → "flat".            |
| Threshold         | 0.05 — at least 1 in 20 sampled lines must look like a heading                          |
| MAX_HEADING_LEN   | 60 characters — lines longer than this are never headings                               |

**Heading heuristics — _is_heading_line()**

- Markdown markers — line starts with `#`, `##`, or `###` (unambiguous, always heading).
- Numbered patterns — matches `1. / 1.1 / 1.1.1 / Section N / Chapter N` via regex (case-insensitive).
- ALL CAPS — `line.isupper()` is True and length ≥ 3 characters (prevents "OK" or "ID" triggering).
- Title Case — `line.istitle()` is True and word count ≥ 2 (prevents single capitalised words triggering).
- Colon-terminated — line ends with ":" and word count ≤ 6 (e.g. "Refund Policy:").

The heuristic is deliberately conservative — it would rather miss a heading than falsely split a sentence. False positives (calling body text a heading) cause worse retrieval damage than false negatives.

### 5.2 Three chunkers — identical output schema

| Chunker                 | Trigger condition                      | Boundary detection                                                | chunk_type emitted |
|-------------------------|----------------------------------------|-------------------------------------------------------------------|--------------------|
| chunk_markdown()        | file_type = "md"                       | `##` and `###` markers — unambiguous, no heuristic needed         | "headed"           |
| chunk_txt_structured()  | txt or pdf + structure="structured"   | `_is_heading_line()` + `_heading_level()` + `_clean_heading()`    | "headed"           |
| chunk_txt_semantic()    | txt or pdf + structure="flat"         | Cosine similarity drops between sentence embeddings               | "semantic"         |

**chunk_txt_structured() design**

- `_heading_level()` maps heuristic signals to level 1 (section) or level 2 (subsection) — mirrors `##` vs `###` from markdown chunker.
- `_clean_heading()` strips `##` markers, numbered prefixes (1. / 1.1), Section/Chapter labels, and trailing colons before storing heading text.
- Flushes buffer on every high-confidence heading. Carries `OVERLAP_CHARS` from config into next chunk.
- `heading_confidence` is always "high" — this chunker only runs when `detect_structure()` confirmed the document is structured.

**chunk_txt_semantic() design**

- Split text into sentences via regex `(?<=[.!?])\s+(?=[A-Z])` plus hard splits on newlines (paragraph breaks are always boundaries).
- Embed all sentences in one batched `model.encode()` call (`batch_size=32`) — never sentence-by-sentence.
- `_find_boundaries()`: compute cosine similarity between each adjacent sentence pair. Threshold = `DROP_PERCENTILE` percentile of all similarities for that document. Boundaries are indices where similarity falls below threshold. Threshold is relative to each document — adapts to content density.
- `_group_into_chunks()`: merge sentence groups using boundaries as preferred splits. Enforce `MAX_TOKENS` ceiling by force-splitting oversized groups at sentence boundaries. Enforce `MIN_TOKENS` floor by merging undersized groups with next neighbour.
- Overlap carries last `OVERLAP_SENTENCES` sentences from previous group — more semantically coherent than character-level overlap for prose.
- `heading_confidence` is always "none" — flat docs have no reliable headings by definition.

### 5.3 Chunk schema — 11 fields

All chunkers emit this exact dict. `text_for_embedding` is used at embed time then popped — never stored in ChromaDB.

| Field               | Description                                                                                                                     |
|---------------------|---------------------------------------------------------------------------------------------------------------------------------|
| id                  | `{source_doc}_{section_idx:02d}_{subsection_idx:02d}_{chunk_idx:02d}`                                                           |
| text                | Raw chunk body — used for display and citation in UI                                                                           |
| text_for_embedding  | Heading prepended to body (e.g. `Refund Policy\n\nThe base tier...`). Embed this, not `text`. Popped before ChromaDB store.   |
| section             | Top-level section heading or empty string                                                                                       |
| subsection          | Subsection heading or empty string                                                                                              |
| anchor              | `"Section > Subsection"` human-readable path — display and citation only                                                       |
| source_doc          | Relative path from dataset/ root (e.g. `"books/ml_textbook.pdf"`)                                                               |
| chunk_type          | "headed" (structural boundary) \| "semantic" (similarity drop) \| "free_form" (short, no heading)                              |
| heading_confidence  | "high" (structural chunkers) \| "low" (ambiguous) \| "none" (semantic chunker)                                                 |
| position_ratio      | 0.0–1.0 float — position of chunk in document. 0.0 = start, 1.0 = end                                                          |
| token_count         | `tiktoken` cl100k_base token count of `text` field — used for context budgeting and token gate in re-ranker                    |

Metadata audit: 7 of 11 fields are actively used in retrieval logic. `token_count` and `anchor` are passive but justified. `text_for_embedding` is ingestion-only. `heading_confidence` is wired into re-ranker score (+0.05 bonus for "high").

## 6. Retrieval Strategy

Entry point: `retrieve(query, state, history)`. Query is embedded once using the model stored in PipelineState and the vector reused across all stages. Seven stages run in sequence.

### 6.1 Seven-stage pipeline

| Stage              | Name + driver                   | Detail                                                                                                                                                                                                                                                                  |
|--------------------|---------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 0 — Embed query    | Model from PipelineState        | Read `model_key`, `requires_prefix`, `query_prefix` from state. Apply prefix if needed. Single `model.encode()` call. Vector reused across all downstream stages.                                                                                                      |
| 1 — Classify intent| Regex primary, LLM fallback     | Patterns match fact / summary / comparison / conversational. If regex returns ambiguous result, make a DeepSeek call. Drives k value and post-processing path.                                                                                                         |
| 2 — Detect scope   | Keyword match on state          | Tokenise each `source_doc` stem (e.g. `"ml_textbook"` → \["ml","textbook"\]). Match against query words. Confident match → pin `filter_source`. No match → search whole collection.                                                                                    |
| 3 — Build filters  | Intent + scope                  | Construct ChromaDB where clause. Scope match → `source_doc` filter. Comparison intent → call `_extract_sections_llm()` → two section filters for separate sub-queries. Conversational → collect `excluded_ids` from history.                                            |
| 4 — Cosine search  | ChromaDB                        | Pass query vector directly — skip re-embedding. Fetch k×3 for summary (MMR needs headroom), k×2 for all others. Comparison fires two separate queries (one per section), merges results.                                                                                |
| 5 — Re-rank        | Pure Python score adjustment    | Five signals applied to every candidate. Results sorted descending by adjusted score. See Section 6.2 for signal weights.                                                                                                                                              |
| 6 — Post-process   | Intent-specific                 | Different final step per intent. See Section 6.3 for detail.                                                                                                                                                                                                           |

### 6.2 Re-ranking signals

| Signal                    | Detail                                                                                                       |
|---------------------------|--------------------------------------------------------------------------------------------------------------|
| +0.15 heading match       | Any query word appears in section or subsection name of the chunk. Most impactful signal.                   |
| +0.05 chunk_type          | `chunk_type = "headed"`. Small bonus over "semantic" or "free_form" chunks.                                 |
| +0.05 heading_confidence  | `heading_confidence = "high"`. Rewards chunks from structured sections.                                     |
| -0.05 position penalty    | `position_ratio < 0.05` or `> 0.95`. Penalises intro boilerplate and appendix material.                      |
| -0.10 token gate          | `token_count > model_ctx_tokens`. Chunk was truncated at embed time — vector is less reliable. Applied as penalty not hard drop. |

### 6.3 Intent-specific post-processing

| Intent        | Behaviour                                                                                                                                                                 |
|---------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| fact          | top-k by adjusted score. No MMR. Precision over diversity. `k = k_fact` from config.                                                                                      |
| summary       | MMR with `mmr_lambda` from config (0.7 small → 0.5 large). Redundancy approximated by section overlap — no extra embedding calls at query time. Deduplicates by section after MMR. |
| comparison    | Two separate ChromaDB queries — one per extracted section. k/2 results from each. Interleaved in final result list. Guarantees equal representation from both sides.     |
| conversational| Drop chunk IDs in `history.excluded_ids()`. Prepend `history.recent_chunks(n=2)` as context. Trim to token budget using `token_count` sum. `k = k_conversational`.        |

### 6.4 Dynamic k — driven by live collection count

| Collection size                | Settings                                                                                     |
|--------------------------------|----------------------------------------------------------------------------------------------|
| Small collection (< 200 chunks)| k_fact=3, k_summary=6, k_compare=4, k_conversational=3, mmr_lambda=0.7                      |
| Medium collection (< 1000)     | k_fact=4, k_summary=8, k_compare=5, k_conversational=4, mmr_lambda=0.6                      |
| Large collection (1000+)       | k_fact=5, k_summary=12, k_compare=8, k_conversational=5, mmr_lambda=0.5                     |

### 6.5 BM25 hybrid search — stubbed

BM25 is designed in but not yet implemented. The hook is present in PipelineState (`enable_bm25` flag, `bm25_index` field). When built, it will use the `rank_bm25` Python library as an in-memory index alongside ChromaDB.

- BM25 will only activate for fact intent queries — not summary, conversational, or fiction content.
- Fusion strategy: Reciprocal Rank Fusion (RRF). Score = `1/(k + bm25_rank) + 1/(k + vector_rank)` where k=60. No score normalisation needed.
- Trigger: add only if exact-term fact lookups test poorly after the pipeline is live. Legal terms, clause numbers, and proper nouns are the expected failure cases for pure cosine search.

## 7. Embedding Model

### 7.1 Model registry

|                      | **nomic-embed-text-v1.5**         | **bge-large-en-v1.5**             | **text-embedding-3-small**           |
|----------------------|------------------------------------|-----------------------------------|--------------------------------------|
| Provider             | Nomic AI (HuggingFace)            | BAAI (HuggingFace)                | OpenAI API                           |
| Dimensions           | 768                                | 1024                              | 1536                                 |
| Max ctx tokens       | 8192                               | 512                               | 8191                                 |
| Requires prefix      | Yes                                | No                                | No                                   |
| RAM required         | ~550MB                             | ~1.3GB                            | N/A (API)                            |
| Cost                 | Free (local)                       | Free (local)                      | ~$0.002/1M tokens                    |
| When used            | Phase 1 — folder < 500K chars      | Phase 2 — folder ≥ 500K chars     | Optional API fallback                |
| Quality vs bge-large | Slightly lower (~3–5%)             | Best local MTEB scores            | ~8% better than bge-large            |
| trust_remote_code    | True (required)                    | False                             | N/A                                  |

### 7.2 Model selection logic

- Cumulative folder size (`total_size_chars`) is computed in Phase 1 of ingestion — sum of all files including unchanged ones.
- Under 500K chars → nomic. Rationale: best size/quality ratio, 8192 token context handles long chunks well, fast on CPU.
- 500K chars and over → bge-large. Rationale: best MTEB retrieval benchmark scores for mixed-domain content, handles technical textbooks and fiction equally well.
- On re-ingest: `model_key` read from ChromaDB collection metadata. Existing model always wins. `model_source` field set to `"collection_metadata"`.
- If folder has grown past threshold but collection is locked: `model_upgrade_warning` set in state. User must manually wipe collection and re-ingest all files to upgrade model.

### 7.3 Model cache

- Module-level `_MODEL_CACHE` dict maps `model_key` → SentenceTransformer instance.
- `_get_or_load_model()` checks cache first — loads and caches on first call only.
- 1.3GB bge-large model is loaded once per process and reused across all files in the session.

### 7.4 Prefix rules

- nomic requires different prefixes for queries vs documents. Without prefixes, retrieval quality degrades significantly.
- Queries: prepend `"search_query: "` via `embed_query()` helper.
- Documents: prepend `"search_document: "` via `embed_documents()` helper.
- bge-large and text-embedding-3-small require no prefix. `embed_query()` and `embed_documents()` read `requires_prefix` from state and apply or skip automatically.
- This is the most common silent failure mode — forgetting the prefix on nomic at query time.

## 8. LLM Router

LLMRouter is a standalone component. All LLM calls in the pipeline go through it. It handles routing, fallback, timeout, and token tracking. The rest of the pipeline never calls a model API directly.

### 8.1 Model profiles

|                      | DeepSeek R1 (free tier)                                   | GPT-4o mini                               |
|----------------------|-----------------------------------------------------------|-------------------------------------------|
| Cost                 | Free                                                      | ~$0.15 / 1M input tokens                  |
| Speed                | Slower                                                    | Fast                                      |
| Reliability          | Rate limited aggressively                                 | Reliable                                  |
| Quality              | Strong reasoning                                          | Reliable, consistent                      |
| Best for             | Structured extraction, compression, simple classification | User-facing answer generation             |
| Fallback role        | Fallback when GPT budget exhausted                        | Fallback when DeepSeek rate-limited       |

### 8.2 Task routing table

| Task                                | Primary model | Fallback model | Rationale                                                                                                 |
|-------------------------------------|--------------|----------------|-----------------------------------------------------------------------------------------------------------|
| Intent classification (ambiguous)   | DeepSeek     | GPT-4o mini    | Regex handles 90%+ of cases — LLM only for genuinely ambiguous queries. Free model fine for this.        |
| Section extraction (comparison)     | DeepSeek     | GPT-4o mini    | Small structured JSON output task. Free model handles it well. Fallback if rate limited.                 |
| Conversation compression            | DeepSeek     | GPT-4o mini    | Summarisation of old turns — quality less critical than cost here.                                       |
| Final answer generation             | GPT-4o mini  | DeepSeek       | User-facing output — reliability and speed matter most. Switch to DeepSeek only when GPT budget exhausted.|

### 8.3 Three routing triggers — applied in order

- Task complexity — hardcoded per task type. Low complexity (extract, classify, compress) → DeepSeek first. High complexity (answer generation) → GPT-4o mini first. This is the primary decision.
- Token budget — if `state.llm_tokens_used_gpt >= state.llm_budget_gpt`, all subsequent calls route to DeepSeek for the remainder of the session regardless of task type. Budget resets per session.
- Rate limit fallback — if primary model returns HTTP 429 or times out, immediately retry on fallback model. Log the switch to `state.llm_calls_by_task`. Never raise the error to the caller. If both models fail, raise a typed `LLMUnavailableError`.

### 8.4 Section extraction detail

`_extract_sections_llm()` is called only for comparison intent. It receives the query and the list of all known section names from ChromaDB metadata.

- System prompt: `"You are extracting two section names being compared in a query. Return only valid JSON: {section_a: string, section_b: string}. Both values must be from the provided list."`
- User message: the query + newline-separated list of known section names.
- Parse JSON response. If parsing fails or sections not in known list → fall back to searching whole collection without section filter.
- This approach is robust because the LLM picks from a known list rather than hallucinating section names.

## 9. System Architecture

Four layers: React frontend, FastAPI backend, MCP server, and pipeline core. All run locally. Designed to scale — Redis swaps in for JSON state, auth middleware adds to FastAPI, MCP server hosts remotely.

### 9.1 Layer overview

| Layer           | Technology                        | Responsibilities                                                                                                                                                                |
|-----------------|------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| React frontend  | Vite + React, localhost:5173      | Upload UI (drag/drop files), chat interface (query + streamed answer + source chunks panel), ingestion monitor (per-file SSE progress stream)                                 |
| FastAPI backend | Python FastAPI, localhost:8000    | POST /ingest, POST /query, GET /state, GET /ingest/progress (SSE). Manages ConversationHistory per `conversation_id` in memory. Calls pipeline internals directly.            |
| MCP server      | Python MCP SDK, localhost:8001    | Exposes three retrieval tools as LLM-callable MCP tools. Thin wrapper around pipeline internals. Enables agentic multi-step retrieval.                                       |
| Pipeline core   | Python, no network                | All chunkers, retrievers, state management, LLMRouter, embedding helpers. Called directly by FastAPI and MCP server.                                                         |

### 9.2 FastAPI endpoints

| Endpoint | Method + path        | Detail                                                                                                                                                                                                                          |
|----------|----------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Ingest   | POST /ingest         | Accepts `List[UploadFile]`. Validates extensions. Streams files to dataset/ with `shutil.copyfileobj`. Kicks off `ingest_folder()` as async background task. Returns `{status, files_received}`.                             |
| Query    | POST /query          | Body: `{query, conversation_id}`. Loads or creates ConversationHistory for `conversation_id`. Calls `retrieve()`. Calls LLMRouter for answer generation. Appends turn to history. Returns `{answer, chunks, intent, scope, total_tokens}`. |
| State    | GET /state           | Returns serialised PipelineState — `collection_count`, `model_key`, `ingested_files`, session stats, `model_upgrade_warning` if set.                                                     |
| Progress | GET /ingest/progress | SSE stream. Yields one event per file during ingestion — `{filename, status, chunks_added, error}`. Also yields a final summary event on completion.                                     |

### 9.3 MCP server — three tools

| Tool                  | Signature                                                                                   | What it does                                                                                                                                                                           |
|-----------------------|---------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| search_documents      | `search_documents(query: str, source_doc: str = None, section: str = None) -> list[dict]`  | Calls `retrieve()` internally. Passes optional filters. Returns chunk list. Enables LLM to decide when to search rather than always retrieving.                                      |
| get_document_sections | `get_document_sections(source_doc: str = None) -> list[dict]`                              | Queries ChromaDB metadata for distinct section/subsection values. Returns `[{source_doc, section, chunk_count}]`. Enables LLM to understand collection structure before searching.    |
| get_collection_stats  | `get_collection_stats() -> dict`                                                            | Returns `{total_chunks, model_key, model_dims, docs_ingested, collection_name}`. Overview of collection state.                                                                       |

MCP enables agentic retrieval — the LLM can call `get_document_sections()` to understand what is available, then call `search_documents()` twice with targeted section filters, then synthesise a comparison. This multi-step behaviour is not possible with a hardcoded `retrieve()` call.

### 9.4 What goes through MCP vs FastAPI

| Path         | Description                                                                                                            |
|--------------|------------------------------------------------------------------------------------------------------------------------|
| Through MCP  | LLM-driven retrieval — `search_documents`, `get_document_sections`, `get_collection_stats`. Anything LLM decides to call dynamically. |
| Through FastAPI | Human-driven actions — file uploads, query submission, progress monitoring, state inspection. Conversation history management stays in FastAPI. |
| Not through MCP | Ingestion pipeline, file handling, conversation history, LLM answer generation. These are pipeline orchestration concerns, not LLM tool calls. |

## 10. Decisions Log

Every architectural decision made during design, with the reasoning. Ordered chronologically.

| Decision                     | Choice made                                 | Reasoning                                                                                                                                                                        | Session |
|-----------------------------|---------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|
| Heading detection method    | Heuristic scoring (5 rules)                 | No ML model needed, fast, tuneable threshold, works offline                                                                                                                     | S1      |
| Semantic boundary detection | Percentile similarity drop                  | Relative to each document — adapts to content density, not a global threshold                                                                                                   | S1      |
| Overlap unit                | Sentences (semantic) / chars (structured)   | Sentence overlap is semantically coherent for prose; char overlap for structured is consistent with markdown chunker                                                           | S1      |
| MMR redundancy proxy        | Section name overlap                        | No extra embedding calls at query time — avoids latency spike on every summary query                                                                                           | S1      |
| Chunk schema field count    | 11 fields                                   | Audited — 7 actively used in retrieval, 2 passive but justified, 1 ingestion-only, 1 needs wiring                                                                              | S1      |
| text_for_embedding storage  | Pop before ChromaDB store                   | Only needed at embed time — storing it wastes metadata space and is never retrieved                                                                                            | S1      |
| Dynamic config trigger      | Char count of individual doc                | Available before any processing, zero extra compute, independent of collection state                                                                                           | S1      |
| Dynamic k trigger           | Live `collection.count()`                   | k should reflect how much is actually in the store — not the folder size                                                                                                       | S2      |
| Embedding model (phase 1)   | nomic-embed-text-v1.5                       | Best size/quality ratio locally, 8192 token context critical for longer chunks                                                                                                  | S2      |
| Embedding model (phase 2)   | bge-large-en-v1.5                           | Best MTEB retrieval benchmarks for mixed-domain content (fiction + technical)                                                                                                  | S2      |
| Model selection unit        | Cumulative folder size                      | One model per collection — vector space consistency is non-negotiable                                                                                                          | S2      |
| Model on re-ingest          | Collection metadata wins                    | Prevents silent vector space mismatch when folder grows past threshold                                                                                                         | S2      |
| State persistence format    | JSON now, Redis-ready                       | Zero overhead for local single-user; Redis swap is two method changes when multi-user needed                                                                                   | S2      |
| Comparison extraction       | LLM call (DeepSeek) with known list         | Most robust for natural language; regex breaks on varied phrasing; keyword match misses paraphrasing                                                                           | S2      |
| Intent classification       | Regex primary, LLM fallback only            | Regex handles 90%+ of cases — keeps hot path completely free of LLM latency                                                                                                    | S2      |
| LLM routing strategy        | Task complexity + budget + 429 fallback     | Minimise GPT spend without sacrificing user-facing quality                                                                                                                     | S2      |
| Conversation compression    | LLM summarise before dropping               | Preserves context coherence at fraction of token cost vs dropping turns                                                                                                        | S2      |
| BM25 approach               | Stubbed — rank_bm25 + RRF when built        | Add only if exact-term fact lookups test poorly; RRF avoids score normalisation complexity                                                                                    | S2      |
| Collection organisation     | One collection for everything               | Simplest for local single-user; `source_doc` filter handles per-doc scoping at query time                                                                                      | S2      |
| File archive policy         | dataset/processed/ after success only       | Failed files stay in dataset/ for retry; archive only after confirmed ChromaDB store                                                                                           | S2      |
| source_doc field format     | Relative path from dataset/ root            | Prevents collisions when two files share a name in different subfolders                                                                                                       | S2      |
| PDF image handling          | Skip pages < 20 chars extracted text        | `page.get_text("text")` ignores images natively; short-text pages are scanned/decorative                                                                                       | S2      |
| Frontend framework          | React + Vite                                | Standard, fast HMR, component model fits chat + upload + progress monitor UI                                                                                                   | S2      |
| Backend framework           | FastAPI                                     | Same Python stack as pipeline — no context switch, async SSE straightforward                                                                                                   | S2      |
| MCP scope                   | 3 retrieval tools only                      | Ingestion and history management are not LLM-driven — FastAPI is correct layer for those                                                                                       | S2      |

## 11. Build Order

Recommended sequence. Each phase is independently testable before moving to the next.

### Phase 1 — Data models (start here)

- PipelineState dataclass with `to_dict()`, `from_dict()`, `save()`, `load()`, all updater methods
- FileMetadata dataclass with `to_dict()` and `from_dict()`
- ChunkingConfig dataclass
- ConversationTurn dataclass
- ConversationHistory with `add_turn()`, `_trim()`, `excluded_ids()`, `recent_chunks()`
- RetrievalResult dataclass

### Phase 2 — Chunkers and ingestion

- Wire ChunkingConfig into `chunk_markdown()`, `chunk_txt_structured()`, `chunk_txt_semantic()`
- Verify all three emit identical 11-field schema
- `read_txt()`, `read_md()`, `read_pdf()` (with image page skipping)
- `_hash_file()`, `_load_hash_store()`, `_save_hash_store()`
- `_archive_file()` (move to processed/)
- `ingest_folder()` — four-phase entry point
- End-to-end test: ingest a folder with md + txt + pdf, verify ChromaDB contents

### Phase 3 — Retrieval and LLM layer

- `embed_query()` and `embed_documents()` helpers with prefix logic
- `_classify_intent()` regex patterns
- `_detect_scope()` keyword matcher against `state.files_metadata`
- `_extract_sections_llm()` with DeepSeek call and fallback
- `_rerank()` with all 5 signals
- `_mmr()` section-overlap implementation
- `retrieve()` — all 7 stages, returns RetrievalResult
- LLMRouter — `route()`, `call()`, `_call_deepseek()`, `_call_gpt()`, `_handle_fallback()`
- Wire ConversationHistory into conversational intent path

### Phase 4 — API and frontend

- FastAPI app — POST /ingest, POST /query, GET /state, GET /ingest/progress (SSE)
- Conversation history management per `conversation_id` in FastAPI
- React — upload UI with drag/drop and SSE progress monitor
- React — chat interface with source chunks panel
- MCP server — three tools wrapping pipeline internals
- End-to-end test: upload folder, query via chat, verify answer + sources

### Phase 5 — Future extensions

- Swap to bge-large when first full book is ingested — verify collection metadata persists model key
- BM25 with rank_bm25 + RRF fusion — only if exact-term fact lookups test poorly
- Redis state store — swap `save()` and `load()` methods only when multi-user API is needed
- Add `source_doc` pre-filter as default on all `retrieve()` calls when collection exceeds 5000 chunks
- Consider chapter-level metadata for book navigation (`chapter_num`, `chapter_title` fields)

*RAG Pipeline Architecture · Final Draft · All decisions captured · Ready to build*
