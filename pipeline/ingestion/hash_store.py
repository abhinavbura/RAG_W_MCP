"""
Hash store for tracking file changes via MD5.
Prevents re-ingestion of unchanged files.
Only written after successful archive — never on partial success.
"""
import hashlib
import json
from pathlib import Path
from typing import Dict


def _hash_file(file_path: str) -> str:
    """
    Compute MD5 hash of raw file bytes.
    
    Args:
        file_path: Path to file
        
    Returns:
        Hex digest of MD5 hash
        
    Raises:
        IOError: If file cannot be read
    """
    try:
        md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception as e:
        raise IOError(f"Failed to hash file {file_path}: {str(e)}")


def _load_hash_store(folder_path: str) -> Dict[str, str]:
    """
    Load hash store from .rag_hashes.json.
    
    Args:
        folder_path: Path to dataset/ folder
        
    Returns:
        Dict mapping relative file paths → MD5 hashes
        Returns empty dict if file doesn't exist
    """
    hash_file = Path(folder_path) / ".rag_hashes.json"
    
    if not hash_file.exists():
        return {}
    
    try:
        with open(hash_file, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load hash store: {str(e)}")
        return {}


def _save_hash_store(folder_path: str, hashes: Dict[str, str]) -> None:
    """
    Save hash store to .rag_hashes.json.
    Only called after successful file archive — never on partial success.
    
    Args:
        folder_path: Path to dataset/ folder
        hashes: Dict mapping file paths → MD5 hashes
        
    Raises:
        IOError: If file cannot be written
    """
    hash_file = Path(folder_path) / ".rag_hashes.json"
    
    try:
        # Ensure parent directory exists
        hash_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(hash_file, "w") as f:
            json.dump(hashes, f, indent=2)
    except Exception as e:
        raise IOError(f"Failed to save hash store to {hash_file}: {str(e)}")
