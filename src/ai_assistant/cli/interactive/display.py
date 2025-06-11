from rich.console import Console
from rich.panel import Panel
from pyfiglet import Figlet
from typing import Dict
import os

console = Console()

def print_helios_banner():
    os.system('cls' if os.name == 'nt' else 'clear')  # Clear the console
    f = Figlet(font='standard')
    banner = f.renderText('HELIOS')
    console.print(f"[bold orange1]{banner}[/bold orange1]")
    console.print("[bold]Your AI Coding Companion[/bold]\n")

def show_welcome():
    console.print(Panel.fit(
        "[bold green]Welcome to the Interactive AI Assistant[/bold green]\n"
        "Your repository context is loaded. "
        "Type a request or use a command.\n"
        "Type `/help` for all commands, or `exit` to quit.",
        title="Chat Mode"
    ))

def show_help():
    """Display available commands and controls."""
    help_text = """
[bold cyan]Available Commands:[/bold cyan]
  /help                    Show this help message
  /file <path>             Add a file to context
  /files                   List files in current context
  /clear                   Clear conversation history
  /refresh                 Refresh repository context
  /repo                    Show repository statistics
  /model [name]            Show/switch AI model
  /apply                   Apply all code changes from the last AI response
  /new <filename>          Create a new file with AI assistance
  /save <filename>         Save the last AI code response to a specific file
  /save_commit <filename> [msg] Save and auto-commit with optional message
  /save_conversation <file> Save conversation to file
  /git_add <files>         Add files to git staging
  /git_commit <message>    Commit staged changes
  /git_push                Push commits to remote
  /review                  Review staged changes and create a commit.

[bold cyan]GitHub Integration:[/bold cyan]
  /github create_repo <name>         Create a new GitHub repository.
  /github create_branch <name>       Create a new branch in the current repo.
  /github review_pr <number>         Get an AI summary of a pull request.
  /github create_issue <title>       Create a new issue with the given title.

[bold cyan]Controls:[/bold cyan]
  Ctrl+C                   Stop current AI response generation
  exit, quit, bye          Exit the session

[bold green]Tip:[/bold green] For more advanced options, use the non-interactive CLI commands like
`helios github create-pr --help`.
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
    if file_count > 30:
        panel_content += "\n".join(files_info[:30])
        panel_content += f"\n... and {file_count - 30} more files."
    else:
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

[bold]File Types:[/bold]
{chr(10).join([f"- {ext}: {count} files" for ext, count in sorted(extensions.items())])}

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
    """Display goodbye message when exiting."""
    console.print("\n[bold blue]Thanks for using Helios AI Assistant![/bold blue]")
    console.print("[dim]Goodbye! 👋[/dim]\n")