# MCP server — 3 retrieval tools exposed as LLM-callable MCP tools.
# Thin wrapper around pipeline internals.
# Enables agentic multi-step retrieval (LLM decides when and what to search).
#
# Tools:
#
# search_documents(query: str, source_doc: str = None, section: str = None) -> list[dict]
#   Calls retrieve() internally. Passes optional filters.
#   Returns chunk list (debug fields stripped).
#
# get_document_sections(source_doc: str = None) -> list[dict]
#   Queries ChromaDB metadata for distinct section values.
#   Returns [{source_doc, section, chunk_count}].
#   Optional source_doc filter.
#
# get_collection_stats() -> dict
#   Returns {total_chunks, model_key, model_dims, docs_ingested, collection_name}.
#
# NOTE: Ingestion, history, and answer generation are NOT exposed via MCP.
# Those are pipeline orchestration concerns, handled by FastAPI.
