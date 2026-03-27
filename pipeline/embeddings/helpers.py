"""
Embedding helpers for the RAG pipeline.

CRITICAL: Forgetting the prefix on nomic at query time silently breaks retrieval.
          embed_query and embed_documents are the only correct way to encode text.
"""
from typing import List


def embed_query(query: str, state) -> List[float]:
    """
    Encode a single query string into a vector.

    Applies state.query_prefix when state.requires_prefix is True (nomic model).
    For bge-large and others, prefix is an empty string — no-op.

    Args:
        query: Raw query string from the user.
        state: PipelineState — reads requires_prefix, query_prefix, _model_instance.

    Returns:
        Flat list of floats (length = state.model_dims).
    """
    text = f"{state.query_prefix}{query}" if state.requires_prefix else query
    return state._model_instance.encode(text, show_progress_bar=False).tolist()


def embed_documents(texts: List[str], state) -> List[List[float]]:
    """
    Encode a batch of document texts into vectors.

    Applies state.doc_prefix when state.requires_prefix is True (nomic model).
    Uses batch_size=32 — never encodes one-at-a-time.

    Args:
        texts: List of strings to embed (text_for_embedding field from chunk dicts).
        state: PipelineState — reads requires_prefix, doc_prefix, _model_instance.

    Returns:
        List of float vectors, one per input string.
    """
    if not texts:
        return []
    if state.requires_prefix:
        texts = [f"{state.doc_prefix}{t}" for t in texts]
    embeddings = state._model_instance.encode(texts, batch_size=32, show_progress_bar=False)
    return [vec.tolist() for vec in embeddings]
