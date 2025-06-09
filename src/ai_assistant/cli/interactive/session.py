from pathlib import Path
from typing import Optional
from rich.prompt import Prompt

from ...core.config import Config
from ...services.file_service import FileService
from ...services.github_service import GitHubService
from ...utils.file_utils import FileUtils
from .command_handler import CommandHandler
from .chat_handler import ChatHandler
from . import display

class InteractiveSession:
    """Manages the state and main loop for an interactive chat session."""
    
    def __init__(self, config: Config):
        self.config = config
        self.file_service = FileService(config)
        self.github_service = GitHubService(config, Path.cwd())
        self.file_utils = FileUtils()
        
        # State
        self.conversation_history = []
        self.current_files = {}
        self.last_ai_response_content: Optional[str] = None

        # Handlers
        self.command_handler = CommandHandler(self)
        self.chat_handler = ChatHandler(self)
    
    async def start(self):
        """Start the interactive mode session."""
        display.show_welcome()
        
        while True:
            try:
                user_input = Prompt.ask("\n[bold blue]You[/bold blue]")
                
                if user_input.lower() in ['exit', 'quit', 'q']:
                    break
                elif user_input.lower() == 'help':
                    display.show_help()
                elif user_input.startswith('/'):
                    await self.command_handler.handle(user_input)
                else:
                    self.last_ai_response_content = None  # Clear before new chat
                    await self.chat_handler.handle(user_input)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                display.console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")