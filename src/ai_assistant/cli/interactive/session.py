from pathlib import Path
from typing import Optional
import questionary
import asyncio
import signal

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
        # Correctly initialize GitHubService with only the config object
        self.github_service = GitHubService(config)
        
        self.vector_store = VectorStore(config)

        # State
        self.conversation_history = []
        self.current_files = {} 
        self.last_ai_response_content: Optional[str] = None

        # Handlers
        self.command_handler = CommandHandler(self)
        self.chat_handler = ChatHandler(self)
        
        signal.signal(signal.SIGINT, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        """Handle Ctrl+C interrupt to stop AI generation."""
        if hasattr(self, 'chat_handler'):
            self.chat_handler.stop_generation()

    async def start(self):
        """Start the interactive mode session."""
        # The banner is now shown in main.py before model selection.
        display.show_welcome()

        try:
            # We use /refresh to populate self.current_files
            await self.command_handler.handle("/refresh")
            display.console.print("[green]✓ Repository context initialized[/green]")
        except Exception as e:
            display.console.print(f"[yellow]Warning: Could not initialize repository context: {e}[/yellow]")

        while True:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: display.console.input("\n[bold cyan]You:[/bold cyan] ")
                )
                
                if not user_input.strip():
                    continue

                if user_input.lower() in ['exit', 'quit', 'bye']:
                    display.show_goodbye()
                    break

                if user_input.startswith('/'):
                    await self.command_handler.handle(user_input)
                else:
                    await self.chat_handler.handle(user_input)

            except KeyboardInterrupt:
                self.chat_handler.stop_generation()
                display.console.print("\n[yellow]Use 'exit' or 'quit' to leave the session.[/yellow]")
                continue
            except EOFError:
                display.show_goodbye()
                break
            except Exception as e:
                display.console.print(f"[red]Unexpected error: {e}[/red]")
                import traceback
                display.console.print(f"[dim]{traceback.format_exc()}[/dim]")

        display.console.print("\n[yellow]Exiting Helios. Goodbye![/yellow]")