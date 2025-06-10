from pathlib import Path
from rich.console import Console
from . import display

console = Console()

async def add_file_to_context(session, file_path: str):
    """Add file to context."""
    try:
        path = Path(file_path)
        if not path.exists():
            console.print(f"[red]File not found: {file_path}[/red]")
            return
        
        content = await session.file_service.read_file(path)
        session.current_files[file_path] = content
        console.print(f"[green]Added file to context: {file_path}[/green]")
    except Exception as e:
        console.print(f"[red]Error adding file: {e}[/red]")

def clear_history(session):
    """Clear conversation history and file context."""
    session.conversation_history.clear()
    session.current_files.clear()
    console.print("[green]Conversation history and file context cleared[/green]")

def switch_model(session, model_name: str):
    """Switch AI model."""
    if model_name in session.config.models:
        session.config.model_name = model_name
        console.print(f"[green]Switched to model: {model_name}[/green]")
    else:
        console.print(f"[red]Model not found: {model_name}[/red]")
        available = ', '.join(session.config.models.keys())
        console.print(f"Available models: {available}")

def _format_conversation(session) -> str:
    """Helper to format the conversation history for saving."""
    lines = []
    for entry in session.conversation_history:
        lines.append(f"## {entry['role'].capitalize()}\n\n{entry['content']}\n")
    return "\n---\n\n".join(lines)

async def save_conversation(session, file_path: str):
    """Save conversation to file."""
    try:
        path = Path(file_path)
        content = _format_conversation(session)
        await session.file_service.write_file(path, content)
        console.print(f"[green]Conversation saved to: {file_path}[/green]")
    except Exception as e:
        console.print(f"[red]Error saving conversation: {e}[/red]")

async def show_repository_stats(session):
    """Show repository statistics and structure."""
    try:
        # Assumes a commands module exists as in the original code
        from ..commands import CodeCommands 
        repo_context = CodeCommands.build_repo_context(str(Path.cwd()))
        git_context = await session.github_service.get_repository_context(Path.cwd())
        display.show_repo_stats(repo_context, git_context)
    except Exception as e:
        console.print(f"[red]Error getting repository stats: {e}[/red]")

async def refresh_repo_context(session):
    """Refresh repository context by reloading all files."""
    try:
        from ..commands import CodeCommands
        console.print("[yellow]Refreshing repository context...[/yellow]")
        
        # Clear current files and reload from repository
        session.current_files.clear()
        repo_context = CodeCommands.build_repo_context(str(Path.cwd()))
        
        if repo_context:
            session.current_files.update(repo_context)
            file_count = len(repo_context)
            total_lines = sum(len(content.split('\n')) for content in repo_context.values())
            console.print(f"[green]✓ Repository context refreshed: {file_count} files ({total_lines} total lines)[/green]")
            
            # Show a summary of loaded files
            if file_count > 10:
                sample_files = list(repo_context.keys())[:10]
                console.print(f"[dim]Sample files: {', '.join([Path(f).name for f in sample_files])}... and {file_count - 10} more[/dim]")
            else:
                console.print(f"[dim]Loaded files: {', '.join([Path(f).name for f in repo_context.keys()])}[/dim]")
        else:
            console.print("[yellow]No files found in repository to load[/yellow]")
            
    except Exception as e:
        import traceback
        console.print(f"[red]Error refreshing repository context: {e}[/red]")
        console.print(f"[dim]{traceback.format_exc()}[/dim]")