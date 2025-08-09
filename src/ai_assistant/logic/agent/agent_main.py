from rich.console import Console
from rich.panel import Panel

from .planner import Planner
from .executor import Executor
from .theme import Theme

console = Console()

async def run_agentic_workflow(session, goal: str, interactive: bool):
    """
    Orchestrates the planning and execution phases for any agentic task.
    """
    if not goal:
        console.print("[red]Agentic goal cannot be empty.[/red]")
        return

    planner = Planner(session)
    executor = Executor(session)

    plan = await planner.get_plan(goal)
    
    if not plan:
        console.print(Panel("Could not formulate a valid plan. Aborting.", border_style=Theme.ERROR, title=f"[{Theme.ERROR}]Planning Failed[/{Theme.ERROR}]"))
        return

    # Pass the goal and interactive flag to the executor
    await executor.execute_plan(plan, goal, interactive=interactive)

async def run_knight_mode(session, goal: str):
    """
    The main entry point for the explicit '/knight' agentic mode.
    Invokes the agentic workflow in full interactive mode.
    """
    if not goal:
        return console.print("[red]Usage: /knight <your project goal>[/red]")

    await run_agentic_workflow(session, goal, interactive=True)