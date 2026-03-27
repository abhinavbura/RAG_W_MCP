"""
MCP Server — 3 retrieval tools exposed as LLM-callable MCP tools.
Thin wrapper around pipeline internals.

Tools:
  search_documents(query, source_doc=None, section=None) -> list[dict]
  get_document_sections(source_doc=None) -> list[dict]
  get_collection_stats() -> dict

Ingestion, history management, and answer generation are NOT exposed here.
Those are pipeline orchestration concerns handled by FastAPI.

Run with:
    python -m mcp_server.server
    (MCP clients connect via stdio transport)
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from pipeline.state.pipeline_state import PipelineState
from pipeline.state.conversation import ConversationHistory
from pipeline.retrieval.retrieve import retrieve

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# MCP app
# ---------------------------------------------------------------------------

mcp = FastMCP("RAG Pipeline")

# ---------------------------------------------------------------------------
# Lazy singleton state — loaded once when first tool is called
# ---------------------------------------------------------------------------

_STATE_PATH = Path(os.environ.get("DATASET_PATH", "./dataset")) / ".rag_state.json"
_state: Optional[PipelineState] = None


def _get_state() -> PipelineState:
    """Load PipelineState from disk on first call; return cached copy after."""
    global _state
    if _state is None:
        if _STATE_PATH.exists():
            try:
                _state = PipelineState.load(str(_STATE_PATH))
                logger.info("MCP server: loaded PipelineState from %s", _STATE_PATH)
            except Exception as exc:
                logger.warning("Could not load state: %s", exc)
                _state = PipelineState(folder_path=str(_STATE_PATH.parent))
        else:
            _state = PipelineState(folder_path=str(_STATE_PATH.parent))
            logger.info("MCP server: no state file found, using fresh PipelineState")
    return _state


# ---------------------------------------------------------------------------
# Tool: search_documents
# ---------------------------------------------------------------------------

_DEBUG_FIELDS = {"scores_before", "scores_after", "latency_ms", "total_fetched", "score_before", "score_after"}


@mcp.tool()
def search_documents(
    query: str,
    source_doc: Optional[str] = None,
    section: Optional[str] = None,
) -> list:
    """
    Search the RAG knowledge base and return relevant chunks.

    Args:
        query:      Natural language query string.
        source_doc: Optional — restrict search to a specific document
                    (relative path from dataset/ root, e.g. 'books/ml_textbook.pdf').
        section:    Optional — restrict search to a specific section name.

    Returns:
        List of chunk dicts. Each chunk contains:
          text, anchor, source_doc, section, subsection,
          chunk_type, heading_confidence, position_ratio, token_count.
        Debug fields (scores_before, scores_after, latency_ms) are stripped.
    """
    state = _get_state()

    if state._collection is None:
        logger.warning("search_documents called but collection not loaded")
        return []

    # Override scope/section via the query scope mechanism if caller supplies them
    history = ConversationHistory()
    result = retrieve(query, state, history)

    # Apply optional caller-supplied filters client-side
    # (retrieve() uses state.files_metadata for scope auto-detection;
    #  here we allow explicit overrides as a post-filter)
    chunks = result.chunks

    if source_doc:
        chunks = [c for c in chunks if c.get("source_doc", "") == source_doc]

    if section:
        chunks = [c for c in chunks if c.get("section", "") == section]

    # Strip debug fields — keep only retrieval-useful fields
    clean: list = []
    for chunk in chunks:
        clean.append({k: v for k, v in chunk.items() if k not in _DEBUG_FIELDS})

    return clean


# ---------------------------------------------------------------------------
# Tool: get_document_sections
# ---------------------------------------------------------------------------

@mcp.tool()
def get_document_sections(source_doc: Optional[str] = None) -> list:
    """
    Return known sections in the ChromaDB collection.

    Args:
        source_doc: Optional — filter to a specific document.

    Returns:
        List of dicts: [{source_doc, section, chunk_count}]
        Ordered by source_doc then section.
    """
    state = _get_state()

    if state._collection is None:
        logger.warning("get_document_sections called but collection not loaded")
        return []

    try:
        res = state._collection.get(include=["metadatas"])
    except Exception as exc:
        logger.error("ChromaDB get failed: %s", exc)
        return []

    # Aggregate (source_doc, section) → chunk_count
    counts: dict = {}
    for meta in (res.get("metadatas") or []):
        if not meta:
            continue
        doc = meta.get("source_doc", "")
        sec = meta.get("section", "")

        if source_doc and doc != source_doc:
            continue
        if not sec:
            continue  # skip chunks with no section

        key = (doc, sec)
        counts[key] = counts.get(key, 0) + 1

    result = [
        {"source_doc": doc, "section": sec, "chunk_count": count}
        for (doc, sec), count in sorted(counts.items())
    ]
    return result


# ---------------------------------------------------------------------------
# Tool: get_collection_stats
# ---------------------------------------------------------------------------

@mcp.tool()
def get_collection_stats() -> dict:
    """
    Return an overview of the RAG collection.

    Returns:
        {total_chunks, model_key, model_dims, docs_ingested, collection_name}
    """
    state = _get_state()

    total_chunks = 0
    collection_name = state.collection_name or "rag_pipeline"

    if state._collection is not None:
        try:
            total_chunks = state._collection.count()
        except Exception as exc:
            logger.warning("Could not count collection: %s", exc)

    # docs_ingested = unique source_doc values in the collection
    docs_ingested: list = []
    if state._collection is not None:
        try:
            res = state._collection.get(include=["metadatas"])
            docs_ingested = sorted(
                {m.get("source_doc", "") for m in (res.get("metadatas") or []) if m}
            )
        except Exception:
            pass

    return {
        "total_chunks": total_chunks,
        "model_key": state.model_key or "",
        "model_dims": state.model_dims or 0,
        "docs_ingested": docs_ingested,
        "collection_name": collection_name,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
