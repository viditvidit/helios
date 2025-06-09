"""
Utility for building prompts to send to the AI model.
"""
from typing import Dict
from ..core.config import ModelConfig
from ..models.request import CodeRequest

class PromptBuilder:
    """Constructs the final prompt string from a CodeRequest."""
    
    def __init__(self, model_config: ModelConfig):
        self.model_config = model_config

    def build(self, request: CodeRequest) -> str:
        """Builds the prompt string."""
        parts = []
        
        # System prompt is handled by the AI service if the API supports it.
        # Here, we include it directly for models like Ollama's /generate.
        if self.model_config.system_prompt:
            parts.append(self.model_config.system_prompt)

        # Add file context
        if request.files:
            parts.append("Here is the content of the relevant files:")
            for path, content in request.files.items():
                parts.append(f"--- START OF FILE: {path} ---\n{content}\n--- END OF FILE: {path} ---")

        # Add git context
        if request.git_context:
            parts.append(f"Current Git Status:\n{request.git_context}")

        # Main user prompt
        parts.append(f"User Request: {request.prompt}")

        # Add specific instructions
        if request.instructions:
            parts.append(f"Instructions: {request.instructions}")
        else:
            parts.append("Please provide your response.")

        return "\n\n".join(parts)