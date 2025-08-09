import inspect
import json
from typing import List, Any, Tuple
import copy

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text

from ...services.ai_service import AIService
from ...models.request import CodeRequest
from .tools import TOOL_REGISTRY
from .theme import Theme

console = Console()

class Executor:
    def __init__(self, session):
        self.session = session
        # The work_dir is now a mutable attribute of the session, set by tools
        self.session.work_dir = self.session.config.work_dir
        self.tools = TOOL_REGISTRY

    async def _summarize_plan_with_ai(self, plan: List[Any], goal: str) -> str:
        """Uses an AI call to create a checklist summary of the plan."""
        plan_str = "\n".join([f"- {step.get('reasoning')}" for step in plan if step.get("command") != "task_complete"])
        
        summary_prompt = (
            "You are a summarization AI. A user provided a goal, and an agent created a technical plan. "
            "Convert this plan into a human-readable markdown checklist of the key outcomes. "
            "Only list out the checklist options, no headings of tasks. "
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
        
    def _render_step_for_display(self, step: dict[str, Any]) -> Tuple[str, str]:
        """
        Translates an execution step into a human-readable format for display.
        Returns a tuple of (action_description, reasoning_text).
        """
        command = step.get("command", "unknown_command")
        args = step.get("arguments", {})
        reasoning = step.get("reasoning", "No reasoning provided.")
        
        action_text = f"[bold yellow]Executing Tool:[/bold yellow] [dim]{command}[/dim]" # Fallback

        if command == "create_project_workspace":
            action_text = f"[bold cyan]mkdir[/bold cyan] [green]{args.get('directory_name', '')}[/green]"
        elif command == "run_shell_command":
            action_text = f"[bold cyan]$[/bold cyan] [green]{args.get('command', '')}[/green]"
        elif command == "generate_code_concurrently":
            count = len(args.get('files', []))
            action_text = f"[bold cyan]Generating {count} file(s)...[/bold cyan]"
        elif command == "review_and_commit_changes":
            action_text = f"[bold cyan]git commit -m[/bold cyan] [green]\"{args.get('commit_message', '')}\"[/green]"
        elif command == "setup_git_and_push":
            action_text = f"[bold cyan]Initializing Git and pushing to new repo...[/bold cyan]"

        return action_text, reasoning

    async def execute_plan(self, plan: List[Any], goal: str, interactive: bool = True) -> None:
        if interactive:
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
            action_str, reasoning_str = self._render_step_for_display(step)

            if interactive:
                step_title_text = Text(f"Step {current_step}/{total_steps}", style="")
                display_content = f"{action_str}\n\n[bold]Reasoning:[/bold] [dim]{reasoning_str}[/dim]"
                console.print(Panel(display_content, title=step_title_text, border_style=Theme.STEP_PANEL_BORDER, expand=False))

                action = await questionary.select("Action:", choices=["Execute", "Skip", "Edit", "Abort"]).ask_async()

                if action == "Abort": return
                if action == "Skip": continue
                if action == "Edit":
                    step_json = json.dumps(step, indent=2)
                    edited_json_str = await questionary.text("Edit step JSON:", multiline=True, default=step_json).ask_async()
                    try:
                        step = json.loads(edited_json_str or "{}")
                        command_name = step.get("command") # Re-read command name after edit
                    except json.JSONDecodeError: continue
            else:
                # Non-interactive mode: just announce the step being executed.
                panel_title = Text(f"Step {current_step}/{total_steps}", style=Theme.PROMPT)
                console.print(Panel(action_str, title=panel_title, border_style=Theme.STEP_PANEL_BORDER, expand=False))

            args = step.get("arguments", {})
            if command_name in self.tools:
                tool_func = self.tools[command_name]['function']
                sig = inspect.signature(tool_func)
                
                # Always pass the session object if expected
                if 'session' in sig.parameters:
                    args['session'] = self.session

                # Override `cwd` for commands that need it with the session's current work_dir
                if command_name == "run_shell_command" or command_name == "generate_code_concurrently":
                     args['cwd'] = str(self.session.work_dir)

                # Filter args to only include parameters that the function actually accepts
                valid_params = set(sig.parameters.keys())
                filtered_args = {k: v for k, v in args.items() if k in valid_params}
                
                # Log filtered parameters for debugging
                if len(args) != len(filtered_args):
                    ignored_params = set(args.keys()) - valid_params
                    console.print(f"[dim]Ignoring unsupported parameters for {command_name}: {ignored_params}[/dim]")

                success = await tool_func(**filtered_args)

                if not success:
                    error_title = Text("Execution Failed", style=Theme.ERROR)
                    console.print(Panel(f"Step failed. Aborting plan.", border_style=Theme.ERROR, title=error_title))
                    return
            else:
                unknown_cmd_title = Text("Unknown Command", style=Theme.ERROR)
                console.print(Panel(f"Unknown command: {command_name}.", border_style=Theme.ERROR, title=unknown_cmd_title))
                return
            console.print()