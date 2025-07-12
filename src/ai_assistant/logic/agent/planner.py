import json
import re
from typing import List, Tuple, Any, Optional

from rich.console import Console
from rich.panel import Panel

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
            # Exclude session from the prompt as the AI doesn't need to know about it
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
            if command not in self.tools and command not in ["task_complete"]:
                return False, f"Step {i+1} uses an unknown command: '{command}'."
        return True, ""

    def _extract_json_from_response(self, response: str) -> Optional[str]:
        """
        Extracts a JSON array from the model's response, handling markdown fences.
        """
        # First, try to find JSON within a markdown code block
        match = re.search(r'```json\s*(\[.*\])\s*```', response, re.DOTALL)
        if match:
            return match.group(1)
        
        # If not in a code block, try to find any JSON array
        match = re.search(r'(\[.*\])', response, re.DOTALL)
        if match:
            return match.group(1)
            
        return None

    async def get_plan(self, goal: str) -> Optional[List[Any]]:
        """
        Generates and validates a plan from the AI.
        This version is simplified as the Executor now handles all presentation.
        """
        current_model_config = self.config.get_current_model()
        base_system_prompt = current_model_config.system_prompt
        agent_instructions = current_model_config.agent_instructions
        formatted_tools = self._format_tools_for_prompt()

        if not agent_instructions:
             console.print(f"[{Theme.ERROR}]Error: Agent instructions are not defined in models.yaml.[/{Theme.ERROR}]")
             return None
        
        final_prompt = (
            f"{base_system_prompt}\n\n"
            f"## Agentic Mode Instructions\n{agent_instructions}\n\n"
            "### Important Planning Principles:\n"
            "1.  **Directory Awareness:** Always be mindful of the current working directory (`cwd`). Use `create_project_workspace` to establish the root project folder. For all subsequent file operations or shell commands, ensure the `cwd` argument is set correctly to operate in the right location.\n"
            "2.  **Project Initialization Strategy:** When using a command-line tool to scaffold a new project, recognize that such tools often create their own project directory. To avoid creating redundant nested folders (e.g., `my-app/my-app`), you should typically run the scaffolding command in a parent directory and let it create the final project folder. **Do not** use `create_project_workspace` to create a directory that a scaffolding tool will then also create.\n"
            "3.  **Be Methodical:** Deconstruct the goal into small, logical steps. For example: create workspace -> install dependencies -> generate code -> run build/test.\n\n"
            f"### Available Tools\n{formatted_tools}\n\n"
            f"---\n"
            f"**User Request:** {goal}"
        )
        
        request = CodeRequest(prompt=final_prompt)
        raw_response = ""
        with console.status(f"[{Theme.PROMPT}][dim]The Knight is formulating a plan[/dim][/{Theme.PROMPT}]"):
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    raw_response += chunk

        plan_str = self._extract_json_from_response(raw_response)
        
        if not plan_str:
            console.print(Panel("The AI did not return a valid plan in the expected format.", border_style=Theme.ERROR, title=f"[{Theme.ERROR}]Planning Error[/{Theme.ERROR}]"))
            console.print("[bold dim]Model's Raw Response:[/bold dim]")
            console.print(f"[dim]{raw_response}[/dim]")
            return None

        try:
            plan = json.loads(plan_str)
            is_valid, error_message = self._validate_plan(plan)
            
            if not is_valid:
                console.print(Panel(f"[bold]Error:[/bold] The AI generated an invalid plan.\n[bold]Reason:[/bold] {error_message}", border_style=Theme.ERROR, title=f"[{Theme.ERROR}]Plan Invalid[/{Theme.ERROR}]"))
                return None
            
            return plan
            
        except json.JSONDecodeError as e:
            console.print(Panel(f"[bold]Error:[/bold] Failed to decode the JSON plan. {e}", border_style=Theme.ERROR, title=f"[{Theme.ERROR}]JSON Decode Error[/{Theme.ERROR}]"))
            console.print("[bold dim]Extracted JSON String:[/bold dim]")
            console.print(f"[dim]{plan_str}[/dim]")
            return None