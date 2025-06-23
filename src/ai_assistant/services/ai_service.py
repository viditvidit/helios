# src/ai_assistant/services/ai_service.py

import asyncio
import json
from typing import Optional, AsyncGenerator, List, Dict

import aiohttp
from rich.text import Text

from ..core.config import Config
from ..core.exceptions import AIServiceError
from ..models.request import CodeRequest, ContentPart # UPDATED IMPORT
from ..utils.parsing_utils import build_file_tree


class AIService:
    """Service for interacting with local AI models via the /api/chat endpoint."""

    def __init__(self, config: Config):
        self.config = config
        self.model_config = config.get_current_model()
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=self.model_config.timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and not self.session.closed:
            await self.session.close()

    def _build_chat_messages(self, request: CodeRequest) -> List[Dict[str, any]]:
        """
        Builds messages for Ollama. Now handles multimodal prompts by extracting text
        and including image data if the model supports it (like llava).
        """
        messages = []
        if self.model_config.system_prompt:
            messages.append({"role": "system", "content": self.model_config.system_prompt})

        text_prompt = " ".join([part.content for part in request.prompt if part.type == 'text'])
        images_base64 = [part.content for part in request.prompt if part.type == 'image']

        user_prompt_parts = []
        # --- THE PROMPT FIX ---
        # If there are images, add a placeholder to the text prompt to signal to the AI.
        if images_base64:
            user_prompt_parts.append("[SYSTEM NOTE: An image has been provided. Please analyze it to answer the user's request.]\n")

        if request.repository_files:
            user_prompt_parts.append(f"--- REPOSITORY FILE TREE ---\n{build_file_tree(request.repository_files)}\n---")
        if request.files:
            user_prompt_parts.append("\n--- FILE CONTEXT ---\n")
            for path, content in request.files.items():
                user_prompt_parts.append(f"START OF FILE: {path}\n{content}\nEND OF FILE: {path}")
        
        user_prompt_parts.append(f"\nMy Request: {text_prompt}")
        user_prompt_content = "\n\n".join(user_prompt_parts)

        # Add history
        for turn in request.conversation_history[:-1]:
            messages.append(turn)
        
        user_message = {"role": "user", "content": user_prompt_content}
        if images_base64:
            user_message["images"] = images_base64
        
        messages.append(user_message)
        return messages

    async def stream_generate(self, request: CodeRequest) -> AsyncGenerator[str, None]:
        """Streams a response, removing content within <Thinking>...</Thinking> tags."""
        
        # In a real multi-provider setup, you would have a dispatcher here.
        # For now, we assume Ollama. Note: your config.py has 'provider', not 'type'.
        if self.model_config.type != 'ollama':
            raise AIServiceError(f"Unsupported provider for this service version: {self.model_config.type}")

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
        
        buffer = ""
        in_thought_block = False
        start_tag, end_tag = "<Thinking>", "</Thinking>"

        try:
            async with self.session.post(url, json=payload) as response:
                response.raise_for_status()
                async for line in response.content:
                    if not line: continue
                    try:
                        data = json.loads(line.decode('utf-8'))
                        if 'message' in data and data['message'].get('content'):
                            chunk = data['message']['content']
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
                        if data.get('done'): break
                    except (json.JSONDecodeError, UnicodeDecodeError): continue
                if not in_thought_block and buffer:
                    yield buffer
        except Exception as e:
            raise AIServiceError(f"Connection error to Ollama: {e}")