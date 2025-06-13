from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.columns import Columns
from pyfiglet import Figlet
from typing import Dict
import os

console = Console()

def print_helios_banner():
    os.system('cls' if os.name == 'nt' else 'clear')
    f = Figlet(font='smkeyboard')
    banner = f.renderText('HELIOS')
    console.print(f"[bold orange1]{banner}[/bold orange1]")
    console.print("[bold]Your AI Coding Companion[/bold]\n")

def show_welcome():
    print_helios_banner()
    console.print(Panel.fit(
        "[bold green]Welcome to the Interactive AI Assistant[/bold green]\n"
        "Your repository context is loaded. "
        "Type a request or use a command.\n"
        "Type `/help` for all commands, or `exit` to quit.",
        title="Helios"
    ))

def show_help():
    """Display available commands and controls."""
    help_text = """
[bold cyan]General Commands:[/bold cyan]
  /help                    Show this help message
  @<file_or_dir>           Mention a file or directory within your prompt to add it to context.
  /file <path>             Add a file to context
  /files                   List files in current context
  /clear                   Clear conversation history
  /refresh                 Refresh repository context
  /index                   Manually re-index the entire repository.
  /repo                    Show local repository statistics and status
  /model                   Show/switch AI model
  /apply                   Apply all code changes from the last AI response
  /new <filename>          Create a new empty file
  /save <filename>         Save the last AI code response to a specific file

[bold cyan]Local Git Commands:[/bold cyan]
  /git_add <files...>      Stage one or more files for commit
  /git_commit <message>    Commit staged changes with a message
  /git_switch <branch>     Switch to a different local branch
  /git_log                 Show recent commit history
  /git_pull                Pull latest changes for the current branch
  /git_push                Push committed changes to the remote repository
  
[bold cyan]GitHub Workflow Commands:[/bold cyan]
  /review [-d]             Review changes, commit, push, and create a PR.
  /create_repo             Interactively create a new GitHub repository
  /create_branch           Interactively create a new local branch
  /create_issue            Interactively create a new GitHub Issue
  /issue_list [--filter <user|none|all>]  List open issues.
                           (Default: shows all assigned issues).
                           <user>: issues for a specific user.
                           'none': unassigned issues.
                           'all': all issues, assigned or not.
  /issue_comment <#> <text> Add a comment to an issue.
  /issue_assign <#> <user> Assign an issue to a user.
  /issue_close <#> [text]  Close an issue, optionally with a comment.
  /create_pr               Interactively create a new Pull Request
  /pr_list                 List open Pull Requests.
  /pr_link_issue <pr#> <iss#> Link a PR to an issue.
  /pr_request_review <pr#> <user..> Request reviews for a PR.
  /pr_approve <#>          Approve a Pull Request.
  /pr_comment <#>          Add a comment to a Pull Request.
  /pr_merge <#>            Merge a Pull Request.

 [bold cyan]Code Quality Commands:[/bold cyan]
  /optimize <filename>     Ask the AI to optimize/refactor a specific file.
  /scan                    Perform a high-level scan of the repository for potential improvements. 

[bold cyan]AI-Powered Review Commands:[/bold cyan]
  /repo_summary            Get an AI-generated summary of the entire repository.
  /pr_review <#>           Get an AI-generated review of a specific Pull Request.
"""
    console.print(Panel(help_text.strip(), border_style="blue", title="Help", title_align="left"))

def list_files_in_context(current_files: Dict[str, str]):
    if not current_files:
        console.print("[yellow]No files loaded in context.[/yellow]")
        return
    file_count = len(current_files)
    total_lines = sum(len(content.splitlines()) for content in current_files.values())
    files_info = [f"- {fp} ({len(content.splitlines())} lines)" for fp, content in current_files.items()]
    panel_content = f"Total: {file_count} files, {total_lines} lines\n\n"
    panel_content += "\n".join(files_info)
    console.print(Panel(panel_content, title="Files in Context", border_style="blue"))

def show_repo_stats(repo_context: Dict[str, str], git_context: Dict):
    from pathlib import Path
    file_count = len(repo_context)
    total_lines = sum(len(content.split('\n')) for content in repo_context.values())
    extensions = {}
    for file_path in repo_context.keys():
        ext = Path(file_path).suffix or 'no extension'
        extensions[ext] = extensions.get(ext, 0) + 1
    stats_text = f"""
[bold]Repository Context:[/bold]
- Total Files Scanned: {file_count}
- Total Lines of Code: {total_lines}
- Current Branch: [cyan]{git_context.get('current_branch', 'N/A')}[/cyan]

[bold]Git Status:[/bold]
[dim]{git_context.get('status', 'N/A') or 'No changes detected'}[/dim]
"""
    console.print(Panel(stats_text, title="Repository Overview", border_style="blue"))    

def show_code_suggestions():
    suggestion_message = (
        "The AI response contains code. You can use commands like:\n"
        "- `/apply` to automatically save all changes to their respective files.\n"
        "- `/save <filename.ext>` to save the first code block to a new file.\n"
        "- `/review` to see all changes and commit."
    )
    console.print(
        Panel(suggestion_message, title="[yellow]Code Actions Available[/yellow]", border_style="yellow", expand=False)
    )

def show_goodbye():
    console.print("\n[bold blue]Thanks for using Helios AI Assistant![/bold blue]")
    console.print("[dim]Goodbye! 👋[/dim]\n")