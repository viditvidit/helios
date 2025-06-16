import asyncio
import os
import json
try:
    import json5  # For lenient JSON parsing (allows trailing commas, comments, etc.)
except ImportError:
    json5 = None
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskProgressColumn
from rich.text import Text
from typing import List, Dict, Any
import re
import shutil

from . import file_logic, code_logic
from ..services.ai_service import AIService
from ..logic import git_logic, github_logic, code_logic, file_logic 
from ..services.github_service import GitHubService
from ..utils.git_utils import GitUtils
from ..models.request import CodeRequest

# New imports for hybrid tools
import requests
from bs4 import BeautifulSoup
from googlesearch import search as google_search
import wikipediaapi

console = Console()

async def generate_code_for_file(session, filename: str, prompt: str) -> bool:
    """
    Generates code for a single file. Does NOT display its own spinner.
    """
    generation_prompt = (
        "You are a code-writing AI. Your only task is to generate the raw code for a single file based on the user's request. "
        "Your output must be ONLY the code itself.\n\n"
        "**CRITICAL INSTRUCTIONS:**\n"
        "- DO NOT include any explanations, introductory text, or summaries.\n"
        "- DO NOT wrap the code in markdown code blocks like ```python.\n"
        "- DO NOT include the command to run the file.\n"
        "- For JSON files, ensure the output is VALID JSON with proper syntax.\n"
        "- For package.json files, include all required fields and valid structure.\n\n"
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
    
    # Enhanced cleanup logic
    generated_code = generated_code.strip()
    
    # Remove markdown code blocks if present
    if generated_code.startswith("```"):
        lines = generated_code.split('\n')
        if len(lines) > 1:
            # Remove first line (```language)
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            # Remove last line (```)
            lines = lines[:-1]
        generated_code = '\n'.join(lines)
    
    # Validate JSON files before saving
    if filename.endswith('.json'):
        try:
            json.loads(generated_code)
            console.print(f"[green]✓ Generated valid JSON for {filename}[/green]")
        except json.JSONDecodeError as e:
            console.print(f"[yellow]⚠ Generated invalid JSON for {filename}, attempting to fix...[/yellow]")
            # Try to fix common JSON issues
            generated_code = fix_json_content(generated_code)
            try:
                json.loads(generated_code)
                console.print(f"[green]✓ Fixed JSON for {filename}[/green]")
            except json.JSONDecodeError:
                console.print(f"[red]✗ Could not fix JSON for {filename}[/red]")
                return False
    
    session.last_ai_response_content = f"```{filename}\n{generated_code}\n```"
    return await file_logic.save_code(session, filename)

def fix_json_content(content: str) -> str:
    """
    Attempts to fix common JSON formatting issues.
    """
    # Remove any leading/trailing whitespace
    content = content.strip()
    
    # Remove trailing commas (common AI mistake)
    content = re.sub(r',\s*}', '}', content)
    content = re.sub(r',\s*]', ']', content)
    
    # Fix common quote issues
    content = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', content)
    
    # Ensure proper string quoting
    content = re.sub(r':\s*([^"\[\{][^,\}\]]*[^,\}\]\s])\s*([,\}\]])', r': "\1"\2', content)
    
    return content

async def generate_code_concurrently(session, files: List[Dict[str, Any]]) -> bool:
    """
    Generates code for multiple files concurrently using a robust runner pattern.
    """
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=True
    )

    # Define a local "runner" coroutine that wraps the main task
    # and handles its own progress bar updates.
    async def _runner(base_coro, progress_id, filename: str) -> bool:
        try:
            # Await the actual code generation
            success = await base_coro
            if success:
                progress.update(progress_id, completed=1, description=f"[green]✓ Wrote {filename}")
                return True
            else:
                progress.update(progress_id, completed=1, description=f"[red]✗ FAILED {filename}")
                return False
        except Exception as e:
            progress.update(progress_id, completed=1, description=f"[red]✗ CRASHED {filename}")
            console.print(f"[red]Error generating {filename}: {e}[/red]")
            return False

    with progress:
        # Create a list of runner tasks to execute
        runner_tasks = []
        for f in files:
            filename = f['filename']
            prompt = f['prompt']
            
            # Create the base task (the actual work)
            base_task_coro = generate_code_for_file(session, filename, prompt)
            
            # Create the progress bar for this task
            progress_id = progress.add_task(f"Writing {filename}...", total=1)
            # Create the runner task that will manage the base task and its progress bar
            runner_task = _runner(base_task_coro, progress_id, filename)
            runner_tasks.append(runner_task)

        # Run all the runner tasks concurrently and wait for them all to finish
        results = await asyncio.gather(*runner_tasks)

    # The overall tool succeeds only if all individual tasks succeeded
    return all(results)

