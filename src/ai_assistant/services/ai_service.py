# src/ai_assistant/services/ai_service.py

import asyncio
import json
import os
from typing import Optional, AsyncGenerator, List, Dict

import aiohttp
import google.generativeai as genai
from rich.text import Text

from ..core.config import Config
from ..core.exceptions import AIServiceError, ConfigurationError
from ..models.request import CodeRequest
from ..utils.parsing_utils import build_file_tree

class AIService:
    """Service for interacting with AI models from different providers."""

    def __init__(self, config: Config):
        self.config = config
        self.model_config = config.get_current_model()
        self.aiohttp_session: Optional[aiohttp.ClientSession] = None

        if self.model_config.provider == 'gemini':
            if not self.model_config.api_key:
                raise ConfigurationError("Gemini API key not found in configuration.")
            genai.configure(api_key=self.model_config.api_key)

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=self.model_config.timeout)
        self.aiohttp_session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.aiohttp_session and not self.aiohttp_session.closed:
            await self.aiohttp_session.close()

    def _build_ollama_messages(self, request: CodeRequest) -> List[Dict[str, str]]:
        messages = []
        if self.model_config.system_prompt:
            messages.append({"role": "system", "content": self.model_config.system_prompt})
        
        user_prompt_parts = []
        if request.repository_files:
            user_prompt_parts.append(f"--- REPOSITORY FILE TREE ---\n{build_file_tree(request.repository_files)}\n---")
        if request.files:
            user_prompt_parts.append("\n--- FILE CONTEXT ---\n")
            for path, content in request.files.items():
                user_prompt_parts.append(f"START OF FILE: {path}\n{content}\nEND OF FILE: {path}")
        
        user_prompt_parts.append(f"\nMy Request: {request.prompt}")
        user_prompt_content = "\n\n".join(user_prompt_parts)
        
        history = request.conversation_history[:-1]
        for turn in history: messages.append(turn)
        messages.append({"role": "user", "content": user_prompt_content})
        return messages

    async def _stream_ollama(self, request: CodeRequest) -> AsyncGenerator[str, None]:
        if not self.aiohttp_session or self.aiohttp_session.closed:
            raise AIServiceError("AIOHTTP session is not active.")

        messages = self._build_ollama_messages(request)
        payload = {
            "model": self.model_config.name, "messages": messages, "stream": True,
            "options": {"temperature": self.model_config.temperature, "num_ctx": self.model_config.context_length}
        }
        url = f"{self.model_config.endpoint}/api/chat"
        
        try:
            async with self.aiohttp_session.post(url, json=payload) as response:
                response.raise_for_status()
                async for line in response.content:
                    if line:
                        data = json.loads(line.decode('utf-8'))
                        if 'message' in data and data['message'].get('content'):
                            yield data['message']['content']
                        if data.get('done'): break
        except Exception as e:
            raise AIServiceError(f"Connection error to Ollama: {e}")

    def _build_gemini_contents(self, request: CodeRequest) -> List[Dict]:
        contents = []
        for turn in request.conversation_history[:-1]:
            contents.append({"role": turn['role'], "parts": [{"text": turn['content']}]})
        
        user_prompt_parts = []
        if request.repository_files:
            user_prompt_parts.append(f"--- REPO TREE ---\n{build_file_tree(request.repository_files)}\n---")
        if request.files:
            user_prompt_parts.append("\n--- FILE CONTEXT ---\n")
            for path, content in request.files.items():
                user_prompt_parts.append(f"File: {path}\n```\n{content}\n```")
        user_prompt_parts.append(f"\nMy Request: {request.prompt}")
        
        contents.append({"role": "user", "parts": [{"text": "\n\n".join(user_prompt_parts)}]})
        return contents

    async def _stream_gemini(self, request: CodeRequest) -> AsyncGenerator[str, None]:
        model = genai.GenerativeModel(
            self.model_config.name,
            system_instruction=self.model_config.system_prompt
        )
        contents = self._build_gemini_contents(request)
        
        try:
            response = await model.generate_content_async(contents, stream=True)
            async for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            raise AIServiceError(f"Error with Gemini API: {e}")

    async def stream_generate(self, request: CodeRequest) -> AsyncGenerator[str, None]:
        provider = self.model_config.provider
        
        provider_stream = None
        if provider == 'ollama':
            provider_stream = self._stream_ollama(request)
        elif provider == 'gemini':
            provider_stream = self._stream_gemini(request)
        else:
            raise AIServiceError(f"Unsupported provider: {provider}")

        # Universal Thinking tag filter
        buffer, in_thought_block = "", False
        start_tag, end_tag = "<Thinking>", "</Thinking>"
        
        async for chunk in provider_stream:
            buffer += chunk
            while True:
                scan_again = False
                if in_thought_block:
                    end_pos = buffer.find(end_tag)
                    if end_pos != -1:
                        buffer = buffer[end_pos + len(end_tag):]
                        in_thought_block = False
                        scan_again = True
                    else: break
                else:
                    start_pos = buffer.find(start_tag)
                    if start_pos != -1:
                        yield buffer[:start_pos]
                        buffer = buffer[start_pos + len(start_tag):]
                        in_thought_block = True
                        scan_again = True
                    else: break
            if not in_thought_block and buffer:
                yield buffer
                buffer = ""
        
        if not in_thought_block and buffer:
            yield buffer