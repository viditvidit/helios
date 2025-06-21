# src/ai_assistant/logic/agent/tools.py

import asyncio
import re
import shutil
from typing import List, Dict, Any
import questionary
import platform
import requests
from bs4 import BeautifulSoup
from pathlib import Path

from googlesearch import search as google_search
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskProgressColumn
from rich.text import Text
from rich.syntax import Syntax
from rich.panel import Panel

from ...logic import git_logic, file_logic 
from ...services.ai_service import AIService
from ...services.github_service import GitHubService
from ...models.request import CodeRequest
from ...utils.git_utils import GitUtils

console = Console()

async def create_project_workspace(session, directory_name: str) -> bool:
    """Creates the main project directory. This should be the first step for any new project."""
    work_dir = session.config.work_dir / directory_name
    if work_dir.exists():
        console.print(f"[yellow]Workspace directory '{directory_name}' already exists. Using it.[/yellow]")
    else:
        work_dir.mkdir(parents=True)
        console.print(f"[green]✓ Created project workspace: {directory_name}[/green]")
    return True

async def review_and_commit_changes(session, commit_message: str, show_diff: bool = True) -> bool:
    """
    A non-interactive tool for the agent to review and commit changes.
    It stages all unstaged files, displays the diff, and commits with a given message.
    """
    git_utils = GitUtils()
    repo_path = session.config.work_dir
    
    if not await git_utils.is_git_repo(repo_path):
        console.print("[red]Not a git repository.[/red]")
        return False

    unstaged = await git_utils.get_unstaged_files(repo_path)
    if unstaged:
        console.print("[dim]Staging all detected changes...[/dim]")
        await git_utils.add_files(repo_path, unstaged)

    per_file_diffs = await git_utils.get_staged_diff_by_file(repo_path)
    if not per_file_diffs:
        console.print("[yellow]No changes to review or commit.[/yellow]")
        return True # Not a failure state

    if show_diff:
        for filename, diff_content in per_file_diffs.items():
            console.print(Panel(Syntax(diff_content, "diff", theme="vim", word_wrap=True), title=f"Changes for {filename}", border_style="yellow"))
    else:
        summary_lines = [Text(f"  • {f}: ").append(f"+{d.count(chr(10)+'+')} ", style="green").append(f"-{d.count(chr(10)+'-')}", style="red") for f, d in per_file_diffs.items()]
        console.print(Panel(Text("\n").join(summary_lines), title="Staged Changes Summary", border_style="cyan"))

    console.print(f"Committing with message: [italic]'{commit_message}'[/italic]")
    await git_utils.commit(repo_path, commit_message)
    console.print("[green]✓ Changes committed.[/green]")
    return True

async def run_shell_command(session, command: str, cwd: str, can_fail: bool = False, verbose: bool = False, background: bool = False, force_overwrite: bool = False) -> bool:
    """Executes a shell command, with enhanced error handling for missing dependencies."""
    run_dir = Path(cwd)

    if force_overwrite:
        scaffold_match = re.search(r'(create-react-app|vite|next|vue create)\s+([^\s]+)', command)
        if scaffold_match:
            target_path = run_dir / scaffold_match.group(2)
            if target_path.exists():
                shutil.rmtree(target_path)
    
    console.print(f"Running command: [bold magenta]{command}[/bold magenta] in [dim]{run_dir}[/dim]")

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=run_dir
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            console.print(f"[green]✓ Shell command finished successfully.[/green]")
            if verbose and stdout:
                console.print(Panel(stdout.decode().strip(), title="Output", border_style="dim"))
            return True
        else:
            stderr_text = stderr.decode().strip()
            stdout_text = stdout.decode().strip()
            
            # --- NEW: Smarter, Yes/No Dependency Installation ---
            if 'command not found' in stderr_text.lower():
                missing_cmd = command.split()[0]
                
                # Suggest a default install command based on OS
                os_name = platform.system().lower()
                install_suggestion = ""
                if os_name == "darwin": # macOS
                    install_suggestion = f"brew install {missing_cmd}"
                    if missing_cmd == "mvn": install_suggestion = "brew install maven"
                elif os_name == "linux":
                    install_suggestion = f"sudo apt-get install -y {missing_cmd}"
                    if missing_cmd == "mvn": install_suggestion = "sudo apt-get install -y maven"
                
                console.print(f"[yellow]Command '{missing_cmd}' not found.[/yellow]")
                
                if install_suggestion:
                    proceed_install = await questionary.confirm(f"Attempt to install with: '{install_suggestion}'?").ask_async()
                else:
                    proceed_install = await questionary.confirm(f"Attempt to install '{missing_cmd}'? (You may need to find the correct command)").ask_async()

                if proceed_install:
                    final_install_command = install_suggestion
                    # If we couldn't suggest a command, ask the user for it
                    if not final_install_command:
                        final_install_command = await questionary.text("Please enter the installation command:").ask_async()

                    if not final_install_command:
                        console.print("[yellow]Skipping command due to missing dependency.[/yellow]")
                        return True # Gracefully skip

                    console.print(f"Attempting to install with: [magenta]{final_install_command}[/magenta]")
                    install_process = await asyncio.create_subprocess_shell(final_install_command, cwd=run_dir)
                    if await install_process.wait() == 0:
                        console.print(f"[green]✓ Installation successful. Retrying original command...[/green]")
                        return await run_shell_command(session, command, cwd, can_fail, verbose, background)
                    else:
                        console.print(f"[red]Installation failed. Aborting step.[/red]")
                        return False
                else:
                    console.print("[yellow]Skipping command due to missing dependency.[/yellow]")
                    return True # Gracefully skip
            
            console.print("[bold red]Shell command failed. Output:[/bold red]")
            if stdout_text: console.print(Text("[stdout] ", style="dim") + Text(stdout_text))
            if stderr_text: console.print(Text("[stderr] ", style="dim") + Text(stderr_text))
            return can_fail

    except Exception as e:
        console.print(f"[red]✗ An unexpected error occurred while running shell command: {e}[/red]")
        return False

