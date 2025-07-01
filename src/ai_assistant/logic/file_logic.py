from pathlib import Path
from rich.console import Console

from ..utils.parsing_utils import extract_file_content_from_response
from ..services.file_service import FileService

console = Console()

'''
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

    code_blocks = extract_file_content_from_response(session.last_ai_response_content)
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
'''

async def new_file(session, file_path_str: str):
    """Logic to create a new empty file using the centralized FileService."""
    if not file_path_str:
        console.print("[red]Usage: /new <filename> [@directory][/red]")
        return False
    
    # Parse the input to separate filename and directory
    parts = file_path_str.split()
    filename = parts[0]
    
    # Check if there's a directory specified with @
    target_dir = None
    for part in parts[1:]:
        if part.startswith('@'):
            target_dir = part[1:]  # Remove the @ symbol
            break
    
    # Construct the full path
    if target_dir:
        # Use the specified directory relative to work_dir
        path = session.file_service.work_dir.joinpath(target_dir, filename)
    else:
        # Use work_dir as base
        path = session.file_service.work_dir.joinpath(filename)

    if path.exists():
        console.print(f"[yellow]File already exists: {path.relative_to(session.file_service.work_dir)}[/yellow]")
        return True

    try:
        # Create parent directories if they don't exist
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use the file_service to handle the write operation
        await session.file_service.write_file(path, "")
        
        relative_path_str = str(path.relative_to(session.file_service.work_dir))
        session.current_files[relative_path_str] = ""
        console.print(f"[green]✓ Created new file and added to context: {relative_path_str}[/green]")
        return True
    except Exception as e:
        console.print(f"[red]Error creating file: {e}[/red]")
        return False

# --- MODIFIED TO PASS THE SESSION OBJECT ---
async def save_code(session, file_path_str: str, code_to_save: str = None):
    """Logic to save code to a specific file path."""
    if not file_path_str:
        console.print("[red]Filename cannot be empty.[/red]")
        return False
    
    # --- THE FIX: If code is not provided, get it from the last response ---
    if code_to_save is None:
        if not session.last_ai_response_content:
            console.print("[red]No AI response available to save from.[/red]")
            return False
            
        code_blocks = extract_file_content_from_response(session.last_ai_response_content)
        
        # --- FIX FOR ISSUE #2 ---
        # If no code blocks are found, assume the entire response is the file content.
        # This is useful for saving text files like README.md where the AI might not use fences.
        if not code_blocks:
            console.print("[yellow]No code blocks found. Treating entire response as file content.[/yellow]")
            code_to_save = session.last_ai_response_content
        else:
            # Default to saving the first code block if some are found.
            code_to_save = code_blocks[0]['code']

    # The path is now a full path string provided by the caller
    path = Path(file_path_str)
    
    try:
        await session.file_service.write_file(path, code_to_save)
        relative_path_str = str(path.relative_to(session.config.work_dir))
        console.print(f"[green]✓ Saved changes to {relative_path_str}[/green]")
        session.current_files[relative_path_str] = code_to_save
        return True
    except Exception as e:
        console.print(f"[red]Error saving file: {e}[/red]")
        return False

async def apply_changes(session):
    """Logic to apply all code blocks from the last response to their files."""
    if not session.last_ai_response_content:
        return console.print("[red]No AI response available to apply changes from.[/red]")

    code_blocks = [b for b in extract_file_content_from_response(session.last_ai_response_content) if b.get('filename')]
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