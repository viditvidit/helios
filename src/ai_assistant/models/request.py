"""
Request models for AI service
"""
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class CodeRequest:
    """Request model for code generation and modification."""
    prompt: str
    files: Dict[str, str] = field(default_factory=dict)
    git_context: str = ""
    instructions: str = ""
    conversation_history: List[Dict] = field(default_factory=list)