async def generate_code_concurrently(session, files: List[Dict[str, Any]], cwd: str = None) -> bool:
    """Generates code for multiple files concurrently with a clean, dynamic progress bar."""
    base_dir = Path(cwd) if cwd else session.config.work_dir
    
    progress = Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console, transient=True)

    with progress:
        tasks = []
        for f in files:
            filename, prompt = f.get('filename'), f.get('prompt')
            if not filename or not prompt: continue
            
            progress_task_id = progress.add_task(f"[dim]Writing {filename}...[/dim]", total=1)
            # Pass the base_dir to the file generation function
            coro = generate_code_for_file(session, filename, prompt, base_dir)
            tasks.append((asyncio.create_task(coro), progress_task_id, filename))

        results = []
        for task, progress_task_id, filename in tasks:
            try:
                success = await task
                results.append(success)
                style, icon = ("green", "✓") if success else ("red", "✗")
                progress.update(progress_task_id, description=f"[{style}]{icon} Wrote {filename}[/{style}]", completed=1)
            except Exception as e:
                results.append(False)
                progress.update(progress_task_id, description=f"[red]✗ CRASHED {filename}[/red]", completed=1)
    
    return all(results)

async def web_search(query: str, num_results: int = 5) -> str:
    """Performs a web search using Google and returns the top results."""
    console.print(f"Searching web for: [italic]{query}[/italic]...")
    try:
        search_results = await asyncio.to_thread(google_search, query, num_results=num_results, stop=num_results, pause=1)
        return "\n".join([f"{i+1}. {result}" for i, result in enumerate(search_results)]) or "No results found."
    except Exception as e:
        return f"Error during web search: {e}"

