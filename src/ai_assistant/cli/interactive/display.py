from rich.console import Console
from rich.panel import Panel
from pyfiglet import Figlet
from typing import Dict

console = Console()

def print_helios_banner():
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
    """Show help information for interactive mode."""
    help_text = """
[bold]Available Commands:[/bold]
  /help                       Show this help message.
  /exit, /quit, /q            Exit the interactive session.

[bold]Context Management:[/bold]
  /file <path>                Add/update a specific file in the active context.
  /files                      List all files currently loaded in the context.
  /repo                       Show repository statistics and overview.
  /refresh                    Reload all files from the repository into context.
  /clear                      Clear the conversation history (keeps file context).

[bold]Code & File Operations:[/bold]
  /new <path>                 Create a new, empty file.
  /save <filename>            Save the first code block from the last AI response.

[bold]Git Operations:[/bold]
  /review                     Start an interactive review of staged changes.
  /git_add <f1> [f2..]        Stage specified file(s) for the next commit.
  /git_commit <message>       Commit staged changes with a message.
  /git_push                   Push committed changes to the remote repository.

[bold]Session & Model:[/bold]
  /model [name]               Show current model or switch to a new one.
  /save_conversation <path>   Save the conversation to a markdown file.

[bold]Chatting with the AI:[/bold]
Simply type your message and press Enter. The AI has access to all loaded repository
files to help with your request.
"""
    console.print(Panel(help_text, title="[bold]Helios Help[/bold]", border_style="blue", expand=False))

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
        "- `/save <filename.ext>` to save the first code block.\n"
        "- `/review` to see all changes and commit."
    )
    console.print(
        Panel(suggestion_message, title="[yellow]Code Actions Available[/yellow]", border_style="yellow", expand=False)
    )