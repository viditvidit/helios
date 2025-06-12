from pathlib import Path
from rich.console import Console
from rich.panel import Panel
import questionary

from ..services.github_service import GitHubService
from ..utils.git_utils import GitUtils
from ..core.exceptions import GitHubServiceError, NotAGitRepositoryError

console = Console()

async def create_repo(session):
    """Logic to interactively create a new GitHub repository."""
    try:
        service = GitHubService(session.config)
        console.print("\n[bold cyan]Creating a new GitHub Repository...[/bold cyan]")
        
        repo_name = await questionary.text("Repository Name:").ask_async()
        if not repo_name: return console.print("[red]Repository name cannot be empty.[/red]")
        description = await questionary.text("Description (optional):").ask_async()
        is_private = await questionary.confirm("Make repository private?", default=True, auto_enter=False).ask_async()

        with console.status(f"Creating repository '{repo_name}' on GitHub..."):
            clone_url = await service.create_repo(repo_name, is_private, description)
        
        console.print(f"To clone your new repository, run:\n[bold]git clone {clone_url}[/bold]")
    except GitHubServiceError as e:
        console.print(f"[red]Error: {e}[/red]")

async def create_branch(session):
    """Logic to interactively create a new GitHub branch (on remote)."""
    try:
        service = GitHubService(session.config)
        console.print("\n[bold cyan]Creating a new GitHub Branch...[/bold cyan]")

        branch_name = await questionary.text("New Branch Name:").ask_async()
        if not branch_name: return console.print("[red]Branch name cannot be empty.[/red]")
        source_branch = await questionary.text("Source Branch on remote:", default="main").ask_async()

        with console.status(f"Creating remote branch '{branch_name}' from '{source_branch}'..."):
            await service.create_branch(branch_name, source_branch)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def create_issue(session):
    """Logic to interactively create a GitHub issue."""
    try:
        service = GitHubService(session.config)
        console.print("\n[bold cyan]Creating a new GitHub Issue...[/bold cyan]")
        
        title = await questionary.text("Issue Title:").ask_async()
        if not title: return console.print("[red]Title cannot be empty.[/red]")
        body = await questionary.text("Issue Body (optional, markdown supported):").ask_async()
        
        with console.status(f"Creating issue: '{title}'..."):
            await service.create_issue(title, body)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def interactive_pr_creation(session):
    """Full interactive flow for creating a PR."""
    service = GitHubService(session.config)
    git_utils = GitUtils()
    repo_path = Path.cwd()
    try:
        if not await git_utils.is_git_repo(repo_path): raise NotAGitRepositoryError(path=repo_path)
        console.print("\n[bold cyan]Creating a new Pull Request...[/bold cyan]")
        
        branch_action = await questionary.select("Which branch for the PR?", choices=["Create new branch", "Use existing branch"]).ask_async()
        head_branch = ""

        if branch_action == "Create new branch":
            new_branch_name = await questionary.text("Enter name for the new local feature branch:").ask_async()
            if not new_branch_name: return console.print("[red]Branch name cannot be empty.[/red]")
            await git_utils.switch_branch(repo_path, new_branch_name, create=True)
            head_branch = new_branch_name
        else:
            local_branches = await git_utils.get_local_branches(repo_path)
            head_branch = await questionary.select("Select branch to merge from:", choices=local_branches).ask_async()
            if head_branch != await git_utils.get_current_branch(repo_path):
                await git_utils.switch_branch(repo_path, head_branch)
        
        console.print(f"[green]✓ Using branch '{head_branch}'.[/green]")
        with console.status(f"[yellow]Pushing '{head_branch}' to remote...[/yellow]"):
            await git_utils.push(repo_path, head_branch, set_upstream=True)

        title = await questionary.text("PR Title:").ask_async()
        if not title: return console.print("[red]Title cannot be empty.[/red]")
        body = await questionary.text("PR Body (optional):").ask_async()
        base = await questionary.text("Base branch to merge into:", default="main").ask_async()
        
        with console.status("Creating PR..."):
            await service.create_pull_request(title, body, head_branch, base)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error creating PR: {e}[/red]")

async def repo_summary(session):
    """Logic to get AI summary of the repo."""
    try:
        service = GitHubService(session.config)
        with console.status("[bold yellow]Generating AI repository summary...[/bold yellow]"):
            summary = await service.get_ai_repo_summary()
        console.print(Panel(summary, title="AI Repository Summary", border_style="blue", expand=True))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def pr_review(session, pr_number_str: str):
    """Logic to get AI review of a PR."""
    if not pr_number_str or not pr_number_str.isdigit():
        return console.print("[red]Usage: /pr_review <pr_number>[/red]")
    pr_number = int(pr_number_str)
    try:
        service = GitHubService(session.config)
        with console.status(f"[yellow]Generating AI review for PR #{pr_number}...[/yellow]"):
            summary = await service.get_ai_pr_summary(pr_number)
        console.print(Panel(summary, title=f"AI Review for PR #{pr_number}", border_style="blue", expand=True))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")