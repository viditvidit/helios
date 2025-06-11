import asyncio
import click
from rich.console import Console
from rich.panel import Panel

from ..core.config import Config
from ..services.github_service import GitHubService
from ..core.exceptions import GitHubServiceError, NotAGitRepositoryError

console = Console()

@click.group()
def github():
    """Commands for interacting with GitHub."""
    pass

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

@github.command('create-pr')
@click.option('--title', '-t', required=True, help="Pull request title.")
@click.option('--body', '-b', default="", help="Pull request body.")
@click.option('--head', required=True, help="The branch to merge from.")
@click.option('--base', default="main", help="The branch to merge into.")
@click.pass_obj
def create_pr(config: Config, title: str, body: str, head: str, base: str):
    """Create a new pull request."""
    try:
        service = GitHubService(config)
        asyncio.run(service.create_pull_request(title, body, head, base))
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

@github.command('create-issue')
@click.option('--title', '-t', required=True, help="Issue title.")
@click.option('--body', '-b', default="", help="Issue body (supports markdown).")
@click.pass_obj
def create_issue(config: Config, title: str, body: str):
    """Create a new issue."""
    try:
        service = GitHubService(config)
        asyncio.run(service.create_issue(title, body))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

@github.command('create-branch')
@click.argument('name')
@click.option('--source', default="main", help="The source branch to branch from.")
@click.pass_obj
def create_branch(config: Config, name: str, source: str):
    """Create a new branch."""
    try:
        service = GitHubService(config)
        asyncio.run(service.create_branch(name, source))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")