from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import questionary
from typing import List, Optional
import os

from ..services.github_service import GitHubService
from ..utils.git_utils import GitUtils
from ..core.exceptions import GitHubServiceError, NotAGitRepositoryError

console = Console()

async def ensure_github_credentials(session):
    """Checks for GitHub credentials and prompts the user if they are missing."""
    token = session.config.github.token or os.getenv("GITHUB_TOKEN")
    if token:
        return True # Credentials already exist

    console.print("[bold yellow]GitHub credentials not found.[/bold yellow]")
    token = await questionary.password("Please enter your GitHub Personal Access Token (it will be hidden):").ask_async()
    
    if not token:
        console.print("[red]GitHub token is required to proceed with GitHub operations. Aborting.[/red]")
        return False
        
    # Store for the current session
    session.config.github.token = token
    
    # Re-initialize the service with the new token
    try:
        session.github_service = GitHubService(session.config)
        console.print(f"[green]✓ Authenticated with GitHub as {session.github_service.user.login}.[/green]")
        return True
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        session.config.github.token = None # Clear invalid token
        return False

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

async def approve_pr(session, pr_number_str: str):
    """Logic to approve a PR."""
    if not pr_number_str or not pr_number_str.isdigit():
        return console.print("[red]Usage: /pr_approve <pr_number>[/red]")
    pr_number = int(pr_number_str)
    try:
        service = GitHubService(session.config)
        with console.status(f"Approving PR #{pr_number}..."):
            await service.approve_pr(pr_number)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def comment_on_pr(session, pr_number_str: str):
    """Logic to comment on a PR."""
    if not pr_number_str or not pr_number_str.isdigit():
        return console.print("[red]Usage: /pr_comment <pr_number>[/red]")
    pr_number = int(pr_number_str)
    try:
        comment = await questionary.text("Enter your comment (markdown supported):").ask_async()
        if not comment:
            return console.print("[yellow]Comment cancelled.[/yellow]")
        service = GitHubService(session.config)
        with console.status(f"Posting comment to PR #{pr_number}..."):
            await service.comment_on_pr(pr_number, comment)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def merge_pr(session, pr_number_str: str):
    """Logic to merge a PR."""
    if not pr_number_str or not pr_number_str.isdigit():
        return console.print("[red]Usage: /pr_merge <pr_number>[/red]")
    pr_number = int(pr_number_str)
    try:
        method = await questionary.select(
            "Select merge method:",
            choices=["merge", "squash", "rebase"],
            default="merge"
        ).ask_async()
        
        service = GitHubService(session.config)
        with console.status(f"Merging PR #{pr_number}..."):
            await service.merge_pr(pr_number, method)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def list_issues(session, assignee_filter: Optional[str]):
    """Logic to list open issues with a smart default filter."""
    try:
        service = GitHubService(session.config)
        
        # --- NEW DEFAULT LOGIC ---
        # If no filter is provided, default to '*' (any assigned issue).
        # This is more useful than showing everything including unassigned issues.
        if assignee_filter is None:
            assignee_filter = '*'

        # Build user-friendly text for the status message
        filter_text = ""
        if assignee_filter:
            if assignee_filter.lower() == 'none':
                filter_text = " (Unassigned)"
            elif assignee_filter == '*':
                filter_text = " (Assigned to anyone)"
            else:
                filter_text = f" (Assigned to '{assignee_filter}')"

        with console.status(f"Fetching open issues{filter_text}..."):
            issues = await service.get_issues(assignee_filter=assignee_filter)
        
        if not issues.totalCount:
            return console.print(f"[yellow]No open issues found{filter_text}.[/yellow]")

        table = Table(title=f"Open GitHub Issues{filter_text}")
        table.add_column("#", style="cyan")
        table.add_column("Title", style="magenta")
        table.add_column("Assignees", style="green")
        table.add_column("URL", style="dim")

        for issue in issues:
            assignees = ", ".join([a.login for a in issue.assignees]) or "[dim]None[/dim]"
            table.add_row(str(issue.number), issue.title, assignees, issue.html_url)
        
        console.print(table)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def list_prs(session):
    """Logic to list open pull requests."""
    try:
        service = GitHubService(session.config)
        with console.status("Fetching open pull requests..."):
            prs = await service.get_open_prs()

        if not prs.totalCount:
            return console.print("[yellow]No open pull requests found.[/yellow]")
            
        table = Table(title="Open Pull Requests")
        table.add_column("#", style="cyan")
        table.add_column("Title", style="magenta")
        table.add_column("Author", style="green")
        table.add_column("URL", style="dim")

        for pr in prs:
            table.add_row(str(pr.number), pr.title, pr.user.login, pr.html_url)
        
        console.print(table)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def close_issue(session, issue_number_str: str, comment: str):
    if not issue_number_str or not issue_number_str.isdigit():
        return console.print("[red]Usage: /issue_close <number> [comment...][/red]")
    try:
        service = GitHubService(session.config)
        await service.close_issue(int(issue_number_str), comment)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def comment_on_issue(session, issue_number_str: str, comment: str):
    if not issue_number_str or not issue_number_str.isdigit():
        return console.print("[red]Usage: /issue_comment <number> <comment...>[/red]")
    try:
        service = GitHubService(session.config)
        await service.comment_on_issue(int(issue_number_str), comment)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def assign_issue(session, issue_number_str: str, assignee: str):
    if not issue_number_str or not issue_number_str.isdigit() or not assignee:
        return console.print("[red]Usage: /issue_assign <number> <username>[/red]")
    try:
        service = GitHubService(session.config)
        await service.assign_issue(int(issue_number_str), assignee)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def link_pr_to_issue(session, pr_number_str: str, issue_number_str: str):
    if not pr_number_str or not pr_number_str.isdigit() or not issue_number_str or not issue_number_str.isdigit():
        return console.print("[red]Usage: /pr_link_issue <pr_number> <issue_number>[/red]")
    try:
        service = GitHubService(session.config)
        await service.link_pr_to_issue(int(pr_number_str), int(issue_number_str))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def request_pr_reviewers(session, pr_number_str: str, reviewers: List[str]):
    if not pr_number_str or not pr_number_str.isdigit() or not reviewers:
        return console.print("[red]Usage: /pr_request_review <pr_number> <user1> [user2]...[/red]")
    try:
        service = GitHubService(session.config)
        await service.request_pr_reviewers(int(pr_number_str), reviewers)
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")