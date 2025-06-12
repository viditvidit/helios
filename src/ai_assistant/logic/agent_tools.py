# src/ai_assistant/logic/agent_tools.py

import asyncio
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskProgressColumn
from rich.text import Text

from . import file_logic, code_logic
from ..services.ai_service import AIService
from ..logic import git_logic, github_logic, code_logic, file_logic 
from ..utils.git_utils import GitUtils
from ..models.request import CodeRequest

console = Console()

async def run_shell_command(session, command: str, cwd: str = None, can_fail: bool = False) -> bool:
    """
    Runs a shell command in a specified directory.
    If can_fail is True, a non-zero exit code will not abort the plan.
    """
    work_dir = session.config.work_dir
    run_dir = work_dir / cwd if cwd else work_dir
    
    console.print(f"Running command: [bold magenta]{command}[/bold magenta] in [dim]{run_dir}[/dim]")

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=run_dir
        )

        async def log_output(stream, prefix):
            while True:
                line = await stream.readline()
                if not line: break
                console.print(Text(f"[{prefix}] ", style="dim"), Text.from_ansi(line.decode().strip()))

        await asyncio.gather(
            log_output(process.stdout, "stdout"),
            log_output(process.stderr, "stderr")
        )

        await process.wait()
        
        if process.returncode == 0:
            console.print(f"[green]✓ Shell command finished successfully.[/green]")
            return True
        else:
            # --- THIS IS THE NEW RESILIENCE LOGIC ---
            if can_fail:
                console.print(f"[yellow]! Shell command failed with code {process.returncode}, but was marked as non-critical. Continuing.[/yellow]")
                return True # Return True to not abort the plan
            else:
                console.print(f"[red]✗ Shell command failed with return code {process.returncode}.[/red]")
                return False
            
    except Exception as e:
        console.print(f"[red]✗ An unexpected error occurred while running shell command: {e}[/red]")
        return False

async def generate_code_for_file(session, filename: str, prompt: str) -> bool:
    """
    Generates code for a single file. Does NOT display its own spinner.
    """
    generation_prompt = (
        f"You are a skilled software developer. Your task is to write the code for the file `{filename}`. "
        "Adhere to best practices and write clean, functional code.\n\n"
        f"**Request:** {prompt}\n\n"
        "Provide only the complete, final code for the file. Do not add any explanations or markdown formatting."
    )
    request = CodeRequest(prompt=generation_prompt)
    
    generated_code = ""
    async with AIService(session.config) as ai_service:
        async for chunk in ai_service.stream_generate(request):
            generated_code += chunk
    
    if not generated_code:
        return False
    
    generated_code = generated_code.strip().removeprefix("```").removesuffix("```").strip()
    session.last_ai_response_content = f"```{filename}\n{generated_code}\n```"
    await file_logic.save_code(session, filename)
    return True

async def generate_code_concurrently(session, files: list) -> bool:
    """
    Generates code for multiple files concurrently with a single progress bar.
    """
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=True
    )
    
    with progress:
        # Create a mapping from task to task_id
        task_to_id = {}
        tasks = []
        
        for f in files:
            task = asyncio.create_task(generate_code_for_file(session, f['filename'], f['prompt']))
            task_id = progress.add_task(f"Writing {f['filename']}...", total=1)
            task_to_id[task] = task_id
            tasks.append(task)

        for coro in asyncio.as_completed(tasks):
            task_id = task_to_id[coro]
            try:
                success = await coro
                if success:
                    progress.update(task_id, completed=1, description=f"[green]✓ Wrote {progress.tasks[task_id].description.split(' ')[1]}")
                else:
                    progress.update(task_id, completed=1, description=f"[red]✗ FAILED {progress.tasks[task_id].description.split(' ')[1]}")
            except Exception:
                progress.update(task_id, completed=1, description=f"[red]✗ CRASHED {progress.tasks[task_id].description.split(' ')[1]}")
    
    return all(await asyncio.gather(*tasks, return_exceptions=True))

# The central registry of all tools available to the Knight Agent
TOOL_REGISTRY = {
    # --- Shell & File Tools ---
    "run_shell_command": {
        "function": run_shell_command,
        "description": "Executes a shell command (e.g., `npm install`, `python3 -m venv venv`). Essential for setup.",
        "parameters": { "command": "string", "cwd": "string (optional)", "can_fail": "boolean (optional)" }
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
        "function": github_logic.create_repo,
        "description": "Interactively creates a new repository on GitHub.",
        "parameters": {} # This function is interactive, no args needed from AI
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
    }
}