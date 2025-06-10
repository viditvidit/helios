"""
Request models for AI service
"""
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class CodeRequest:
    """
    Request model for code generation and modification.

    This class encapsulates all the information needed for the AI service to process a code-related request.
    It includes the user's prompt, any relevant files, Git context, instructions, and conversation history.
    """
    prompt: str  # The main request from the user.
    files: Dict[str, str] = field(default_factory=dict)  # A dictionary of file paths and their content.
    git_context: str = ""  # Information about the current Git repository state.
    instructions: str = ""  # Specific instructions for the AI service.
    conversation_history: List[Dict] = field(default_factory=list)  # A list of previous turns in the conversation.