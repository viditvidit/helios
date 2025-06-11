"""
AI Service for handling local model interactions.
Refactored to use the Ollama /api/chat endpoint for better instruction following.
"""
import asyncio
import json
from typing import Optional, AsyncGenerator, List, Dict

import aiohttp

from ..core.config import Config
from ..core.exceptions import AIServiceError
from ..models.request import CodeRequest
from ..utils.parsing_utils import build_file_tree


class AIService:
    """Service for interacting with local AI models via the /api/chat endpoint."""

    def __init__(self, config: Config):
        self.config = config
        self.model_config = config.get_current_model()
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=600, sock_read=120)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def _build_chat_messages(self, request: CodeRequest) -> List[Dict[str, str]]:
        """
        Builds the list of messages for the Ollama chat endpoint.
        The system message contains instructions, and the user message contains all data.
        """
        messages = []

        # 1. System Prompt: Contains the core instructions and formatting rules.
        if self.model_config.system_prompt:
            messages.append({
                "role": "system",
                "content": self.model_config.system_prompt
            })

        # 2. User Prompt: Contains all the data - context, history, and the final request.
        user_prompt_parts = []

        # Add the full repository file tree for structural context.
        if request.repository_files:
            tree_str = build_file_tree(request.repository_files)
            user_prompt_parts.append("This is the file structure of the project for your reference:")
            user_prompt_parts.append("--- REPOSITORY FILE TREE ---")
            user_prompt_parts.append(tree_str)
            user_prompt_parts.append("--- END REPOSITORY FILE TREE ---")

        # Add conversation history.
        history_to_include = request.conversation_history[:-1]
        if history_to_include:
            user_prompt_parts.append("\n--- Previous Conversation ---")
            for turn in history_to_include:
                user_prompt_parts.append(f"{turn['role'].capitalize()}: {turn['content']}")
            user_prompt_parts.append("--- End of Previous Conversation ---")

        # Add relevant file context from RAG
        if request.files:
            user_prompt_parts.append("\n--- Relevant File Context (from semantic search) ---")
            for file_path, content in request.files.items():
                user_prompt_parts.append(f"START OF FILE: {file_path}\n{content}\nEND OF FILE: {file_path}")
            user_prompt_parts.append("--- End of File Context ---")

        # Add the actual, current user request at the very end.
        user_prompt_parts.append(f"\nMy Request: {request.prompt}")
        
        user_prompt_content = "\n\n".join(user_prompt_parts)
        
        messages.append({
            "role": "user",
            "content": user_prompt_content
        })

        return messages

    async def stream_generate(self, request: CodeRequest) -> AsyncGenerator[str, None]:
        if self.model_config.type == 'ollama':
            async for chunk in self._stream_ollama_chat(request):
                yield chunk
        else:
            raise AIServiceError(f"Unsupported streaming model type: {self.model_config.type}")

    async def _stream_ollama_chat(self, request: CodeRequest) -> AsyncGenerator[str, None]:
        """Streams a response from the Ollama /api/chat endpoint."""
        if not self.session or self.session.closed:
            raise AIServiceError("AIOHTTP session is not active.")

        messages = self._build_chat_messages(request)
        
        payload = {
            "model": self.model_config.name,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.model_config.temperature,
                "num_ctx": self.model_config.context_length,
                "num_predict": self.model_config.max_tokens,
            }
        }
        
        url = f"{self.model_config.endpoint}/api/chat"

        try:
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise AIServiceError(f"Ollama API error ({response.status}): {error_text}")
                
                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            if 'message' in data and 'content' in data['message']:
                                yield data['message']['content']
                            if data.get('done', False):
                                break
                        except json.JSONDecodeError:
                            continue
        except asyncio.TimeoutError:
            raise AIServiceError("Request to Ollama timed out. The model may be taking too long to respond.")
        except aiohttp.ClientError as e:
            raise AIServiceError(f"Connection error to Ollama at {url}: {e}")