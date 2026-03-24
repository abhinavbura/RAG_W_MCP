"""
Semantic chunker using sentence embedding similarity.
Triggered for TXT/PDF files with flat (non-structured) prose.
Emits 11-field chunk schema with chunk_type="semantic" and heading_confidence="none".
"""
from typing import List, Dict, Any, Tuple
import re
import numpy as np
import tiktoken
from pipeline.state.chunking_config import ChunkingConfig


def chunk_txt_semantic(text: str, source_doc: str, config: ChunkingConfig, model: Any) -> List[Dict[str, Any]]:
    """
    Chunk a flat (non-structured) text document using semantic similarity.
    
    Strategy:
    - Split into sentences via regex and newlines
    - Embed all sentences in one batched call (batch_size=32)
    - Find boundaries where cosine similarity drops below document-relative threshold
    - Threshold is the `drop_percentile` percentile of all pairwise similarities
    - Group sentences into chunks, enforcing min/max token budgets
    - Use sentence-level overlap from config.overlap_sentences
    
    Args:
        text: Full text document
        source_doc: Relative path from dataset/ root
        config: ChunkingConfig with drop_percentile, overlap_sentences, min/max tokens
        model: SentenceTransformer instance for embedding
        
    Returns:
        List of chunk dicts with 11 fields each
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    
    # Split into sentences
    sentences = _split_sentences(text)
    if not sentences:
        # Edge case: no sentences found, create single chunk
        return [_create_chunk("", "", source_doc, 0, encoding)]
    
    # Embed all sentences in one batch
    embeddings = model.encode(sentences, batch_size=32, show_progress_bar=False)
    
    # Find boundaries based on similarity drop
    boundaries = _find_boundaries(embeddings, config.drop_percentile)
    
    # Group sentences into chunks
    sentence_groups = _group_into_chunks(
        sentences, boundaries, config.min_tokens, config.max_tokens, config.overlap_sentences, encoding
    )
    
    # Create chunk dicts
    chunks = []
    for chunk_idx, group in enumerate(sentence_groups):
        chunk_text = " ".join(group)
        chunk_dict = _create_chunk(chunk_text, source_doc, chunk_idx, encoding)
        chunks.append(chunk_dict)
    
    return chunks


def _split_sentences(text: str) -> List[str]:
    """
    Split text into sentences.
    Primary: regex on sentence boundaries (. ! ?)
    Secondary: paragraph breaks (newlines)
    
    Args:
        text: Full text
        
    Returns:
        List of sentences (cleaned)
    """
    # First, split on paragraph breaks (double newlines or more)
    paragraphs = re.split(r"\n\s*\n", text)
    
    sentences = []
    # Regex pattern for sentence endings: . ! ? followed by space and capital letter
    sentence_pattern = r"(?<=[.!?])\s+(?=[A-Z])"
    
    for para in paragraphs:
        if not para.strip():
            continue
        
        # Split paragraph into sentences
        para_sentences = re.split(sentence_pattern, para.strip())
        for sent in para_sentences:
            sent = sent.strip()
            if sent:
                sentences.append(sent)
    
    return sentences


def _find_boundaries(embeddings: np.ndarray, percentile: int) -> List[int]:
    """
    Find sentence boundaries where cosine similarity drops below threshold.
    
    Threshold is the `percentile` percentile of all pairwise similarities.
    This makes the threshold adaptive to document density.
    
    Args:
        embeddings: Shape (num_sentences, embedding_dim) — normalized embeddings
        percentile: Percentile of similarity drop (0-100)
        
    Returns:
        List of sentence indices that are boundaries (start of new chunk)
    """
    if len(embeddings) < 2:
        return []
    
    # Compute cosine similarity between adjacent sentences
    # Cosine similarity = dot product (embeddings are normalized)
    similarities = []
    for i in range(len(embeddings) - 1):
        sim = np.dot(embeddings[i], embeddings[i + 1])
        similarities.append(sim)
    
    # Find threshold at given percentile
    threshold = np.percentile(similarities, percentile)
    
    # Boundaries are indices where similarity falls below threshold
    boundaries = [0]  # Always start with sentence 0
    for i, sim in enumerate(similarities):
        if sim < threshold:
            boundaries.append(i + 1)  # i+1 is the start of next sentence group
    
    return boundaries


def _group_into_chunks(
    sentences: List[str],
    boundaries: List[int],
    min_tokens: int,
    max_tokens: int,
    overlap_sentences: int,
    encoding: Any,
) -> List[List[str]]:
    """
    Group sentences into chunks using boundaries, enforcing token budgets.
    
    Strategy:
    - Use boundaries as preferred split points
    - If a group is < min_tokens, merge with next group
    - If a group is > max_tokens, force-split at sentence boundary
    - Add last `overlap_sentences` from previous group to each new group
    
    Args:
        sentences: List of sentences
        boundaries: List of sentence indices that start new chunks
        min_tokens: Minimum tokens per chunk
        max_tokens: Maximum tokens per chunk
        overlap_sentences: Number of sentences to carry forward for overlap
        encoding: tiktoken encoding
        
    Returns:
        List of sentence groups (each group is list of sentences)
    """
    if not sentences:
        return []
    
    # Create initial groups using boundaries
    groups = []
    for i, bound_idx in enumerate(boundaries):
        if i < len(boundaries) - 1:
            next_bound = boundaries[i + 1]
            groups.append(sentences[bound_idx:next_bound])
        else:
            groups.append(sentences[bound_idx:])
    
    # Merge undersized groups with next neighbour
    merged_groups = []
    i = 0
    while i < len(groups):
        current_group = groups[i]
        current_tokens = sum(len(encoding.encode(s)) for s in current_group)
        
        # While current group is below min, merge with next
        while current_tokens < min_tokens and i < len(groups) - 1:
            i += 1
            current_group.extend(groups[i])
            current_tokens = sum(len(encoding.encode(s)) for s in current_group)
        
        merged_groups.append(current_group)
        i += 1
    
    # Force-split oversized groups
    final_groups = []
    for group in merged_groups:
        if sum(len(encoding.encode(s)) for s in group) <= max_tokens:
            final_groups.append(group)
        else:
            # Force-split at sentence boundary
            sub_group = []
            sub_tokens = 0
            for sent in group:
                sent_tokens = len(encoding.encode(sent))
                if sub_tokens + sent_tokens <= max_tokens:
                    sub_group.append(sent)
                    sub_tokens += sent_tokens
                else:
                    if sub_group:
                        final_groups.append(sub_group)
                    sub_group = [sent]
                    sub_tokens = sent_tokens
            if sub_group:
                final_groups.append(sub_group)
    
    # Add overlap from previous group to each new group (except first)
    result = []
    for i, group in enumerate(final_groups):
        if i > 0 and overlap_sentences > 0:
            # Add last N sentences from previous group
            prev_group = final_groups[i - 1]
            overlap = prev_group[-overlap_sentences:] if len(prev_group) >= overlap_sentences else prev_group
            result.append(overlap + group)
        else:
            result.append(group)
    
    return result


def _create_chunk(text: str, source_doc: str, chunk_idx: int, encoding: Any) -> Dict[str, Any]:
    """
    Create a single semantic chunk dict with all 11 fields.
    
    Args:
        text: Chunk body text (joined sentences)
        source_doc: Relative source document path
        chunk_idx: Chunk index
        encoding: tiktoken encoding
        
    Returns:
        Dict with all 11 fields
    """
    # For semantic chunks, text_for_embedding is same as text (no heading)
    text_for_embedding = text
    
    # Calculate position ratio (placeholder)
    position_ratio = 0.5
    
    # Calculate token count
    token_count = len(encoding.encode(text))
    
    # Build unique id (no section/subsection for semantic chunks)
    chunk_id = f"{source_doc}_00_00_{chunk_idx:02d}"
    
    return {
        "id": chunk_id,
        "text": text,
        "text_for_embedding": text_for_embedding,
        "section": "",
        "subsection": "",
        "anchor": "",
        "source_doc": source_doc,
        "chunk_type": "semantic",
        "heading_confidence": "none",
        "position_ratio": position_ratio,
        "token_count": token_count,
    }
