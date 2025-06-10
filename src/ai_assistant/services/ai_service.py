"""
AI Service for handling local model interactions.
Now receives pre-selected, relevant context from the RAG pipeline.
"""
import asyncio
import json
from typing import Optional, AsyncGenerator
import aiohttp

from ..core.config import Config
from ..core.exceptions import AIServiceError
from ..models.request import CodeRequest

class AIService:
    """Service for interacting with local AI models"""

    def __init__(self, config: Config):
        self.config = config
        self.model_config = config.get_current_model()
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=600)
        timeout = aiohttp.ClientTimeout(total=timeout_seconds, sock_read=120)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def _build_prompt(self, request: CodeRequest) -> str:
        """
        Builds a simple prompt from the pre-selected context provided by the RAG pipeline.
        """
        prompt_parts = []
        
        if self.model_config.system_prompt:
            prompt_parts.append(f"System Prompt: {self.model_config.system_prompt}")

        if request.files:
            prompt_parts.append("You have been provided with the following relevant context from the codebase:")
            for file_path, content in request.files.items():
                prompt_parts.append(f"--- From file: {file_path} ---\n{content}\n--- End of {file_path} context ---")

        if request.conversation_history:
            history = request.conversation_history[-4:]
            prompt_parts.append("\nRecent Conversation History:")
            for turn in history:
                prompt_parts.append(f"{turn['role'].capitalize()}: {turn['content']}")
        
        prompt_parts.append(f"\nUser Request: {request.prompt}")
        prompt_parts.append("\nBased ONLY on the context provided, please answer the user's request.")

        return "\n\n".join(prompt_parts)

    async def stream_generate(self, request: CodeRequest) -> AsyncGenerator[str, None]:
        if self.model_config.type == 'ollama':
            async for chunk in self._stream_ollama(request):
                yield chunk
        else:
            raise AIServiceError(f"Unsupported streaming model type: {self.model_config.type}")

    async def _stream_ollama(self, request: CodeRequest) -> AsyncGenerator[str, None]:
        if not self.session or self.session.closed:
            raise AIServiceError("AIOHTTP session is not active.")
        prompt = self._build_prompt(request)
        payload = {
            "model": self.model_config.name,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self.model_config.temperature,
                "num_ctx": self.model_config.context_length,
                "num_predict": self.model_config.max_tokens,
            }
        }
        url = f"{self.model_config.endpoint}/api/generate"
        try:
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise AIServiceError(f"Ollama API error ({response.status}): {error_text}")
                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            if 'response' in data:
                                yield data['response']
                            if data.get('done', False):
                                break
                        except json.JSONDecodeError:
                            continue
        except asyncio.TimeoutError:
            raise AIServiceError("Request to Ollama timed out. The model may be taking too long to respond.")
        except aiohttp.ClientError as e:
            raise AIServiceError(f"Connection error to Ollama at {url}: {e}")