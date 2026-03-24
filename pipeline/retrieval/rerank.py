# _rerank(candidates, query, state) -> list[dict]
# Five signals applied to every candidate chunk:
#   +0.15  — any query word in section or subsection
#   +0.05  — chunk_type = "headed"
#   +0.05  — heading_confidence = "high"
#   -0.05  — position_ratio < 0.05 or > 0.95
#   -0.10  — token_count > model_ctx_tokens (chunk truncated at embed time)
# Sort descending by adjusted score. Return sorted list.
# Status: DONE
