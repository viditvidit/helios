from pathlib import Path
from rich.console import Console
from rich.panel import Panel
import questionary
import asyncio

from ...utils.git_utils import GitUtils
from ...utils.parsing_utils import extract_code_blocks
from ...core.exceptions import GitHubServiceError, NotAGitRepositoryError
from ...services.github_service import GitHubService
from . import display

console = Console()

# --- File Operations --- (These are unchanged)
async def handle_new_file(session, file_path: str):
    path = Path(file_path)
    if path.exists():
        console.print(f"[yellow]File already exists: {file_path}[/yellow]")
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        relative_path_str = str(path.relative_to(Path.cwd()))
        session.current_files[relative_path_str] = ""
        console.print(f"[green]✓ Created new file and added to context: {relative_path_str}[/green]")
    except Exception as e:
        console.print(f"[red]Error creating file: {e}[/red]")

async def handle_save_last_code(session, filename: str):
    if not session.last_ai_response_content:
        console.print("[red]No AI response available to save from.[/red]")
        return
    code_blocks = extract_code_blocks(session.last_ai_response_content)
    if not code_blocks:
        console.print("[red]No code blocks found in the last AI response.[/red]")
        return
    code_to_save = code_blocks[0]['code']
    path = Path.cwd().joinpath(filename)
    file_exists = path.exists()
    action_verb = "Updated" if file_exists else "Created"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        await session.file_service.write_file(path, code_to_save)
        console.print(f"[green]✓ {action_verb} file: {filename}[/green]")
        relative_path_str = str(path.relative_to(Path.cwd()))
        session.current_files[relative_path_str] = code_to_save
        console.print(f"[green]✓ {relative_path_str} is now in the active context.[/green]")
    except Exception as e:
        console.print(f"[red]Error saving file: {e}[/red]")

async def handle_apply_changes(session):
    if not session.last_ai_response_content:
        console.print("[red]No AI response available to apply changes from.[/red]")
        return
    code_blocks = extract_code_blocks(session.last_ai_response_content)
    blocks_to_apply = [block for block in code_blocks if block.get('filename')]
    if not blocks_to_apply:
        console.print("[yellow]No code blocks with file paths found in the response to apply.[/yellow]")
        return
    console.print("\n[bold]The following file changes will be applied:[/bold]")
    for block in blocks_to_apply:
        absolute_path = Path.cwd().joinpath(block['filename'])
        status = "[yellow]new file[/yellow]" if not absolute_path.exists() else "[cyan]overwrite[/cyan]"
        console.print(f"  - {block['filename']} ({status})")
    console.print("-" * 20)
    applied_files = []
    for block in blocks_to_apply:
        filename, code = block['filename'], block['code']
        path = Path.cwd().joinpath(filename)
        try:
            path.relative_to(Path.cwd())
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

# --- Git & GitHub Operations ---

async def handle_git_add(session, files: list[str]):
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]This is not a git repository.[/red]")
        return
    added_files = [f for f in files if (repo_path / f).exists() and await git_utils.add_file(repo_path, f)]
    if added_files:
        console.print(f"[green]✓ Staged files: {', '.join(added_files)}[/green]")

async def handle_git_commit(session, message: str):
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]This is not a git repository.[/red]")
        return
    if not message:
        console.print("[red]Commit message cannot be empty.[/red]")
        return
    if await git_utils.commit(repo_path, message):
        console.print(f'[green]✓ Committed with message: "{message}"[/green]')
    else:
        console.print("[yellow]Commit failed. Are there any staged changes?[/yellow]")

async def handle_git_push(session):
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]This is not a git repository.[/red]")
        return
    current_branch = await git_utils.get_current_branch(repo_path)
    with console.status(f"[bold yellow]Pushing to origin/{current_branch}...[/bold yellow]"):
        if await git_utils.push(repo_path, current_branch):
            console.print(f"[green]✓ Successfully pushed to origin/{current_branch}[/green]")
        else:
            console.print("[red]Failed to push changes. Check remote configuration and authentication.[/red]")

async def handle_git_switch(session, branch_name: str):
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path): return console.print("[red]This is not a git repository.[/red]")
    if not branch_name: return console.print("[red]Usage: /git_switch <branch_name>[/red]")
    if await git_utils.switch_branch(repo_path, branch_name): console.print(f"[green]✓ Switched to branch '{branch_name}'.[/green]")
    else: console.print(f"[red]Failed to switch to branch '{branch_name}'. Does it exist?[/red]")

