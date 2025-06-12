#!/usr/bin/env python3
"""
AI Code Assistant - Main CLI Entry Point
"""
import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
import questionary
from rich.console import Console
from rich.panel import Panel

from ..core.config import Config
from ..core.exceptions import AIAssistantError, NotAGitRepositoryError, ConfigurationError
from ..core.logger import setup_logging
from .commands import CodeCommands
from .interactive.session import InteractiveSession
from .interactive import display
from ..utils.git_utils import GitUtils
from ..utils.file_utils import build_repo_context
from ..services.vector_store import VectorStore

console = Console()

async def _run_interactive_mode(config: Config):
    """Runs the interactive REPL mode after model selection."""
    available_models = list(config.models.keys())
    if not available_models:
        console.print("[red]Error: No models found in your configuration file (e.g., configs/models.yaml).[/red]")
        sys.exit(1)

    default_model = config.model_name
    try:
        chosen_model = await questionary.select(
            "Choose a model for this session:",
            choices=available_models,
            default=default_model,
            use_indicator=True,
            style=questionary.Style([
                ('pointer', 'bold fg:cyan'),
                ('selected', 'fg:green'),
                ('highlighted', 'fg:green bold'),
            ])
        ).ask_async()

        if chosen_model is None:
            console.print("\n[yellow]Model selection cancelled. Exiting.[/yellow]")
            sys.exit(0)

        config.set_model(chosen_model)
        console.clear()

    except Exception as e:
        console.print(f"\n[yellow]An issue occurred during model selection: {e}. Exiting.[/yellow]")
        sys.exit(1)

    console.print(f"Using model: [bold green]{config.model_name}[/bold green]")
    session = InteractiveSession(config)
    await session.start()


@click.group(invoke_without_command=True)
@click.option('--config', '-c', type=click.Path(exists=True), help='Config file path')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--model', '-m', help='Override default model for the session')
@click.pass_context
def cli(ctx, config: Optional[str], verbose: bool, model: Optional[str]):
    """
    Helios - Your AI coding companion with RAG-powered context.

    Run `helios index` first to build the context for your repository.
    Then, run `helios` to start the interactive chat session.
    """
    try:
        config_path = Path(config) if config else None
        cfg = Config(config_path=config_path)

        if model:
            cfg.set_model(model)

        ctx.obj = cfg
        setup_logging(verbose)

        if ctx.invoked_subcommand is None:
            display.print_helios_banner()
            asyncio.run(_run_interactive_mode(ctx.obj))

    except ConfigurationError as e:
        console.print(f"[red]Configuration Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        import traceback
        console.print(f"[red]Error initializing: {e}[/red]")
        if verbose:
            console.print(traceback.format_exc())
        sys.exit(1)

@cli.command()
@click.argument('prompt', nargs=-1)
@click.option('--file', '-f', multiple=True, help='Include file in context')
@click.option('--diff', is_flag=True, help='Show diff for changes')
@click.option('--apply', is_flag=True, help='Apply changes automatically')
@click.pass_context
def code(ctx, prompt, file, diff, apply):
    """Generate or modify code based on a prompt (non-interactive)."""
    if not prompt:
        console.print("[yellow]Please provide a prompt for the code command.[/yellow]")
        return
    asyncio.run(_code_command(ctx, prompt, file, diff, apply))

async def _code_command(ctx, prompt, files, diff, apply):
    try:
        cmd = CodeCommands(ctx.obj)
        await cmd.generate_code(
            prompt=" ".join(prompt),
            files=list(files),
            show_diff=diff,
            apply_changes=apply
        )
    except AIAssistantError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

def main():
    cli()

if __name__ == '__main__':
    main()