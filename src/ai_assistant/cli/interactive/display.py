from rich.console import Console
from rich.panel import Panel
from pyfiglet import Figlet
from pathlib import Path
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
  @<file_or_dir>           [dim]Mention a file or directory within your prompt to add it to context.[/dim]
  /help                    [dim]Show this help message[/dim]
  /file <path>             [dim]Add a file to context[/dim]
  /clear                   [dim]Clear conversation history[/dim]
  /refresh                 [dim]Refresh repository context[/dim]
  /index                   [dim]Manually re-index the entire repository[/dim]
  /repo                    [dim]Show local repository statistics and status[/dim]
  /model                   [dim]Show/switch AI model[/dim]
  /apply                   [dim]Apply all code changes from the last AI response[/dim]
  /new <filename>          [dim]Create a new empty file[/dim]
  /save <filename>         [dim]Save the last AI code response to a specific file[/dim]

[bold cyan]Local Git Commands:[/bold cyan]
  /git_add <files...>      [dim]Stage one or more files for commit[/dim]
  /git_commit <message>    [dim]Commit staged changes with a message[/dim]
  /git_switch <branch>     [dim]Switch to a different local branch[/dim]
  /git_log                 [dim]Show recent commit history[/dim]
  /git_pull                [dim]Pull latest changes for the current branch[/dim]
  /git_push                [dim]Push committed changes to the remote repository[/dim]
  
[bold cyan]GitHub Workflow Commands:[/bold cyan]
  /review [-d]             [dim]Review changes, commit, push, and create a PR[/dim]
  /create_repo             [dim]Interactively create a new GitHub repository[/dim]
  /create_branch           [dim]Interactively create a new local branch[/dim]
  /create_issue            [dim]Interactively create a new GitHub Issue[/dim]
  /issue_list [--filter <user|none|all>]  [dim]List open issues
                           (Default: shows all assigned issues)
                           <user>: issues for a specific user
                           'none': unassigned issues
                           'all': all issues, assigned or not[/dim]
  /issue_comment <#> <text> [dim]Add a comment to an issue[/dim]
  /issue_assign <#> <user> [dim]Assign an issue to a user[/dim]
  /issue_close <#> [text]  [dim]Close an issue, optionally with a comment[/dim]
  /create_pr               [dim]Interactively create a new Pull Request[/dim]
  /pr_list                 [dim]List open Pull Requests[/dim]
  /pr_link_issue <pr#> <iss#> [dim]Link a PR to an issue[/dim]
  /pr_request_review <pr#> <user..> [dim]Request reviews for a PR[/dim]
  /pr_approve <#>          [dim]Approve a Pull Request[/dim]
  /pr_comment <#>          [dim]Add a comment to a Pull Request[/dim]
  /pr_merge <#>            [dim]Merge a Pull Request[/dim]

  [bold cyan]Agentic Mode:[/bold cyan]
  /knight <goal>           [dim]Activate the autonomous agent to achieve a high-level goal[/dim]
  /knight_hybrid <goal>    [dim]Activate the advanced hybrid agent with web search and research tools[/dim]


 [bold cyan]Code Quality Commands:[/bold cyan]
  /optimize <filename>     [dim]Ask the AI to optimize/refactor a specific file[/dim]
  /scan                    [dim]Perform a high-level scan of the repository for potential improvements[/dim] 

[bold cyan]AI-Powered Review Commands:[/bold cyan]
  /repo_summary            [dim]Get an AI-generated summary of the entire repository[/dim]
  /pr_review <#>           [dim]Get an AI-generated review of a specific Pull Request[/dim]
"""
    console.print(Panel(help_text.strip(), border_style="blue", title="Help", title_align="left"))

def show_repo_stats(repo_context: Dict[str, str], git_context: Dict):
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