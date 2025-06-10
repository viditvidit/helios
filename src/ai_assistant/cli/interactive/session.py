from pathlib import Path
from typing import Optional
import questionary

from ...core.config import Config
from ...services.file_service import FileService
from ...services.github_service import GitHubService
from ...services.vector_store import VectorStore
from .command_handler import CommandHandler
from .chat_handler import ChatHandler
from . import display

class InteractiveSession:
    """Manages the state and main loop for an interactive chat session."""

    def __init__(self, config: Config):
        self.config = config
        self.file_service = FileService(config)
        self.github_service = GitHubService(config, Path.cwd())
        
        # KEY CHANGE: Initialize the vector store to handle context.
        self.vector_store = VectorStore(config)

        # State
        self.conversation_history = []
        # `current_files` is no longer used to hold the entire repo.
        self.current_files = {} 
        self.last_ai_response_content: Optional[str] = None

        # Handlers
        self.command_handler = CommandHandler(self)
        self.chat_handler = ChatHandler(self)

    async def start(self):
        """Start the interactive mode session."""
        display.print_helios_banner()
        display.show_welcome()

        # No longer need to auto-load context. The `helios index` command handles this.

        while True:
            try:
                user_input = await questionary.text(
                    "You:",
                    qmark=">",
                    style=questionary.Style([('qmark', 'bold fg:cyan'), ('question', 'bold fg:cyan')])
                ).ask_async()

                if user_input is None:
                    break

                user_input = user_input.strip()

                if not user_input:
                    continue
                if user_input.lower() in ['exit', 'quit', 'q']:
                    break
                elif user_input.startswith('/'):
                    await self.command_handler.handle(user_input)
                else:
                    self.last_ai_response_content = None
                    await self.chat_handler.handle(user_input)

            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                display.console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
                import traceback
                display.console.print(f"[dim]{traceback.format_exc()}[/dim]")

        display.console.print("\n[yellow]Exiting Helios. Goodbye![/yellow]")