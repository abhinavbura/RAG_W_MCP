"""
Embedding model loader with module-level caching.
Models are loaded once per process and reused across all files.
"""
from typing import Optional, Any


# Module-level cache: model_key → SentenceTransformer instance
_MODEL_CACHE = {}


# Model registry
_MODEL_REGISTRY = {
    "nomic": {
        "name": "nomic-ai/nomic-embed-text-v1.5",
        "dims": 768,
        "ctx_tokens": 8192,
        "requires_prefix": True,
        "trust_remote_code": True,
        "query_prefix": "search_query: ",
        "doc_prefix": "search_document: ",
    },
    "bge-large": {
        "name": "BAAI/bge-large-en-v1.5",
        "dims": 1024,
        "ctx_tokens": 512,
        "requires_prefix": False,
        "trust_remote_code": False,
        "query_prefix": "",
        "doc_prefix": "",
    },
}


def _get_or_load_model(model_key: str) -> Any:
    """
    Get model from cache, or load and cache if not present.
    Loads only once per process — 1.3GB bge-large reused across all files.
    
    Args:
        model_key: "nomic" or "bge-large"
        
    Returns:
        SentenceTransformer instance
        
    Raises:
        ValueError: If model_key not in registry
        ImportError: If sentence-transformers not installed
    """
    if model_key not in _MODEL_REGISTRY:
        raise ValueError(f"Unknown model_key: {model_key}. Valid options: {list(_MODEL_REGISTRY.keys())}")
    
    # Check cache first
    if model_key in _MODEL_CACHE:
        return _MODEL_CACHE[model_key]
    
    # Load model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError("sentence-transformers required. Install with: pip install sentence-transformers")
    
    model_info = _MODEL_REGISTRY[model_key]
    model = SentenceTransformer(
        model_info["name"],
        trust_remote_code=model_info["trust_remote_code"],
    )
    
    # Cache it
    _MODEL_CACHE[model_key] = model
    
    return model


def get_model_info(model_key: str) -> dict:
    """
    Get model metadata without loading the model.
    
    Args:
        model_key: "nomic" or "bge-large"
        
    Returns:
        Dict with model info (dims, ctx_tokens, requires_prefix, etc.)
        
    Raises:
        ValueError: If model_key not in registry
    """
    if model_key not in _MODEL_REGISTRY:
        raise ValueError(f"Unknown model_key: {model_key}")
    
    return _MODEL_REGISTRY[model_key]


def select_model_for_folder_size(total_size_chars: int) -> str:
    """
    Select embedding model based on cumulative folder size.
    
    Logic:
    - < 500K chars (~10 pages) → nomic (smaller, faster)
    - >= 500K chars (50+ pages) → bge-large (best MTEB scores)
    
    Args:
        total_size_chars: Sum of all file sizes in chars
        
    Returns:
        Model key: "nomic" or "bge-large"
    """
    if total_size_chars < 500_000:
        return "nomic"
    else:
        return "bge-large"
