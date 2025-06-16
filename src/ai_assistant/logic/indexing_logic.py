import json
from datetime import datetime
from pathlib import Path
from rich.console import Console

from ..services.vector_store import VectorStore
from ..utils.file_utils import build_repo_context
from ..core.config import Config

console = Console()
LOG_FILE = Path(".helios/log.json")

def _read_log():
    """Reads the log file, creating it if it doesn't exist."""
    if not LOG_FILE.exists():
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'w') as f:
            json.dump({}, f)
        return {}
    with open(LOG_FILE, 'r') as f:
        return json.load(f)

def _write_log(data: dict):
    """Writes data to the log file."""
    with open(LOG_FILE, 'w') as f:
        json.dump(data, f, indent=4)

async def run_indexing(config: Config) -> dict:
    """
    Scans the repository, chunks files, creates vector embeddings,
    and returns the file context.
    """
    try:
        repo_path = Path.cwd()
        file_contents = build_repo_context(repo_path, config)
        if not file_contents:
            console.print("[yellow]No supported files found to index.[/yellow]")
            return {}

        with console.status(f"[cyan]Indexing {len(file_contents)} files...[/cyan]", spinner="dots"):
            vector_store = VectorStore(config)
            vector_store.index_files(file_contents)
            
            # Log the successful index
            log_data = _read_log()
            log_data['last_indexed'] = datetime.now().isoformat()
            _write_log(log_data)
        
        console.print(f"[green]✓ Indexed {len(file_contents)} files successfully[/green]")
        return file_contents
    except Exception as e:
        console.print(f"[red]✗ Indexing failed: {e}[/red]")
        return {}

async def check_and_run_startup_indexing(config: Config):
    """Checks if indexing is needed on startup and runs it if so."""
    log_data = _read_log()
    last_indexed_str = log_data.get('last_indexed')
    
    needs_indexing = True
    if last_indexed_str:
        last_indexed_date = datetime.fromisoformat(last_indexed_str).date()
        if last_indexed_date == datetime.now().date():
            needs_indexing = False
            console.print("[dim]Loading existing index...[/dim]")
            return build_repo_context(Path.cwd(), config)

    if needs_indexing:
        return await run_indexing(config)