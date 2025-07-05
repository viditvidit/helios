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

def show_welcome():
    print_helios_banner()
    console.print(Panel.fit(
        "[bold orange1]Welcome to Helios[/bold orange1]\n"
        "[dim]Your repository context is loaded. "
        "Type a request or use a /command.\n"
        "Type `/help` for all commands, or `exit` to quit.[/dim]",
    ))

def show_help():
    """Display available commands and controls."""
    help_text = """
[bold cyan]General Commands:[/bold cyan]
  @<file_or_dir>           [dim]Mention a file or directory within your prompt to add it to context.[/dim]
  /help, /h                [dim]Show this help message[/dim]
  /file <path>, /f         [dim]Add a file to context[/dim]
  /clear, /c               [dim]Clear conversation history[/dim]
  /refresh, /r             [dim]Refresh repository context[/dim]
  /index, /i               [dim]Manually re-index the entire repository[/dim]
  /repo, /rp               [dim]Show local repository statistics and status[/dim]
  /model, /m               [dim]Show/switch AI model[/dim]
  /apply, /a               [dim]Apply all code changes from the last AI response[/dim]
  /new <filename>, /n      [dim]Create a new empty file[/dim]
  /save <filename>, /s     [dim]Save the last AI code response to a specific file[/dim]

[bold cyan]Local Git Commands:[/bold cyan]
  /git_add <files...>, /ga [dim]Stage one or more files for commit[/dim]
  /git_commit <message>, /gc [dim]Commit staged changes with a message[/dim]
  /git_switch <branch>, /gs [dim]Switch to a different local branch[/dim]
  /git_log, /gl            [dim]Show recent commit history[/dim]
  /git_pull, /gp           [dim]Pull latest changes for the current branch[/dim]
  /git_push, /gph          [dim]Push committed changes to the remote repository[/dim]
  
[bold cyan]GitHub Workflow Commands:[/bold cyan]
  /review [-d], /rv        [dim]Review changes, commit, push, and create a PR[/dim]
  /create_repo, /cr        [dim]Interactively create a new GitHub repository[/dim]
  /create_branch, /cb      [dim]Interactively create a new local branch[/dim]
  /create_issue, /ci       [dim]Interactively create a new GitHub Issue[/dim]
  /issue_list [--filter <user|none|all>], /il  [dim]List open issues
                           (Default: shows all assigned issues)
                           <user>: issues for a specific user
                           'none': unassigned issues
                           'all': all issues, assigned or not[/dim]
  /issue_comment <#> <text>, /ico [dim]Add a comment to an issue[/dim]
  /issue_assign <#> <user>, /ia [dim]Assign an issue to a user[/dim]
  /issue_close <#> [text], /ic [dim]Close an issue, optionally with a comment[/dim]
  /create_pr, /pr          [dim]Interactively create a new Pull Request[/dim]
  /pr_list, /pl            [dim]List open Pull Requests[/dim]
  /pr_link_issue <pr#> <iss#>, /pli [dim]Link a PR to an issue[/dim]
  /pr_request_review <pr#> <user..>, /prr [dim]Request reviews for a PR[/dim]
  /pr_approve <#>, /pa     [dim]Approve a Pull Request[/dim]
  /pr_comment <#>, /pc     [dim]Add a comment to a Pull Request[/dim]
  /pr_merge <#>, /pm       [dim]Merge a Pull Request[/dim]

  [bold cyan]Helios Agent:[/bold cyan]
  /knight <goal>, /k       [dim]Activate the advanced autonomous agent to achieve a high-level goal with web search and research tools[/dim]

 [bold cyan]Code Quality Commands:[/bold cyan]
  /optimize <filename>, /o [dim]Ask the AI to optimize/refactor a specific file[/dim]
  /scan, /sc               [dim]Perform a high-level scan of the repository for potential improvements[/dim] 

[bold cyan]AI-Powered Review Commands:[/bold cyan]
  /repo_summary, /rs       [dim]Get an AI-generated summary of the entire repository[/dim]
  /pr_review <#>, /prv     [dim]Get an AI-generated review of a specific Pull Request[/dim]
"""
    console.print(Panel(help_text.strip(), border_style="blue", title="Help", title_align="left"))

def show_repo_stats(repo_context: Dict[str, str], git_context: Dict):
    cwd = Path.cwd()
    repo_name = cwd.name
    
    stats_text = f"""
[bold]Repository Overview:[/bold]
- Project: [bold cyan]{repo_name}[/bold cyan]
- Path: [dim]{cwd}[/dim]
- Branch: [cyan]{git_context.get('current_branch', 'N/A')}[/cyan]

[bold]Git Status:[/bold]
[dim]{git_context.get('status', 'N/A') or 'No changes detected'}[/dim]
"""
    console.print(Panel(stats_text, title="Repository Status", border_style="blue"))

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