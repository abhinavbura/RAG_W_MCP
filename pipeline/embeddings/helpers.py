# embed_query(query, state) -> list[float]
#   Applies query_prefix if state.requires_prefix is True.
#   nomic: prepends "search_query: "
#   bge-large / others: no prefix
#   Single model.encode() call. Returns vector.
#
# embed_documents(texts, state) -> list[list[float]]
#   Applies doc_prefix if state.requires_prefix is True.
#   nomic: prepends "search_document: "
#   bge-large / others: no prefix
#   Batched encode (batch_size=32). Returns list of vectors.
#
# NOTE: Forgetting the prefix on nomic at query time is the most common silent failure.
