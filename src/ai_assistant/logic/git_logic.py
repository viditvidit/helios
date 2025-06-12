from pathlib import Path
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.text import Text
import questionary
import re

from ..utils.git_utils import GitUtils
from ..core.exceptions import NotAGitRepositoryError

console = Console()

async def add(files: list[str]):
    """Logic to stage files."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path): return console.print("[red]Not a git repository.[/red]")
    if not files: return console.print("[red]Usage: /git_add <file1> <file2>...[/red]")
    await git_utils.add_files(repo_path, files)
    console.print(f"[green]✓ Staged: {', '.join(files)}[/green]")

async def commit(message: str):
    """Logic to commit staged changes."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path): return console.print("[red]Not a git repository.[/red]")
    if not message: return console.print("[red]Usage: /git_commit <message>[/red]")
    if await git_utils.commit(repo_path, message):
        console.print(f"[green]✓ Committed with message: \"{message}\"[/green]")
    else:
        console.print("[yellow]Nothing to commit.[/yellow]")

async def switch(branch_name: str):
    """Logic to switch local branches."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path): return console.print("[red]Not a git repository.[/red]")
    if not branch_name: return console.print("[red]Usage: /git_switch <branch_name>[/red]")
    if await git_utils.switch_branch(repo_path, branch_name):
        console.print(f"[green]✓ Switched to branch '{branch_name}'.[/green]")
    else:
        console.print(f"[red]Failed to switch to branch '{branch_name}'. Does it exist?[/red]")

async def pull():
    """Logic to pull changes for the current branch."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path): return console.print("[red]Not a git repository.[/red]")
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
    if not await git_utils.is_git_repo(repo_path): return console.print("[red]Not a git repository.[/red]")
    branch = await git_utils.get_current_branch(repo_path)
    with console.status(f"Pushing changes to 'origin/{branch}'..."):
        try:
            await git_utils.push(repo_path, branch)
            console.print(f"[green]✓ Pushed changes successfully.[/green]")
        except Exception as e:
            console.print(f"[red]Push failed: {e}[/red]")

async def review_and_commit(show_diff: bool) -> bool:
    """Handles logic for reviewing changes with two different view modes."""
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
            return False

        console.print(Panel(f"[bold]Found changes in {len(per_file_diffs)} file(s).[/bold]", border_style="cyan"))

        if show_diff:
            # DETAILED VIEW: Panel per file
            for filename, diff_content in per_file_diffs.items():
                console.print(Panel(Syntax(diff_content, "diff", theme="github-dark", word_wrap=True), title=f"{filename}", border_style="green"))
        else:
            # COMPACT VIEW: <filename>: +<add> -<del>
            summary_lines = []
            for filename, diff_content in per_file_diffs.items():
                added = diff_content.count('\n+')
                removed = diff_content.count('\n-')
                summary_line = Text(f"{filename}: ")
                summary_line.append(f"+{added}", style="green")
                summary_line.append(" ")
                summary_line.append(f"-{removed}", style="red")
                summary_lines.append(summary_line)
            console.print(Text("\n").join(summary_lines))

        if not await questionary.confirm("\nProceed to commit these changes?", default=True, auto_enter=False).ask_async():
            console.print("[yellow]Commit aborted.[/yellow]")
            return False

        commit_message = await questionary.text("Enter commit message:").ask_async()
        if not commit_message:
            console.print("[red]Commit message cannot be empty. Aborting.[/red]")
            return False

        await git_utils.commit(repo_path, commit_message)
        console.print(f"[green]✓ Changes committed.[/green]")
        return True
    except NotAGitRepositoryError as e:
        console.print(f"[red]{e.message}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]An error occurred during review: {e}[/red]")
        return False