# src/ai_assistant/logic/agent/planner.py

import json
import re
from typing import Dict, List, Tuple, Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from ...services.ai_service import AIService
from ...models.request import CodeRequest
from .tools import TOOL_REGISTRY
from .theme import Theme

console = Console()

class Planner:
    """
    Handles the planning phase of the agentic workflow.
    It constructs the prompt for the AI, gets a plan, and validates it.
    """
    def __init__(self, session):
        self.session = session
        self.config = session.config
        self.tools = TOOL_REGISTRY

    def _format_tools_for_prompt(self) -> str:
        """Formats the tool registry into a string for the AI prompt."""
        prompt_lines = []
        for name, tool in self.tools.items():
            params = tool.get('parameters', {})
            # Exclude session and other internal params from the AI's view
            params_for_ai = {k: v for k, v in params.items() if k not in ['session', 'config']}
            param_str = ", ".join([f"{k}: {v}" for k, v in params_for_ai.items()])
            prompt_lines.append(f"- `{name}({param_str})`: {tool['description']}")
        return "\n".join(prompt_lines)

    def _validate_plan(self, plan: List[Any]) -> Tuple[bool, str]:
        """Validates the structure and commands of the generated plan."""
        if not isinstance(plan, list):
            return False, "The plan is not a list."
        for i, step in enumerate(plan):
            if not isinstance(step, dict):
                return False, f"Step {i+1} is not a valid object."
            command = step.get("command")
            if not command:
                return False, f"Step {i+1} is missing the required 'command' key."
            if command != "task_complete" and command not in self.tools:
                return False, f"Step {i+1} uses an unknown command: '{command}'."
        return True, ""

    async def get_plan(self, goal: str) -> Optional[List[Any]]:
        """
        Generates a plan from the AI to achieve the given goal.
        
        This method builds a dynamic prompt by combining the base system prompt
        from the user's config with agent-specific instructions and tool definitions.
        """
        # Get all prompt components from the config
        current_model_config = self.config.get_current_model()
        base_system_prompt = current_model_config.system_prompt
        agent_instructions = current_model_config.agent_instructions
        formatted_tools = self._format_tools_for_prompt()

        if not agent_instructions:
             console.print("[bold red]Error:[/bold red] Agent instructions are not defined in models.yaml for the current model.")
             return None

        # Construct the final prompt for the planner
        final_prompt = (
            f"{base_system_prompt}\n\n"
            f"## Agentic Mode Instructions\n\n"
            f"{agent_instructions}\n\n"
            f"### Available Tools\n\n"
            f"{formatted_tools}\n\n"
            f"---\n"
            f"Generate the JSON plan for the following goal:\n**Goal:** {goal}"
        )
        
        request = CodeRequest(prompt=final_prompt)
        plan_str = ""
        with console.status(f"[bold {Theme.PROMPT}]The Knight is formulating a plan...[/bold {Theme.PROMPT}]"):
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    plan_str += chunk

        try:
            # Clean up the response to extract only the JSON
            json_match = re.search(r'\[.*\]', plan_str, re.DOTALL)
            if not json_match:
                raise json.JSONDecodeError("No JSON array found in the AI response.", plan_str, 0)
            
            plan_str = json_match.group(0)
            plan = json.loads(plan_str)

            is_valid, error_message = self._validate_plan(plan)
            if not is_valid:
                console.print(Panel(f"[bold]Error:[/bold] The AI generated an invalid plan.\n[bold]Reason:[/bold] {error_message}", border_style=Theme.ERROR, title="[bold red]Plan Invalid[/bold red]"))
                return None
            
            json_syntax = Syntax(json.dumps(plan, indent=2), "json", theme="monokai", line_numbers=True)
            console.print(Panel(json_syntax, title=f"[bold {Theme.PLAN_TITLE}]Execution Plan[/bold {Theme.PLAN_TITLE}]", border_style=Theme.PLAN_TITLE))
            return plan
        except json.JSONDecodeError as e:
            console.print(Panel(f"[bold]Error:[/bold] AI did not return a valid JSON plan. {e}", border_style=Theme.ERROR, title="[bold red]JSON Decode Error[/bold red]"))
            console.print(f"[dim]Received: {plan_str}[/dim]")
            return None