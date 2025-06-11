from pathlib import Path
from rich.console import Console
import click

from ...utils.git_utils import GitUtils
from ...utils.parsing_utils import extract_code_blocks
from ...core.exceptions import AIAssistantError
from ..commands import CodeCommands
import questionary
from ...cli.commands import CodeCommands
from . import display

console = Console()


async def handle_new_file(session, file_path: str):
    """Creates a new empty file and adds it to the context."""
    path = Path(file_path)
    if path.exists():
        console.print(f"[yellow]File already exists: {file_path}[/yellow]")
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        # Add empty file to context
        relative_path_str = str(path.relative_to(Path.cwd()))
        session.current_files[relative_path_str] = ""
        console.print(f"[green]✓ Created new file and added to context: {relative_path_str}[/green]")
    except Exception as e:
        console.print(f"[red]Error creating file: {e}[/red]")


async def handle_save_last_code(session, filename: str):
    """Saves the first code block from the last AI response to a file."""
    if not session.last_ai_response_content:
        console.print("[red]No AI response available to save from.[/red]")
        return

    code_blocks = extract_code_blocks(session.last_ai_response_content)
    if not code_blocks:
        console.print("[red]No code blocks found in the last AI response.[/red]")
        return

    code_to_save = code_blocks[0]['code']
    path = Path.cwd().joinpath(filename)
    
    # Check if file already exists
    file_exists = path.exists()
    action_verb = "Updated" if file_exists else "Created"
    
    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        await session.file_service.write_file(path, code_to_save)
        console.print(f"[green]✓ {action_verb} file: {filename}[/green]")
        
        # Add/update the newly saved file in the active context
        relative_path_str = str(path.relative_to(Path.cwd()))
        session.current_files[relative_path_str] = code_to_save
        console.print(f"[green]✓ {relative_path_str} is now in the active context.[/green]")
        
        # Check if this is a git repository and suggest git operations
        await _suggest_git_operations(session, relative_path_str, file_exists)
        
    except Exception as e:
        console.print(f"[red]Error saving file: {e}[/red]")


