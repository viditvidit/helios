"""
CLI command implementations
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import List, Optional, Dict

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.text import Text
from rich.columns import Columns
from rich.layout import Layout

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

class CodeCommands:
    """Implementation of code-related commands"""

    def __init__(self, config: Config):
        self.config = config
        self.file_service = FileService(config)
        self.file_utils = FileUtils()
        self.github_service = GitHubService(config, Path.cwd())
        self.git_utils = GitUtils()

    async def get_ai_repo_summary(self, repo_path: Path = None) -> str:
        """Gets repository context and asks AI to summarize it."""
        return await self.github_service.get_ai_repo_summary(repo_path)

    async def generate_code(self, prompt: str, files: List[str],
                          show_diff: bool = False, apply_changes: bool = False):
        """Generate or modify code based on a prompt and file context."""
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
                    async for chunk in ai_service.stream_generate(request):
                        response_content += chunk

                await self._display_and_process_response(response_content, show_diff, apply_changes)

        except Exception as e:
            logger.error(f"Error during code generation: {e}", exc_info=True)
            raise AIAssistantError(f"Failed to generate code: {e}")

    async def review_changes(self, show_summary: bool = True, show_diff: bool = True):
        """Review staged changes and optionally commit and push them after verification."""
        repo_path = Path.cwd()
        try:
            if not await self.git_utils.is_git_repo(repo_path):
                raise NotAGitRepositoryError(path=repo_path, message="Not a Git repository. Cannot review changes.")

            staged_diff = await self.git_utils.get_staged_diff(repo_path)
            if not staged_diff:
                if click.confirm("No staged changes found. Stage all modified files?"):
                    await self.git_utils.add_all(repo_path)
                    staged_diff = await self.git_utils.get_staged_diff(repo_path)
                    if not staged_diff:
                        console.print("[yellow]No changes to stage. Aborting.[/yellow]")
                        return
                else:
                    console.print("[yellow]No staged changes to review. Aborting.[/yellow]")
                    return

            # Get staged files and their individual diffs
            changed_files = []
            file_diffs = {}
            
            try:
                # Get list of staged files
                result = await asyncio.create_subprocess_exec(
                    'git', 'diff', '--cached', '--name-only',
                    cwd=repo_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await result.communicate()
                
                if result.returncode == 0 and stdout.decode().strip():
                    files = stdout.decode().strip().split('\n')
                    for file in files:
                        if file.strip():
                            # Get individual file diff
                            file_diff_result = await asyncio.create_subprocess_exec(
                                'git', 'diff', '--cached', '--', file.strip(),
                                cwd=repo_path,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )
                            file_diff_stdout, _ = await file_diff_result.communicate()
                            
                            if file_diff_result.returncode == 0:
                                file_diff = file_diff_stdout.decode()
                                # Process diff to show only changed lines with context
                                processed_diff = self._process_github_style_diff(file_diff)
                                file_diffs[file.strip()] = processed_diff
                                
                            # Determine file status
                            status_result = await asyncio.create_subprocess_exec(
                                'git', 'status', '--porcelain', '--cached', '--', file.strip(),
                                cwd=repo_path,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )
                            status_stdout, _ = await status_result.communicate()
                            
                            if status_stdout:
                                status_line = status_stdout.decode().strip()
                                status = status_line[:2] if status_line else "M "
                                status_icon = "📝" if "M" in status else "📄" if "A" in status else "🗑️" if "D" in status else "📄"
                                changed_files.append(f"{status_icon} {file.strip()}")
                            else:
                                changed_files.append(f"📝 {file.strip()}")
                                
            except Exception as e:
                console.print(f"[yellow]Debug: Error getting staged files: {e}[/yellow]")
                # Fallback: Extract from main diff
                import re
                diff_files = re.findall(r'diff --git a/(.*?) b/', staged_diff)
                for file in diff_files:
                    changed_files.append(f"📝 {file}")
                    file_diffs[file] = staged_diff  # Use full diff as fallback

            # Show summary if requested
            if show_summary:
                if changed_files:
                    files_content = "\n".join(changed_files)
                    files_content += f"\n\n📊 Total: {len(changed_files)} files"
                else:
                    files_content = "No staged files found"
                    
                console.print(Panel(
                    files_content,
                    title="📋 Staged Files",
                    border_style="cyan",
                    padding=(1, 1)
                ))
                console.print()  # Add spacing

            # Show individual file diffs if requested
            if show_diff and file_diffs:
                for file_path, diff_content in file_diffs.items():
                    if diff_content.strip():
                        # Get file extension for syntax highlighting
                        file_ext = Path(file_path).suffix.lower()
                        
                        console.print(Panel(
                            Syntax(diff_content, "diff", theme="github-dark", word_wrap=True),
                            title=f"🔍 {file_path}",
                            border_style="green",
                            padding=(1, 1)
                        ))
                        console.print()  # Add spacing between files

            if not click.confirm("Proceed to commit these changes?", default=True):
                console.print("[yellow]Commit aborted.[/yellow]")
                return

            commit_message = click.prompt("Enter commit message")

            if not commit_message:
                console.print("[red]Commit message cannot be empty. Aborting.[/red]")
                return

            await self.git_utils.commit(repo_path, commit_message)
            console.print(f"[green]✓ Changes committed with message: '{commit_message}'[/green]")

            if click.confirm("Push changes to remote?", default=False):
                with console.status("[bold yellow]Pushing changes...[/bold yellow]"):
                    branch = await self.git_utils.get_current_branch(repo_path)
                    await self.git_utils.push(repo_path, branch)
                console.print(f"[green]✓ Changes pushed to branch '{branch}'.[/green]")
            else:
                console.print("[yellow]Changes were not pushed.[/yellow]")

        except NotAGitRepositoryError as e:
            console.print(f"[red]{e.message}[/red]")
        except Exception as e:
            logger.error(f"Error during review process: {e}", exc_info=True)
            raise AIAssistantError(f"Failed to review changes: {e}")

    async def _prepare_request(self, prompt: str, files: List[str]) -> CodeRequest:
        """Prepare AI request with file and Git context."""
        file_contents = {}
        read_tasks = [self.file_service.read_file(Path(file)) for file in files]
        results = await asyncio.gather(*read_tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                console.print(f"[yellow]Warning: Could not read {files[i]}: {result}[/yellow]")
            else:
                file_contents[files[i]] = result

        repo_context = await self.github_service.get_repository_context()
        git_context_str = (
            f"Current Branch: {repo_context.get('current_branch')}\n"
            f"Unstaged Changes:\n{repo_context.get('status') or 'None'}"
        ) if repo_context.get("is_git_repo") else ""

        return CodeRequest(prompt=prompt, files=file_contents, git_context=git_context_str)

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
            # Simple check for a file path.
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

    def _process_github_style_diff(self, diff_content: str) -> str:
        """Process diff content to show GitHub-style condensed view with only changed sections."""
        if not diff_content.strip():
            return diff_content
            
        lines = diff_content.split('\n')
        processed_lines = []
        in_hunk = False
        context_lines = 3  # Number of context lines to show
        
        for line in lines:
            # Keep diff headers
            if line.startswith('diff --git') or line.startswith('index ') or line.startswith('---') or line.startswith('+++'):
                processed_lines.append(line)
            # Process hunk headers
            elif line.startswith('@@'):
                processed_lines.append(line)
                in_hunk = True
            # Process content lines in hunks
            elif in_hunk:
                # Always include added, removed, or context lines
                if line.startswith(('+', '-', ' ')) or line == '':
                    processed_lines.append(line)
                # Stop processing if we hit another diff section
                elif line.startswith('diff --git'):
                    in_hunk = False
                    processed_lines.append(line)
            else:
                processed_lines.append(line)
        
        return '\n'.join(processed_lines)