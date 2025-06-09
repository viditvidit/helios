"""
File operations service
"""
import logging
import aiofiles
from pathlib import Path
from typing import List, Dict
from ..core.config import Config
from ..core.exceptions import FileServiceError

logger = logging.getLogger(__name__)

class FileService:
    """Service for asynchronous file operations."""
    
    def __init__(self, config: Config):
        self.config = config
    
    async def read_file(self, file_path: Path) -> str:
        """Read file content asynchronously, with validation."""
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            
            if file_path.stat().st_size > self.config.max_file_size:
                raise FileServiceError(f"File is too large: {file_path} ({file_path.stat().st_size} bytes)")
            
            # Allow supported extensions or files with no extension (like Dockerfile)
            if file_path.suffix and file_path.suffix not in self.config.supported_extensions and file_path.name not in self.config.supported_extensions:
                 raise FileServiceError(f"Unsupported file type: {file_path.suffix}")
            
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            logger.debug(f"Successfully read file: {file_path}")
            return content
                
        except UnicodeDecodeError:
            logger.error(f"Unicode decode error for file: {file_path}")
            raise FileServiceError(f"Unable to decode file as UTF-8: {file_path}")
        except Exception as e:
            if not isinstance(e, FileServiceError):
                logger.error(f"Unexpected error reading file {file_path}: {e}")
                raise FileServiceError(f"Error reading file {file_path}: {e}")
            raise e

    async def write_file(self, file_path: Path, content: str):
        """Write content to file asynchronously."""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            logger.info(f"Successfully wrote changes to file: {file_path}")
        except Exception as e:
            logger.error(f"Error writing to file {file_path}: {e}")
            raise FileServiceError(f"Error writing file {file_path}: {e}")