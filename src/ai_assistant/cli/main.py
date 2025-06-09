import asyncio
import sys
from pathlib import Path
from typing import Optional
import re
import requests
import os

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
from .interactive import InteractiveMode

console = Console()

@click.group()
@click.option('--config', '-c', type=click.Path(exists=True), help='Config file path')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--model', '-m', help='Override default model')
@click.pass_context
def cli(ctx, config: Optional[str], verbose: bool, model: Optional[str]):
    """Helios AI Code Assistant"""
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

@cli.command(name="repo-summary", help="Get an AI-generated summary of a Git repository's status or a remote repo's purpose.")
@click.argument('repo', required=False)
@click.option('--path', 'repo_path_str', default=None, type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True), help="Path to the Git repository (defaults to current directory).")
@click.pass_context
def repo_summary_command(ctx, repo, repo_path_str):
    """
    Provides an AI-generated summary of the specified Git repository.
    If a repo URL is provided, fetches its metadata from GitHub.
    """
    if repo and re.match(r'https?://|git@', repo):
        # Remote repo summary
        asyncio.run(_remote_repo_summary(ctx, repo))
    else:
        # Local repo summary (default)
        repo_path = Path(repo_path_str) if repo_path_str else Path.cwd()
        asyncio.run(_repo_summary_command(ctx, repo_path))

async def _remote_repo_summary(ctx, repo_url):
    """
    Summarize a remote GitHub repository using its metadata.
    """
    console = Console()
    # Extract owner/repo from URL
    m = re.search(r'github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/\.]+)', repo_url)
    if not m:
        console.print("[red]Only GitHub repositories are supported for remote summaries.[/red]")
        return
    owner, repo = m.group('owner'), m.group('repo')
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    headers = {"Accept": "application/vnd.github.v3+json"}
    # Optionally add GitHub token for higher rate limits
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    # Fetch repo metadata
    repo_resp = requests.get(api_url, headers=headers)
    if repo_resp.status_code != 200:
        console.print(f"[red]Failed to fetch repo metadata: {repo_resp.text}[/red]")
        return
    repo_data = repo_resp.json()

    # Fetch README
    readme_resp = requests.get(readme_url, headers=headers)
    readme_content = ""
    if readme_resp.status_code == 200:
        import base64
        readme_json = readme_resp.json()
        if "content" in readme_json:
            readme_content = base64.b64decode(readme_json["content"]).decode("utf-8", errors="ignore")
            if len(readme_content) > 2000:
                readme_content = readme_content[:2000] + "\n...[truncated]"
    else:
        readme_content = "(No README found or could not fetch README.)"

    # Compose prompt for AI
    license_info = repo_data.get('license')
    license_name = license_info['name'] if license_info and 'name' in license_info else 'N/A'

    prompt = (
        f"Repository: {repo_data.get('full_name')}\n"
        f"Description: {repo_data.get('description')}\n"
        f"Topics: {', '.join(repo_data.get('topics', []))}\n"
        f"Stars: {repo_data.get('stargazers_count')}, Forks: {repo_data.get('forks_count')}\n"
        f"Default Branch: {repo_data.get('default_branch')}\n"
        f"License: {license_name}\n"
        f"README:\n{readme_content}\n"
        "Please provide a detailed summary of what this repository is for, its main features, and any notable technologies or usage instructions."
    )

    # Use your AI service to summarize
    from ..models.request import CodeRequest
    from ..services.ai_service import AIService
    request = CodeRequest(prompt=prompt)
    summary = ""
    async with AIService(ctx.obj) as ai_service:
        async for chunk in ai_service.stream_generate(request):
            summary += chunk
    console.print(summary)

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