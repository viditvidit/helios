import difflib
import os
from pathlib import Path
from typing import List, Tuple, Dict

from ..core.config import Config


def build_repo_context(repo_path: Path, config: Config) -> Dict[str, str]:
    """
    Recursively collect the content of all supported text files in a directory.
    Skips common temporary/build directories.
    Option 1 - Remove file size limits to include full context:
    """
    context = {}
    excluded_dirs = {'.git', 'node_modules', '__pycache__', 'venv', '.venv', 'build', 'dist', 'target', 'tests'}

    for root, dirs, files in os.walk(repo_path, topdown=True):
        dirs[:] = [d for d in dirs if d not in excluded_dirs]

        for file in files:
            file_path = Path(root) / file
            try:
                # Use relative path for keys
                relative_path_str = str(file_path.relative_to(repo_path))

                is_supported_name = file_path.name in config.supported_extensions
                is_supported_ext = file_path.suffix in config.supported_extensions

                if is_supported_name or is_supported_ext:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        context[relative_path_str] = f.read()
            except (IOError, OSError, UnicodeDecodeError):
                # Ignore files that can't be opened, read, or decoded
                continue
    return context


class FileUtils:
    """Utility functions for file operations"""

    @staticmethod
    def generate_diff(original: str, modified: str, filename: str = "file") -> str:
        """Generate unified diff between two strings"""
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=""
        )

        return ''.join(diff)

    @staticmethod
    def get_language_from_extension(ext: str) -> str:
        """Get syntax highlighting language from file extension"""
        lang_map = {
            '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
            '.java': 'java', '.cpp': 'cpp', '.c': 'c', '.go': 'go',
            '.rs': 'rust', '.rb': 'ruby', '.php': 'php',
            '.html': 'html', '.css': 'css', '.scss': 'scss',
            '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml',
            '.md': 'markdown', '.txt': 'text', '.sh': 'bash'
        }
        return lang_map.get(ext.lower(), 'text')