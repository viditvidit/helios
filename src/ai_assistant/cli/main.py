import asyncio
import sys
from pathlib import Path
from typing import Optional
import yaml
import aiohttp
import click
import questionary
from rich.console import Console

from ..core.config import Config, PROJECT_ROOT
from ..core.exceptions import ConfigurationError
from ..core.logger import setup_logging
from .interactive.session import InteractiveSession
from .interactive import display

console = Console()

async def _run_first_time_setup():
    """Guides the user through an initial setup process."""
    console.print("\n[bold yellow]Welcome to Helios! It looks like this is your first run.[/bold yellow]")
    console.print("Let's get you set up with your local AI model endpoint.")

    endpoint = await questionary.text(
        "Enter your Ollama endpoint URL:",
        default="http://localhost:11434"
    ).ask_async()

    if not endpoint:
        console.print("[red]Endpoint cannot be empty. Exiting setup.[/red]")
        sys.exit(1)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{endpoint}/api/tags") as response:
                if response.status != 200:
                    console.print(f"[red]Error: Could not connect to Ollama at {endpoint}. Status: {response.status}[/red]")
                    console.print("Please ensure Ollama is running and accessible.")
                    sys.exit(1)
                models_data = await response.json()

        available_models = [model['name'] for model in models_data.get('models', [])]
        if not available_models:
            console.print(f"[red]No models found at {endpoint}. Please pull a model with `ollama pull <model_name>`.[/red]")
            sys.exit(1)

        chosen_default = await questionary.select(
            "Which model should be your default?",
            choices=available_models,
            use_indicator=True
        ).ask_async()

        if not chosen_default:
            console.print("[yellow]No default model selected. Exiting setup.[/yellow]")
            sys.exit(1)

        # Create models.yaml
        models_config = {
            'default_model': chosen_default,
            'models': {
                name: {
                    'name': name,
                    'type': 'ollama',
                    'endpoint': endpoint,
                    'context_length': 8000,
                    'temperature': 0.5,
                    'max_tokens': 4096,
                    'system_prompt': "You are Helios, a helpful AI code assistant. Your goal is to help users with their coding tasks by providing accurate, concise, and helpful responses.",
                    'agent_instructions': "You are an autonomous agent. Formulate a plan and execute it step-by-step using the provided tools."
                } for name in available_models
            }
        }
        
        config_dir = PROJECT_ROOT / "configs"
        config_dir.mkdir(exist_ok=True)
        models_yaml_path = config_dir / "models.yaml"
        with open(models_yaml_path, 'w') as f:
            yaml.dump(models_config, f, sort_keys=False)
        console.print(f"[green]✓ Configuration saved to {models_yaml_path}[/green]")

    except aiohttp.ClientError as e:
        console.print(f"[red]Connection failed: {e}. Please check the Ollama endpoint and your network.[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]An unexpected error occurred during setup: {e}[/red]")
        sys.exit(1)


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
        if "Models config file not found" in str(e):
            asyncio.run(_run_first_time_setup())
            console.print("\n[green]✓ Setup complete! Please run Helios again to start the session.[/green]")
            sys.exit(0)
        else:
            console.print(f"[red]Configuration Error: {e}[/red]")
            sys.exit(1)
    except Exception as e:
        import traceback
        console.print(f"[red]Error initializing: {e}[/red]")
        if verbose:
            console.print(traceback.format_exc())
        sys.exit(1)

def main():
    cli()

if __name__ == '__main__':
    main()