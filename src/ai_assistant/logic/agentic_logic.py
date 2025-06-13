# src/ai_assistant/logic/agentic_logic.py

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
            "You are 'Knight', an autonomous AI software engineer. Your task is to create a step-by-step plan to achieve a user's goal. "
            "Think like a senior developer. Use scaffolding tools when available. Be resilient to minor failures.\n\n"
            f"**User's Goal:** {goal}\n\n"
            "**Available Tools:**\n"
            f"{self._format_tools_for_prompt()}\n\n"
            "**Instructions & Best Practices:**\n"
            "1. **Python Virtual Environments:** To install packages or run a server in a Python venv, DO NOT try to `source` activate it. Instead, call the python/pip executables directly from the venv's bin folder. Example for macOS/Linux: `venv/bin/python -m pip install fastapi`. Example for Windows: `venv\\Scripts\\python.exe -m pip install fastapi`. The same applies to running a server: `venv/bin/python -m uvicorn main:app`.\n"
            "2. **Resilience:** For non-critical steps like running tests or linters, set `can_fail: true` in the `run_shell_command` arguments. This prevents the entire plan from aborting if a test fails.\n"
            "3. **Use Scaffolding:** If the user wants a standard project (e.g., React, Vue), your first step should always be to use `run_shell_command` with their official CLIs (e.g., `npx create-react-app frontend`). Do not create files like `package.json` manually.\n"
            "4. **Plan Structure:** The plan must be a valid JSON array of objects. Each object needs 'command', 'arguments', and 'reasoning' keys.\n"
            "5. **Efficiency:** Use `generate_code_concurrently` for writing multiple custom files at once.\n"
            "6. **Final Command:** The plan MUST end with the command `task_complete`.\n"
            "7. **Output Format:** Provide ONLY the raw JSON plan. No introductory text or explanations."
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
                return None

            json_syntax = Syntax(json.dumps(plan, indent=2), "json", theme="monokai", line_numbers=True)
            console.print(Panel(json_syntax, title="📝 Execution Plan", border_style="green"))
            return plan
        except json.JSONDecodeError:
            console.print("[red]Error: AI did not return a valid JSON plan.[/red]"); console.print(f"[dim]Received: {plan_str}[/dim]"); return None

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