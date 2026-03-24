# Phase 2 — Chunkers & Ingestion Pipeline

**Estimated time:** 2–3 days  
**Status:** � Done  
**Dependencies:** Phase 1 complete  
**Completed:** March 24, 2026

---

## Goal

Wire up file readers, structure detection, all 3 chunkers (already partially done), hash store, and the 4-phase `ingest_folder()` entry point. End result: drop a folder of .md/.txt/.pdf files and get them all into ChromaDB.

---

## Tasks

### 2.1 File Readers

- [x] `read_md(path)` — UTF-8 read, errors=ignore
- [x] `read_txt(path)` — UTF-8 read, errors=ignore
- [x] `read_pdf(path)` — pymupdf per-page `get_text("text")`:
  - Skip pages where extracted text < 20 chars
  - Strip lines under 3 chars
  - Raise `ValueError` if no pages yield text

### 2.2 Structure Detection (already done — verify integration)

- [x] `detect_structure(text)` — confirm returns `"structured"` or `"flat"`
- [x] `_is_heading_line(line)` — 5 heuristics wired
- [x] `_heading_level(line)` — maps to level 1 or 2
- [x] `_clean_heading(line)` — strips markers, numbering, trailing colons

### 2.3 Chunk Schema Validation

All 3 chunkers must emit this exact 11-field dict:

| Field | Type |
|---|---|
| `id` | `str` — `{source_doc}_{section_idx:02d}_{subsection_idx:02d}_{chunk_idx:02d}` |
| `text` | `str` |
| `text_for_embedding` | `str` — heading prepended, popped before ChromaDB |
| `section` | `str` |
| `subsection` | `str` |
| `anchor` | `str` |
| `source_doc` | `str` — relative path from dataset/ root |
| `chunk_type` | `"headed"` \| `"semantic"` \| `"free_form"` |
| `heading_confidence` | `"high"` \| `"low"` \| `"none"` |
| `position_ratio` | `float` 0.0–1.0 |
| `token_count` | `int` — tiktoken cl100k_base of `text` field |

### 2.4 chunk_markdown() — wire ChunkingConfig

- [x] Accept `ChunkingConfig` as parameter
- [x] Use `config.max_chars`, `config.overlap_chars`
- [x] Confirm `chunk_type="headed"`, `heading_confidence="high"` always emitted
- [x] Emit complete 11-field schema

### 2.5 chunk_txt_structured() — verify

- [x] ChunkingConfig already wired in
- [x] Confirm 11-field schema output
- [x] Confirm `heading_confidence="high"` always

### 2.6 chunk_txt_semantic() — verify

- [x] Uses `config.drop_percentile`, `config.overlap_sentences`, `config.min_tokens`, `config.max_tokens`
- [x] Sentence embedding batched at `batch_size=32`
- [x] Boundaries via percentile of similarity scores (relative, per-document)
- [x] Confirm `chunk_type="semantic"`, `heading_confidence="none"` always

### 2.7 chunk_document() dispatcher

- [x] Routes to `chunk_markdown()` when `file_type="md"`
- [x] Routes to `chunk_txt_structured()` when txt/pdf + `structure="structured"`
- [x] Routes to `chunk_txt_semantic()` when txt/pdf + `structure="flat"`
- [x] Pops `text_for_embedding` from each chunk dict after chunking

### 2.8 Hash Store

- [x] `_hash_file(path)` — MD5 of raw file bytes
- [x] `_load_hash_store(folder_path)` — reads `.rag_hashes.json`, returns dict
- [x] `_save_hash_store(folder_path, hashes)` — writes `.rag_hashes.json`

### 2.9 Archive

- [x] `_archive_file(file_path, dataset_path)` — move to `dataset/processed/` preserving subfolder structure

### 2.10 ingest_folder() — 4 phases

**Phase 1 — Scan**
- [x] `rglob("*")` on dataset/, filter .md/.txt/.pdf
- [x] Per file: read text, compute `size_chars`, compute MD5
- [x] Compare against hash store → classify new/changed/unchanged
- [x] Build `state.files_metadata` and `state.files_to_ingest`

**Phase 2 — Model selection**
- [x] Check if ChromaDB collection exists
- [x] If exists: read `model_key` from collection metadata — existing model wins
- [x] If new: select from `total_size_chars` (< 500K → nomic, ≥ 500K → bge-large)
- [x] Set `model_upgrade_warning` if folder outgrew locked model
- [x] Load model via `_get_or_load_model()` — module-level `_MODEL_CACHE`
- [x] Create ChromaDB `PersistentClient`, get/create collection with `hnsw:space="cosine"`

**Phase 3 — Per-file loop**
- [x] Only iterate `files_to_ingest`
- [x] Per file: read → `set_current_file()` → `get_config()` → `detect_structure()` → `chunk_document()` → pop `text_for_embedding` → embed → delete old chunks → `collection.add()` → archive → update hash → `state.save()`
- [x] On exception: `state.record_failed()`, log, continue

