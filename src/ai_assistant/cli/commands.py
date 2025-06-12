"""
CLI command implementations
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import List, Optional, Dict
import signal

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax

from ..core.config import Config
from ..core.exceptions import AIAssistantError, FileServiceError, NotAGitRepositoryError
from ..models.request import CodeRequest
from ..services.ai_service import AIService
from ..services.file_service import FileService
from ..services.github_service import GitHubService
from ..utils.file_utils import FileUtils
from ..utils.git_utils import GitUtils

console = Console()
logger = logging.getLogger(__name__)

_should_stop = False
def _signal_handler(signum, frame):
    global _should_stop
    _should_stop = True

class CodeCommands:
    """Implementation of code-related commands"""

    def __init__(self, config: Config):
        self.config = config
        self.file_service = FileService(config)
        self.file_utils = FileUtils()
        self.github_service = GitHubService(config)
        self.git_utils = GitUtils()

    async def generate_code(self, prompt: str, files: List[str],
                          show_diff: bool = False, apply_changes: bool = False):
        global _should_stop
        _should_stop = False
        # Register the signal handler for this command run
        original_handler = signal.signal(signal.SIGINT, _signal_handler)
        
        try:
            request = await self._prepare_request(prompt, files)

            async with AIService(self.config) as ai_service:
                response_content = ""
                with Progress(...) as progress:
                    # ...
                    async for chunk in ai_service.stream_generate(request):
                        if _should_stop:
                            console.print("\n[yellow]Code generation stopped by user.[/yellow]")
                            break
                        response_content += chunk
                
                if not _should_stop:
                    await self._display_and_process_response(response_content, show_diff, apply_changes)

        except Exception as e:
            logger.error(f"Error during code generation: {e}", exc_info=True)
            raise AIAssistantError(f"Failed to generate code: {e}")
        finally:
            # Restore the original signal handler
            signal.signal(signal.SIGINT, original_handler)

    async def _prepare_request(self, prompt: str, files: List[str]) -> CodeRequest:
        """Prepare AI request with file context."""
        file_contents = {}
        read_tasks = [self.file_service.read_file(Path(file)) for file in files]
        results = await asyncio.gather(*read_tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                console.print(f"[yellow]Warning: Could not read {files[i]}: {result}[/yellow]")
            else:
                file_contents[files[i]] = result

        return CodeRequest(prompt=prompt, files=file_contents)

    async def _display_and_process_response(self, content: str, show_diff: bool, apply_changes: bool):
        """Display AI response and handle diff/apply logic."""
        console.print(Panel(
            Syntax(content, "markdown", theme="github-dark", word_wrap=True),
            title=f"AI Response ({self.config.get_current_model().name})",
            border_style="blue"
        ))

        code_blocks = self._extract_code_blocks(content)
        if not code_blocks:
            console.print("[yellow]No file-specific code blocks found in the response.[/yellow]")
            return

        if not apply_changes and not click.confirm("Apply these changes?", default=True):
            console.print("[yellow]Changes not applied.[/yellow]")
            return

        for file_path_str, code in code_blocks.items():
            file_path = Path(file_path_str)
            if show_diff:
                await self._show_file_diff(file_path, code)
            await self._apply_code_changes(file_path, code)

        console.print("[green]✓ Changes applied successfully.[/green]")

    def _extract_code_blocks(self, content: str) -> Dict[str, str]:
        """Extracts code blocks that have a file path specified in the language hint."""
        pattern = re.compile(r"```(?:\w*:)?(.+?)\n(.*?)\n```", re.DOTALL)
        matches = pattern.findall(content)

        code_blocks = {}
        for path, code in matches:
            file_path = path.strip()
            if '/' in file_path or '\\' in file_path or '.' in file_path:
                code_blocks[file_path] = code.strip()
        return code_blocks

    async def _show_file_diff(self, file_path: Path, new_code: str):
        """Displays a colorized diff for a file's changes."""
        try:
            if file_path.exists():
                original_code = await self.file_service.read_file(file_path)
                diff = self.file_utils.generate_diff(original_code, new_code, str(file_path))
                panel_title = f"Diff for {file_path}"
                syntax_lang = "diff"
            else:
                diff = new_code
                panel_title = f"New File: {file_path}"
                syntax_lang = self.file_utils.get_language_from_extension(file_path.suffix)

            console.print(Panel(
                Syntax(diff, syntax_lang, theme="github-dark", word_wrap=True),
                title=panel_title, border_style="yellow"
            ))
        except (FileServiceError, Exception) as e:
            console.print(f"[red]Error showing diff for {file_path}: {e}[/red]")

    async def _apply_code_changes(self, file_path: Path, code: str):
        """Applies the provided code to the specified file."""
        try:
            await self.file_service.write_file(file_path, code)
            console.print(f"[green]✓ Applied changes to {file_path}[/green]")
        except FileServiceError as e:
            console.print(f"[red]Error applying changes to {file_path}: {e}[/red]")