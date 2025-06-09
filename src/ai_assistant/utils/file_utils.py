import difflib
from pathlib import Path
from typing import List, Tuple

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
    def get_file_language(file_path: Path) -> str:
        """Determine programming language from file extension"""
        extension_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.jsx': 'javascript',
            '.tsx': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.h': 'c',
            '.hpp': 'cpp',
            '.go': 'go',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
            '.html': 'html',
            '.css': 'css',
            '.scss': 'scss',
            '.sass': 'sass',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.xml': 'xml',
            '.md': 'markdown',
            '.sh': 'bash',
            '.sql': 'sql',
            '.r': 'r',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala',
            '.clj': 'clojure'
        }
        
        return extension_map.get(file_path.suffix.lower(), 'text')
    
    @staticmethod
    def extract_functions(content: str, language: str) -> List[Tuple[str, int, int]]:
        """Extract function definitions from code (simplified implementation)"""
        functions = []
        lines = content.split('\n')
        
        if language == 'python':
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('def ') or stripped.startswith('async def '):
                    func_name = stripped.split('(')[0].replace('def ', '').replace('async ', '').strip()
                    functions.append((func_name, i + 1, i + 1))  # Simplified - just line number
        
        elif language in ['javascript', 'typescript']:
            for i, line in enumerate(lines):
                stripped = line.strip()
                if ('function ' in stripped or 
                    '=>' in stripped or 
                    stripped.startswith('const ') and '=' in stripped):
                    # Simplified function detection
                    parts = stripped.split()
                    if len(parts) > 1:
                        functions.append((parts[1], i + 1, i + 1))
        
        return functions
    
    @staticmethod
    def count_lines_of_code(content: str, language: str) -> dict:
        """Count lines of code, comments, and blank lines"""
        lines = content.split('\n')
        stats = {
            'total': len(lines),
            'code': 0,
            'comments': 0,
            'blank': 0
        }
        
        comment_patterns = {
            'python': ['#'],
            'javascript': ['//', '/*', '*'],
            'typescript': ['//', '/*', '*'],
            'java': ['//', '/*', '*'],
            'cpp': ['//', '/*', '*'],
            'c': ['//', '/*', '*'],
            'go': ['//', '/*', '*'],
            'rust': ['//', '/*', '*'],
            'ruby': ['#'],
            'php': ['//', '#', '/*', '*'],
            'html': ['<!--'],
            'css': ['/*', '*'],
        }
        
        patterns = comment_patterns.get(language, ['#', '//'])
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                stats['blank'] += 1
            elif any(stripped.startswith(p) for p in patterns):
                stats['comments'] += 1
            else:
                stats['code'] += 1
        
        return stats