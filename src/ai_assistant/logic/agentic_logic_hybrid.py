# src/ai_assistant/logic/agentic_logic_hybrid_v2.py

import json
import re
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.rule import Rule
import questionary
import inspect

from ..services.ai_service import AIService
from ..models.request import CodeRequest
from .agent_tools_hybrid import HYBRID_TOOL_REGISTRY
from . import github_logic

console = Console()

class Theme:
    HEADER = "#81A1C1"; GOAL = "#D8DEE9"; PLAN_TITLE = "#B48EAD"
    STEP_HEADER = "#5E81AC"; REASONING = "#ABEDFF"; SUCCESS = "#388238"; PROMPT = "#54A7FF"

class KnightAgentHybrid:
    def __init__(self, session):
        self.session = session; self.config = session.config; self.work_dir = Path.cwd()
        self.tools = HYBRID_TOOL_REGISTRY

    def _format_tools_for_prompt(self, relevant_tools: dict):
        # Now takes a subset of tools to format
        prompt_lines = []
        for name, tool in relevant_tools.items():
            params = tool.get('parameters', {})
            params_for_ai = {k: v for k, v in params.items() if k not in ['session', 'config', 'repo_path', 'current_files']}
            param_str = ", ".join([f"{k}: {v}" for k, v in params_for_ai.items()])
            prompt_lines.append(f"- `{name}({param_str})`: {tool['description']}")
        return "\n".join(prompt_lines)

    async def run(self, goal: str):
        plan = await self._get_initial_plan(goal)
        if not plan: console.print("[red]Could not formulate a plan. Aborting.[/red]"); return
        
        if await questionary.confirm("Proceed with the execution of this plan?", default=True, auto_enter=False).ask_async():
            console.print(); await self._execute_plan(plan)
        else: console.print("[yellow]Plan execution aborted by user.[/yellow]")

    # --- NEW: Stage 1 - Tool Selection ---
    async def _select_relevant_tools(self, goal: str) -> dict:
        tool_names = list(self.tools.keys())
        
        prompt = (
            "You are a tool selection AI. Your task is to identify the most relevant tools to achieve a user's goal. "
            "Given the user's goal and a list of available tool names, respond with only a comma-separated list of the names of the tools that are necessary. "
            "Do not include any other text or explanation.\n\n"
            f"**Available Tools:** {', '.join(tool_names)}\n\n"
            f"**User's Goal:** {goal}\n\n"
            "**Relevant Tool Names:**"
        )
        
        request = CodeRequest(prompt=prompt)
        response_str = ""
        with console.status(f"[bold {Theme.PROMPT}]Selecting relevant tools...[/bold {Theme.PROMPT}]"):
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    response_str += chunk
        
        # Use regex to find all valid tool names in the response, making it robust
        selected_names = re.findall(r'\b(' + '|'.join(re.escape(name) for name in tool_names) + r')\b', response_str)
        
        if not selected_names:
            console.print("[yellow]Warning: Could not automatically select tools. Using all tools as a fallback.[/yellow]")
            return self.tools

        relevant_tools = {name: self.tools[name] for name in selected_names if name in self.tools}
        console.print(f"[dim]Selected tools: {', '.join(relevant_tools.keys())}[/dim]")
        return relevant_tools

    def _validate_plan(self, plan: list) -> (bool, str):
        if not isinstance(plan, list): return False, "The plan is not a list."
        for i, step in enumerate(plan):
            if not isinstance(step, dict): return False, f"Step {i+1} is not a valid object."
            command = step.get("command")
            if not command: return False, f"Step {i+1} is missing the required 'command' key. Invalid step: {step}"
            if command != "task_complete" and command not in self.tools: return False, f"Step {i+1} uses an unknown command: '{command}'."
        return True, ""

    # --- MODIFIED: Stage 2 - Plan Generation ---
    async def _get_initial_plan(self, goal: str) -> list:
        prompt = (
            "You are a master software architect AI. Your sole task is to create a JSON array of objects to fulfill a user's goal. "
            "Your response MUST be a valid JSON array and nothing else. Follow the guidelines strictly.\n\n"
            "**Available Tools:**\n"
            f"{self._format_tools_for_prompt(self.tools)}\n\n"
            "**CRITICAL GUIDELINES FOR SUCCESS:**\n"
            "1. **Schema:** Each step must have `command`, `arguments` (even if empty {}), and `reasoning` keys.\n"
            "2. **Tool Selection:** You can only use the tools listed above.\n"
            "3. **Dependency Conflicts (IMPORTANT):** When using `npm install` to add new libraries to a project created by a tool like `create-react-app`, peer dependency conflicts are very common. To prevent the plan from failing, you **MUST** add the argument `\"allow_dependency_conflicts\": true` to that specific `run_shell_command` step. This is a common and necessary practice in modern web development.\n"
            "4. **Code Generation:** Use `generate_code_concurrently` to write multiple files at once for maximum efficiency. It is preferred over `generate_code_for_file`.\n"
            "5. **Finalization:** The **ONLY** way to commit and push code to a new GitHub repo is with the `setup_git_and_push` tool. This is the final step of your plan before `task_complete`. \n"
            "   - **DO NOT** use `git_add`, `git_commit`, `github_create_repo`, or `git_initial_push` individually. The `setup_git_and_push` command handles all of these steps idempotently.\n"
            "6. **Verification Step:** For web applications, after all code is generated, add `run_shell_command` steps to start the frontend and backend servers using `background=True`. This demonstrates a working final product.\n"
            "7. **Final Command:** The plan MUST end with a `task_complete` command, which takes a `message` argument for the user.\n\n"
            "---"
            f"Generate the JSON plan for the following goal:\n**Goal:** {goal}"
        )

        request = CodeRequest(prompt=prompt)
        plan_str = ""
        with console.status(f"[bold {Theme.PROMPT}]The Knight is formulating a plan...[/bold {Theme.PROMPT}]"):
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    plan_str += chunk

        try:
            plan_str = plan_str.strip().removeprefix("```json").removesuffix("```").strip()
            plan = json.loads(plan_str)
            is_valid, error_message = self._validate_plan(plan)
            if not is_valid:
                console.print(f"[bold red]Error: The AI generated an invalid plan.[/bold red]"); console.print(f"[red]Reason: {error_message}[/red]")
                json_syntax = Syntax(json.dumps(plan, indent=2), "json", theme="monokai"); console.print(Panel(json_syntax, title="[red]Invalid Plan Details[/red]", border_style="red")); return None
            json_syntax = Syntax(json.dumps(plan, indent=2), "json", theme="monokai", line_numbers=True)
            console.print(Panel(json_syntax, title=f"[bold {Theme.PLAN_TITLE}]📝 Execution Plan[/bold {Theme.PLAN_TITLE}]", border_style=Theme.PLAN_TITLE)); return plan
        except json.JSONDecodeError:
            console.print("[red]Error: AI did not return a valid JSON plan.[/red]"); console.print(f"[dim]Received: {plan_str}[/dim]"); return None

    async def _execute_plan(self, plan: list):
        github_commands_in_plan = [step for step in plan if 'github' in step.get('command', '') or 'git' in step.get('command', '')]
        if github_commands_in_plan:
            if not await github_logic.ensure_github_credentials(self.session):
                console.print("[red]Could not verify GitHub credentials. Aborting plan.[/red]"); return
        for i, step in enumerate(plan):
            command_name = step.get("command"); reasoning = step.get('reasoning', 'No reasoning provided.')
            if command_name == "task_complete":
                message = step.get('arguments', {}).get('message', 'The task is complete.')
                console.print(Panel(f"[bold {Theme.SUCCESS}]✨ Knight Task Complete ✨[/bold {Theme.SUCCESS}]\n\n{message}", border_style=Theme.SUCCESS)); break
            console.print(Rule(f"[bold {Theme.STEP_HEADER}]Step {i+1}/{len(plan)}: {command_name}[/bold {Theme.STEP_HEADER}]"))
            console.print(Text("🤔 Reasoning: ", style=f"bold {Theme.REASONING}") + Text(f"{reasoning}", style="italic dim"))
            args = step.get("arguments", {})
            if command_name in self.tools:
                tool_func = self.tools[command_name]['function']
                sig = inspect.signature(tool_func)
                if 'session' in sig.parameters: args['session'] = self.session
                if 'config' in sig.parameters: args['config'] = self.config
                if 'repo_path' in sig.parameters: args['repo_path'] = self.work_dir
                if 'current_files' in sig.parameters: args['current_files'] = self.session.current_files
                success = await tool_func(**args)
                if success is False: console.print(f"[red]Step '{command_name}' failed. Aborting plan.[/red]"); return
            else: console.print(f"[red]Unknown command: {command_name}. Aborting.[/red]"); return
            console.print()

async def run_knight_hybrid_mode(session, goal: str):
    if not goal: return console.print("[red]Usage: /knight_hybrid <your project goal>[/red]")
    agent = KnightAgentHybrid(session)
    await agent.run(goal)