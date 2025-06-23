"""
AI Service for handling local model interactions.
Refactored to use the Ollama /api/chat endpoint for better instruction following.
"""
import asyncio
import json
from typing import Optional, AsyncGenerator, List, Dict

import aiohttp
from rich.text import Text

from ..core.config import Config
from ..core.exceptions import AIServiceError
from ..models.request import CodeRequest, ContentPart
from ..utils.parsing_utils import build_file_tree


class AIService:
    """Service for interacting with local AI models via the /api/chat endpoint."""

    def __init__(self, config: Config):
        self.config = config
        self.model_config = config.get_current_model()
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        # Increased timeout for potentially long AI operations like reviews
        timeout = aiohttp.ClientTimeout(total=self.model_config.timeout)
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

        if self.model_config.system_prompt:
            messages.append({"role": "system", "content": self.model_config.system_prompt})

        user_prompt_parts = []
        if request.repository_files:
            tree_str = build_file_tree(request.repository_files)
            user_prompt_parts.append("This is the file structure of the project for your reference:")
            user_prompt_parts.append(f"--- REPOSITORY FILE TREE ---\n{tree_str}\n--- END REPOSITORY FILE TREE ---")

        history_to_include = request.conversation_history[:-1]
        if history_to_include:
            user_prompt_parts.append("\n--- Previous Conversation ---")
            for turn in history_to_include:
                user_prompt_parts.append(f"{turn['role'].capitalize()}: {turn['content']}")
            user_prompt_parts.append("--- End of Previous Conversation ---")

        if request.files:
            user_prompt_parts.append("\n--- Relevant File Context ---")
            for file_path, content in request.files.items():
                user_prompt_parts.append(f"START OF FILE: {file_path}\n{content}\nEND OF FILE: {file_path}")
            user_prompt_parts.append("--- End of File Context ---")

        user_prompt_parts.append(f"\nMy Request: {request.prompt}")
        
        user_prompt_content = "\n\n".join(user_prompt_parts)
        messages.append({"role": "user", "content": user_prompt_content})

        return messages

    async def stream_generate(self, request: CodeRequest) -> AsyncGenerator[str, None]:
        """Streams a response, removing content within <Thinking>...</Thinking> tags."""
        if self.model_config.type != 'ollama':
            raise AIServiceError(f"Unsupported streaming model type: {self.model_config.type}")

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
        start_tag = "<Thinking>"
        end_tag = "</Thinking>"

        try:
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise AIServiceError(f"Ollama API error ({response.status}): {error_text}")
                
                async for line in response.content:
                    if not line: continue
                    try:
                        data = json.loads(line.decode('utf-8'))
                        if 'message' in data and 'content' in data['message']:
                            chunk = data['message']['content']
                            buffer += chunk
                            
                            # Process the buffer as long as there's something to do
                            while True:
                                scan_again = False
                                if in_thought_block:
                                    end_pos = buffer.find(end_tag)
                                    if end_pos != -1:
                                        # End of thought block found. Discard content up to tag.
                                        buffer = buffer[end_pos + len(end_tag):]
                                        in_thought_block = False
                                        scan_again = True # There might be another tag in the remaining buffer
                                    else:
                                        # Still inside a thought block, need more data.
                                        # Discard the current buffer as it's all thought content.
                                        buffer = ""
                                else: # Not in a thought block
                                    start_pos = buffer.find(start_tag)
                                    if start_pos != -1:
                                        # Start of a thought block found.
                                        # Yield the content before the tag.
                                        if start_pos > 0:
                                            yield buffer[:start_pos]
                                        # Keep the content after the tag for the next scan.
                                        buffer = buffer[start_pos + len(start_tag):]
                                        in_thought_block = True
                                        scan_again = True # The rest of the buffer needs scanning.
                                    else:
                                        # No tags found, yield the whole buffer and clear it.
                                        if buffer:
                                            yield buffer
                                        buffer = ""
                                
                                if not scan_again:
                                    break # Nothing more to process in the buffer for now

                        if data.get('done'):
                            break
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                
                # After the loop, yield any remaining buffer content if not in a thought block.
                if buffer and not in_thought_block:
                    yield buffer

        except asyncio.TimeoutError:
            raise AIServiceError("Request to Ollama timed out. The model may be taking too long to respond.")
        except aiohttp.ClientError as e:
            raise AIServiceError(f"Connection error to Ollama at {url}: {e}")