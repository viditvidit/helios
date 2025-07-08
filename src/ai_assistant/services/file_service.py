import logging
import aiofiles
from pathlib import Path
from ..core.config import Config
from ..core.exceptions import FileServiceError

logger = logging.getLogger(__name__)

class FileService:
    """Service for asynchronous file operations."""
    
    def __init__(self, config: Config):
        self.config = config
        # THE FIX: Work relative to the project root defined in config
        self.work_dir = config.work_dir
    
    async def read_file(self, file_path: Path | str) -> str:
        """Read file content asynchronously, with validation."""
        # Ensure file_path is a Path object and resolve it against the work_dir
        # This handles both relative paths from the root and absolute paths safely.
        full_path = self.work_dir.joinpath(file_path).resolve()
        
        try:
            # Security check to prevent reading files outside the project directory
            full_path.relative_to(self.work_dir)
            
            if not full_path.exists():
                raise FileNotFoundError(f"File not found: {full_path}")
            
            if full_path.stat().st_size > self.config.max_file_size:
                raise FileServiceError(f"File is too large: {full_path} ({full_path.stat().st_size} bytes)")
            
            # Allow supported extensions or files with no extension (like Dockerfile)
            if full_path.suffix and full_path.suffix not in self.config.supported_extensions and full_path.name not in self.config.supported_extensions:
                 raise FileServiceError(f"Unsupported file type: {full_path.suffix}")
            
            async with aiofiles.open(full_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            logger.debug(f"Successfully read file: {full_path}")
            return content
                
        except UnicodeDecodeError:
            logger.error(f"Unicode decode error for file: {full_path}")
            raise FileServiceError(f"Unable to decode file as UTF-8: {full_path}")
        except ValueError:
            raise FileServiceError(f"Security error: Attempted to read file outside of project directory: {full_path}")
        except Exception as e:
            if not isinstance(e, FileServiceError):
                logger.error(f"Unexpected error reading file {full_path}: {e}")
                raise FileServiceError(f"Error reading file {full_path}: {e}")
            raise e

    async def write_file(self, file_path: Path, content: str):
        """Write content to file asynchronously."""
        try:
            # Ensure we are writing within the project directory
            file_path.resolve().relative_to(self.work_dir)

            file_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            logger.info(f"Successfully wrote changes to file: {file_path}")
        except ValueError:
             raise FileServiceError(f"Security error: Attempted to write file outside of project directory: {file_path}")
        except Exception as e:
            logger.error(f"Error writing to file {file_path}: {e}")
            raise FileServiceError(f"Error writing file {file_path}: {e}")