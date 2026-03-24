"""
Conversation history management with token budgeting and compression.
Separate from PipelineState — one ConversationHistory per user conversation.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class ConversationTurn:
    """Single turn in a conversation."""
    
    query: str
    intent: str  # "fact" | "summary" | "comparison" | "conversational"
    chunks: List[Dict[str, Any]] = field(default_factory=list)  # List of chunk dicts
    token_count: int = 0
    timestamp: str = ""  # ISO 8601 timestamp
    
    def __post_init__(self):
        """Set timestamp if not provided."""
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize turn to dictionary."""
        return {
            "query": self.query,
            "intent": self.intent,
            "chunks": self.chunks,
            "token_count": self.token_count,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationTurn":
        """Deserialize turn from dictionary."""
        return cls(**data)


@dataclass
class ConversationHistory:
    """Rolling window conversation history with token budgeting and compression."""
    
    max_tokens: int = 1500
    turns: List[ConversationTurn] = field(default_factory=list)
    _total_token_count: int = field(default=0, init=False, repr=False)
    
    def add_turn(self, turn: ConversationTurn) -> None:
        """
        Add a new turn to history and enforce token budget via _trim().
        
        Args:
            turn: ConversationTurn to add
        """
        self.turns.append(turn)
        self._update_total_tokens()
        self._trim()
    
    def _update_total_tokens(self) -> None:
        """Recalculate total token count across all turns."""
        self._total_token_count = sum(turn.token_count for turn in self.turns)
    
    def _trim(self) -> None:
        """
        Enforce token budget.
        1. If over budget, mark oldest turn for compression (goal: ~100 tokens)
        2. If still over budget, drop oldest turn entirely
        """
        if self._total_token_count <= self.max_tokens:
            return
        
        # Try to compress oldest turn first
        if len(self.turns) > 1:
            oldest_turn = self.turns[0]
            # Attempt compression: reduce token count estimate to ~100
            # In production, this calls LLMRouter to summarize via DeepSeek
            # For now, we'll mark it for compression and drop if still needed
            compression_reduction = max(0, oldest_turn.token_count - 100)
            oldest_turn.token_count = max(100, oldest_turn.token_count // 3)
            self._update_total_tokens()
        
        # If still over budget, drop oldest turn entirely
        while self._total_token_count > self.max_tokens and len(self.turns) > 1:
            self.turns.pop(0)
            self._update_total_tokens()
    
    def excluded_ids(self) -> List[str]:
        """
        Get all chunk IDs across all turns.
        Returned list is passed to retriever so already-seen chunks are never re-fetched.
        
        Returns:
            Flat list of chunk IDs from all turns' chunks
        """
        ids = []
        for turn in self.turns:
            for chunk in turn.chunks:
                if "id" in chunk:
                    ids.append(chunk["id"])
        return ids
    
    def recent_chunks(self, n: int = 2) -> List[Dict[str, Any]]:
        """
        Get all chunks from the last N turns.
        Used to inject context for conversational queries so LLM can resolve references.
        
        Args:
            n: Number of recent turns to include
            
        Returns:
            List of all chunks from last N turns
        """
        chunks = []
        for turn in self.turns[-n:]:
            chunks.extend(turn.chunks)
        return chunks
    
    def get_total_tokens(self) -> int:
        """Get current total token count."""
        self._update_total_tokens()
        return self._total_token_count
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize entire history to dictionary."""
        return {
            "max_tokens": self.max_tokens,
            "turns": [turn.to_dict() for turn in self.turns],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationHistory":
        """Deserialize history from dictionary."""
        history = cls(max_tokens=data.get("max_tokens", 1500))
        history.turns = [
            ConversationTurn.from_dict(turn_data)
            for turn_data in data.get("turns", [])
        ]
        history._update_total_tokens()
        return history
