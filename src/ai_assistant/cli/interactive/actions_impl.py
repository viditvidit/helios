from pathlib import Path
from rich.console import Console
import click

from ...utils.git_utils import GitUtils
from ...utils.parsing_utils import extract_code_blocks
from ...core.exceptions import AIAssistantError
from ..commands import CodeCommands  # <-- **THE FIX**: Corrected import path, moved to top.

console = Console()


async def handle_new_file(session, file_path: str):
    """Creates a new empty file and adds it to the context."""
    path = Path(file_path)
    if path.exists():
        console.print(f"[yellow]File already exists: {file_path}[/yellow]")
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        # Add empty file to context
        relative_path_str = str(path.relative_to(Path.cwd()))
        session.current_files[relative_path_str] = ""
        console.print(f"[green]✓ Created new file and added to context: {relative_path_str}[/green]")
    except Exception as e:
        console.print(f"[red]Error creating file: {e}[/red]")


async def handle_save_last_code(session, filename: str):
    """Saves the first code block from the last AI response to a file."""
    if not session.last_ai_response_content:
        console.print("[red]No AI response available to save from.[/red]")
        return

    code_blocks = extract_code_blocks(session.last_ai_response_content)
    if not code_blocks:
        console.print("[red]No code blocks found in the last AI response.[/red]")
        return

    code_to_save = code_blocks[0]['code']
    path = Path(filename)
    try:
        await session.file_service.write_file(path, code_to_save)
        console.print(f"[green]✓ Code saved to {filename}[/green]")
        # Add/update the newly saved file in the active context
        relative_path_str = str(path.relative_to(Path.cwd()))
        session.current_files[relative_path_str] = code_to_save
        console.print(f"[green]✓ {relative_path_str} is now in the active context.[/green]")
    except Exception as e:
        console.print(f"[red]Error saving file: {e}[/red]")


async def handle_git_add(session, files: list[str]):
    """Stages one or more files using git."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]This is not a git repository.[/red]")
        return

    added_files = []
    for f_str in files:
        if (repo_path / f_str).exists():
            if await git_utils.add_file(repo_path, f_str):
                added_files.append(f_str)
        else:
            console.print(f"[yellow]Warning: File not found, cannot stage: {f_str}[/yellow]")

    if added_files:
        console.print(f"[green]✓ Staged files: {', '.join(added_files)}[/green]")


async def handle_git_commit(session, message: str):
    """Commits staged changes with a given message."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]This is not a git repository.[/red]")
        return

    if not message:
        console.print("[red]Commit message cannot be empty.[/red]")
        return

    try:
        if await git_utils.commit(repo_path, message):
            console.print(f"[green]✓ Committed with message: \"{message}\"[/green]")
        else:
            console.print("[yellow]Commit failed. Are there any staged changes?[/yellow]")
    except Exception as e:
        console.print(f"[red]Error during commit: {e}[/red]")


async def handle_git_push(session):
    """Pushes committed changes to the remote repository."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]This is not a git repository.[/red]")
        return

    try:
        current_branch = await git_utils.get_current_branch(repo_path)
        with console.status(f"[bold yellow]Pushing to origin/{current_branch}...[/bold yellow]"):
            if await git_utils.push(repo_path, current_branch):
                console.print(f"[green]✓ Successfully pushed to origin/{current_branch}[/green]")
            else:
                console.print("[red]Failed to push changes. Check remote configuration and authentication.[/red]")
    except Exception as e:
        console.print(f"[red]Error during push: {e}[/red]")


async def handle_repo_review(session):
    """Initiates an interactive review of repository changes."""
    # **THE FIX**: The import was moved to the top. This function now just uses it.
    cmd = CodeCommands(session.config)
    try:
        await cmd.review_changes()
    except AIAssistantError as e:
        console.print(f"[red]Error during review: {e}[/red]")