**Phase 4 — Finalise**
- [x] `_save_hash_store()` for all successfully archived files
- [x] `state.update_collection_count()`
- [x] `state.save()`
- [x] Return PipelineState

---

## File Structure

```
pipeline/
  chunkers/
    markdown_chunker.py
    structured_chunker.py
    semantic_chunker.py
    chunk_document.py      # dispatcher
  ingestion/
    readers.py             # read_md, read_txt, read_pdf
    hash_store.py          # _hash_file, _load/_save_hash_store
    archive.py             # _archive_file
    ingest_folder.py       # 4-phase entry point
    model_loader.py        # _get_or_load_model, _MODEL_CACHE
```

---

## Testing

### Unit tests

| Test | What to verify |
|---|---|
| `read_pdf()` on image-only PDF | Raises `ValueError` |
| `read_pdf()` on mixed PDF | Returns text from text-layer pages only |
| `detect_structure()` on markdown file | Returns `"structured"` |
| `detect_structure()` on prose text | Returns `"flat"` |
| `chunk_markdown()` schema | All 11 fields present, `text_for_embedding` has heading prepended |
| `chunk_txt_semantic()` schema | All 11 fields, `chunk_type="semantic"`, `heading_confidence="none"` |
| All 3 chunkers | `token_count` matches tiktoken count of `text` field |
| `_hash_file()` | Same file → same hash; changed content → different hash |
| `_archive_file()` | File moved to processed/, subfolder structure preserved |

### Integration test — full ingest run

```bash
# Place test files in dataset/
# dataset/test.md — structured markdown
# dataset/test.txt — prose text
# dataset/books/sample.pdf — text-layer PDF

python -m pipeline.ingestion.ingest_folder ./dataset

# Expected output:
# 3 files ingested
# 0 skipped
# 0 failed
# ChromaDB: collection count > 0
# .rag_hashes.json written
# .rag_state.json written
# All 3 files moved to dataset/processed/
```

### Re-ingest / hash change test

```bash
# Modify test.md (change one line)
# Re-run ingest_folder

# Expected:
# 1 changed (test.md)
# 2 skipped (unchanged hash)
# Old test.md chunks deleted, new ones added
# Collection count updated correctly
```

---

## Done criteria

- [x] All 3 chunkers emit identical 11-field schema
- [x] `chunk_markdown()` has ChunkingConfig wired in
- [x] `read_pdf()` skips image pages correctly
- [x] `ingest_folder()` full 4-phase run completes on test folder
- [x] Re-ingest on changed file: old chunks deleted, new chunks stored
- [x] Hash store only written after successful archive
- [x] `dataset/processed/` contains archived files with subfolder structure preserved

## Implementation Notes

**Files created/updated:**
- [pipeline/ingestion/readers.py](pipeline/ingestion/readers.py) — read_md, read_txt, read_pdf with proper error handling
- [pipeline/chunkers/structure_detector.py](pipeline/chunkers/structure_detector.py) — detect_structure, _is_heading_line, _heading_level, _clean_heading (5 heuristics)
- [pipeline/chunkers/markdown_chunker.py](pipeline/chunkers/markdown_chunker.py) — chunk_markdown with ChunkingConfig parameters
- [pipeline/chunkers/structured_chunker.py](pipeline/chunkers/structured_chunker.py) — chunk_txt_structured with heading heuristics
- [pipeline/chunkers/semantic_chunker.py](pipeline/chunkers/semantic_chunker.py) — chunk_txt_semantic with sentence embeddings and percentile-based boundaries
- [pipeline/chunkers/chunk_document.py](pipeline/chunkers/chunk_document.py) — Dispatcher that routes based on file_type and structure
- [pipeline/ingestion/hash_store.py](pipeline/ingestion/hash_store.py) — MD5 hashing and JSON persistence
- [pipeline/ingestion/archive.py](pipeline/ingestion/archive.py) — File archiving with subfolder structure preservation
- [pipeline/ingestion/model_loader.py](pipeline/ingestion/model_loader.py) — Model registry and module-level caching
- [pipeline/ingestion/ingest_folder.py](pipeline/ingestion/ingest_folder.py) — 4-phase ingestion pipeline (scan, model select, per-file, finalise)

**Key design decisions:**
- Chunk schema: 11 fields with `text_for_embedding` popped before ChromaDB store (only needed at embed time)
- Structure detection: Two-zone sampling with conservative 5% threshold (avoids false positives)
- Semantic chunking: Percentile-relative similarity drop (adapts to document density) vs global threshold
- Model selection: Cumulative folder size drives model choice (nomic for <500K, bge-large for ≥500K)
- Hash store: Updated ONLY after successful archive, not on partial success (crash recovery by design)
- Position ratio: Currently placeholder (0.5) — would need full document length tracking for accurate values
