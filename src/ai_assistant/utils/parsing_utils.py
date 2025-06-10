import re
from pathlib import Path
from typing import List, Dict

def extract_code_blocks(text: str) -> List[Dict[str, str]]:
    """
    Extracts code blocks from text, identifying language and filename from the info string.
    Handles formats like:
    - ```python path/to/file.py
    - ```python filename="path/to/file.py"
    - ```path/to/file.py
    Returns a list of dictionaries, each with 'language' and 'filename'.
    """
    # A simpler, more robust regex to capture the entire info string and the code
    code_block_regex = re.compile(r"```([^\n]*)\n(.*?)\n```", re.DOTALL)
    
    extracted_items = []
    for match in code_block_regex.finditer(text):
        info_string = match.group(1).strip()
        code = match.group(2).strip()

        filename = None
        language = None

        # 1. Most specific: Look for filename="path/to/file.ext"
        fn_match = re.search(r"filename=[\"']([^\"']+)[\"']", info_string)
        if fn_match:
            filename = fn_match.group(1)
            # Remove the found part to avoid re-parsing it as a language
            info_string = info_string.replace(fn_match.group(0), "").strip()

        parts = info_string.split()
        remaining_parts = []

        # 2. In the remaining parts, look for a path-like string
        if not filename:
            for part in parts:
                # A simple but effective check for a file path (contains slashes or a dot)
                if '/' in part or '\\' in part or ('.' in part and len(part) > 1):
                    filename = part
                else:
                    remaining_parts.append(part)
        else: # filename was found with filename="..."
            remaining_parts = parts

        # 3. Assume the first remaining part is the language
        if remaining_parts:
            language = remaining_parts[0]
        
        # We only care about blocks that have identified code
        if code:
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