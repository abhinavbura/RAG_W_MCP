"""
Scope detection — determines whether a query targets a specific source document.

Strategy: tokenise the stem of each ingested filename, then count how many
of those tokens appear in the query. A confident match (score > 0, unique winner)
pins retrieval to that source_doc via a ChromaDB where-filter.

Returns the RELATIVE path (from dataset/ root) on a match, None otherwise.
The relative path format matches the source_doc field stored in ChromaDB metadata.
"""
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _detect_scope(query: str, state) -> Optional[str]:
    """
    Match query words against ingested file stems to detect a scoped query.

    Args:
        query: Raw query string from the user.
        state: PipelineState — reads files_metadata and folder_path.

    Returns:
        Relative source_doc path if a confident unique match is found, else None.
    """
    if not state.files_metadata:
        return None

    query_words = set(re.findall(r"\b\w+\b", query.lower()))
    # Remove short stop words that could cause false positives
    query_words -= {"the", "a", "an", "is", "in", "of", "for", "to", "and", "or"}

    best_score = 0
    best_path: Optional[str] = None
    tie = False

    for fm in state.files_metadata:
        # Build relative path (the value stored in ChromaDB source_doc field)
        abs_path = fm.path.replace("\\", "/")
        folder = state.folder_path.replace("\\", "/").rstrip("/") + "/"
        rel_path = abs_path[len(folder):] if abs_path.startswith(folder) else abs_path

        # Tokenise stem only — strip extension and split on non-word chars
        filename = os.path.basename(rel_path)
        stem = re.sub(r"[^a-z0-9]+", " ", filename.rsplit(".", 1)[0].lower())
        stem_tokens = set(stem.split())

        score = len(stem_tokens & query_words)

        if score > best_score:
            best_score = score
            best_path = rel_path
            tie = False
        elif score == best_score and score > 0:
            # Two files scored equally — not confident enough to pin
            tie = True

    if best_score > 0 and not tie and best_path:
        logger.debug("Scope detected: '%s' (score=%d).", best_path, best_score)
        return best_path

    logger.debug("No confident scope match found.")
    return None
