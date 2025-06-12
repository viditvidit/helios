import asyncio
import re
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner
from rich.markdown import Markdown
from rich.syntax import Syntax
import questionary
from typing import Optional, List

from ...services.ai_service import AIService
from ...models.request import CodeRequest
from ...utils.parsing_utils import extract_code_blocks
from ...utils.file_utils import build_repo_context, FileUtils
from . import display

console = Console()

class ChatHandler:
    def __init__(self, session):
        self.session = session
        self.config = session.config
        self._stop_generation = False
        self._generation_task: Optional[asyncio.Task] = None

    def stop_generation(self):
        self._stop_generation = True
        if self._generation_task and not self._generation_task.done():
            self._generation_task.cancel()
            console.print("\n[yellow]Stopping generation...[/yellow]")

    async def _find_file_in_project(self, filename: str) -> Optional[Path]:
        """Searches for a file in the project directory."""
        # Use Path.glob to find the file recursively
        matches = list(self.config.work_dir.glob(f"**/{filename}"))
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            # If multiple matches, ask the user to clarify
            try:
                chosen_path_str = await questionary.select(
                    f"Found multiple files named '{filename}'. Please choose one:",
                    choices=[str(p.relative_to(self.config.work_dir)) for p in matches]
                ).ask_async()
                return self.config.work_dir / chosen_path_str if chosen_path_str else None
            except Exception:
                return None # User cancelled
        return None

    async def _handle_code_response(self, response_content: str):
        # ... (This method is unchanged from the previous correct version)
        pass

    async def _stream_and_process_response(self, request: CodeRequest):
        """
        A dedicated coroutine to wrap the async generator and handle the streaming logic.
        This is the correct pattern for use with asyncio.create_task.
        """
        response_content = ""
        live_panel = Panel(Spinner("dots", text=" Thinking..."), border_style="green")
        
        try:
            async with AIService(self.config) as ai_service:
                with Live(live_panel, console=console, refresh_per_second=10, vertical_overflow="visible") as live:
                    async for chunk in ai_service.stream_generate(request):
                        if self._stop_generation:
                            raise asyncio.CancelledError
                        response_content += str(chunk)
                        live.update(Panel(Markdown(response_content, code_theme="monokai"), border_style="green", title="AI Assistant"))
            
            self.session.last_ai_response_content = response_content
            self.session.conversation_history.append({"role": "assistant", "content": response_content})
            await self._handle_code_response(response_content)
        except asyncio.CancelledError:
            # Don't print a message here, the stop_generation method does it.
            pass
        except Exception as e:
            console.print(f"[bold red]Error during response generation: {e}[/bold red]")


    async def handle(self, message: str, session):
        """Main message handler with corrected @mention and AIService usage."""
        try:
            self._stop_generation = False
            
            # --- Robust @mention Logic with File Finder ---
            mentioned_context = {}
            mentions = re.findall(r'@([^\s]+)', message)
            
            if mentions:
                console.print("[dim]Processing @mentions...[/dim]")
                for mention in mentions:
                    # First check if it's a directory path
                    dir_path = self.config.work_dir / mention
                    if dir_path.is_dir():
                        console.print(f"  [dim]Adding context from directory: {mention}[/dim]")
                        try:
                            # Use build_repo_context to get all files in the directory
                            dir_context = build_repo_context(dir_path, self.config)
                            for file_path, content in dir_context.items():
                                relative_path = str(file_path.relative_to(self.config.work_dir))
                                mentioned_context[relative_path] = content
                        except Exception as e:
                            console.print(f"[yellow]Warning: Could not read directory {mention}: {e}[/yellow]")
                    else:
                        # Check if it's a direct file path
                        file_path = self.config.work_dir / mention
                        if file_path.is_file():
                            console.print(f"  [dim]Adding context from file: {mention}[/dim]")
                            try:
                                content = await self.session.file_service.read_file(file_path)
                                mentioned_context[mention] = content
                            except Exception as e:
                                console.print(f"[yellow]Warning: Could not read file {mention}: {e}[/yellow]")
                        else:
                            # Try to find the file using fuzzy search
                            found_path = await self._find_file_in_project(mention)
                            if found_path:
                                console.print(f"  [dim]Adding context from file: {found_path.relative_to(self.config.work_dir)}[/dim]")
                                try:
                                    content = await self.session.file_service.read_file(found_path)
                                    mentioned_context[str(found_path.relative_to(self.config.work_dir))] = content
                                except Exception as e:
                                    console.print(f"[yellow]Warning: Could not read mentioned file {mention}: {e}[/yellow]")
                            else:
                                console.print(f"[yellow]Warning: Mentioned file '{mention}' not found in project.[/yellow]")

            # Semantic search for supplemental context
            rag_context = {}
            with console.status("[dim]Searching for relevant code snippets...[/dim]"):
                relevant_chunks = self.session.vector_store.search(message, k=5)
                for chunk in relevant_chunks:
                    if chunk['file_path'] not in mentioned_context:
                        if chunk['file_path'] not in rag_context:
                            rag_context[chunk['file_path']] = ""
                        rag_context[chunk['file_path']] += f"\n... (Snippet) ...\n{chunk['text']}\n"
            
            final_context = {**rag_context, **mentioned_context}

            session.conversation_history.append({"role": "user", "content": message})
            
            request = CodeRequest(
                prompt=message,
                files=final_context,
                repository_files=list(session.current_files.keys()),
                conversation_history=session.conversation_history.copy(),
            )

            # --- DEFINITIVE FIX for asyncio TypeError ---
            # Create a task for the wrapper coroutine, not the generator itself.
            self._generation_task = asyncio.create_task(self._stream_and_process_response(request))
            await self._generation_task

        except asyncio.CancelledError:
             # This is expected when Ctrl+C is pressed, so we can ignore it here.
            pass
        except Exception as e:
            console.print(f"[bold red]Error handling chat message: {e}[/bold red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")