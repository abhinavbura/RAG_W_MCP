"""
Pipeline state management and file metadata tracking.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
import json
from datetime import datetime
import hashlib


@dataclass
class FileMetadata:
    """Per-file metadata for tracking ingestion status and changes."""
    
    path: str
    file_type: str  # "md" | "txt" | "pdf"
    size_chars: int
    hash: str  # MD5 of raw file bytes
    status: str  # "new" | "changed" | "unchanged" | "failed" | "ingested"
    chunks_added: int = 0
    error: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileMetadata":
        """Deserialize from dictionary."""
        return cls(**data)


@dataclass
class PipelineState:
    """Single source of truth for all runtime state. JSON-serialisable."""
    
    # Folder group
    folder_path: str
    total_files: int = 0
    total_size_chars: int = 0
    files_metadata: List[FileMetadata] = field(default_factory=list)
    files_to_ingest: List[str] = field(default_factory=list)
    
    # Model group
    model_key: str = ""  # "nomic" or "bge-large"
    model_name: str = ""  # Full HuggingFace model identifier
    model_dims: int = 0
    model_ctx_tokens: int = 0
    requires_prefix: bool = False
    query_prefix: str = ""
    doc_prefix: str = ""
    model_source: str = ""  # "computed" or "collection_metadata"
    
    # ChromaDB group
    collection_name: str = "rag_pipeline"
    db_path: str = "./chroma_db"
    collection_exists: bool = False
    collection_count: int = 0
    
    # Current file group
    current_doc: str = ""
    current_doc_size: int = 0
    current_doc_band: str = ""  # "small" | "medium" | "large"
    current_structure: str = ""  # "structured" or "flat"
    current_chunker: str = ""  # "markdown" | "structured" | "semantic"
    current_config: Dict[str, Any] = field(default_factory=dict)
    
    # Session group
    session_id: str = ""  # 8-char MD5 hash
    session_started_at: str = ""  # ISO 8601 timestamp
    ingested_files: List[str] = field(default_factory=list)
    skipped_files: List[str] = field(default_factory=list)
    failed_files: List[tuple] = field(default_factory=list)  # [(filename, reason), ...]
    total_chunks_added: int = 0
    model_upgrade_warning: str = ""
    
    # LLM Budget group
    llm_tokens_used_deepseek: int = 0
    llm_tokens_used_gpt: int = 0
    llm_budget_gpt: int = 50000  # Configurable, default 50000
    llm_calls_by_task: Dict[str, int] = field(default_factory=dict)
    
    # BM25 group
    enable_bm25: bool = False
    bm25_index: Optional[Any] = None
    
    # Private fields (never serialised)
    _model_instance: Optional[Any] = field(default=None, init=False, repr=False)
    _collection: Optional[Any] = field(default=None, init=False, repr=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary, excluding private fields."""
        result = asdict(self)
        # Remove private fields
        result.pop("_model_instance", None)
        result.pop("_collection", None)
        # Convert FileMetadata objects to dicts
        result["files_metadata"] = [
            fm.to_dict() if isinstance(fm, FileMetadata) else fm
            for fm in self.files_metadata
        ]
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineState":
        """Deserialize from dictionary. Private fields set to None."""
        # Convert file_metadata dicts back to FileMetadata objects
        if "files_metadata" in data:
            data["files_metadata"] = [
                FileMetadata.from_dict(fm) if isinstance(fm, dict) else fm
                for fm in data["files_metadata"]
            ]
        return cls(**data)
    
    def save(self, path: str) -> None:
        """Save state to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: str) -> "PipelineState":
        """Load state from JSON file."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def set_current_file(self, file_metadata: FileMetadata, doc_band: str, 
                        structure: str, chunker: str, config: Dict[str, Any]) -> None:
        """Refresh all current_* fields for the file being processed."""
        self.current_doc = file_metadata.path
        self.current_doc_size = file_metadata.size_chars
        self.current_doc_band = doc_band
        self.current_structure = structure
        self.current_chunker = chunker
        self.current_config = config
    
    def record_ingested(self, filename: str, chunks_added: int) -> None:
        """Record successful ingestion of a file."""
        self.ingested_files.append(filename)
        self.total_chunks_added += chunks_added
        # Update file_metadata status
        for fm in self.files_metadata:
            if fm.path == filename:
                fm.status = "ingested"
                fm.chunks_added = chunks_added
                break
    
    def record_failed(self, filename: str, reason: str) -> None:
        """Record failed ingestion. Does NOT update hash store."""
        self.failed_files.append((filename, reason))
        # Update file_metadata status
        for fm in self.files_metadata:
            if fm.path == filename:
                fm.status = "failed"
                fm.error = reason
                break
    
    def record_skipped(self, filename: str) -> None:
        """Record skipped file (unchanged hash)."""
        self.skipped_files.append(filename)
        # Update file_metadata status
        for fm in self.files_metadata:
            if fm.path == filename:
                fm.status = "unchanged"
                break
    
    def update_collection_count(self, collection: Any) -> None:
        """Update live chunk count from ChromaDB collection."""
        self.collection_count = collection.count()
    
    def generate_session_id(self) -> None:
        """Generate 8-char session ID and set started_at timestamp."""
        self.session_id = hashlib.md5(
            datetime.now().isoformat().encode()
        ).hexdigest()[:8]
        self.session_started_at = datetime.now().isoformat()
