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
        
        # Automatically load repository context on startup
        await self._auto_load_repo_context()
        
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

    async def _auto_load_repo_context(self):
        """Automatically load all repository files into context."""
        try:
            from ..commands import CodeCommands
            repo_context = CodeCommands.build_repo_context(str(Path.cwd()))
            
            if repo_context:
                self.current_files.update(repo_context)
                file_count = len(repo_context)
                total_lines = sum(len(content.split('\n')) for content in repo_context.values())
                
                display.console.print(f"[green]✓ Auto-loaded {file_count} files ({total_lines} total lines) from repository into context[/green]")
                
                # Show a summary of loaded files
                if file_count > 10:
                    sample_files = list(repo_context.keys())[:10]
                    display.console.print(f"[dim]Sample files: {', '.join([Path(f).name for f in sample_files])}... and {file_count - 10} more[/dim]")
                else:
                    display.console.print(f"[dim]Loaded files: {', '.join([Path(f).name for f in repo_context.keys()])}[/dim]")
            else:
                display.console.print("[yellow]No files found in current directory to load into context[/yellow]")
                
        except Exception as e:
            display.console.print(f"[yellow]Warning: Could not auto-load repository context: {e}[/yellow]")