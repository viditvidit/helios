import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.rule import Rule
from rich.text import Text
import questionary
import inspect

from ..services.ai_service import AIService
from ..models.request import CodeRequest
from .agent_tools import TOOL_REGISTRY
from . import github_logic 

console = Console()

class KnightAgent:
    
    def __init__(self, session):
        self.session = session
        self.config = session.config
        self.work_dir = Path.cwd()
        self.tools = TOOL_REGISTRY

    def _format_tools_for_prompt(self):
        prompt_lines = []
        for name, tool in self.tools.items():
            params = tool.get('parameters', {})
            params_for_ai = {k: v for k, v in params.items() if k not in ['session', 'config', 'repo_path', 'current_files']}
            param_str = ", ".join([f"{k}: {v}" for k, v in params_for_ai.items()])
            prompt_lines.append(f"- `{name}({param_str})`: {tool['description']}")
        return "\n".join(prompt_lines)
    
    async def run(self, goal: str):
        console.print(Panel(f"[bold cyan]Knight Mode Activated[/bold cyan]\nGoal: [i][bold]{goal}[/bold][/i]", title="Agent", border_style="blue"))
        plan = await self._get_initial_plan(goal)
        if not plan:
            console.print("[red]Could not formulate a plan. Aborting.[/red]")
            return

        if await questionary.confirm("Proceed with the execution of this plan?", default=True, auto_enter=False).ask_async():
            console.print()
            await self._execute_plan(plan)
        else:
            console.print("[yellow]Plan execution aborted by user.[/yellow]")


    def _validate_plan(self, plan: list) -> (bool, str):
        if not isinstance(plan, list):
            return False, "The plan is not a list."
        for i, step in enumerate(plan):
            if not isinstance(step, dict):
                return False, f"Step {i+1} is not a valid object."
            command = step.get("command")
            if not command:
                return False, f"Step {i+1} is missing the required 'command' key. Invalid step: {step}"
            if command != "task_complete" and command not in self.tools:
                return False, f"Step {i+1} uses an unknown command: '{command}'."
        return True, ""
        
    async def _get_initial_plan(self, goal: str) -> list:
        
        prompt = (
            "You are a master software architect AI. Your sole task is to create a JSON array of objects to fulfill a user's goal. "
            "Your response MUST be a valid JSON array and nothing else. Follow the guidelines strictly.\n\n"
            "**Available Tools:**\n"
            f"{self._format_tools_for_prompt()}\n\n"
            "**CRITICAL GUIDELINES FOR SUCCESS:**\n"
            """
            The user can invoke you in an agentic capacity using `/knight <goal>` or `/knight_hybrid <goal>`. Your role is to formulate a step-by-step plan as a JSON array to achieve this goal.
            **Key Guidelines for Planning:**
            1.  **Universal Project Workflow:** Your plan must follow this logical sequence:
                a.  **Scaffold:** Use `run_shell_command` with the correct official tool (e.g., `npx create-react-app`, `python -m venv`, `mkdir`, etc.) to create the main project directory and structure. **Do not** generate config files like `package.json` manually.
                b.  **Install Dependencies:** Use `run_shell_command` to install any additional libraries needed (e.g., `npm install axios`, `pip install streamlit`). For `npm`, set `allow_dependency_conflicts: true` to prevent errors.
                c.  **Generate Code:** Use `generate_code_concurrently` to create all necessary source files. You **must** replace default template files with code that implements the user's actual requirements.
                d.  **Finalize:** Use `setup_git_and_push` as the last major step to commit all work and push it to a new GitHub repository.
                e.  **Verify (Optional but Recommended):** For web applications, add a final `run_shell_command` with `background: true` to start the development server.
            2.  **Working Directories:** Always use the `cwd` parameter in `run_shell_command` when you need to execute commands inside a subdirectory you've created (e.g., `cwd: "my-new-app"`).
            3.  **Final Command:** The plan MUST end with a single `task_complete` command, including a summary `message` for the user.
            4.  **Research:** Use the `web_search` and `fetch_web_content` tools to research libraries, find documentation, or resolve errors before writing code.

            ### Shell and File Tools

            -   **`run_shell_command(command, cwd, can_fail, verbose, force_overwrite, background, allow_dependency_conflicts)`**: Executes a shell command. Use for project setup, dependency installation, and running servers.
            -   **`create_file(file_path_str)`**: Creates a new, empty file.
            -   **`generate_code_for_file(filename, prompt)`**: Generates and saves code for a single file.
            -   **`generate_code_concurrently(files)`**: The most efficient way to build a project. Generates code for multiple files in parallel. The `files` argument is a list of dicts, where each dict has `'filename'` and `'prompt'`.
            -   **`list_files(path)`**: Lists all files and directories recursively to understand project structure.

            ### Code Quality and Analysis Tools

            -   **`optimize_file(filename)`**: Uses AI to analyze and refactor a single file for bugs, performance, and readability.
            -   **`scan_repository()`**: Performs a high-level AI scan of all files in context to identify potential improvements.
            -   **`validate_and_fix_json_files(directory, project_only)`**: Validates and attempts to fix all JSON files in a directory. Crucial to run before `npm install` if `package.json` issues are suspected.

            ### Git and GitHub Tools

            -   **`setup_git_and_push(commit_message, repo_name, branch)`**: The primary tool for finalizing a project. It handles staging ALL files, committing, creating the GitHub repo, and pushing the initial commit. Use this as the final step instead of individual git/github tools for new projects.
            -   **`github_create_repo(repo_name, description, is_private)`**: Creates a new repository on GitHub programmatically. Used by `setup_git_and_push`.
            -   **`git_add(files)`**: Stages one or more files for commit. Use `files=['.']` to stage all.
            -   **`git_commit(message)`**: Commits staged changes.
            -   **`git_push()`**: Pushes committed changes to the remote repository.
            -   **`git_pull()`**: Pulls the latest changes from the remote repository.
            -   **`git_switch_branch(branch_name, create)`**: Switches to a different local branch. Can also create a new branch.

            ### Research Tools

            -   **`web_search(query)`**: Performs a Google search to find information, documentation, or library versions.
            -   **`fetch_web_content(url)`**: Reads the text content of a URL. Use after `web_search` to 'read' a link.
            -   **`wikipedia_summary(topic)`**: Looks up a topic on Wikipedia to get a concise summary.
            """
            "---"
            f"Generate the JSON plan for the following goal:\n**Goal:** {goal}"
        )

        request = CodeRequest(prompt=prompt)
        plan_str = ""
        with console.status("[bold yellow]Formulating a resilient plan...[/bold yellow]"):
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    plan_str += chunk

        try:
            plan_str = plan_str.strip().removeprefix("```json").removesuffix("```").strip()
            plan = json.loads(plan_str)
            
            is_valid, error_message = self._validate_plan(plan)
            if not is_valid:
                console.print(f"[bold red]Error: The AI generated an invalid plan.[/bold red]")
                console.print(f"[red]Reason: {error_message}[/red]")
                json_syntax = Syntax(json.dumps(plan, indent=2), "json", theme="monokai")
                console.print(Panel(json_syntax, title="[red]Invalid Plan Details[/red]", border_style="red"))
                return []

            json_syntax = Syntax(json.dumps(plan, indent=2), "json", theme="monokai", line_numbers=True)
            console.print(Panel(json_syntax, title="📝 Execution Plan", border_style="green"))
            return plan
        except json.JSONDecodeError:
            console.print("[red]Error: AI did not return a valid JSON plan.[/red]"); console.print(f"[dim]Received: {plan_str}[/dim]"); return []

    async def _execute_plan(self, plan: list):
        github_commands_in_plan = [step for step in plan if 'github' in step.get('command', '')]
        if github_commands_in_plan:
            if not await github_logic.ensure_github_credentials(self.session):
                console.print("[red]Could not verify GitHub credentials. Aborting plan.[/red]")
                return
                
        for i, step in enumerate(plan):
            command_name = step.get("command")
            reasoning = step.get('reasoning', 'No reasoning provided.')
            
            if command_name == "task_complete":
                message = step.get('arguments', {}).get('message', 'The task is complete.')
                console.print(Panel(f"[bold green]✨ Knight Task Complete ✨[/bold green]\n\n{message}", border_style="green"))
                break

            console.print(Rule(f"[bold]Step {i+1}/{len(plan)}: {command_name}[/bold]"))
            console.print(Text("🤔 Reasoning: ", style="bold yellow") + Text(f"{reasoning}", style="italic dim"))
            
            args = step.get("arguments", {})
            
            if command_name in self.tools:
                tool_func = self.tools[command_name]['function']
                
                sig = inspect.signature(tool_func)
                if 'session' in sig.parameters: args['session'] = self.session
                if 'config' in sig.parameters: args['config'] = self.config
                if 'repo_path' in sig.parameters: args['repo_path'] = self.work_dir
                if 'current_files' in sig.parameters: args['current_files'] = self.session.current_files
                
                success = await tool_func(**args)
                if success is False:
                    console.print(f"[red]Step '{command_name}' failed. Aborting plan.[/red]")
                    return
            else:
                console.print(f"[red]Unknown command: {command_name}. Aborting.[/red]")
                return
            console.print()

async def run_knight_mode(session, goal: str):
    if not goal: return console.print("[red]Usage: /knight <your project goal>[/red]")
    agent = KnightAgent(session)
    await agent.run(goal)