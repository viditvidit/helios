# src/ai_assistant/logic/agent/interactive_agent.py

import inspect
from pathlib import Path
from typing import List, Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .planner import Planner
from .tools import TOOL_REGISTRY
from .theme import Theme

console = Console()

class InteractiveAgent:
    """
    An agent that collaborates with the user by generating a plan
    and then asking for confirmation before executing each step.
    """
    def __init__(self, session):
        self.session = session
        self.planner = Planner(session)
        self.tools = TOOL_REGISTRY
        self.work_dir = Path.cwd()

    async def run(self, goal: str) -> None:
        """
        Runs the interactive agent workflow:
        1. Generate a plan silently.
        2. Execute the plan step-by-step, confirming each action with a clean UI.
        """
        plan = await self.planner.get_plan(goal)
        if not plan:
            console.print(Panel("I couldn't devise a plan for that request. Please try rephrasing or be more specific.", border_style=Theme.ERROR, title=f"[{Theme.ERROR}]Planning Failed[/{Theme.ERROR}]"))
            return

        for i, step in enumerate(plan):
            command_name = step.get("command")
            if command_name == "task_complete":
                message = step.get('arguments', {}).get('message', 'The task is complete.')
                console.print(Panel(f"✨ {message}", border_style=Theme.SUCCESS, title=f"[{Theme.SUCCESS}]Task Complete[/{Theme.SUCCESS}]"))
                break

            reasoning = step.get('reasoning', 'No reasoning provided.')
            args = step.get("arguments", {})
            
            console.print(Text(reasoning, style=Theme.ACTION_REASONING))
            
            # --- NEW: Show the actual command for run_shell_command ---
            if command_name == "run_shell_command" and 'command' in args:
                prompt_message = Text("Execute command: ", style=Theme.PROMPT) + Text(f"'{args['command']}'", style="bold magenta") + Text("?", style=Theme.PROMPT)
            else:
                prompt_message = f"Execute tool: {command_name}?"
            
            proceed = await questionary.confirm(
                prompt_message,
                default=True,
                auto_enter=False
            ).ask_async()

            if not proceed:
                console.print(f"[{Theme.ERROR}]Aborting execution as requested.[/{Theme.ERROR}]")
                return

            if command_name in self.tools:
                tool_func = self.tools[command_name]['function']
                
                sig = inspect.signature(tool_func)
                if 'session' in sig.parameters:
                    args['session'] = self.session
                
                success = await tool_func(**args)
                if not success:
                    console.print(Panel(f"Step '{command_name}' failed. Aborting plan.", border_style=Theme.ERROR, title=f"[{Theme.ERROR}]Execution Failed[/{Theme.ERROR}]"))
                    return
            else:
                console.print(Panel(f"Unknown command: {command_name}. Aborting.", border_style=Theme.ERROR, title=f"[{Theme.ERROR}]Unknown Command[/{Theme.ERROR}]"))
                return
            console.print()