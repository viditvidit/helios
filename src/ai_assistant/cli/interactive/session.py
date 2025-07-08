import signal
from pathlib import Path
from typing import Optional, Iterable

from rich.console import Console
import questionary
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, FuzzyCompleter
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML

from .command_handler import CommandHandler
from .chat_handler import ChatHandler
from . import display
from ...core.config import Config
from ...services.file_service import FileService
from ...services.github_service import GitHubService
from ...services.vector_store import VectorStore
from ...logic import indexing_logic
from ...utils.git_utils import GitUtils

console = Console()

# --- NEW: Custom Completer for file paths ---
class FilePathCompleter(Completer):
    def __init__(self, session):
        self.session = session  # Reference to session for dynamic file list
    
    def get_completions(self, document, complete_event) -> Iterable[Completion]:
        """Yields all possible file paths for the fuzzy completer to filter."""
        text_before_cursor = document.text_before_cursor
        
        # Only trigger if there's an '@' and no space after it yet
        if '@' in text_before_cursor:
            word_before_cursor = document.get_word_before_cursor(WORD=True)
            if word_before_cursor.startswith('@'):
                # The word we are completing is after the '@'
                search_text = word_before_cursor[1:]
                # Get current file list dynamically from session
                current_files = sorted(list(set(self.session.current_files.keys())))
                for path in current_files:
                    yield Completion(
                        path,
                        start_position=-len(search_text),
                        display=path
                    )

class StatusBar:
    """Manages the status bar information."""
    
    def __init__(self, config: Config):
        self.config = config
        self.git_utils = GitUtils()
        self._current_dir = str(Path.cwd())
        self._current_branch = None
        self._current_model = config.model_name
        
    async def get_current_branch(self) -> str:
        """Get the current git branch."""
        try:
            if await self.git_utils.is_git_repo(Path.cwd()):
                branch = await self.git_utils.get_current_branch(Path.cwd())
                return branch or "no-branch"
            return "no-git"
        except Exception:
            return "no-git"
    
    async def update_status(self):
        """Update status information."""
        self._current_dir = str(Path.cwd())
        self._current_branch = await self.get_current_branch()
        self._current_model = self.config.model_name
        
    def get_toolbar_text(self) -> HTML:
        """Get the toolbar text for prompt_toolkit."""
        # Truncate directory path if too long
        max_dir_len = 40
        display_dir = self._current_dir
        if len(display_dir) > max_dir_len:
            display_dir = "..." + display_dir[-(max_dir_len-3):]
            
        return HTML(
            f'<style>'
            f'Dir: <b>{display_dir}</b> | '
            f'Branch: <style bg="ansigreen">{self._current_branch}</style> | '
            f'Model: <style bg="ansiyellow">{self._current_model}</style>'
            f'</style>'
        )

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
        self.status_bar = StatusBar(config)
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
        console.print("[yellow]Helios project not initialized in this directory.[/yellow]")
        if await questionary.confirm(f"Initialize project in current directory? ({Path.cwd()})", default=True, auto_enter=False).ask_async():
            if not await GitUtils().is_git_repo(Path.cwd()):
                if await questionary.confirm("This directory is not a Git repository. Initialize one now?", default=True, auto_enter=False).ask_async():
                    await GitUtils().init_repo(Path.cwd())
                    console.print("[green]✓ Git repository initialized.[/green]")
            (Path.cwd() / ".helios").mkdir(exist_ok=True)
        else:
            console.print("[red]Initialization cancelled. Exiting.[/red]"); exit(0)

    async def start(self):
        """Start the interactive mode session, with advanced autocomplete and status bar."""
        await self._setup_working_directory()
        
        file_contents = await indexing_logic.check_and_run_startup_indexing(self.config)
        if file_contents:
            self.current_files.update(file_contents)
        else:
            console.print("[yellow]Could not initialize repository context.[/yellow]")
        
        # Initialize status bar
        await self.status_bar.update_status()
        
        display.show_welcome()

        # --- NEW: Setup prompt_toolkit session with custom styles and fuzzy completer ---
        # Create a completer that gets file list dynamically from session
        file_completer = FilePathCompleter(self)  # Pass session instead of static file list
        fuzzy_file_completer = FuzzyCompleter(file_completer)

        # Custom styles for the autocomplete menu and status bar
        style = Style.from_dict({
            'completion-menu.completion.current': 'bg:#333333 #ffffff', # Selected item
            'completion-menu.completion': 'bg:#1a1a1a #666666',      # Other items
            'completion-menu.meta.completion.current': 'bg:#333333 #cccccc',
            'completion-menu.meta.completion': 'bg:#1a1a1a #444444',
            '': '#00d7ff bold',  # Default text color (cyan, bold)
            'prompt': '#ffffff bold',  # Prompt symbol color
            'bottom-toolbar': 'bg:#222222 #333333',  # Status bar style
        })

        prompt_session = PromptSession(
            message=[('class:prompt', '> ')],
            completer=fuzzy_file_completer,
            complete_while_typing=True,
            style=style,
            input_processors=[],
            bottom_toolbar=self.status_bar.get_toolbar_text,
        )

        while True:
            try:
                # Update status bar before each prompt
                await self.status_bar.update_status()
                
                console.print("")
                user_input = await prompt_session.prompt_async()
                
                if not user_input.strip(): continue
                if user_input.lower() in ['exit', 'quit', 'bye']: display.show_goodbye(); break
                
                if user_input.startswith('/'):
                    await self.command_handler.handle(user_input)
                else:
                    await self.chat_handler.handle(user_input, self)

            except KeyboardInterrupt:
                # This is triggered by our custom signal handler
                console.print("") # Newline after prompt
                continue 
            except EOFError:
                display.show_goodbye(); break
            except Exception as e:
                console.print(f"[red]Unexpected error: {e}[/red]")
                import traceback
                console.print(f"[dim]{traceback.format_exc()}[/dim]")