from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.text import Text

from pathlib import Path
import questionary
import re

from ..utils.git_utils import GitUtils
from ..core.exceptions import NotAGitRepositoryError

console = Console()

async def add(files: list[str]):
    """Logic to stage files."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]Not a git repository.[/red]")
        return False
    if not files:
        console.print("[red]Usage: /git_add <file1> <file2>...[/red]")
        return False
    await git_utils.add_files(repo_path, files)
    console.print(f"[green]✓ Staged: {', '.join(files)}[/green]")
    return True

async def commit(message: str):
    """Logic to commit staged changes."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]Not a git repository.[/red]")
        return False
    if not message:
        console.print("[red]Usage: /git_commit <message>[/red]")
        return False
    if await git_utils.commit(repo_path, message):
        console.print(f"[green]✓ Committed with message: \"{message}\"[/green]")
        return True
    else:
        console.print("[yellow]Nothing to commit.[/yellow]")
        return True # Not a failure state

async def switch(branch_name: str = None, create: bool = False):
    """
    Interactively switches to a local or remote branch.
    If branch_name is provided and fails, it falls back to the interactive selector.
    """
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]Not a git repository.[/red]")
        return False

    # --- NEW INTERACTIVE LOGIC ---
    if branch_name:
        # If a branch name is given, try to switch directly first.
        if await git_utils.switch_branch(repo_path, branch_name, create=create):
            console.print(f"[green]✓ Switched to branch '{branch_name}'.[/green]")
            return True
        else:
            console.print(f"[red]Failed to switch to branch '{branch_name}'.[/red]")
    
    # --- Interactive Selector ---
    try:
        with console.status("[dim]Fetching available branches...[/dim]"):
            local_branches = await git_utils.get_local_branches(repo_path)
            remote_branches = await git_utils.get_all_branches(repo_path)
            current_branch = await git_utils.get_current_branch(repo_path)

        # Combine, sort, and remove duplicates and the current branch
        all_branches = sorted(list(set(local_branches + remote_branches)))
        choices = [b for b in all_branches if b != current_branch]

        if not choices:
            console.print("[yellow]No other branches available to switch to.[/yellow]")
            return True

        selected_branch = await questionary.select(
            "Choose a branch to switch to:",
            choices=choices,
            use_indicator=True,
            style=questionary.Style([
                ('pointer', 'bold fg:cyan'),
                ('selected', 'fg:green'),
                ('highlighted', 'fg:green bold'),
            ])
        ).ask_async()

        if selected_branch:
            if await git_utils.switch_branch(repo_path, selected_branch, create=False):
                console.print(f"[green]✓ Switched to branch '{selected_branch}'.[/green]")
                return True
            else:
                console.print(f"[red]Could not switch to selected branch '{selected_branch}'.[/red]")
                return False
        else:
            console.print("[yellow]Branch switch cancelled.[/yellow]")
            return True # User cancelled, not a failure.

    except Exception as e:
        console.print(f"[red]An error occurred while trying to switch branches: {e}[/red]")
        return False

async def pull():
    """Logic to pull changes for the current branch."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]Not a git repository.[/red]")
        return False
    branch = await git_utils.get_current_branch(repo_path)
    with console.status(f"Pulling latest changes for '{branch}'..."):
        if await git_utils.pull(repo_path):
            console.print(f"[green]✓ Pulled latest changes for '{branch}'.[/green]")
            return True
        else:
            console.print("[red]Pull failed. Check for conflicts or connection issues.[/red]")
            return False

async def push():
    """Logic to push changes for the current branch."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]Not a git repository.[/red]")
        return False
    branch = await git_utils.get_current_branch(repo_path)
    with console.status(f"Pushing changes to 'origin/{branch}'..."):
        try:
            await git_utils.push(repo_path, branch)
            console.print(f"[green]✓ Pushed changes successfully.[/green]")
            return True
        except Exception as e:
            console.print(f"[red]Push failed: {e}[/red]")
            return False

async def log():
    """Logic to display the formatted git log."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        return console.print("[red]This is not a git repository.[/red]")
    
    log_output = await git_utils.get_formatted_log(repo_path)
    console.print(Panel(log_output, title="Recent Commits", border_style="blue"))

async def review_and_commit(show_diff: bool = False) -> tuple[bool, str]:
    """
    Handles reviewing and committing.
    Returns a tuple: (commit_successful, committed_branch_name)
    """
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

        per_file_diffs = await git_utils.get_staged_diff_by_file(repo_path)
        if not per_file_diffs:
            console.print("[yellow]No staged changes to review.[/yellow]")
            return False, ""

        if show_diff:
            for filename, diff_content in per_file_diffs.items():
                console.print(Panel(Syntax(diff_content, "diff", theme="github-dark", word_wrap=True), title=f"{filename}"))
        else:
            summary_lines = [Text(f"{f}: ").append(f"+{d.count('\n+')} ", style="green").append(f"-{d.count('\n-')}", style="red") for f, d in per_file_diffs.items()]
            console.print(Text("\n").join(summary_lines))

        if not await questionary.confirm("\nProceed to commit these changes?", default=True, auto_enter=False).ask_async():
            console.print("[yellow]Commit aborted.[/yellow]")
            return False, ""

        commit_message = await questionary.text("Enter commit message:").ask_async()
        if not commit_message:
            console.print("[red]Commit message cannot be empty. Aborting.[/red]")
            return False, ""

        await git_utils.commit(repo_path, commit_message)
        current_branch = await git_utils.get_current_branch(repo_path)
        console.print(f"[green]✓ Changes committed to branch '{current_branch}'.[/green]")
        return True, current_branch
    except NotAGitRepositoryError as e:
        console.print(f"[red]{e.message}[/red]")
        return False, ""
    except Exception as e:
        console.print(f"[red]An error occurred during review: {e}[/red]")
        return False, ""