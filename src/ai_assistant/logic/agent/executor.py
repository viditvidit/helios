import inspect
from pathlib import Path
from typing import List, Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from ...logic import github_logic
from .tools import TOOL_REGISTRY
from .theme import Theme

console = Console()

class Executor:
    """
    Handles the execution phase of the agentic workflow.
    It takes a validated plan and runs each step.
    """
    def __init__(self, session):
        self.session = session
        self.work_dir = Path.cwd()
        self.tools = TOOL_REGISTRY

    async def execute_plan(self, plan: List[Any]) -> None:
        """Executes each step of the plan after user confirmation."""
        if any('github' in step.get('command', '') or 'git' in step.get('command', '') for step in plan):
            if not await github_logic.ensure_github_credentials(self.session):
                console.print(Panel("Could not verify GitHub credentials. Aborting plan.", border_style=Theme.ERROR, title="[bold red]Authentication Failed[/bold red]"))
                return

        if not await questionary.confirm("Proceed with the execution of this plan?", default=True, auto_enter=False).ask_async():
            console.print("[yellow]Plan execution aborted by user.[/yellow]")
            return

        console.print()
        for i, step in enumerate(plan):
            command_name = step.get("command")
            reasoning = step.get('reasoning', 'No reasoning provided.')

            if command_name == "task_complete":
                message = step.get('arguments', {}).get('message', 'The task is complete.')
                console.print(Panel(f"[bold]✨ Knight Task Complete ✨[/bold]\n\n{message}", border_style=Theme.SUCCESS, title="[bold green]Success[/bold green]"))
                break

            console.print(Rule(f"[bold {Theme.STEP_HEADER}]Step {i+1}/{len(plan)}: {command_name}[/bold {Theme.STEP_HEADER}]"))
            console.print(Text("Reasoning: ", style=f"bold {Theme.REASONING}") + Text(f"{reasoning}", style="italic dim"))
            
            args = step.get("arguments", {})
            if command_name in self.tools:
                tool_func = self.tools[command_name]['function']
                
                # Inject session automatically if the tool needs it
                sig = inspect.signature(tool_func)
                if 'session' in sig.parameters:
                    args['session'] = self.session
                
                success = await tool_func(**args)
                if not success:
                    console.print(Panel(f"Step '{command_name}' failed. Aborting plan.", border_style=Theme.ERROR, title="[bold red]Execution Failed[/bold red]"))
                    return
            else:
                console.print(Panel(f"Unknown command: {command_name}. Aborting.", border_style=Theme.ERROR, title="[bold red]Unknown Command[/bold red]"))
                return
            console.print()