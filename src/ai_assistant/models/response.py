"""
Response models from AI service
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class CodeResponse:
    """Response model for code generation."""
    content: str
    model: str
    usage: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)