"""
ChunkingConfig dataclass and dynamic configuration factory.
Chunking parameters driven by individual document size.
Retrieval parameters driven by live collection chunk count.
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class ChunkingConfig:
    """Configuration for chunking and retrieval, determined by doc and collection size."""
    
    # Chunking parameters
    max_chars: int
    overlap_chars: int
    min_tokens: int
    max_tokens: int
    overlap_sentences: int
    drop_percentile: int
    
    # Retrieval k values
    k_fact: int
    k_summary: int
    k_compare: int
    k_conversational: int
    
    # Diversity parameter
    mmr_lambda: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_chars": self.max_chars,
            "overlap_chars": self.overlap_chars,
            "min_tokens": self.min_tokens,
            "max_tokens": self.max_tokens,
            "overlap_sentences": self.overlap_sentences,
            "drop_percentile": self.drop_percentile,
            "k_fact": self.k_fact,
            "k_summary": self.k_summary,
            "k_compare": self.k_compare,
            "k_conversational": self.k_conversational,
            "mmr_lambda": self.mmr_lambda,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChunkingConfig":
        """Create from dictionary."""
        return cls(**data)


def get_config(text: str = "", chunk_count: int = 0) -> ChunkingConfig:
    """
    Factory function returning ChunkingConfig based on document size and collection size.
    
    Args:
        text: The text to determine doc size band. If empty, defaults to "medium".
        chunk_count: Live ChromaDB chunk count to determine collection size band.
        
    Returns:
        ChunkingConfig with parameters tuned for the document and collection size.
    """
    # Determine document size band
    doc_size = len(text)
    if doc_size < 100_000:  # ~10 pages
        doc_band = "small"
    elif doc_size < 500_000:  # ~50 pages
        doc_band = "medium"
    else:  # 500K+ chars (400+ pages)
        doc_band = "large"
    
    # Determine collection size band
    if chunk_count < 200:
        coll_band = "small"
    elif chunk_count < 1000:
        coll_band = "medium"
    else:  # 1000+ chunks
        coll_band = "large"
    
    # Configuration matrix
    _CONFIG_MATRIX = {
        ("small", "small"): ChunkingConfig(
            max_chars=1000,
            overlap_chars=100,
            min_tokens=60,
            max_tokens=300,
            overlap_sentences=1,
            drop_percentile=70,
            k_fact=3,
            k_summary=6,
            k_compare=4,
            k_conversational=3,
            mmr_lambda=0.7,
        ),
        ("small", "medium"): ChunkingConfig(
            max_chars=1000,
            overlap_chars=100,
            min_tokens=60,
            max_tokens=300,
            overlap_sentences=1,
            drop_percentile=70,
            k_fact=4,
            k_summary=8,
            k_compare=5,
            k_conversational=4,
            mmr_lambda=0.6,
        ),
        ("small", "large"): ChunkingConfig(
            max_chars=1000,
            overlap_chars=100,
            min_tokens=60,
            max_tokens=300,
            overlap_sentences=1,
            drop_percentile=70,
            k_fact=5,
            k_summary=12,
            k_compare=8,
            k_conversational=5,
            mmr_lambda=0.5,
        ),
        ("medium", "small"): ChunkingConfig(
            max_chars=1500,
            overlap_chars=150,
            min_tokens=80,
            max_tokens=400,
            overlap_sentences=2,
            drop_percentile=75,
            k_fact=3,
            k_summary=6,
            k_compare=4,
            k_conversational=3,
            mmr_lambda=0.7,
        ),
        ("medium", "medium"): ChunkingConfig(
            max_chars=1500,
            overlap_chars=150,
            min_tokens=80,
            max_tokens=400,
            overlap_sentences=2,
            drop_percentile=75,
            k_fact=4,
            k_summary=8,
            k_compare=5,
            k_conversational=4,
            mmr_lambda=0.6,
        ),
        ("medium", "large"): ChunkingConfig(
            max_chars=1500,
            overlap_chars=150,
            min_tokens=80,
            max_tokens=400,
            overlap_sentences=2,
            drop_percentile=75,
            k_fact=5,
            k_summary=12,
            k_compare=8,
            k_conversational=5,
            mmr_lambda=0.5,
        ),
        ("large", "small"): ChunkingConfig(
            max_chars=2000,
            overlap_chars=200,
            min_tokens=100,
            max_tokens=500,
            overlap_sentences=3,
            drop_percentile=80,
            k_fact=3,
            k_summary=6,
            k_compare=4,
            k_conversational=3,
            mmr_lambda=0.7,
        ),
        ("large", "medium"): ChunkingConfig(
            max_chars=2000,
            overlap_chars=200,
            min_tokens=100,
            max_tokens=500,
            overlap_sentences=3,
            drop_percentile=80,
            k_fact=4,
            k_summary=8,
            k_compare=5,
            k_conversational=4,
            mmr_lambda=0.6,
        ),
        ("large", "large"): ChunkingConfig(
            max_chars=2000,
            overlap_chars=200,
            min_tokens=100,
            max_tokens=500,
            overlap_sentences=3,
            drop_percentile=80,
            k_fact=5,
            k_summary=12,
            k_compare=8,
            k_conversational=5,
            mmr_lambda=0.5,
        ),
    }
    
    return _CONFIG_MATRIX[(doc_band, coll_band)]
