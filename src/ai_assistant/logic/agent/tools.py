# src/ai_assistant/logic/agent/tools.py

import asyncio
import os
import json
import re
import shutil
from typing import List, Dict, Any

import requests
from bs4 import BeautifulSoup
from googlesearch import search as google_search
import wikipediaapi
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
            console.print(Panel(Syntax(diff_content, "diff", theme="monokai", word_wrap=True), title=f"Changes for {filename}", border_style="yellow"))
    else:
        summary_lines = [Text(f"  • {f}: ").append(f"+{d.count(chr(10)+'+')} ", style="green").append(f"-{d.count(chr(10)+'-')}", style="red") for f, d in per_file_diffs.items()]
        console.print(Panel(Text("\n").join(summary_lines), title="Staged Changes Summary", border_style="cyan"))

    console.print(f"Committing with message: [italic]'{commit_message}'[/italic]")
    await git_utils.commit(repo_path, commit_message)
    console.print("[green]✓ Changes committed.[/green]")
    return True

async def generate_code_for_file(session, filename: str, prompt: str) -> bool:
    """Generates code for a single file. Does NOT display its own spinner."""
    generation_prompt = (
        "You are a code-writing AI. Your only task is to generate the raw code for a single file based on the user's request. "
        "Your output must be ONLY the code itself.\n\n"
        "**CRITICAL INSTRUCTIONS:**\n"
        "- DO NOT include any explanations, introductory text, or summaries.\n"
        "- DO NOT wrap the code in markdown code blocks like ```python.\n"
        "- DO NOT include the command to run the file.\n\n"
        f"**File to create:** `{filename}`\n"
        f"**Code to generate based on this prompt:** {prompt}"
    )
    request = CodeRequest(prompt=generation_prompt)
    
    generated_code = ""
    async with AIService(session.config) as ai_service:
        async for chunk in ai_service.stream_generate(request):
            generated_code += chunk
    
    if not generated_code:
        return False
    
    generated_code = generated_code.strip()
    if generated_code.startswith("```"):
        lines = generated_code.split('\n')
        generated_code = '\n'.join(lines[1:-1]) if len(lines) > 2 and lines[-1].strip() == "```" else generated_code

    session.last_ai_response_content = f"```{filename}\n{generated_code}\n```"
    return await file_logic.save_code(session, filename)

async def generate_code_concurrently(session, files: List[Dict[str, Any]]) -> bool:
    """Generates code for multiple files concurrently using a robust runner pattern."""
    progress = Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), transient=True
    )

    async def _runner(base_coro, progress_id, filename: str) -> bool:
        try:
            success = await base_coro
            progress.update(progress_id, completed=1, description=f"[green]✓ Wrote {filename}" if success else f"[red]✗ FAILED {filename}")
            return success
        except Exception as e:
            progress.update(progress_id, completed=1, description=f"[red]✗ CRASHED {filename}")
            console.print(f"[red]Error generating {filename}: {e}[/red]")
            return False

    with progress:
        runner_tasks = []
        for f in files:
            filename, prompt = f['filename'], f['prompt']
            base_task_coro = generate_code_for_file(session, filename, prompt)
            progress_id = progress.add_task(f"Writing {filename}...", total=1)
            runner_task = _runner(base_task_coro, progress_id, filename)
            runner_tasks.append(runner_task)

        results = await asyncio.gather(*runner_tasks)

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
    work_dir = session.config.work_dir
    run_dir = work_dir / (cwd or '.')

    if force_overwrite:
        scaffold_match = re.search(r'(create-react-app|vite|next|vue create)\s+([^\s]+)', command)
        target_dir_name = None
        if scaffold_match:
            target_dir_name = scaffold_match.group(2)
        elif command.strip().startswith('mkdir'):
             target_dir_name = command.strip().split(maxsplit=1)[1]

        if target_dir_name:
            target_path = run_dir / target_dir_name
            if target_path.exists():
                console.print(f"[yellow]Force overwrite enabled. Removing existing directory: {target_path}[/yellow]")
                shutil.rmtree(target_path)
    
    if cwd and not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"Running command: [bold magenta]{command}[/bold magenta] in [dim]{run_dir}[/dim]")

    server_keywords = ['uvicorn', 'npm start', 'npm run dev', 'yarn start', 'yarn dev', 'flask run', 'serve', 'next dev', 'vite']
    if not background and any(keyword in command.lower() for keyword in server_keywords):
        background = True
        console.print(f"[yellow]Detected server command. Running in background mode.[/yellow]")

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=run_dir
        )

        if background:
            session.background_processes = getattr(session, 'background_processes', [])
            session.background_processes.append(process)
            console.print(f"[green]✓ Command started in background (PID: {process.pid}).[/green]")
            await asyncio.sleep(3)
            return True

        if not verbose:
            with console.status(f"[dim]Executing...[/dim]", spinner="dots"):
                stdout, stderr = await process.communicate()
        else:
            stdout, stderr = await process.communicate()

        if process.returncode == 0:
            console.print(f"[green]✓ Shell command finished successfully.[/green]")
            return True
        
        stdout_text, stderr_text = stdout.decode().strip(), stderr.decode().strip()
        
        if 'already exists' in stderr_text.lower() or 'already up to date' in stderr_text.lower():
            console.print(f"[yellow]✓ Resource already exists or is up to date. Continuing.[/yellow]")
            return True

        console.print("[bold red]Shell command failed. Output:[/bold red]")
        if stdout_text: console.print(Text("[stdout] ", style="dim") + Text(stdout_text))
        if stderr_text: console.print(Text("[stderr] ", style="dim") + Text(stderr_text))
            
        if can_fail:
            console.print(f"[yellow]! Command failed but was marked as non-critical. Continuing.[/yellow]")
            return True
        
        return False
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