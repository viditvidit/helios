import asyncio
import re
from typing import List, Dict, Any
import questionary
from bs4 import BeautifulSoup
from pathlib import Path

from googlesearch import search as google_search
import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskProgressColumn
from rich.text import Text
from rich.syntax import Syntax
from rich.panel import Panel

from ...logic import file_logic
from ...services.ai_service import AIService
from ...services.github_service import GitHubService
from ...models.request import CodeRequest
from ...utils.git_utils import GitUtils
from ...utils.parsing_utils import extract_code_blocks

console = Console()

async def create_project_workspace(session, directory_name: str) -> bool:
    """Creates the main project directory. This should be the first step for any new project."""
    work_dir = session.config.work_dir / directory_name
    if work_dir.exists():
        console.print(f"[yellow]Workspace directory '{directory_name}' already exists. Using it.[/yellow]")
    else:
        work_dir.mkdir(parents=True)
        console.print(f"[green]✓ Created project workspace: {directory_name}[/green]")
    # Set the new working directory for the executor's context
    session.work_dir = work_dir
    return True

async def review_and_commit_changes(session, commit_message: str, show_diff: bool = True) -> bool:
    """
    A non-interactive tool for the agent to review and commit changes.
    It stages all unstaged files, displays the diff, and commits with a given message.
    """
    git_utils = GitUtils()
    repo_path = session.work_dir # Use the session's active work_dir
    
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

async def _get_ai_corrected_command(session, original_command: str, stderr: str) -> str:
    """Internal helper to ask the AI for a corrected shell command."""
    prompt = (
        "You are a shell command debugging expert. The following command failed. "
        "Based on the error message, provide the corrected command. "
        "ONLY respond with the corrected command string and nothing else.\n\n"
        f"Original Command: `{original_command}`\n"
        f"Error Output (stderr):\n```\n{stderr}\n```\n\n"
        "Corrected command:"
    )
    request = CodeRequest(prompt=prompt)
    correction = ""
    async with AIService(session.config) as ai_service:
        async for chunk in ai_service.stream_generate(request):
            correction += chunk
    
    # Clean up markdown fences and whitespace
    return correction.strip().replace('`', '')

async def run_shell_command(session, command: str, cwd: str, can_fail: bool = False, verbose: bool = False) -> bool:
    """Executes a shell command with real-time output streaming."""
    run_dir = Path(cwd)
    
    # Print command info once and don't repeat it
    console.print(f"Running command: [bold magenta]{command}[/bold magenta] in [dim]{run_dir}[/dim]")

    try:
        start_time = asyncio.get_event_loop().time()
        
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout for unified output
            cwd=run_dir
        )
        
        # Create a live panel for streaming output
        output_lines = []
        max_lines = 15  # Show last 15 lines
        
        # Status tracking
        elapsed = 0
        
        async def read_output():
            nonlocal output_lines
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                
                decoded_line = line.decode().strip()
                if decoded_line:  # Only add non-empty lines
                    output_lines.append(decoded_line)
                    # Keep only the last max_lines
                    if len(output_lines) > max_lines:
                        output_lines = output_lines[-max_lines:]
        
        # Use a simple status spinner instead of complex panel updates
        with console.status(f"[cyan]Executing...[/cyan]") as status:
            # Start reading output
            read_task = asyncio.create_task(read_output())
            
            # Update status with elapsed time
            while process.returncode is None:
                await asyncio.sleep(1)
                elapsed += 1
                mins, secs = divmod(elapsed, 60)
                time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                status.update(f"[cyan]Executing... ({time_str})[/cyan]")
        
        # Ensure we've read all output
        await read_task
        
        # Calculate final execution time
        end_time = asyncio.get_event_loop().time()
        execution_time = end_time - start_time
        mins, secs = divmod(int(execution_time), 60)
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
        
        if process.returncode == 0:
            console.print(f"[green]✓ Shell command finished successfully in {time_str}[/green]")
            
            # Show final output summary
            if output_lines:
                last_lines = output_lines[-3:]
                if last_lines:
                    console.print(f"[dim]Last output: {' | '.join(last_lines)}[/dim]")
            
            return True
        
        # Handle command failure
        console.print(f"[bold red]Shell command failed after {time_str}. Return code: {process.returncode}[/bold red]")
        
        if output_lines:
            error_output = "\n".join(output_lines[-10:])
            console.print(Panel(
                f"[red]{error_output}[/red]",
                title="Error Output",
                border_style="red"
            ))

        if can_fail:
            console.print("[yellow]Continuing execution as this step was allowed to fail.[/yellow]")
            return True

        # Try AI correction
        error_text = "\n".join(output_lines[-5:]) if output_lines else "Command failed with no output"
        
        with console.status("[cyan]Asking AI for a fix...[/cyan]"):
            corrected_command = await _get_ai_corrected_command(session, command, error_text)

        if not corrected_command or corrected_command.lower() == command.lower():
            console.print("[red]AI could not suggest a correction. Aborting step.[/red]")
            return False

        console.print(f"Helios suggests this correction: [bold yellow]{corrected_command}[/bold yellow]")
        if await questionary.confirm("Execute the corrected command?", default=True).ask_async():
            return await run_shell_command(session, corrected_command, cwd, can_fail, verbose)
        else:
            console.print("[yellow]User declined correction. Aborting step.[/yellow]")
            return False

    except Exception as e:
        console.print(f"[red]✗ An unexpected error occurred while running shell command: {e}[/red]")
        return False

