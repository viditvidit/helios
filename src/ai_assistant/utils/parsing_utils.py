import re
from pathlib import Path
from typing import List, Dict

def extract_code_blocks(text: str) -> List[Dict[str, str]]:
    """
    Extracts code blocks from text.
    Looks for ```language filename="path/to/file.ext" ... or ```language path/to/file.ext ...
    Returns a list of dictionaries, each with 'language', 'filename', and 'code'.
    'filename' can be None if not found.
    """
    code_block_regex = re.compile(
        r"```(?:([\w+-.]+))?(?:\s+filename=[\"']([^\"']+)[\"'])?(?:\s+([^\s]+))?\s*\n(.*?)\n```",
        re.DOTALL
    )
    extracted_items = []
    for match in code_block_regex.finditer(text):
        token1 = match.group(1)
        token2 = match.group(2)
        token3 = match.group(3)
        code = match.group(4).strip()

        if token2:
            filename = token2
        elif token3:
            filename = token3
        elif token1 and '.' in token1:
            filename = token1
        else:
            filename = None

        if token1 and not (filename == token1 and '.' in token1):
            language = token1
        else:
            language = None
        
        extracted_items.append({
            "language": language,
            "filename": filename,
            "code": code
        })
    return extracted_items

def build_file_tree(file_context: Dict[str, str], max_files: int = 20) -> str:
    """Build a concise file tree representation."""
    file_paths = list(file_context.keys())
    
    if len(file_paths) <= max_files:
        return ", ".join([Path(p).name for p in file_paths])
    else:
        shown_files = [Path(p).name for p in file_paths[:max_files]]
        return f"{', '.join(shown_files)}, and {len(file_paths) - max_files} more files"