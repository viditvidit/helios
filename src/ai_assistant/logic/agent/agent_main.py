from rich.console import Console
from rich.panel import Panel

from .planner import Planner
from .executor import Executor
from .theme import Theme

console = Console()

async def run_knight_mode(session, goal: str):
    """
    The main entry point for the agentic mode.
    Orchestrates the planning and execution phases.
    """
    if not goal:
        return console.print("[red]Usage: /knight <your project goal>[/red]")

    planner = Planner(session)
    executor = Executor(session)

    plan = await planner.get_plan(goal)
    
    if not plan:
        console.print(Panel("Could not formulate a valid plan. Aborting.", border_style=Theme.ERROR, title=f"[{Theme.ERROR}]Planning Failed[/{Theme.ERROR}]"))
        return

    # Pass the goal to the executor for a better summary
    await executor.execute_plan(plan, goal)