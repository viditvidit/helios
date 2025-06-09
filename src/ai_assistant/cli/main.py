#!/usr/bin/env python3
"""
AI Code Assistant - Main CLI Entry Point
"""
import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from ..core.config import Config
from ..core.exceptions import AIAssistantError, NotAGitRepositoryError
from ..services.ai_service import AIService
from ..services.file_service import FileService
from ..services.github_service import GitHubService
from ..utils.git_utils import GitUtils
from ..core.logger import setup_logging
from .commands import CodeCommands
# Updated import to reflect the new modular structure
from .interactive.session import InteractiveSession

console = Console()



@click.group()
@click.option('--config', '-c', type=click.Path(exists=True), help='Config file path')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--model', '-m', help='Override default model')
@click.pass_context
def cli(ctx, config: Optional[str], verbose: bool, model: Optional[str]):
    """AI Code Assistant - Your local AI coding companion"""
    try:
        # Initialize configuration
        config_path = Path(config) if config else None
        ctx.obj = Config(config_path=config_path)
        
        if model:
            ctx.obj.model_name = model
            
        # Setup logging
        setup_logging(verbose)
        
        # Display welcome message
        if ctx.invoked_subcommand is None:
            console.print(Panel.fit(
                "[bold blue]AI Code Assistant[/bold blue]\n"
                "Your local AI coding companion\n\n"
                "Use --help to see available commands",
                title="Welcome"
            ))
            
    except Exception as e:
        console.print(f"[red]Error initializing: {e}[/red]")
        sys.exit(1)

@cli.command()
@click.argument('prompt', nargs=-1)
@click.option('--file', '-f', multiple=True, help='Include file in context')
@click.option('--diff', is_flag=True, help='Show diff for changes')
@click.option('--apply', is_flag=True, help='Apply changes automatically')
@click.pass_context
def code(ctx, prompt, file, diff, apply):
    """Generate or modify code based on prompt"""
    asyncio.run(_code_command(ctx, prompt, file, diff, apply))

@cli.command()
@click.pass_context
def chat(ctx):
    """Start interactive chat mode"""
    asyncio.run(_chat_command(ctx))

@cli.command(name="repo-summary", help="Get an AI-generated summary of a Git repository's status.") 
@click.option('--path', 'repo_path_str', default=None, type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True), help="Path to the Git repository (defaults to current directory).")
@click.pass_context
def repo_summary_command(ctx, repo_path_str: Optional[str]):
    """Provides an AI-generated summary of the specified Git repository."""
    repo_path = Path(repo_path_str) if repo_path_str else Path.cwd()
    asyncio.run(_repo_summary_command(ctx, repo_path))

async def _repo_summary_command(ctx, repo_path: Path):
    try:
        cmd = CodeCommands(ctx.obj)
        summary = await cmd.get_ai_repo_summary(repo_path)
        console.print(summary)
    except NotAGitRepositoryError as e:
        console.print(f"[yellow]{e.message}[/yellow]")
        if click.confirm(f"Do you want to initialize a new Git repository at '{repo_path}'?", default=False):
            git_utils = GitUtils()
            initialized = await git_utils.initialize_repository(repo_path)
            if initialized:
                console.print(f"[green]Successfully initialized Git repository at '{repo_path}'.[/green]")
                # Optionally, suggest creating a default branch or other next steps
                console.print("Attempting to get repository summary again...")
                try:
                    summary = await cmd.get_ai_repo_summary(repo_path)
                    console.print(summary)
                except AIAssistantError as e_retry:
                    console.print(f"[red]Error getting summary after initialization: {e_retry}[/red]")
            else:
                console.print(f"[red]Failed to initialize Git repository at '{repo_path}'.[/red]")
        else:
            console.print("Repository initialization skipped.")
    except AIAssistantError as e:
        console.print(f"[red]Error: {e}[/red]")

@cli.command()
@click.option('--branch', '-b', help='Create new branch for changes')
@click.option('--commit', '-c', is_flag=True, help='Commit changes')
@click.option('--push', is_flag=True, help='Push to remote')
@click.pass_context
def review(ctx, branch, commit, push):
    """Review and commit code changes"""
    asyncio.run(_review_command(ctx, branch, commit, push))

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

async def _chat_command(ctx):
    try:
        # Updated to use InteractiveMode instead of InteractiveSession
        interactive = InteractiveMode(ctx.obj)
        await interactive.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Goodbye![/yellow]")
    except AIAssistantError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


async def _review_command(ctx, branch, commit, push):
    try:
        cmd = CodeCommands(ctx.obj)
        await cmd.review_changes(
            create_branch=branch,
            commit_changes=commit,
            push_changes=push
        )
    except AIAssistantError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

if __name__ == '__main__':
    cli()