async def _suggest_git_operations(session, file_path: str, was_existing_file: bool):
    """Suggest git operations after saving a file."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    
    # Only suggest if this is a git repository
    if not await git_utils.is_git_repo(repo_path):
        return
    
    try:
        # Check if file is already tracked or has changes
        is_tracked = await git_utils.is_file_tracked(repo_path, file_path)
        has_changes = await git_utils.has_uncommitted_changes(repo_path, file_path)
        
        if has_changes or not is_tracked:
            action = "modified" if was_existing_file else "created"
            console.print(f"\n[bold cyan]Git Operations Available:[/bold cyan]")
            
            if not is_tracked:
                console.print(f"  • File is [yellow]untracked[/yellow]. Add it with: [dim]/git_add {file_path}[/dim]")
            else:
                console.print(f"  • File has been [yellow]{action}[/yellow]. Stage it with: [dim]/git_add {file_path}[/dim]")
            
            console.print(f"  • After staging, commit with: [dim]/git_commit \"Updated {file_path}\"[/dim]")
            console.print(f"  • Then push with: [dim]/git_push[/dim]")
            
            # Auto-suggest a commit message based on the changes
            suggested_message = _generate_commit_message(file_path, was_existing_file)
            console.print(f"  • Suggested commit message: [dim]\"{suggested_message}\"[/dim]")
            
    except Exception as e:
        # Silently fail git suggestions if git operations fail
        pass


def _generate_commit_message(file_path: str, was_existing_file: bool) -> str:
    """Generate a suggested commit message based on the file operation."""
    file_name = Path(file_path).name
    
    if was_existing_file:
        return f"Update {file_name} with AI-generated changes"
    else:
        return f"Add {file_name} - AI-generated file"


async def handle_save_and_commit(session, filename: str, commit_message: str = None):
    """Save code and automatically stage and commit it."""
    # First save the file
    await handle_save_last_code(session, filename)
    
    # Then automatically add and commit if this is a git repo
    git_utils = GitUtils()
    repo_path = Path.cwd()
    
    if not await git_utils.is_git_repo(repo_path):
        console.print("[yellow]Not a git repository - skipping commit[/yellow]")
        return
    
    try:
        relative_path_str = str(Path(filename).relative_to(Path.cwd()))
        
        # Stage the file
        if await git_utils.add_file(repo_path, relative_path_str):
            console.print(f"[green]✓ Staged: {relative_path_str}[/green]")
            
            # Generate commit message if not provided
            if not commit_message:
                commit_message = _generate_commit_message(relative_path_str, Path(filename).exists())
            
            # Commit the changes
            if await git_utils.commit(repo_path, commit_message):
                console.print(f"[green]✓ Committed: \"{commit_message}\"[/green]")
                console.print("[cyan]Ready to push with: /git_push[/cyan]")
            else:
                console.print("[yellow]Commit failed - no changes to commit[/yellow]")
        else:
            console.print(f"[red]Failed to stage file: {relative_path_str}[/red]")
            
    except Exception as e:
        console.print(f"[red]Error during auto-commit: {e}[/red]")


async def handle_apply_changes(session):
    """Applies all code changes from the last AI response to their respective files."""
    if not session.last_ai_response_content:
        console.print("[red]No AI response available to apply changes from.[/red]")
        return

    code_blocks = extract_code_blocks(session.last_ai_response_content)
    blocks_to_apply = [block for block in code_blocks if block.get('filename')]

    if not blocks_to_apply:
        console.print("[yellow]No code blocks with file paths found in the response to apply.[/yellow]")
        console.print("Tip: You can save a snippet to a new file using: [dim]/save <filename>[/dim]")
        return

    console.print("\n[bold]The following file changes will be applied:[/bold]")
    for block in blocks_to_apply:
        # Create an absolute path to check against
        absolute_path = Path.cwd().joinpath(block['filename'])
        status = "[yellow]new file[/yellow]" if not absolute_path.exists() else "[cyan]overwrite[/cyan]"
        console.print(f"  - {block['filename']} ({status})")

    console.print("-" * 20)
    applied_files = []
    for block in blocks_to_apply:
        filename = block['filename']
        code = block['code']
        # Create a full, absolute path for file operations.
        path = Path.cwd().joinpath(filename)
        
        try:
            # Security Check: Ensure the path is within the current working directory.
            # `relative_to` will raise a ValueError if it's not a subpath.
            path.relative_to(Path.cwd())

            # Ensure parent directory exists before writing
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Now, proceed with writing the file and updating context.
            await session.file_service.write_file(path, code)
            
            relative_path_str = str(path.relative_to(Path.cwd()))
            session.current_files[relative_path_str] = code
            
            console.print(f"[green]✓ Applied changes to {filename}[/green]")
            applied_files.append(filename)
        except ValueError:
            # This catches the security error from `relative_to`.
            console.print(f"[red]Security Error: Attempted to write to '{path}' which is outside the current project directory. Skipping.[/red]")
        except Exception as e:
            console.print(f"[red]Error applying changes to {filename}: {e}[/red]")

    if not applied_files:
        return

    console.print("\n[green]✓ All detected changes have been applied.[/green]")

    git_utils = GitUtils()
    if await git_utils.is_git_repo(Path.cwd()):
        files_str = " ".join(f'"{f}"' for f in applied_files) # Quote paths for safety
        console.print(f"\n[bold cyan]Git Actions:[/bold cyan] You can now stage these files with [dim]/git_add {files_str}[/dim] or use [dim]/review[/dim] to commit.")


async def handle_git_add(session, files: list[str]):
    """Stages one or more files using git."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]This is not a git repository.[/red]")
        return

    added_files = []
    for f_str in files:
        if (repo_path / f_str).exists():
            if await git_utils.add_file(repo_path, f_str):
                added_files.append(f_str)
        else:
            console.print(f"[yellow]Warning: File not found, cannot stage: {f_str}[/yellow]")

    if added_files:
        console.print(f"[green]✓ Staged files: {', '.join(added_files)}[/green]")


async def handle_git_commit(session, message: str):
    """Commits staged changes with a given message."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]This is not a git repository.[/red]")
        return

    if not message:
        console.print("[red]Commit message cannot be empty.[/red]")
        return

    try:
        if await git_utils.commit(repo_path, message):
            console.print(f"[green]✓ Committed with message: \"{message}\"[/green]")
        else:
            console.print("[yellow]Commit failed. Are there any staged changes?[/yellow]")
    except Exception as e:
        console.print(f"[red]Error during commit: {e}[/red]")


async def handle_git_push(session):
    """Pushes committed changes to the remote repository."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]This is not a git repository.[/red]")
        return

    try:
        current_branch = await git_utils.get_current_branch(repo_path)
        with console.status(f"[bold yellow]Pushing to origin/{current_branch}...[/bold yellow]"):
            if await git_utils.push(repo_path, current_branch):
                console.print(f"[green]✓ Successfully pushed to origin/{current_branch}[/green]")
            else:
                console.print("[red]Failed to push changes. Check remote configuration and authentication.[/red]")
    except Exception as e:
        console.print(f"[red]Error during push: {e}[/red]")

async def handle_repo_review(session, summary_only: bool = False, show_diff: bool = True):
    """Handle repository review command."""
    try:
        # Create CodeCommands instance and call the review_changes method
        code_commands = CodeCommands(session.config)
        
        if summary_only:
            # Show only summary, no diff
            await code_commands.review_changes(show_summary=True, show_diff=False)
        else:
            # Show both summary and diff
            await code_commands.review_changes(show_summary=True, show_diff=show_diff)
            
    except Exception as e:
        display.console.print(f"[red]Error during repository review: {e}[/red]")
        import traceback
        display.console.print(f"[dim]{traceback.format_exc()}[/dim]")