# --- NEW HYBRID TOOLS ---

async def web_search(query: str, num_results: int = 5) -> str:
    """Performs a web search using Google and returns the top results."""
    console.print(f"Searching web for: [italic]{query}[/italic]...")
    try:
        # googlesearch is synchronous, so we run it in a thread to not block asyncio
        search_results = await asyncio.to_thread(google_search, query, num_results=num_results, stop=num_results, pause=1)
        formatted_results = [f"{i+1}. {result}" for i, result in enumerate(search_results)]
        return "\n".join(formatted_results) if formatted_results else "No results found."
    except Exception as e:
        return f"Error during web search: {e}"

async def fetch_web_content(url: str) -> str:
    """Fetches the textual content of a given URL, stripping HTML."""
    console.print(f"Fetching content from: [italic]{url}[/italic]...")
    try:
        # requests is synchronous
        response = await asyncio.to_thread(requests.get, url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        # Extract text and clean up whitespace
        text = ' '.join(soup.get_text().split())
        return text[:8000] # Return a reasonable chunk of text
    except Exception as e:
        return f"Error fetching URL content: {e}"

async def wikipedia_summary(topic: str) -> str:
    """Gets a summary of a topic from Wikipedia."""
    console.print(f"Searching Wikipedia for: [italic]{topic}[/italic]...")
    try:
        wiki_api = wikipediaapi.Wikipedia('HeliosAgent/1.0', 'en')
        page = await asyncio.to_thread(wiki_api.page, topic)
        if page.exists():
            return f"Title: {page.title}\nSummary: {page.summary[:2000]}..."
        else:
            return f"Topic '{topic}' not found on Wikipedia."
    except Exception as e:
        return f"Error fetching from Wikipedia: {e}"

async def list_files_recursive(session, path: str = '.') -> str:
    """Lists all files and directories recursively from a given path."""
    start_path = session.config.work_dir / path
    console.print(f"Listing files in: [italic]{start_path}[/italic]...")
    try:
        tree = []
        for root, dirs, files in os.walk(start_path):
            level = root.replace(str(start_path), '').count(os.sep)
            indent = ' ' * 4 * level
            tree.append(f"{indent}{os.path.basename(root)}/")
            sub_indent = ' ' * 4 * (level + 1)
            for f in files:
                tree.append(f"{sub_indent}{f}")
        return "\n".join(tree)
    except Exception as e:
        return f"Error listing files: {e}"

async def validate_and_fix_json_files(session, directory: str = '.', project_only: bool = False) -> bool:
    """
    Validates and attempts to fix JSON files in the specified directory.
    If project_only is True, excludes node_modules and other common dependency directories.
    """
    work_dir = session.config.work_dir / directory
    console.print(f"Validating JSON files in: [italic]{work_dir}[/italic]...")
    
    if project_only:
        # Only check project-level JSON files, exclude dependencies
        json_files = []
        exclude_dirs = {'node_modules', '.git', 'dist', 'build', '.next', 'coverage', '.nyc_output', 'vendor', '__pycache__'}
        
        for json_file in work_dir.rglob("*.json"):
            # Check if any part of the path contains excluded directories
            if not any(part in exclude_dirs for part in json_file.parts):
                json_files.append(json_file)
    else:
        json_files = list(work_dir.glob("**/*.json"))
    
    if not json_files:
        console.print("[yellow]No JSON files found.[/yellow]")
        return True
    
    console.print(f"[dim]Found {len(json_files)} JSON files to validate...[/dim]")
    
    all_valid = True
    for json_file in json_files:
        try:
            with json_file.open("r", encoding="utf-8") as f:
                content = f.read()
            
            # Try to parse as JSON
            try:
                data = json.loads(content)
                # Only print validation success for project files, not dependencies
                if project_only or len(json_files) < 20:  # Only show details for small sets
                    console.print(f"[green]✓ {json_file.name} is valid JSON[/green]")
            except json.JSONDecodeError as e:
                console.print(f"[yellow]⚠ {json_file.name} has JSON errors, attempting to fix...[/yellow]")
                
                # Attempt to fix the JSON
                fixed_content = fix_json_content(content)
                
                try:
                    data = json.loads(fixed_content)
                    # Write the fixed content back
                    with json_file.open("w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    console.print(f"[green]✓ Fixed and saved {json_file.name}[/green]")
                except json.JSONDecodeError:
                    console.print(f"[red]✗ Could not fix {json_file.name}: {e}[/red]")
                    all_valid = False
                    
        except Exception as e:
            console.print(f"[red]✗ Error processing {json_file.name}: {e}[/red]")
            all_valid = False
    
    return all_valid

# --- FIXED GIT PUSH TOOL ---
async def git_initial_push(session, remote_name: str = "origin", branch: str = "main") -> bool:
    """
    Adds a remote and pushes the initial commit to GitHub.
    """
    clone_url = getattr(session, 'repo_clone_url', None)
    if not clone_url:
        console.print("[red]Could not find repository clone URL. Did github_create_repo run first?[/red]")
        return False

    # --- THE FIX: Use the actual username from the config ---
    username = session.config.github.username
    if not username:
        console.print("[red]Could not determine GitHub username. Please ensure you are authenticated.[/red]")
        return False
    
    # Replace the placeholder with the actual username
    clone_url = clone_url.replace("YOUR_USERNAME", username)
        
    git_utils = git_logic.GitUtils()
    # This tool should always run from the root of the project
    work_dir = session.config.work_dir
    try:
        await git_utils._run_git_command(work_dir, ['remote', 'add', remote_name, clone_url])
    except Exception as e:
        if "remote origin already exists" in str(e).lower():
            console.print("[yellow]Remote 'origin' already exists. Setting URL...[/yellow]")
            await git_utils._run_git_command(work_dir, ['remote', 'set-url', remote_name, clone_url])
        else:
            console.print(f"[red]Failed to add remote: {e}[/red]")
            return False
            
    try:
        await git_utils.push(work_dir, branch, set_upstream=True)
        console.print(f"[green]✓ Pushed initial commit to GitHub remote '{remote_name}'.[/green]")
        return True
    except Exception as e:
        console.print(f"[red]Failed to push to GitHub: {e}[/red]")
        return False

async def github_create_repo_non_interactive(session, repo_name: str, description: str = "", is_private: bool = False) -> bool:
    """
    Ensures a GitHub repository exists. Creates it if it's missing, otherwise uses the existing one.
    This is a non-interactive version for the agent to use.
    """
    console.print(f"Ensuring GitHub repo exists: [italic]{repo_name}[/italic]...")
    try:
        service = GitHubService(session.config)
        # We need a new method in GitHubService to handle this logic
        repo = await service.get_or_create_repo(repo_name, is_private, description)
        
        if repo:
            session.repo_clone_url = repo.clone_url
            return True
        else:
            return False
    except Exception as e:
        console.print(f"[red]Error ensuring GitHub repo exists: {e}[/red]")
        return False

async def run_shell_command(session, command: str, cwd: str = None, can_fail: bool = False, verbose: bool = False, force_overwrite: bool = False, background: bool = False, allow_dependency_conflicts: bool = False, pre_validate_json: bool = True) -> bool:
    work_dir = session.config.work_dir
    run_dir = work_dir / cwd if cwd else work_dir

    if cwd and not run_dir.exists():
        console.print(f"[yellow]Note: Working directory '{run_dir.relative_to(work_dir)}' does not exist. Creating it now.[/yellow]")
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            console.print(f"[red]✗ Failed to create working directory '{run_dir}': {e}[/red]")
            return False

    # FIXED: Only validate JSON for package management commands, and only project files
    should_validate_json = (pre_validate_json and 
                           any(cmd in command.lower() for cmd in ['npm install', 'npm i ', 'yarn install', 'yarn add']))
    
    if should_validate_json:
        console.print("[dim]Pre-validating project JSON files before package installation...[/dim]")
        await validate_and_fix_json_files(session, cwd or '.', project_only=True)

    # REMOVED: Universal JSON auto-formatting - this was causing the repeated validation
    
    effective_command = command
    if allow_dependency_conflicts:
        cmd_lower = command.strip().lower()
        if cmd_lower.startswith("npm install") or cmd_lower.startswith("npm i "):
            console.print("[yellow]Dependency conflicts allowed. Appending '--legacy-peer-deps' for npm.[/yellow]")
            effective_command += " --legacy-peer-deps"
        elif cmd_lower.startswith("yarn install") or cmd_lower.startswith("yarn add"):
            console.print("[yellow]Dependency conflicts allowed. Appending '--legacy-peer-deps' for yarn.[/yellow]")
            effective_command += " --legacy-peer-deps"

    console.print(f"Running command: [bold magenta]{effective_command}[/bold magenta] in [dim]{run_dir}[/dim]")

    server_keywords = ['uvicorn', 'npm start', 'yarn start', 'flask run', 'python -m http.server', 'serve', '--watch', '--reload', 'next dev', 'vite', 'webpack-dev-server']
    if not background and any(keyword in command.lower() for keyword in server_keywords):
        console.print(f"[yellow]Detected server command. Running in background mode.[/yellow]")
        background = True

    if force_overwrite and "create-react-app" in command:
        parts = command.split()
        if len(parts) >= 3:
            target_dir = parts[-1]
            target_path = run_dir / target_dir
            if target_path.exists():
                console.print(f"[yellow]Force overwrite enabled. Removing existing directory: {target_path}[/yellow]")
                shutil.rmtree(target_path)

    try:
        if background:
            process = await asyncio.create_subprocess_shell(
                effective_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=run_dir
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=3.0)
                stdout, stderr = await process.communicate()
                if process.returncode != 0:
                    console.print("[bold red]Server command failed to start. Output:[/bold red]")
                    if stdout:
                        console.print(Text("[stdout] ", style="dim") + Text(stdout.decode().strip()))
                    if stderr:
                        console.print(Text("[stderr] ", style="dim") + Text(stderr.decode().strip()))
                    return False
                else:
                    console.print(f"[green]✓ Background command completed successfully.[/green]")
                    return True
            except asyncio.TimeoutError:
                console.print(f"[green]✓ Server started successfully and running in background (PID: {process.pid}).[/green]")
                session.background_processes = getattr(session, 'background_processes', [])
                session.background_processes.append(process)
                return True
        else:
            process = await asyncio.create_subprocess_shell(
                effective_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=run_dir
            )
            if not verbose:
                with console.status(f"[dim]Executing...[/dim]", spinner="dots"):
                    stdout, stderr = await process.communicate()
            else:
                stdout, stderr = await process.communicate()

            if process.returncode == 0:
                console.print(f"[green]✓ Shell command finished successfully.[/green]")
                return True
            else:
                stdout_text = stdout.decode().strip() if stdout else ""
                stderr_text = stderr.decode().strip() if stderr else ""
                
                # Enhanced error handling for common cases
                if command.strip().startswith('mkdir') and 'File exists' in stderr_text:
                    console.print(f"[yellow]✓ Directory already exists. Continuing.[/yellow]")
                    return True
                    
                if "create-react-app" in command and "contains files that could conflict" in stdout_text:
                    console.print(f"[yellow]✓ Directory contains conflicting files, but this is expected in development. Continuing.[/yellow]")
                    return True
                    
                if 'command not found' in stderr_text or ': command not found' in stderr_text:
                    missing_cmd = command.split()[0]
                    console.print(f"[yellow]⚠ Command '{missing_cmd}' not found.[/yellow]")
                    console.print(f"[dim]Consider installing it first, then retry this step.[/dim]")
                    console.print(f"[yellow]✓ Treating missing command as non-critical. Continuing.[/yellow]")
                    return True
                    
                if ('already exists' in stderr_text.lower() or 
                    'already up to date' in stderr_text.lower() or
                    'already up-to-date' in stdout_text.lower()):
                    console.print(f"[yellow]✓ Resource already exists or is up to date. Continuing.[/yellow]")
                    return True
                
                # FIXED: Only attempt JSON fix for actual JSON errors, and only if we haven't already validated
                if (not should_validate_json and 
                    ('ejsonparse' in stderr_text.lower() or 'json.parse' in stderr_text.lower())):
                    console.print(f"[red]✗ JSON parsing error detected. Attempting to fix project JSON files...[/red]")
                    if await validate_and_fix_json_files(session, cwd or '.', project_only=True):
                        console.print(f"[yellow]✓ JSON files fixed. Retrying command...[/yellow]")
                        # Retry the command once after fixing JSON
                        return await run_shell_command(session, command, cwd, can_fail, verbose, force_overwrite, background, allow_dependency_conflicts, pre_validate_json=False)
                    else:
                        console.print(f"[red]✗ Could not fix JSON files.[/red]")
                
                console.print("[bold red]Shell command failed. Output:[/bold red]")
                if stdout_text:
                    console.print(Text("[stdout] ", style="dim") + Text(stdout_text))
                if stderr_text:
                    console.print(Text("[stderr] ", style="dim") + Text(stderr_text))
                    
                if can_fail:
                    console.print(f"[yellow]! Command failed but was marked as non-critical. Continuing.[/yellow]")
                    return True
                else:
                    console.print(f"[red]✗ Aborting plan due to failed command.[/red]")
                    return False
    except Exception as e:
        console.print(f"[red]✗ An unexpected error occurred while running shell command: {e}[/red]")
        return False

async def setup_git_and_push(session, commit_message: str, repo_name: str, branch: str = "main") -> bool:
    """
    A high-level tool that performs the entire initial Git setup and push sequence.
    This tool is now fully idempotent with better conflict resolution.
    """
    console.print(f"Starting full Git and GitHub setup for [italic]{repo_name}[/italic]...")
    git_utils = git_logic.GitUtils()
    work_dir = session.config.work_dir

    # FIXED: Pre-validate only project JSON files before git operations
    console.print("[dim]Pre-validating project JSON files before Git operations...[/dim]")
    await validate_and_fix_json_files(session, '.', project_only=True)

    # 0. Initialize git repo if it doesn't exist
    if not await git_utils.is_git_repo(work_dir):
        console.print("[dim]Initializing git repository...[/dim]")
        await git_utils.init_repo(work_dir)
    
    # 1. Stage all files
    console.print("[dim]Staging all files...[/dim]")
    try:
        await git_utils.add_files(work_dir, ['.'])
        console.print("[green]✓ Files staged.[/green]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not stage files: {e}. Continuing...[/yellow]")

    # 2. Commit the files (if there are changes)
    try:
        status = await git_utils.get_status(work_dir)
        if "nothing to commit" in status or not status.strip():
            console.print("[yellow]✓ No changes to commit. Repository is up to date.[/yellow]")
        else:
            console.print(f"[dim]Committing with message: '{commit_message}'...[/dim]")
            commit_made = await git_utils.commit(work_dir, commit_message)
            if commit_made:
                console.print("[green]✓ Files committed.[/green]")
            else:
                 console.print("[yellow]✓ Nothing new to commit.[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not check git status: {e}. Attempting commit anyway...[/yellow]")
        try:
            await git_utils.commit(work_dir, commit_message)
        except Exception as commit_error:
            if "nothing to commit" not in str(commit_error).lower():
                 console.print(f"[yellow]Commit failed: {commit_error}. Continuing...[/yellow]")

    # 3. Ensure the GitHub repo exists AND get its URL
    console.print(f"[dim]Ensuring GitHub repository '{repo_name}' exists...[/dim]")
    if not await github_create_repo_non_interactive(session, repo_name):
        console.print("[red]Failed to create or access GitHub repository.[/red]")
        return False

    clone_url = getattr(session, 'repo_clone_url', None)
    if not clone_url:
        console.print("[red]Critical error: Repo was handled but clone URL was not found.[/red]")
        return False

    # 4. Add or Update the remote to point to the CORRECT repository URL FIRST
    try:
        console.print("[dim]Setting remote 'origin'...[/dim]")
        await git_utils._run_git_command(work_dir, ['remote', 'add', 'origin', clone_url])
        console.print("[green]✓ Remote 'origin' added.[/green]")
    except Exception as e:
        if "remote origin already exists" in str(e).lower():
            console.print("[yellow]Remote 'origin' already exists. Setting URL instead...[/yellow]")
            try:
                await git_utils._run_git_command(work_dir, ['remote', 'set-url', 'origin', clone_url])
                console.print("[green]✓ Remote URL updated.[/green]")
            except Exception as url_error:
                console.print(f"[yellow]Warning: Could not update remote URL: {url_error}[/yellow]")
        else:
            console.print(f"[yellow]Warning: Could not set remote: {e}[/yellow]")

    # 5. Rename the local branch to the target branch name
    try:
        console.print(f"[dim]Ensuring local branch is '{branch}'...[/dim]")
        await git_utils._run_git_command(work_dir, ['branch', '-M', branch])
        console.print(f"[green]✓ Local branch is now '{branch}'.[/green]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not rename branch: {e}[/yellow]")

    # FIXED: Better handling of divergent branches and push conflicts
    # 6. Configure git to handle divergent branches with merge strategy
    try:
        await git_utils._run_git_command(work_dir, ['config', 'pull.rebase', 'false'])
        console.print("[dim]Configured git to use merge strategy for divergent branches.[/dim]")
    except Exception:
        pass  # Not critical if this fails
    
    # 7. Pull from remote to reconcile histories (e.g., the initial README)
    try:
        console.print(f"[dim]Pulling from origin to reconcile histories...[/dim]")
        await git_utils._run_git_command(work_dir, ['pull', 'origin', branch, '--allow-unrelated-histories', '--no-edit', '--strategy-option=ours'])
        console.print("[green]✓ Histories reconciled using merge strategy.[/green]")
    except Exception as e:
        if "couldn't find remote ref" in str(e).lower():
             console.print(f"[dim]Remote branch '{branch}' doesn't exist yet. Skipping pull.[/dim]")
        else:
             console.print(f"[yellow]Warning: Pull failed: {e}. Attempting force push...[/yellow]")
             # If pull fails due to conflicts, we'll try a force push instead
             try:
                 console.print(f"[dim]Force pushing branch '{branch}' to origin...[/dim]")
                 await git_utils._run_git_command(work_dir, ['push', '--force-with-lease', 'origin', branch])
                 console.print(f"[green]✓ Force pushed project to GitHub![/green]")
                 return True
             except Exception as force_push_error:
                 console.print(f"[red]Force push also failed: {force_push_error}[/red]")
                 return False

    # 8. Push the final, reconciled state to the remote
    try:
        console.print(f"[dim]Pushing branch '{branch}' to origin...[/dim]")
        await git_utils.push(work_dir, branch, set_upstream=True)
        console.print(f"[green]✓ Successfully pushed project to GitHub![/green]")
        return True
    except Exception as e:
        console.print(f"[yellow]Normal push failed: {e}. Attempting force push with lease...[/yellow]")
        try:
            await git_utils._run_git_command(work_dir, ['push', '--force-with-lease', '--set-upstream', 'origin', branch])
            console.print(f"[green]✓ Successfully force pushed project to GitHub![/green]")
            return True
        except Exception as force_error:
            console.print(f"[red]All push attempts failed: {force_error}[/red]")
            console.print(f"[yellow]The repository and commits are ready. You may need to push manually.[/yellow]")
            return False

# The central registry of all tools available to the Knight Agent

HYBRID_TOOL_REGISTRY = {
    # --- Shell & File Tools ---
    "run_shell_command": {
        "function": run_shell_command,
        "description": "Executes a shell command. Use `verbose=True` for debugging. Use `background=True` for servers. Use `allow_dependency_conflicts=True` to handle `npm` peer dependency issues.",
        "parameters": {
            "command": "string", 
            "cwd": "string (optional)", 
            "can_fail": "boolean (optional)",
            "verbose": "boolean (optional, default is false)",
            "force_overwrite": "boolean (optional, default is false)",
            "background": "boolean (optional, auto-detected for server commands)",
            "allow_dependency_conflicts": "boolean (optional, default is false)"
        }
    },
    "create_file": {
        "function": file_logic.new_file,
        "description": "Creates a new, empty file at a given path.",
        "parameters": { "file_path_str": "string" }
    },
    "generate_code_for_file": {
        "function": generate_code_for_file,
        "description": "Generates and saves code for a single file.",
        "parameters": { "filename": "string", "prompt": "string" }
    },
    "generate_code_concurrently": {
        "function": generate_code_concurrently,
        "description": "Generates code for multiple files in parallel. The most efficient way to build a project.",
        "parameters": { "files": "list[dict] (Each dict needs 'filename' and 'prompt')" }
    },
    # --- Code Analysis & Quality Tools ---
    "optimize_file": {
        "function": code_logic.optimize_file,
        "description": "Uses AI to analyze and refactor a single file for bugs, performance, and readability.",
        "parameters": { "filename": "string" }
    },
    "scan_repository": {
        "function": code_logic.scan_repository,
        "description": "Performs a high-level AI scan of all files in context to identify potential improvements.",
        "parameters": {}
    },
    # --- Git Tools ---
    "git_init": {
        "function": git_logic.GitUtils().init_repo,
        "description": "Initializes a Git repository in the specified directory.",
        "parameters": { "repo_path": "Path (ignore)" }
    },
    "git_add": {
        "function": git_logic.add,
        "description": "Stages one or more files for commit. Use `files=['.']` to stage all.",
        "parameters": { "files": "list[string]" }
    },
    "git_commit": {
        "function": git_logic.commit,
        "description": "Commits staged changes with a message.",
        "parameters": { "message": "string" }
    },
    "git_push": {
        "function": git_logic.push,
        "description": "Pushes committed changes to the remote repository for the current branch.",
        "parameters": {}
    },
    "git_pull": {
        "function": git_logic.pull,
        "description": "Pulls the latest changes from the remote repository for the current branch.",
        "parameters": {}
    },
    "git_switch_branch": {
        "function": git_logic.switch,
        "description": "Switches to a different local branch. Can also create a new branch.",
        "parameters": { "branch_name": "string", "create": "boolean (optional)" }
    },
    # --- GitHub Tools ---
    "github_create_repo": {
        "function": github_create_repo_non_interactive,
        "description": "Creates a new repository on GitHub programmatically.",
        "parameters": {"repo_name": "string", "description": "string (optional)", "is_private": "boolean (optional, defaults to false/public)"}
    },
    "git_initial_push": {
        "function": git_initial_push,
        "description": "Performs the first push to a newly created GitHub repository to link it.",
        "parameters": {"branch": "string (e.g., 'main' or 'master')"}
    },
    "setup_git_and_push": {
        "function": setup_git_and_push,
        "description": "The primary tool for finalizing a project. It handles staging ALL files, committing, creating the GitHub repo, and pushing the initial commit. Use this as the final step instead of the individual git/github tools.",
        "parameters": {"commit_message": "string", "repo_name": "string", "branch": "string (optional, defaults to 'main')"}
    },
    "github_create_issue": {
        "function": github_logic.create_issue,
        "description": "Interactively creates a new issue on the GitHub repository.",
        "parameters": {}
    },
    "github_list_issues": {
        "function": github_logic.list_issues,
        "description": "Lists open issues from the repository. Can filter by assignee.",
        "parameters": { "assignee_filter": "string (optional: a username, 'none', or '*')" }
    },
    "github_list_prs": {
        "function": github_logic.list_prs,
        "description": "Lists open Pull Requests from the repository.",
        "parameters": {}
    },
    "github_approve_pr": {
        "function": github_logic.approve_pr,
        "description": "Approves a specified Pull Request.",
        "parameters": { "pr_number_str": "string" }
    },
    "github_merge_pr": {
        "function": github_logic.merge_pr,
        "description": "Interactively merges a specified Pull Request.",
        "parameters": { "pr_number_str": "string" }
    },
    "github_ai_pr_review": {
        "function": github_logic.pr_review,
        "description": "Performs a comprehensive AI review of a specific Pull Request.",
        "parameters": { "pr_number_str": "string" }
    },
    "github_ai_repo_summary": {
        "function": github_logic.repo_summary,
        "description": "Generates a high-level AI-powered summary of the entire repository.",
        "parameters": {}
    },
    # New Research & File System Tools
    "web_search": {
        "function": web_search, 
        "description": "Performs a Google search to find information, documentation, or library versions.", "parameters": {"query": "string"}
        },
    "fetch_web_content": {
        "function": fetch_web_content, 
        "description": "Reads the text content of a URL. Use after `web_search` to 'read' a link.", "parameters": {"url": "string"}
        },
    "wikipedia_summary": {
        "function": wikipedia_summary, 
        "description": "Looks up a topic on Wikipedia to get a concise summary.", "parameters": {"topic": "string"}
        },
    "list_files": {
        "function": list_files_recursive, 
        "description": "Lists all files and directories to understand the current project structure.", "parameters": {"path": "string (optional, defaults to root)"}
        },
}