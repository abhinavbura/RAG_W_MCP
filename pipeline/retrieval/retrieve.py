# retrieve(query, state, history=None) -> RetrievalResult
# 7-stage pipeline:
#   Stage 0 — embed_query() once, reuse vector
#   Stage 1 — _classify_intent()
#   Stage 2 — _detect_scope()
#   Stage 3 — Build ChromaDB where clause
#   Stage 4 — Cosine search (k*3 for summary, k*2 for others; separate queries for comparison)
#   Stage 5 — _rerank() — 5 signals
#   Stage 6 — Intent-specific post-processing (fact/summary/comparison/conversational)
# Returns fully populated RetrievalResult with latency_ms.
# Status: IN PROGRESS — needs RetrievalResult + LLMRouter wired in
