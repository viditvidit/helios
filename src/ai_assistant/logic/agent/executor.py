# src/ai_assistant/logic/agent/executor.py

import inspect
import json
from typing import List, Any
import copy

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.text import Text

from ...logic import github_logic
from ...services.ai_service import AIService
from ...models.request import CodeRequest
from .tools import TOOL_REGISTRY
from .theme import Theme

console = Console()

class Executor:
    def __init__(self, session):
        self.session = session
        self.work_dir = self.session.config.work_dir
        self.tools = TOOL_REGISTRY

    async def _summarize_plan_with_ai(self, plan: List[Any], goal: str) -> str:
        """Uses an AI call to create a checklist summary of the plan."""
        plan_str = "\n".join([f"- {step.get('reasoning')}" for step in plan if step.get("command") != "task_complete"])
        
        summary_prompt = (
            "You are a summarization AI. A user provided a goal, and an agent created a technical plan. "
            "Convert this plan into a human-readable markdown checklist of the key outcomes. "
            "Focus on what will be created or achieved.\n\n"
            f"**User's Goal:** {goal}\n\n"
            f"**Technical Plan Steps:**\n{plan_str}\n\n"
            "**Markdown Checklist Summary:**"
        )
        
        request = CodeRequest(prompt=summary_prompt)
        summary = ""
        async with AIService(self.session.config) as ai_service:
            async for chunk in ai_service.stream_generate(request):
                summary += chunk
        return summary.strip()

    async def execute_plan(self, plan: List[Any], goal: str) -> None:
        summary = await self._summarize_plan_with_ai(plan, goal)
        
        summary_title = Text("Execution Summary", style=Theme.SUMMARY_TITLE)
        console.print(Panel(Markdown(summary), title=summary_title, border_style=Theme.SUMMARY_BORDER, title_align="left"))

        if not await questionary.confirm("Proceed with this plan?", default=True, auto_enter=False).ask_async():
            console.print("[yellow]Plan execution aborted by user.[/yellow]")
            return

        console.print()
        
        editable_plan = copy.deepcopy(plan)
        
        executable_steps = [s for s in editable_plan if s.get('command') != 'task_complete']
        total_steps = len(executable_steps)
        current_step = 0

        for step in editable_plan:
            command_name = step.get("command")
            
            if command_name == "task_complete":
                message = step.get('arguments', {}).get('message', 'The task is complete.')
                success_title = Text("Task Complete", style=Theme.SUCCESS)
                console.print(Panel(f"{message}", border_style=Theme.SUCCESS, title=success_title))
                break

            current_step += 1
            step_title_text = Text(f"Step {current_step}/{total_steps}: ", style="") + Text(command_name, style="bold")
            step_json = json.dumps(step, indent=2)
            console.print(Panel(Syntax(step_json, "json", theme="monokai"), title=step_title_text, border_style=Theme.STEP_PANEL_BORDER))

            action = await questionary.select("Action:", choices=["Execute", "Skip", "Edit", "Abort"]).ask_async()

            if action == "Abort": return
            if action == "Skip": continue
            if action == "Edit":
                edited_json_str = await questionary.text("Edit step:", multiline=True, default=step_json).ask_async()
                try:
                    step = json.loads(edited_json_str or "{}")
                    command_name = step.get("command")
                except json.JSONDecodeError: continue

            args = step.get("arguments", {})
            if command_name in self.tools:
                tool_func = self.tools[command_name]['function']
                sig = inspect.signature(tool_func)
                
                if 'session' in sig.parameters:
                    args['session'] = self.session

                if command_name == "create_project_workspace":
                    dir_name = args.get("directory_name")
                    await tool_func(**args)
                    if dir_name:
                        self.work_dir = self.session.config.work_dir / dir_name
                        console.print(f"[dim]Workspace for all subsequent steps set to: ./{dir_name}[/dim]")
                    success = True
                else:
                    if 'cwd' in sig.parameters:
                        args['cwd'] = str(self.work_dir)
                    success = await tool_func(**args)

                if not success:
                    error_title = Text("Execution Failed", style=Theme.ERROR)
                    console.print(Panel(f"Step '{command_name}' failed. Aborting plan.", border_style=Theme.ERROR, title=error_title))
                    return
            else:
                unknown_cmd_title = Text("Unknown Command", style=Theme.ERROR)
                console.print(Panel(f"Unknown command: {command_name}.", border_style=Theme.ERROR, title=unknown_cmd_title))
                return
            console.print()