async def generate_code_concurrently(session, files: List[Dict[str, Any]], cwd: str) -> bool:
    """Generates code for multiple files concurrently and saves them to the specified directory."""
    base_dir = Path(cwd)
    console.print(f"[dim]Generating code in directory: {base_dir}[/dim]")
    
    progress = Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console, transient=True)

    async def generate_and_save(file_path_str: str, file_prompt: str, p_task_id: Any):
        full_path = base_dir / file_path_str
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        generation_prompt = (
            "You are a code-writing AI. Your only task is to generate the raw code for a single file based on the user's request. "
            "Your output must be ONLY the code itself.\n\n"
            "**CRITICAL INSTRUCTIONS:**\n"
            "- DO NOT include any explanations, introductory text, or summaries.\n"
            "- DO NOT wrap the code in markdown code blocks like ```python.\n"
            f"**File to create:** `{file_path_str}`\n"
            f"**Code to generate based on this prompt:** {file_prompt}"
        )
        request = CodeRequest(prompt=generation_prompt)
        
        try:
            generated_code = ""
            async with AIService(session.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    generated_code += chunk
            
            # The AI might still sometimes add fences, so we strip them just in case.
            code_blocks = extract_code_blocks(f"```{full_path.suffix.strip('.')}\n{generated_code}\n```")
            final_code = code_blocks[0]['code'] if code_blocks else generated_code

            await file_logic.save_code(session, str(full_path), final_code)
            progress.update(p_task_id, description=f"[green]✓ Wrote {file_path_str}[/green]", completed=1)
            return True
        except Exception as e:
            progress.update(p_task_id, description=f"[red]✗ FAILED {file_path_str}[/red]", completed=1)
            console.print(f"[red]Error generating {file_path_str}: {e}[/red]")
            return False

    with progress:
        tasks = []
        for f in files:
            filename, prompt = f.get('filename'), f.get('prompt')
            if not filename or not prompt: continue
            
            progress_task_id = progress.add_task(f"[dim]Writing {filename}...[/dim]", total=1)
            tasks.append(generate_and_save(filename, prompt, progress_task_id))

        results = await asyncio.gather(*tasks)
    
    return all(results)


async def web_search(query: str, num_results: int = 5) -> str:
    """Performs a web search using Google and returns the top results."""
    console.print(f"Searching web for: [italic]{query}[/italic]...")
    try:
        with console.status(f"[cyan]Searching Google...[/cyan]"):
            search_results = await asyncio.to_thread(google_search, query, num_results=num_results, stop=num_results, pause=1)
        return "\n".join([f"{i+1}. {result}" for i, result in enumerate(search_results)]) or "No results found."
    except Exception as e:
        return f"Error during web search: {e}"

async def fetch_web_content(url: str) -> str:
    """Fetches the textual content of a given URL, stripping HTML."""
    console.print(f"Fetching content from: [italic]{url}[/italic]...")
    try:
        with console.status(f"[cyan]Fetching web content...[/cyan]"):
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
        with console.status(f"[cyan]Checking/creating GitHub repository...[/cyan]"):
            service = GitHubService(session.config)
            repo = await service.get_or_create_repo(repo_name, is_private, description)
        if repo:
            session.repo_clone_url = repo.clone_url
            return True
        return False
    except Exception as e:
        console.print(f"[red]Error ensuring GitHub repo exists: {e}[/red]")
        return False

async def setup_git_and_push(session, commit_message: str, repo_name: str, branch: str = "main") -> bool:
    """A high-level tool that performs the entire initial Git setup and push sequence."""
    console.print(f"Starting full Git and GitHub setup for [italic]{repo_name}[/italic]...")
    git_utils = GitUtils()
    work_dir = session.work_dir

    with console.status(f"[cyan]Initializing Git repository...[/cyan]"):
        if not await git_utils.is_git_repo(work_dir):
            await git_utils.init_repo(work_dir)
        
        await git_utils.add_files(work_dir, ['.'])
        
        status = await git_utils.get_status(work_dir)
    
    if "nothing to commit" in status:
        console.print("[yellow]✓ No changes to commit.[/yellow]")
    else:
        with console.status(f"[cyan]Committing changes...[/cyan]"):
            await git_utils.commit(work_dir, commit_message)
        console.print("[green]✓ Files committed.[/green]")

    if not await github_create_repo_non_interactive(session, repo_name):
        return False

    clone_url = getattr(session, 'repo_clone_url', None)
    if not clone_url: return False

    with console.status(f"[cyan]Setting up remote and pushing...[/cyan]"):
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
        "description": "Creates the main project directory. MUST be the first step for any new project plan. This sets the working directory for all subsequent steps.",
        "parameters": { "directory_name": "string" }
    },
    "run_shell_command": {
        "function": run_shell_command,
        "description": "Executes a shell command. Use for project setup, dependency installation, running build tools, etc. It can self-correct on failure. ALWAYS use the `cwd` argument to specify which directory to run in.",
        "parameters": { "command": "string", "cwd": "string", "can_fail": "boolean (optional, default False)", "verbose": "boolean (optional, default False)" }
    },
    "generate_code_concurrently": {
        "function": generate_code_concurrently,
        "description": "Generates code for multiple files in parallel and saves them. The most efficient way to write code for a project. The `cwd` argument is the base path for where to save the files.",
        "parameters": { "files": "list[dict] (Each dict needs 'filename' and 'prompt')", "cwd": "string"}
    },
    "setup_git_and_push": {
        "function": setup_git_and_push,
        "description": "A finalization tool. It handles staging ALL files, committing, creating the GitHub repo if needed, and pushing the initial commit.",
        "parameters": {"commit_message": "string", "repo_name": "string", "branch": "string (optional, defaults to 'main')"}
    },
    "review_and_commit_changes": {
        "function": review_and_commit_changes,
        "description": "A powerful tool to stage all files, show a summary of changes, and commit them with a message. Use for managing changes within an existing repository.",
        "parameters": {"commit_message": "string"}
    },
    "web_search": {
        "function": web_search, 
        "description": "Performs a Google search to find information, documentation, or best practices before generating code.", "parameters": {"query": "string"}
    },
    "fetch_web_content": {
        "function": fetch_web_content, 
        "description": "Reads the text content of a URL. Use after `web_search` to 'read' a promising link.", "parameters": {"url": "string"}
    },
}