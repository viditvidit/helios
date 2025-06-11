from pathlib import Path
from rich.console import Console
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
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

async def switch_model(session, model_name: str = None):
    """Switch the AI model used for generation."""
    if model_name is None:
        # Show interactive selector
        available_models = list(session.config.models.keys())
        current_model = session.config.model_name
        
        # Create choices with current model highlighted
        choices = []
        for model in available_models:
            if model == current_model:
                choices.append(Choice(value=model, name=f"{model} (current)"))
            else:
                choices.append(Choice(value=model, name=model))
        
        try:
            selected_model = await inquirer.select(
                message="Select model:",
                choices=choices,
                default=current_model,
                pointer="→"
            ).execute_async()
            
            if selected_model and selected_model != current_model:
                session.config.model_name = selected_model
                console.print(f"[green]✓ Switched to model: {selected_model}[/green]")
            else:
                console.print("[yellow]Model selection cancelled or unchanged.[/yellow]")
                
        except KeyboardInterrupt:
            console.print("[yellow]Model selection cancelled.[/yellow]")
    else:
        # Direct model switching (legacy support)
        if model_name in session.config.models:
            session.config.model_name = model_name
            console.print(f"[green]✓ Switched to model: {model_name}[/green]")
        else:
            available = ", ".join(session.config.models.keys())
            console.print(f"[red]Model '{model_name}' not found. Available models: {available}[/red]")

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
        
        # Use the existing build_repo_context utility with required arguments
        repo_path = Path.cwd()
        file_contents = build_repo_context(repo_path, session.config)
        
        if file_contents:
            # Update session current files
            session.current_files.update(file_contents)
            console.print(f"[green]✓ Refreshed context with {len(file_contents)} files[/green]")
        else:
            console.print("[yellow]No files found to index[/yellow]")
        
    except Exception as e:
        console.print(f"[red]Error refreshing repository context: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")