# src/ai_assistant/logic/agent/qna_tools.py

from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ...utils.git_utils import GitUtils
from ...utils.parsing_utils import build_file_tree
from ...services.github_service import GitHubService

console = Console()

async def get_current_git_branch(session) -> str:
    """
    A tool that directly executes the git command to find the current branch
    and returns the answer as a string.
    """
    try:
        git_utils = GitUtils()
        repo_path = Path.cwd()
        if not await git_utils.is_git_repo(repo_path):
            return "This does not appear to be a Git repository."
        
        branch = await git_utils.get_current_branch(repo_path)
        return f"You are currently on the '{branch}' branch."

    except Exception as e:
        return f"An error occurred while checking the git branch: {e}"

async def get_git_status(session) -> str:
    """A tool to get the current git status, including unstaged and untracked files."""
    try:
        git_utils = GitUtils()
        repo_path = Path.cwd()
        if not await git_utils.is_git_repo(repo_path):
            return "This does not appear to be a Git repository."

        # Fetch both staged and unstaged changes
        staged_files = await git_utils.get_staged_files(repo_path)
        unstaged_files = await git_utils.get_unstaged_files(repo_path)

        if not staged_files and not unstaged_files:
            return "✅ Your working directory is clean."

        content = ""
        if staged_files:
            staged_list = "\n".join([f"  • {f}" for f in staged_files])
            content += f"[bold green]Staged Changes:[/bold green]\n{staged_list}\n\n"
        
        if unstaged_files:
            unstaged_list = "\n".join([f"  • {f}" for f in unstaged_files])
            content += f"[bold yellow]Unstaged Changes:[/bold yellow]\n{unstaged_list}"

        return Panel(content.strip(), title="Git Status", border_style="blue")

    except Exception as e:
        return f"An error occurred while checking git status: {e}"

async def get_git_log(session) -> str:
    """A tool to get the recent git commit history."""
    try:
        git_utils = GitUtils()
        repo_path = Path.cwd()
        if not await git_utils.is_git_repo(repo_path):
            return "This does not appear to be a Git repository."

        log_output = await git_utils.get_formatted_log(repo_path, count=10)
        return Panel(log_output, title="Recent Commits", border_style="blue")

    except Exception as e:
        return f"An error occurred while fetching the git log: {e}"

async def get_project_structure(session) -> str:
    """A tool to display the file and directory structure of the current project."""
    files = list(session.current_files.keys())
    if not files:
        return "No files are currently indexed in the project context. Run /index first."
    
    tree_str = build_file_tree(files)
    return Panel(tree_str, title="Project File Structure", border_style="cyan")

async def list_open_github_issues(session, assignee: str = None) -> str:
    """A tool to list open GitHub issues, optionally filtering by assignee."""
    try:
        service = GitHubService(session.config)
        
        # Use '*' to mean "assigned to anyone", which is often what users imply.
        # If the user says "my issues", the AI should substitute their username.
        assignee_filter = assignee or "*"
        
        issues = await service.get_issues(assignee_filter=assignee_filter)

        if not issues or issues.totalCount == 0:
            filter_str = f" for assignee '{assignee}'" if assignee else ""
            return f"No open issues found{filter_str}."

        content = ""
        for issue in issues:
            assignees_str = ", ".join([a.login for a in issue.assignees]) or "Unassigned"
            content += f"• [bold cyan]#{issue.number}[/bold cyan] {issue.title}\n  ([dim]Assigned to: {assignees_str}[/dim])\n"

        return Panel(content, title="Open GitHub Issues", border_style="blue")

    except Exception as e:
        return f"An error occurred while fetching GitHub issues: {e}"