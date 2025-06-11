import asyncio
import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from pathlib import Path

from ..core.config import Config
from ..services.github_service import GitHubService
from ..utils.git_utils import GitUtils
from ..core.exceptions import GitHubServiceError, NotAGitRepositoryError

console = Console()

@click.group()
def github():
    """Commands for interacting with Git and GitHub."""
    pass

# --- Repository & Branching ---

@github.command('create-repo')
@click.argument('name')
@click.option('--description', '-d', default="", help="Repository description.")
@click.option('--private/--public', 'is_private', default=True, help="Set repository visibility.")
@click.pass_obj
def create_repo(config: Config, name: str, description: str, is_private: bool):
    """Create a new GitHub repository."""
    try:
        service = GitHubService(config)
        asyncio.run(service.create_repo(name, is_private, description))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

@github.command('create-branch')
@click.argument('name')
@click.option('--source', default="main", help="The source branch to branch from (defaults to 'main').")
@click.pass_obj
def create_branch(config: Config, name: str, source: str):
    """Create a new branch on GitHub from a source branch."""
    try:
        service = GitHubService(config)
        asyncio.run(service.create_branch(name, source))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

# --- Summaries and Reviews ---

@github.command('summary')
@click.pass_obj
def repo_summary(config: Config):
    """Get an AI-generated summary of the current repository."""
    try:
        service = GitHubService(config)
        with console.status("[bold yellow]Getting AI repository summary...[/bold yellow]"):
            summary = asyncio.run(service.get_ai_repo_summary())
        console.print(Panel(summary, title="AI Repository Summary", border_style="blue"))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

@github.command('review-pr')
@click.argument('pr_number', type=int)
@click.pass_obj
def review_pr(config: Config, pr_number: int):
    """Get an AI-generated summary of a pull request."""
    try:
        service = GitHubService(config)
        with console.status(f"[bold yellow]Getting AI summary for PR #{pr_number}...[/bold yellow]"):
            summary = asyncio.run(service.get_ai_pr_summary(pr_number))
        console.print(Panel(summary, title=f"AI Summary for PR #{pr_number}", border_style="blue"))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

@github.command('review')
@click.pass_obj
def review_staged(config: Config):
    """Review staged changes and create a commit."""
    asyncio.run(_review_staged_changes(config))

async def _review_staged_changes(config: Config):
    repo_path = Path.cwd()
    git_utils = GitUtils()

    try:
        if not await git_utils.is_git_repo(repo_path):
            raise NotAGitRepositoryError(path=repo_path)

        staged_diff = await git_utils.get_staged_diff(repo_path)
        if not staged_diff:
            console.print("[yellow]No staged changes to review. Use 'git add' to stage files.[/yellow]")
            return

        console.print(Panel(Syntax(staged_diff, "diff", theme="github-dark", word_wrap=True),
                              title="Staged Changes", border_style="green"))

        if not click.confirm("\nProceed to commit these changes?", default=True):
            console.print("[yellow]Commit aborted.[/yellow]")
            return

        commit_message = click.prompt("Enter commit message")
        if not commit_message:
            console.print("[red]Commit message cannot be empty. Aborting.[/red]")
            return

        await git_utils.commit(repo_path, commit_message)
        console.print(f"[green]✓ Changes committed with message: '{commit_message}'[/green]")

        if click.confirm("Push changes to remote?", default=False):
            branch = await git_utils.get_current_branch(repo_path)
            with console.status(f"[bold yellow]Pushing to '{branch}'...[/bold yellow]"):
                await git_utils.push(repo_path, branch)
            console.print(f"[green]✓ Changes pushed to branch '{branch}'.[/green]")

    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

# --- Issues and Pull Requests ---

@github.command('create-pr')
@click.option('--title', '-t', required=True, help="Pull request title.")
@click.option('--body', '-b', default="", help="Pull request body.")
@click.option('--head', required=True, help="The branch to merge from.")
@click.option('--base', default="main", help="The branch to merge into.")
@click.pass_obj
def create_pr(config: Config, title: str, body: str, head: str, base: str):
    """Create a new pull request on GitHub."""
    try:
        service = GitHubService(config)
        asyncio.run(service.create_pull_request(title, body, head, base))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

@github.command('create-issue')
@click.option('--title', '-t', required=True, help="Issue title.")
@click.option('--body', '-b', default="", help="Issue body (supports markdown).")
@click.pass_obj
def create_issue(config: Config, title: str, body: str):
    """Create a new issue on GitHub."""
    try:
        service = GitHubService(config)
        asyncio.run(service.create_issue(title, body))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")