async def fetch_web_content(url: str) -> str:
    """Fetches the textual content of a given URL, stripping HTML."""
    console.print(f"Fetching content from: [italic]{url}[/italic]...")
    try:
        response = await asyncio.to_thread(requests.get, url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        return ' '.join(soup.get_text().split())[:8000]
    except Exception as e:
        return f"Error fetching URL content: {e}"

async def github_create_repo_non_interactive(session, repo_name: str, description: str = "", is_private: bool = False) -> bool:
    """Ensures a GitHub repository exists. Creates it if it's missing, otherwise uses the existing one."""
    console.print(f"Ensuring GitHub repo exists: [italic]{repo_name}[/italic]...")
    try:
        service = GitHubService(session.config)
        repo = await service.get_or_create_repo(repo_name, is_private, description)
        if repo:
            session.repo_clone_url = repo.clone_url
            return True
        return False
    except Exception as e:
        console.print(f"[red]Error ensuring GitHub repo exists: {e}[/red]")
        return False

async def run_shell_command(session, command: str, cwd: str = None, can_fail: bool = False, verbose: bool = False, background: bool = False, force_overwrite: bool = False) -> bool:
    """Executes a shell command, with enhanced error handling for missing dependencies."""
    run_dir = Path(cwd)

    if force_overwrite:
        scaffold_match = re.search(r'(create-react-app|vite|next|vue create)\s+([^\s]+)', command)
        if scaffold_match:
            target_path = run_dir / scaffold_match.group(2)
            if target_path.exists():
                shutil.rmtree(target_path)
    
    console.print(f"Running command: [bold red]{command}[/bold red] in [dim]{run_dir}[/dim]")

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=run_dir
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            console.print(f"[green]✓ Shell command finished successfully.[/green]")
            if verbose and stdout:
                console.print(Panel(stdout.decode().strip(), title="Output", border_style="dim"))
            return True
        else:
            stderr_text = stderr.decode().strip()
            stdout_text = stdout.decode().strip()
            
            if 'command not found' in stderr_text:
                missing_cmd = command.split()[0]
                console.print(f"[yellow]Command '{missing_cmd}' not found.[/yellow]")
                
                install_command = await questionary.text(
                    f"Would you like to try installing it? (e.g., 'brew install {missing_cmd}', 'npm install -g {missing_cmd}'). Leave blank to skip."
                ).ask_async()

                if install_command:
                    console.print(f"Attempting to install with: [magenta]{install_command}[/magenta]")
                    install_process = await asyncio.create_subprocess_shell(
                        install_command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=run_dir
                    )
                    await install_process.wait()

                    if install_process.returncode == 0:
                        console.print(f"[green]✓ Installation successful. Retrying original command...[/green]")
                        # Retry the original command
                        return await run_shell_command(session, command, str(run_dir), can_fail, verbose, background)
                    else:
                        console.print(f"[red]Installation failed. Aborting step.[/red]")
                        return False # Abort if install fails
                else:
                    console.print("[yellow]Skipping command due to missing dependency.[/yellow]")
                    return True # Gracefully skip the step
            
            # Existing error handling
            console.print("[bold red]Shell command failed. Output:[/bold red]")
            if stdout_text: console.print(Text("[stdout] ", style="dim") + Text(stdout_text))
            if stderr_text: console.print(Text("[stderr] ", style="dim") + Text(stderr_text))
            
            return can_fail

    except Exception as e:
        console.print(f"[red]✗ An unexpected error occurred while running shell command: {e}[/red]")
        return False

async def setup_git_and_push(session, commit_message: str, repo_name: str, branch: str = "main") -> bool:
    """A high-level tool that performs the entire initial Git setup and push sequence."""
    console.print(f"Starting full Git and GitHub setup for [italic]{repo_name}[/italic]...")
    git_utils = git_logic.GitUtils()
    work_dir = session.config.work_dir

    if not await git_utils.is_git_repo(work_dir):
        await git_utils.init_repo(work_dir)
    
    await git_utils.add_files(work_dir, ['.'])
    
    status = await git_utils.get_status(work_dir)
    if "nothing to commit" in status:
        console.print("[yellow]✓ No changes to commit.[/yellow]")
    else:
        await git_utils.commit(work_dir, commit_message)
        console.print("[green]✓ Files committed.[/green]")

    if not await github_create_repo_non_interactive(session, repo_name):
        return False

    clone_url = getattr(session, 'repo_clone_url', None)
    if not clone_url: return False

    try:
        await git_utils._run_git_command(work_dir, ['remote', 'add', 'origin', clone_url])
    except Exception:
        await git_utils._run_git_command(work_dir, ['remote', 'set-url', 'origin', clone_url])
    
    await git_utils._run_git_command(work_dir, ['branch', '-M', branch])
    
    try:
        await git_utils.push(work_dir, branch, set_upstream=True)
        console.print(f"[green]✓ Successfully pushed project to GitHub![/green]")
        return True
    except Exception:
        console.print(f"[yellow]Initial push failed. Attempting to reconcile and re-push...[/yellow]")
        try:
            await git_utils._run_git_command(work_dir, ['pull', 'origin', branch, '--allow-unrelated-histories', '--no-edit'])
            await git_utils.push(work_dir, branch)
            console.print(f"[green]✓ Successfully reconciled and pushed project to GitHub![/green]")
            return True
        except Exception as final_e:
            console.print(f"[red]All push attempts failed: {final_e}[/red]")
            return False

TOOL_REGISTRY = {
    "create_project_workspace": {
        "function": create_project_workspace,
        "description": "Creates the main project directory. MUST be the first step for any new project plan.",
        "parameters": { "directory_name": "string" }
    },
    "run_shell_command": {
        "function": run_shell_command,
        "description": "Executes a shell command. Use for project setup, dependency installation, and running servers.",
        "parameters": { "command": "string", "cwd": "string (optional)", "can_fail": "boolean (optional)", "verbose": "boolean (optional)", "background": "boolean (optional)", "force_overwrite": "boolean (optional)" }
    },
    "generate_code_concurrently": {
        "function": generate_code_concurrently,
        "description": "Generates code for multiple files in parallel. The most efficient way to build a project.",
        "parameters": { "files": "list[dict] (Each dict needs 'filename' and 'prompt')" }
    },
    "setup_git_and_push": {
        "function": setup_git_and_push,
        "description": "The primary tool for finalizing a project. It handles staging ALL files, committing, creating the GitHub repo, and pushing the initial commit.",
        "parameters": {"commit_message": "string", "repo_name": "string", "branch": "string (optional, defaults to 'main')"}
    },
    "review_and_commit_changes": {
        "function": review_and_commit_changes,
        "description": "A powerful tool to stage all files, show a summary of changes, and commit them with a message. Use this for managing changes within an existing repository.",
        "parameters": {"commit_message": "string"}
    },
    "web_search": {
        "function": web_search, 
        "description": "Performs a Google search to find information, documentation, or library versions.", "parameters": {"query": "string"}
    },
    "fetch_web_content": {
        "function": fetch_web_content, 
        "description": "Reads the text content of a URL. Use after `web_search` to 'read' a link.", "parameters": {"url": "string"}
    },
}