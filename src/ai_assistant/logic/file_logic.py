from pathlib import Path
from rich.console import Console

from ..utils.parsing_utils import extract_code_blocks
from ..services.file_service import FileService

console = Console()

async def new_file(file_path_str: str, current_files: dict):
    """Logic to create a new empty file."""
    if not file_path_str:
        return console.print("[red]Usage: /new <filename>[/red]")
    path = Path(file_path_str)
    if path.exists():
        return console.print(f"[yellow]File already exists: {file_path_str}[/yellow]")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        relative_path_str = str(path.relative_to(Path.cwd()))
        current_files[relative_path_str] = ""
        console.print(f"[green]✓ Created new file and added to context: {relative_path_str}[/green]")
    except Exception as e:
        console.print(f"[red]Error creating file: {e}[/red]")

async def save_code(session, filename: str):
    """Logic to save the last code block to a file."""
    if not filename:
        return console.print("[red]Usage: /save <filename>[/red]")
    if not session.last_ai_response_content:
        return console.print("[red]No AI response available to save from.[/red]")

    code_blocks = extract_code_blocks(session.last_ai_response_content)
    if not code_blocks:
        return console.print("[red]No code blocks found in the last AI response.[/red]")

    code_to_save = code_blocks[0]['code']
    path = Path.cwd().joinpath(filename)
    action_verb = "Updated" if path.exists() else "Created"
    
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        await session.file_service.write_file(path, code_to_save)
        console.print(f"[green]✓ {action_verb} file: {filename}[/green]")
        relative_path_str = str(path.relative_to(Path.cwd()))
        session.current_files[relative_path_str] = code_to_save
        console.print(f"[green]✓ {relative_path_str} is now in the active context.[/green]")
    except Exception as e:
        console.print(f"[red]Error saving file: {e}[/red]")

async def apply_changes(session):
    """Logic to apply all code blocks from the last response to their files."""
    if not session.last_ai_response_content:
        return console.print("[red]No AI response available to apply changes from.[/red]")

    code_blocks = [b for b in extract_code_blocks(session.last_ai_response_content) if b.get('filename')]
    if not code_blocks:
        return console.print("[yellow]No code blocks with file paths found in the response.[/yellow]")

    console.print("\n[bold]The following file changes will be applied:[/bold]")
    for block in code_blocks:
        status = "[yellow]new file[/yellow]" if not Path.cwd().joinpath(block['filename']).exists() else "[cyan]overwrite[/cyan]"
        console.print(f"  - {block['filename']} ({status})")
    
    console.print("-" * 20)
    applied_files = []
    for block in code_blocks:
        filename, code = block['filename'], block['code']
        path = Path.cwd().joinpath(filename)
        try:
            path.relative_to(Path.cwd()) # Security check
            path.parent.mkdir(parents=True, exist_ok=True)
            await session.file_service.write_file(path, code)
            relative_path_str = str(path.relative_to(Path.cwd()))
            session.current_files[relative_path_str] = code
            console.print(f"[green]✓ Applied changes to {filename}[/green]")
            applied_files.append(filename)
        except ValueError:
            console.print(f"[red]Security Error: Attempted to write outside project directory: '{path}'. Skipping.[/red]")
        except Exception as e:
            console.print(f"[red]Error applying changes to {filename}: {e}[/red]")
    
    if applied_files:
        console.print("\n[green]✓ All detected changes have been applied.[/green]")