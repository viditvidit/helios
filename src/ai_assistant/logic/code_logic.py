from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from ..services.ai_service import AIService
from ..models.request import CodeRequest

console = Console()

async def optimize_file(session, filename: str):
    """Sends a file to the AI for optimization and returns the improved code."""
    console.print(f"[cyan]Optimizing file: {filename}...[/cyan]")
    try:
        file_path = Path(filename)
        content = await session.file_service.read_file(file_path)
        
        prompt = (
            "You are an expert code optimizer. Review the following code carefully. "
            "Your task is to identify and fix bugs, refactor for improved readability and performance, "
            "and ensure it adheres to best practices. Provide only the complete, final, improved code "
            f"in a single code block for the file `{filename}`. Do not add any explanations before or after the code block."
        )
        
        request = CodeRequest(prompt=prompt, files={filename: content})
        
        optimized_code = ""
        async with AIService(session.config) as ai_service:
            async for chunk in ai_service.stream_generate(request):
                optimized_code += chunk
        
        return optimized_code
        
    except FileNotFoundError:
        console.print(f"[red]Error: File not found at '{filename}'[/red]")
        return None
    except Exception as e:
        console.print(f"[red]An error occurred during file optimization: {e}[/red]")
        return None

async def scan_repository(session):
    """Scans all files and asks the AI to identify areas for improvement."""
    console.print("[cyan]Scanning repository for potential improvements...[/cyan]")
    
    file_contents = "\n\n".join([f"--- START {path} ---\n{content}\n--- END {path} ---" for path, content in session.current_files.items()])
    
    prompt = (
        "You are a senior code reviewer. Analyze the following files from a repository. "
        "Do not suggest code changes. Instead, provide a high-level report in markdown format. "
        "For each file that has issues, create a heading for the filename and use bullet points "
        "to list potential improvements, such as code smells, performance bottlenecks, or areas that lack clarity. "
        "If a file is good, you don't need to mention it."
    )
    
    request = CodeRequest(prompt=prompt, files={"repository_context": file_contents})
    
    report = ""
    with console.status("[bold yellow]AI is reviewing your code...[/bold yellow]"):
        async with AIService(session.config) as ai_service:
            async for chunk in ai_service.stream_generate(request):
                report += chunk
                
    console.print(Panel(Syntax(report, "markdown", theme="github-dark"), title="Repository Scan Report", border_style="blue"))