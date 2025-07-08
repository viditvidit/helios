import ast
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class CodeAnalyzer:
    """A service to analyze code and extract structural information."""

    def analyze_file(self, file_path: Path, content: str) -> Dict[str, Any]:
        """Analyzes a file's content and returns a summary."""
        analysis = {"path": str(file_path)}
        if file_path.suffix == '.py':
            analysis.update(self._analyze_python(content))
        # Add analyzers for other languages here (e.g., using tree-sitter)
        return analysis

    def _analyze_python(self, content: str) -> Dict[str, Any]:
        """Analyzes Python code using the 'ast' module."""
        results = {"classes": [], "functions": []}
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    results["functions"].append({
                        "name": node.name,
                        "lineno": node.lineno,
                        "args": [arg.arg for arg in node.args.args]
                    })
                elif isinstance(node, ast.ClassDef):
                    results["classes"].append({
                        "name": node.name,
                        "lineno": node.lineno,
                        "methods": [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    })
        except SyntaxError as e:
            logger.warning(f"Could not parse Python file due to syntax error: {e}")
        return results