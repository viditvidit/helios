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
        else:
            # filename was found with filename="..."
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

def build_file_tree(file_paths: List[str]) -> str:
    """
    Builds a textual representation of a file tree from a list of file paths.
    
    Example:
    ['src/main.py', 'src/utils/helpers.py', 'README.md']
    
    Output:
    ├── README.md
    └── src
        ├── main.py
        └── utils
            └── helpers.py
    """
    tree = {}
    for path_str in sorted(file_paths):
        path = Path(path_str)
        parts = path.parts
        node = tree
        for part in parts:
            node = node.setdefault(part, {})

    def generate_tree_lines(d, indent=''):
        lines = []
        # Sort items: directories first, then files alphabetically
        items = sorted(d.items(), key=lambda x: (not bool(x[1]), x[0]))
        for i, (name, children) in enumerate(items):
            connector = '└── ' if i == len(items) - 1 else '├── '
            lines.append(f"{indent}{connector}{name}")
            if children:
                extension = '    ' if i == len(items) - 1 else '│   '
                lines.extend(generate_tree_lines(children, indent + extension))
        return lines

    return '\n'.join(generate_tree_lines(tree))