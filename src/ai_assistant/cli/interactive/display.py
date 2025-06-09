from rich.console import Console
from rich.panel import Panel

console = Console()

def show_welcome():
    console.print(Panel.fit(
        "[bold green]Interactive AI Assistant[/bold green]\n"
        "Type 'help' for commands, 'exit' to quit",
        title="Chat Mode"
    ))

def show_help():
    """Show help information"""
    help_text = """
[bold]Available Commands:[/bold]
  - /file <path>              - Add an existing file to context.
  - /new <path>               - Create a new file in the repository.
  - /files                    - List files currently added to context.
  - /repo                     - Show repository statistics and overview.
  - /refresh                  - Refresh repository context for next message.
  - /clear                    - Clear conversation history and file context.
  - /model <name>             - Switch AI model.
  - /save_conversation <path> - Save conversation to file.
  - /save <filename>          - Save the first code block from the last AI response to a file.
  - /git_add <file1> [f2..]   - Stage specified file(s) for commit.
  - /git_commit <message>     - Commit staged changes with a commit message.
  - /git_push                 - Push committed changes to remote repository.
  - help                      - Show this help.
  - exit/quit/q               - Exit interactive mode.

[bold]Chat:[/bold]
Just type your message to chat with the AI. The assistant has full access to your repository
context and can help you understand, modify, and work with your codebase.
"""
    console.print(Panel(help_text, title="Help", border_style="green"))

def list_files_in_context(current_files: dict):
    if not current_files:
        console.print("[yellow]No files in context[/yellow]")
        return
    
    files_info = [f"- {fp} ({len(content.splitlines())} lines)" for fp, content in current_files.items()]
    console.print(Panel('\n'.join(files_info), title="Files in Context", border_style="blue"))

def show_repo_stats(repo_context: dict, git_context: dict):
    from pathlib import Path
    file_count = len(repo_context)
    total_lines = sum(len(content.split('\n')) for content in repo_context.values())
    
    extensions = {}
    for file_path in repo_context.keys():
        ext = Path(file_path).suffix or 'no extension'
        extensions[ext] = extensions.get(ext, 0) + 1
    
    stats_text = f"""
Repository Statistics:
- Total Files: {file_count}
- Total Lines: {total_lines}
- Current Branch: {git_context.get('current_branch', 'N/A')}
- Git Status: {git_context.get('status', 'N/A')}

File Types:
{chr(10).join([f"- {ext}: {count} files" for ext, count in sorted(extensions.items())])}

Recent Files:
{chr(10).join([f"- {Path(p).name}" for p in list(repo_context.keys())[:10]])}
{f"... and {file_count - 10} more files" if file_count > 10 else ""}
"""
    console.print(Panel(stats_text, title="Repository Overview", border_style="blue"))

def show_code_suggestions():
    suggestion_message = (
        "AI response contains code suggestions.\n"
        "You can use the following commands:\n"
        "- `/save <your_filename.ext>` to save the first code block.\n"
        "- `/git_add <your_filename.ext>`\n"
        "- `/git_commit Your commit message`\n"
        "- `/git_push`"
    )
    console.print(
        Panel(suggestion_message, title="[yellow]Code Actions Suggested[/yellow]", border_style="yellow", expand=False)
    )