async def handle_review(session):
    """Restored /review workflow with the classic [y/N] prompt style."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    try:
        if not await git_utils.is_git_repo(repo_path):
            raise NotAGitRepositoryError(path=repo_path)

        unstaged_changes = await git_utils.get_unstaged_files(repo_path)
        if unstaged_changes:
            console.print("[yellow]Unstaged changes detected:[/yellow]")
            for f in unstaged_changes:
                console.print(f"  - {f}")
            
            should_stage = await questionary.confirm(
                "Stage these files before reviewing?",
                default=True,
                auto_enter=False
            ).ask_async()
            if should_stage:
                await git_utils.add_files(repo_path, unstaged_changes)
                console.print("[green]✓ Staged all detected changes.[/green]")

        staged_diff = await git_utils.get_staged_diff(repo_path)
        if not staged_diff:
            console.print("[yellow]No staged changes to review. Use `/git_add <file>` to stage files first.[/yellow]")
            return

        from rich.syntax import Syntax
        from rich.panel import Panel
        console.print(Panel(Syntax(staged_diff, "diff", theme="github-dark", word_wrap=True),
                              title="Staged Changes", border_style="green"))

        should_commit = await questionary.confirm(
            "Proceed to commit these changes?",
            default=True,
            auto_enter=False
        ).ask_async()
        if not should_commit:
            console.print("[yellow]Commit aborted.[/yellow]")
            return

        commit_message = await questionary.text("Enter commit message:").ask_async()
        if not commit_message:
            console.print("[red]Commit message cannot be empty. Aborting.[/red]")
            return

        await git_utils.commit(repo_path, commit_message)
        console.print(f"[green]✓ Changes committed with message: '{commit_message}'[/green]")

        should_create_pr = await questionary.confirm(
            "Create a Pull Request for this commit?",
            default=True,
            auto_enter=False
        ).ask_async()
        if should_create_pr:
            current_branch = await git_utils.get_current_branch(repo_path)
            if current_branch.lower() in ["main", "master", "develop"]:
                console.print(f"[yellow]You are on the '{current_branch}' branch. It's recommended to create PRs from a feature branch.[/yellow]")
                should_continue = await questionary.confirm(
                    "Continue anyway?",
                    default=False,
                    auto_enter=False
                ).ask_async()
                if not should_continue:
                    console.print("[yellow]PR creation aborted.[/yellow]")
                    return

            with console.status(f"[bold yellow]Pushing '{current_branch}' to remote to enable PR creation...[/bold yellow]"):
                await git_utils.push(repo_path, current_branch, set_upstream=True)
            
            await handle_create_pr(session, head_branch_suggestion=current_branch)

    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def handle_create_repo(session):
    """Interactively create a new GitHub repository."""
    try:
        service = GitHubService(session.config)
        console.print("\n[bold cyan]Creating a new GitHub Repository...[/bold cyan]")
        
        repo_name = await questionary.text("Repository Name:").ask_async()
        if not repo_name:
            return console.print("[red]Repository name cannot be empty. Aborting.[/red]")

        description = await questionary.text("Description (optional):").ask_async()
        
        is_private = await questionary.confirm(
            "Make repository private?",
            default=True,
            auto_enter=False
        ).ask_async()

        with console.status(f"Creating repository '{repo_name}' on GitHub..."):
            clone_url = await service.create_repo(repo_name, is_private, description)
        
        console.print(f"To clone your new repository, run:\n[bold]git clone {clone_url}[/bold]")

    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error creating repository: {e}[/red]")

async def handle_create_branch(session):
    """Interactively create a new GitHub branch."""
    try:
        service = GitHubService(session.config)
        console.print("\n[bold cyan]Creating a new GitHub Branch...[/bold cyan]")

        branch_name = await questionary.text("New Branch Name:").ask_async()
        if not branch_name:
            return console.print("[red]Branch name cannot be empty. Aborting.[/red]")

        source_branch = await questionary.text("Source Branch:", default="main").ask_async()

        with console.status(f"Creating branch '{branch_name}' from '{source_branch}'..."):
            await service.create_branch(branch_name, source_branch)

    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error creating branch: {e}[/red]")

async def handle_create_pr(session, head_branch_suggestion: str = ""):
    """Interactively create a pull request."""
    try:
        service = GitHubService(session.config)
        git_utils = GitUtils()
        
        console.print("\n[bold cyan]Creating a new Pull Request...[/bold cyan]")
        
        title = await questionary.text("PR Title:").ask_async()
        if not title:
            return console.print("[red]Title cannot be empty. Aborting.[/red]")
            
        body = await questionary.text("PR Body (optional, markdown supported):").ask_async()
        
        head_branch = await questionary.text(
            "Head branch (the branch to merge from):",
            default=head_branch_suggestion or await git_utils.get_current_branch(Path.cwd())
        ).ask_async()
        
        base_branch = await questionary.text(
            "Base branch (the branch to merge into):",
            default="main"
        ).ask_async()

        with console.status(f"Creating PR: '{title}'..."):
            await service.create_pull_request(title, body, head_branch, base_branch)

    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error creating PR: {e}[/red]")

async def handle_create_issue(session):
    """Interactively create a GitHub issue."""
    try:
        service = GitHubService(session.config)
        console.print("\n[bold cyan]Creating a new GitHub Issue...[/bold cyan]")
        
        title = await questionary.text("Issue Title:").ask_async()
        if not title:
            return console.print("[red]Title cannot be empty. Aborting.[/red]")
        
        body = await questionary.text("Issue Body (optional, markdown supported):").ask_async()
        
        with console.status(f"Creating issue: '{title}'..."):
            await service.create_issue(title, body)
            
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error creating issue: {e}[/red]")

async def handle_repo_summary(session):
    """New: Handler for the /repo_summary command."""
    try:
        service = GitHubService(session.config)
        with console.status("[bold yellow]Generating AI repository summary...[/bold yellow]"):
            summary = await service.get_ai_repo_summary()
        console.print(Panel(summary, title="AI Repository Summary", border_style="blue", expand=True))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")

async def handle_pr_review(session, pr_number_str: str):
    """New: Handler for the /pr_review command."""
    if not pr_number_str or not pr_number_str.isdigit():
        return console.print("[red]Usage: /pr_review <pr_number>[/red]")
    
    pr_number = int(pr_number_str)
    try:
        service = GitHubService(session.config)
        with console.status(f"[bold yellow]Generating AI review for PR #{pr_number}...[/bold yellow]"):
            summary = await service.get_ai_pr_summary(pr_number)
        console.print(Panel(summary, title=f"AI Review for PR #{pr_number}", border_style="blue", expand=True))
    except (GitHubServiceError, NotAGitRepositoryError) as e:
        console.print(f"[red]Error: {e}[/red]")