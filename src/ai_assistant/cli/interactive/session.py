from pathlib import Path
from typing import Optional
from rich.prompt import Prompt

from ...core.config import Config
from ...services.file_service import FileService
from ...services.github_service import GitHubService
from ...utils.file_utils import build_repo_context
from .command_handler import CommandHandler
from .chat_handler import ChatHandler
from . import display

class InteractiveSession:
    """Manages the state and main loop for an interactive chat session."""

    def __init__(self, config: Config):
        self.config = config
        self.file_service = FileService(config)
        self.github_service = GitHubService(config, Path.cwd())

        # State
        self.conversation_history = []
        self.current_files = {}  # Holds the full context of all repo files
        self.last_ai_response_content: Optional[str] = None

        # Handlers
        self.command_handler = CommandHandler(self)
        self.chat_handler = ChatHandler(self)

    async def start(self):
        """Start the interactive mode session."""
        display.print_helios_banner()
        display.show_welcome()

        await self.refresh_repo_context(show_summary=True)

        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]Helios[/bold cyan]")
                user_input = user_input.strip()

                if not user_input:
                    continue
                if user_input.lower() in ['exit', 'quit', 'q']:
                    display.console.print("[yellow]Exiting Helios. Goodbye![/yellow]")
                    break
                elif user_input.startswith('/'):
                    await self.command_handler.handle(user_input)
                else:
                    self.last_ai_response_content = None
                    await self.chat_handler.handle(user_input)

            except (KeyboardInterrupt, EOFError):
                display.console.print("\n[yellow]Exiting...[/yellow]")
                break
            except Exception as e:
                display.console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
                import traceback
                display.console.print(f"[dim]{traceback.format_exc()}[/dim]")

    async def refresh_repo_context(self, show_summary: bool = False):
        """Load or reload all repository files into the session context."""
        with display.console.status("[bold yellow]Scanning repository for context...[/bold yellow]"):
            repo_path = Path.cwd()
            repo_context = build_repo_context(repo_path, self.config)

        self.current_files.clear()
        if repo_context:
            self.current_files.update(repo_context)
            file_count = len(repo_context)
            total_lines = sum(len(content.split('\n')) for content in repo_context.values())
            msg = f"[green]✓ Context updated: {file_count} files ({total_lines} total lines) loaded.[/green]"

            if show_summary:
                display.console.print(msg)
                if file_count > 10:
                    sample_files = list(repo_context.keys())[:10]
                    display.console.print(f"[dim]Including: {', '.join([Path(f).name for f in sample_files])}... and {file_count - 10} more.[/dim]")
                else:
                    display.console.print(f"[dim]Loaded files: {', '.join([Path(f).name for f in repo_context.keys()])}[/dim]")
            else:
                display.console.print(msg)
        else:
            display.console.print("[yellow]No supported files found to load into context.[/yellow]")