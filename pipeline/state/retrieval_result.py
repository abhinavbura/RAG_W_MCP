"""
RetrievalResult dataclass — typed return from retrieve() with debug fields.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class RetrievalResult:
    """Result from retrieve() containing ranked chunks and metadata."""
    
    # Primary output
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    
    # Request metadata
    query: str = ""
    intent: str = ""  # "fact" | "summary" | "comparison" | "conversational"
    scope: Optional[str] = None  # Detected source_doc if scoped, None otherwise
    sections: Optional[List[str]] = None  # [section_a, section_b] for comparison, None otherwise
    
    # Retrieval configuration
    k: int = 0  # Number of chunks requested
    model_key: str = ""  # Embedding model used
    filter_applied: bool = False  # True if ChromaDB where clause was used
    
    # Context budgeting
    total_tokens: int = 0  # Sum of token_count across all returned chunks
    
    # Debug fields (stripped in production)
    total_fetched: int = 0  # Candidate count before re-ranking
    scores_before: List[float] = field(default_factory=list)  # Before re-rank
    scores_after: List[float] = field(default_factory=list)  # After re-rank
    latency_ms: float = 0.0  # Total wall-clock retrieval time
    
    def to_dict(self, include_debug: bool = True) -> Dict[str, Any]:
        """
        Serialize to dictionary.
        
        Args:
            include_debug: If False, strips debug fields for production.
            
        Returns:
            Dictionary representation of the result
        """
        result = {
            "chunks": self.chunks,
            "query": self.query,
            "intent": self.intent,
            "scope": self.scope,
            "sections": self.sections,
            "k": self.k,
            "model_key": self.model_key,
            "filter_applied": self.filter_applied,
            "total_tokens": self.total_tokens,
            "total_fetched": self.total_fetched,
        }
        
        if include_debug:
            result["scores_before"] = self.scores_before
            result["scores_after"] = self.scores_after
            result["latency_ms"] = self.latency_ms
        
        return result
    
    def strip_debug(self) -> "RetrievalResult":
        """
        Return a copy with debug fields removed for production use.
        
        Returns:
            New RetrievalResult without debug fields
        """
        from copy import deepcopy
        result = deepcopy(self)
        result.scores_before = []
        result.scores_after = []
        result.latency_ms = 0.0
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetrievalResult":
        """Deserialize from dictionary."""
        return cls(**data)
