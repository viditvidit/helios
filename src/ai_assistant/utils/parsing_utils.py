import re
from pathlib import Path
from typing import List, Dict, Optional

def extract_file_content_from_response(text: str) -> List[Dict[str, str]]:
    """
    Extracts file content from an AI's response. It robustly handles two formats:
    1. The preferred custom XML-like tag: <file path="..."></file>
    2. A common fallback markdown block with a path attribute: ```... path="..."
    """
    extracted_items = []

    # 1. Try to find the preferred <file> tag format first.
    xml_pattern = re.compile(r'<file\s+path=["\'](.*?)["\']>(.*?)</file>', re.DOTALL)
    for match in xml_pattern.finditer(text):
        path = match.group(1).strip()
        content = match.group(2).strip()
        if path and content:
            extracted_items.append({"filename": path, "code": content})
    
    if extracted_items:
        return extracted_items

    # 2. If no <file> tags, fall back to finding markdown blocks with a path attribute.
    # This handles the model's "stubborn" output.
    md_pattern = re.compile(r"```[^\n]*?(?:path|filename)=[\"'](.*?)[\"'][^\n]*\n(.*?)\n```", re.DOTALL)
    for match in md_pattern.finditer(text):
        path = match.group(1).strip().lstrip('@') # Also strip @ here for good measure
        content = match.group(2).strip()
        if path and content:
            extracted_items.append({"filename": path, "code": content})

    return extracted_items


def build_file_tree(file_paths: List[str]) -> str:
    """
    Builds a textual representation of a file tree from a list of file paths.
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
        items = sorted(d.items(), key=lambda x: (not bool(x[1]), x[0]))
        for i, (name, children) in enumerate(items):
            connector = '└── ' if i == len(items) - 1 else '├── '
            lines.append(f"{indent}{connector}{name}")
            if children:
                extension = '    ' if i == len(items) - 1 else '│   '
                lines.extend(generate_tree_lines(children, indent + extension))
        return lines

    return '\n'.join(generate_tree_lines(tree))
