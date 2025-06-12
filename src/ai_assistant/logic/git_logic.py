from pathlib import Path
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.text import Text
import questionary

from ..utils.git_utils import GitUtils
from ..core.exceptions import NotAGitRepositoryError

console = Console()

async def add(files: list[str]):
    """Logic to stage files."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        return console.print("[red]This is not a git repository.[/red]")
    if not files:
        return console.print("[red]Usage: /git_add <file1> <file2>...[/red]")
    await git_utils.add_files(repo_path, files)
    console.print(f"[green]✓ Staged: {', '.join(files)}[/green]")

async def commit(message: str):
    """Logic to commit staged changes."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        return console.print("[red]This is not a git repository.[/red]")
    if not message:
        return console.print("[red]Usage: /git_commit <message>[/red]")
    if await git_utils.commit(repo_path, message):
        console.print(f"[green]✓ Committed with message: \"{message}\"[/green]")
    else:
        console.print("[yellow]Nothing to commit.[/yellow]")

async def switch(branch_name: str):
    """Logic to switch local branches."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        return console.print("[red]Not a git repository.[/red]")
    if not branch_name:
        return console.print("[red]Usage: /git_switch <branch_name>[/red]")
    if await git_utils.switch_branch(repo_path, branch_name):
        console.print(f"[green]✓ Switched to branch '{branch_name}'.[/green]")
    else:
        console.print(f"[red]Failed to switch to branch '{branch_name}'. Does it exist?[/red]")

async def pull():
    """Logic to pull changes for the current branch."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        return console.print("[red]Not a git repository.[/red]")
    branch = await git_utils.get_current_branch(repo_path)
    with console.status(f"Pulling latest changes for '{branch}'..."):
        if await git_utils.pull(repo_path):
            console.print(f"[green]✓ Pulled latest changes for '{branch}'.[/green]")
        else:
            console.print("[red]Pull failed. Check for conflicts or connection issues.[/red]")

async def push():
    """Logic to push changes for the current branch."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        return console.print("[red]Not a git repository.[/red]")
    branch = await git_utils.get_current_branch(repo_path)
    with console.status(f"Pushing changes to 'origin/{branch}'..."):
        try:
            await git_utils.push(repo_path, branch)
            console.print(f"[green]✓ Pushed changes successfully.[/green]")
        except Exception as e:
            console.print(f"[red]Push failed: {e}[/red]")

async def review_and_commit(show_diff: bool = False) -> bool:
    """Handles the full logic for reviewing and committing changes."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    try:
        if not await git_utils.is_git_repo(repo_path):
            raise NotAGitRepositoryError(path=repo_path)

        unstaged = await git_utils.get_unstaged_files(repo_path)
        if unstaged:
            console.print("[yellow]Unstaged changes detected:[/yellow]")
            for f in unstaged: console.print(f"  - {f}")
            if await questionary.confirm("Stage these files before reviewing?", default=True, auto_enter=False).ask_async():
                await git_utils.add_files(repo_path, unstaged)
                console.print("[green]✓ Staged all detected changes.[/green]")

        staged_diff = await git_utils.get_staged_diff(repo_path)
        if not staged_diff:
            console.print("[yellow]No staged changes to review.[/yellow]")
            return False

        if show_diff:
            console.print(Panel(Syntax(staged_diff, "diff", theme="github-dark", word_wrap=True), title="Staged Changes (Full Diff)"))
        else:
            summary_text = [Text(line, style="bold yellow") if line.startswith('diff --git') else Text(line, style="green") if line.startswith('+') else Text(line, style="red") for line in staged_diff.split('\n') if not line.startswith(('+++', '---'))]
            console.print(Panel(Text('\n').join(summary_text), title="Staged Changes (Summary)"))

        if not await questionary.confirm("Proceed to commit these changes?", default=True, auto_enter=False).ask_async():
            console.print("[yellow]Commit aborted.[/yellow]")
            return False

        commit_message = await questionary.text("Enter commit message:").ask_async()
        if not commit_message:
            console.print("[red]Commit message cannot be empty. Aborting.[/red]")
            return False

        await git_utils.commit(repo_path, commit_message)
        console.print(f"[green]✓ Changes committed.[/green]")
        return True # Indicate success for PR flow
    except NotAGitRepositoryError as e:
        console.print(f"[red]{e.message}[/red]")
        return False