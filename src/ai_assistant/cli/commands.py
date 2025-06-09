"""
CLI command implementations
"""
import asyncio
import logging
import re
import click
from pathlib import Path
from typing import List, Optional, Dict
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

from ..core.config import Config
from ..core.exceptions import AIAssistantError, FileServiceError, GitHubServiceError
from ..services.ai_service import AIService
from ..services.github_service import GitHubService
from ..services.file_service import FileService
from ..models.request import CodeRequest
from ..models.response import CodeResponse
from ..utils.file_utils import FileUtils
from ..utils.git_utils import GitUtils

console = Console()
logger = logging.getLogger(__name__)

class CodeCommands:
    """Implementation of code-related commands"""
    
    def __init__(self, config: Config):
        self.config = config
        self.file_service = FileService(config)
        self.file_utils = FileUtils()
        # GitHubService is initialized with the current working directory
        self.github_service = GitHubService(config, Path.cwd())

    async def get_ai_repo_summary(self, repo_path: Path = None) -> str:
        github_service = GitHubService(self.config, repo_path)
        return await github_service.get_ai_repo_summary(repo_path)

    async def generate_code(self, prompt: str, files: List[str], 
                          show_diff: bool = False, apply_changes: bool = False):
        """Generate or modify code based on a prompt and file context."""
        ai_service = None # Initialize to None for the finally block
        try:
            request = await self._prepare_request(prompt, files)
            
            async with AIService(self.config) as ai_service:
                response_content = ""
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    transient=True,
                    console=console,
                ) as progress:
                    progress.add_task(f"Asking {self.config.get_current_model().name}...", total=None)
                    response_content = ""
                    async for chunk in ai_service.stream_generate(request):
                        response_content += chunk
            
                await self._display_and_process_response(response_content, show_diff, apply_changes)

        except Exception as e:
            logger.error(f"Error during code generation: {e}", exc_info=True)
            raise AIAssistantError(f"Failed to generate code: {e}")
        finally:
            pass # Or remove the finally block if it becomes empty and ai_service is only used in try.

    async def review_changes(self, create_branch: Optional[str] = None,
                           commit_changes: bool = False, push_changes: bool = False):
        """Review staged changes and optionally generate a commit message."""
        try:
            repo_context = await self.github_service.get_repository_context()
            if not repo_context.get("is_git_repo"):
                raise AIAssistantError("Not a Git repository. Cannot review changes.")
            
            staged_diff = await self.github_service.get_staged_diff()
            if not staged_diff:
                console.print("[yellow]No changes are staged for commit. Use 'git add <files>' to stage changes.[/yellow]")
                return

            console.print(Panel(
                Syntax(staged_diff, "diff", theme="github-dark", word_wrap=True),
                title="Staged Changes for Review",
                border_style="yellow"
            ))

            if commit_changes:
                console.print("\nGenerating a commit message based on the staged changes...")
                commit_message = await self._generate_commit_message(staged_diff)
                
                console.print(Panel(commit_message, title="Suggested Commit Message", border_style="green"))
                
                if Confirm.ask("Do you want to commit with this message?", default=True):
                    # For now, we commit directly. A more advanced implementation
                    # would allow editing the message.
                    await self.github_service.git_utils.commit(commit_message)
                    console.print(f"[green]✓ Changes committed.[/green]")
                else:
                    console.print("[yellow]Commit aborted by user.[/yellow]")

        except (GitHubServiceError, Exception) as e:
            logger.error(f"Error during review process: {e}", exc_info=True)
            raise AIAssistantError(f"Failed to review changes: {e}")

    async def _prepare_request(self, prompt: str, files: List[str]) -> CodeRequest:
        """Prepare AI request with file and Git context."""
        file_contents = {}
        git_context_str = ""
        
        # Load file contents concurrently
        read_tasks = [self.file_service.read_file(Path(file)) for file in files]
        results = await asyncio.gather(*read_tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                console.print(f"[yellow]Warning: Could not read {files[i]}: {result}[/yellow]")
            else:
                file_contents[files[i]] = result

        # Get Git context if in a repo
        repo_context = await self.github_service.get_repository_context()   
        if repo_context.get("is_git_repo"):
            try:
                git_context_str = (
                    f"Current Branch: {repo_context.get('current_branch')}\n"
                    f"Unstaged Changes:\n{repo_context.get('status') or 'None'}"
                )
            except GitHubServiceError as e:
                console.print(f"[yellow]Warning: Could not get Git context: {e}[/yellow]")

        return CodeRequest(
            prompt=prompt,
            files=file_contents,
            git_context=git_context_str
        )

    async def _display_and_process_response(self, content: str, show_diff: bool, apply_changes: bool):
        """Display AI response and handle diff/apply logic."""
        console.print(Panel(
            Syntax(content, "markdown", theme="github-dark", word_wrap=True),
            title=f"AI Response ({self.config.get_current_model().name})",
            border_style="blue"
        ))

        code_blocks = self._extract_code_blocks(content)
        if not code_blocks:
            # No file-specific code blocks found; prompt to save the full response instead.
            if click.confirm("No file paths detected in the AI response. Would you like to save the full response to a file?", default=True):
                file_name = click.prompt("Enter file name", default="ai_suggestion.txt")
                await self.file_service.write_file(Path(file_name), content)
                console.print(f"[green]Response saved to {file_name}.[/green]")
            else:
                console.print("[yellow]No changes applied.[/yellow]")
            return

        # Ask to apply changes (unless auto-applying via --apply flag)
        if not apply_changes:
            if not click.confirm("Do you want to apply these changes to your files?", default=True):
                console.print("[yellow]Changes were not applied.[/yellow]")
                return
        else:
            console.print("[green]Auto-applying changes as per --apply flag.[/green]")

        # Optionally show diff and apply changes to each file
        for file_path_str, code in code_blocks.items():
            file_path = Path(file_path_str)
            if show_diff:
                await self._show_file_diff(file_path, code)
            await self._apply_code_changes(file_path, code)
        console.print("[green]✓ Changes applied.[/green]")

        # Git Integration: Initialize repo if not present, then commit and push
        repo_path = Path.cwd()
        git_utils = GitUtils()
        if not await git_utils.is_git_repo(repo_path):
            if click.confirm("This directory is not a Git repository. Do you want to initialize a git repo here?", default=True):
                await git_utils.initialize_repository(repo_path)
                console.print("[green]✓ Git repository initialized.[/green]")
            else:
                console.print("[yellow]Git repository was not initialized.[/yellow]")
                return

        if click.confirm("Do you want to commit and push these changes to git?", default=False):
            for file_path_str in code_blocks:
                await git_utils.add_file(repo_path, file_path_str)
            commit_message = click.prompt("Enter commit message", default="Update via AI Assistant")
            await git_utils.commit(repo_path, commit_message)
            branch = await git_utils.get_current_branch(repo_path)
            await git_utils.push(repo_path, branch)
            console.print(f"[green]✓ Changes committed and pushed to branch {branch}.[/green]")
        else:
            console.print("[yellow]Changes were not pushed to git.[/yellow]")

    def _extract_code_blocks(self, content: str) -> Dict[str, str]:
        """Extracts code blocks that have a file path specified in the language hint."""
        # Regex to find ```language:path/to/file.ext
        # It captures the path and the code content until the closing ```
        pattern = re.compile(r"```(?:\w+:)?(.+?)\n(.*?)\n```", re.DOTALL)
        matches = pattern.findall(content)
        
        code_blocks = {}
        for match in matches:
            path, code = match
            # Clean up potential extra characters around path
            file_path = path.strip()
            # The system prompt requests a path, so we assume it's a file path
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
                border_style = "yellow"
                syntax_lang = "diff"
            else:
                diff = new_code
                panel_title = f"New File: {file_path}"
                border_style = "green"
                syntax_lang = self.file_utils.get_language_from_extension(file_path.suffix)

            console.print(Panel(
                Syntax(diff, syntax_lang, theme="github-dark", word_wrap=True),
                title=panel_title,
                border_style=border_style
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

    async def _generate_commit_message(self, diff: str) -> str:
        """Uses the AI to generate a conventional commit message from a diff."""
        prompt = (
            "Based on the following git diff, please generate a concise and "
            "informative commit message following the Conventional Commits specification. "
            "The message should have a short title (max 50 chars), a blank line, and a brief body explaining the changes. "
            "Do not include the diff in your response, only the commit message itself.\n\n"
            f"```diff\n{diff}\n```"
        )
        request = CodeRequest(prompt=prompt)
        
        ai_service = AIService(self.config)
        try:
            commit_message = await ai_service.stream_generate(request)
            return commit_message.strip()
        finally:
            await ai_service.close_session()