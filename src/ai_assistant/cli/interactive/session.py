# src/ai_assistant/cli/interactive/session.py

import os
import asyncio
import signal
from pathlib import Path
from typing import Optional, Iterable

from rich.console import Console
import questionary
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, FuzzyCompleter
from prompt_toolkit.styles import Style

from .command_handler import CommandHandler
from .chat_handler import ChatHandler
from .orchestrator import Orchestrator 
from . import display
from ...core.config import Config
from ...services.file_service import FileService
from ...services.github_service import GitHubService
from ...services.vector_store import VectorStore
from ...logic import indexing_logic
from ...utils.git_utils import GitUtils

console = Console()

class FilePathCompleter(Completer):
    def __init__(self, session):
        self.session = session
    
    def get_completions(self, document, complete_event) -> Iterable[Completion]:
        text_before_cursor = document.text_before_cursor
        if '@' in text_before_cursor:
            word_before_cursor = document.get_word_before_cursor(WORD=True)
            if word_before_cursor.startswith('@'):
                search_text = word_before_cursor[1:]
                current_files = sorted(list(set(self.session.current_files.keys())))
                for path in current_files:
                    # A basic substring check for completion
                    if search_text.lower() in path.lower():
                        yield Completion(path, start_position=-len(search_text))
    
class InteractiveSession:
    """Manages the state and main loop for an interactive chat session."""
    def __init__(self, config: Config):
        self.config = config
        self.file_service = FileService(config)
        self.github_service = GitHubService(config)
        self.vector_store = VectorStore(config)
        self.conversation_history = []
        self.current_files = {} 
        self.last_ai_response_content: Optional[str] = None
        self.command_handler = CommandHandler(self)
        self.chat_handler = ChatHandler(self)
        self.orchestrator = Orchestrator(self)
        signal.signal(signal.SIGINT, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        if hasattr(self, 'chat_handler') and self.chat_handler._generation_task and not self.chat_handler._generation_task.done():
            self.chat_handler.stop_generation()
        else:
            raise KeyboardInterrupt

    async def _setup_working_directory(self):
        helios_dir = Path.cwd() / ".helios"
        if helios_dir.exists():
            console.print(f"[dim]Using existing project root: {Path.cwd()}[/dim]")
            return
        if await questionary.confirm(f"Initialize project in current directory? ({Path.cwd()})", default=True, auto_enter=False).ask_async():
            if not await GitUtils().is_git_repo(Path.cwd()):
                if await questionary.confirm("This directory is not a Git repository. Initialize one now?", default=True, auto_enter=False).ask_async():
                    await GitUtils().init_repo(Path.cwd())
                    console.print("[green]✓ Git repository initialized.[/green]")
            (Path.cwd() / ".helios").mkdir(exist_ok=True)
        else:
            console.print("[red]Initialization cancelled. Exiting.[/red]"); exit(0)

    async def start(self):
        """Start the interactive mode session, with advanced autocomplete."""
        await self._setup_working_directory()
        
        file_contents = await indexing_logic.check_and_run_startup_indexing(self.config)
        if file_contents:
            self.current_files.update(file_contents)
        else:
            console.print("[yellow]Could not initialize repository context.[/yellow]")
        
        display.show_welcome()

        file_completer = FilePathCompleter(self)
        fuzzy_file_completer = FuzzyCompleter(file_completer)
        style = Style.from_dict({
            'completion-menu.completion.current': 'bg:#333333 #ffffff',
            'completion-menu.completion': 'bg:#1a1a1a #666666',
            '': '#00d7ff bold',
            'prompt': '#ffffff bold',
        })

        prompt_session = PromptSession(
            message=[('class:prompt', '> ')],
            completer=fuzzy_file_completer,
            complete_while_typing=True,
            style=style,
            input_processors=[]
        )

        while True:
            try:
                console.print("")
                user_input = await prompt_session.prompt_async("> ")
                
                if not user_input.strip(): continue
                if user_input.lower() in ['exit', 'quit', 'bye']: 
                    display.show_goodbye()
                    break
                
                # --- FIX 3: Correct the call to orchestrator.handle ---
                # It no longer needs the session passed as it's part of the instance
                await self.orchestrator.handle(user_input)

            except KeyboardInterrupt:
                console.print("") 
                continue 
            except EOFError:
                display.show_goodbye()
                break
            except Exception as e:
                console.print(f"[red]Unexpected error: {e}[/red]")
                import traceback
                console.print(f"[dim]{traceback.format_exc()}[/dim]")