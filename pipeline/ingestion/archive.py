"""
File archiving — move to dataset/processed/ after successful ingestion.
Preserves subfolder structure of original.
Only called after confirmed ChromaDB store AND hash write.
"""
from pathlib import Path
import shutil


def _archive_file(file_path: str, dataset_path: str) -> None:
    """
    Move file to dataset/processed/ after successful ingestion.
    Preserves subfolder structure of original.
    
    Examples:
    - dataset/readme.md → dataset/processed/readme.md
    - dataset/docs/manual.pdf → dataset/processed/docs/manual.pdf
    
    Args:
        file_path: Absolute path to source file
        dataset_path: Absolute path to dataset/ folder
        
    Raises:
        IOError: If file cannot be moved
    """
    try:
        source_path = Path(file_path)
        dataset_folder = Path(dataset_path)
        
        # Get relative path from dataset/ root
        try:
            relative_path = source_path.relative_to(dataset_folder)
        except ValueError:
            raise IOError(f"File {file_path} is not within dataset folder {dataset_path}")
        
        # Build destination path
        processed_folder = dataset_folder / "processed"
        dest_path = processed_folder / relative_path
        
        # Create parent directories if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move file (atomic operation)
        shutil.move(str(source_path), str(dest_path))
        
    except shutil.Error as e:
        raise IOError(f"Failed to move file {file_path} to archive: {str(e)}")
    except Exception as e:
        raise IOError(f"Failed to archive file {file_path}: {str(e)}")
