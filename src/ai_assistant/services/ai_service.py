"""
AI Service for handling local model interactions
"""
import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncGenerator
import aiohttp
from ..core.config import Config, ModelConfig
from ..core.exceptions import AIServiceError
from ..models.request import CodeRequest
from ..models.response import CodeResponse

class AIService:
    """Service for interacting with local AI models"""
    
    def __init__(self, config: Config):
        self.config = config
        self.model_config = config.get_current_model()
        self.session: Optional[aiohttp.ClientSession] = None

    async def close_session(self):
        pass
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None
    
    async def generate_code(self, request: CodeRequest) -> CodeResponse:
        """Generate code based on the request"""
        try:
            if self.model_config.type == 'ollama':
                return await self._generate_ollama(request)
            else:
                raise AIServiceError(f"Unsupported model type: {self.model_config.type}")
                
        except Exception as e:
            raise AIServiceError(f"Error generating code: {e}")
    
    async def _generate_ollama(self, request: CodeRequest) -> CodeResponse:
        """Generate code using Ollama API"""
        prompt = self._build_prompt(request)
        
        payload = {
            "model": self.model_config.name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.model_config.temperature,
                "num_predict": self.model_config.max_tokens,
            }
        }
        
        if not self.session:
            raise AIServiceError("Session not initialized")
            
        url = f"{self.model_config.endpoint}/api/generate"
        
        async with self.session.post(url, json=payload) as response:
            if response.status != 200:
                raise AIServiceError(f"Ollama API error: {response.status}")
            
            data = await response.json()
            
            return CodeResponse(
                content=data.get('response', ''),
                model=self.model_config.name,
                usage={
                    'prompt_tokens': data.get('prompt_eval_count', 0),
                    'completion_tokens': data.get('eval_count', 0),
                    'total_tokens': data.get('prompt_eval_count', 0) + data.get('eval_count', 0)
                }
            )
    
    def _build_prompt(self, request: CodeRequest) -> str:
        """Build the prompt for the AI model"""
        prompt_parts = []
        
        # Add system context
        if self.model_config.system_prompt:
            prompt_parts.append(f"System: {self.model_config.system_prompt}")
        
        # Add file context
        if request.files:
            prompt_parts.append("Context files:")
            for file_path, content in request.files.items():
                prompt_parts.append(f"\n--- {file_path} ---")
                prompt_parts.append(content)
                prompt_parts.append("--- End of file ---\n")
        
        # Add git context
        if request.git_context:
            prompt_parts.append(f"Git context: {request.git_context}")
        
        # Add main prompt
        prompt_parts.append(f"Request: {request.prompt}")
        
        # Add instructions
        if request.instructions:
            prompt_parts.append(f"Instructions: {request.instructions}")
        
        return "\n\n".join(prompt_parts)
    
    async def stream_generate(self, request: CodeRequest) -> AsyncGenerator[str, None]:
        """Generate code with streaming response"""
        if self.model_config.type == 'ollama':
            async for chunk in self._stream_ollama(request):
                yield chunk
        else:
            # For non-streaming models, yield the complete response
            response = await self.generate_code(request)
            yield response.content
    
    async def _stream_ollama(self, request: CodeRequest) -> AsyncGenerator[str, None]:
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        """Stream code generation using Ollama API"""
        prompt = self._build_prompt(request)
        
        payload = {
            "model": self.model_config.name,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self.model_config.temperature,
                "num_predict": self.model_config.max_tokens,
            }
        }
        
        url = f"{self.model_config.endpoint}/api/generate"
        
        async with self.session.post(url, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                raise AIServiceError(f"Ollama API error: {response.status} - {error_text}")
            
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