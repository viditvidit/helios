from pathlib import Path
from rich.console import Console
from . import display
from ...utils.file_utils import build_repo_context


console = Console()

async def add_file_to_context(session, file_path: str):
    """Add file to context (or update it if already present)."""
    try:
        path = Path(file_path)
        if not path.exists():
            console.print(f"[red]File not found: {file_path}[/red]")
            return

        content = await session.file_service.read_file(path)
        # Use relative path as key
        relative_path_str = str(path.relative_to(Path.cwd()))
        session.current_files[relative_path_str] = content
        console.print(f"[green]✓ Refreshed file in context: {relative_path_str}[/green]")
    except Exception as e:
        console.print(f"[red]Error adding file: {e}[/red]")

def clear_history(session):
    """Clear conversation history."""
    session.conversation_history.clear()
    console.print("[green]✓ Conversation history cleared.[/green]")

def switch_model(session, model_name: str):
    """Switch AI model."""
    try:
        session.config.set_model(model_name)
        console.print(f"[green]✓ Switched to model: {model_name}[/green]")
    except Exception as e:
        console.print(f"[red]Error switching model: {e}[/red]")
        available = ', '.join(session.config.models.keys())
        console.print(f"Available models: {available}")


def _format_conversation(session) -> str:
    """Helper to format the conversation history for saving."""
    lines = [f"# Helios AI Chat Session\n\nModel: {session.config.model_name}\n"]
    for entry in session.conversation_history:
        role = entry['role'].capitalize()
        content = entry['content']
        lines.append(f"## {role}\n\n{content}\n")
    return "\n---\n\n".join(lines)

async def save_conversation(session, file_path: str):
    """Save conversation to a markdown file."""
    try:
        path = Path(file_path)
        content = _format_conversation(session)
        await session.file_service.write_file(path, content)
        console.print(f"[green]✓ Conversation saved to: {file_path}[/green]")
    except Exception as e:
        console.print(f"[red]Error saving conversation: {e}[/red]")

async def show_repository_stats(session):
    """Show repository statistics and structure."""
    try:
        # The session.current_files holds the full repo context
        repo_context = session.current_files
        git_context = await session.github_service.get_repository_context(Path.cwd())
        display.show_repo_stats(repo_context, git_context)
    except Exception as e:
        console.print(f"[red]Error getting repository stats: {e}[/red]")

async def refresh_repo_context(session):
    """Refresh repository context by re-scanning files and updating session state."""
    try:
        # Clear existing context
        session.current_files.clear()
        
        # Re-initialize repository context if the session has a repo_context
        if hasattr(session, 'repo_context') and session.repo_context:
            # Refresh the repository context
            await session.repo_context.refresh()
        
        console.print("[green]Repository context refreshed successfully.[/green]")
        
    except Exception as e:
        console.print(f"[red]Error refreshing repository context: {e}[/red]")