from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner
from rich.markdown import Markdown
from pathlib import Path
from typing import Optional
import asyncio
import re

from ...services.ai_service import AIService
from ...models.request import CodeRequest
from ...utils.parsing_utils import extract_code_blocks
from . import display

class ChatHandler:
    def __init__(self, session):
        self.session = session
        self.config = session.config
        self.console = display.console
        self._stop_generation = False
        self._generation_task = None
        self._indexed_file_paths = None

    def stop_generation(self):
        """Stop the current AI response generation."""
        self._stop_generation = True
        if self._generation_task and not self._generation_task.done():
            self._generation_task.cancel()

    def _extract_filenames_from_message(self, message: str) -> list[str]:
        """Extracts potential file paths from a user's message."""
        pattern = r'[\w/.-]+\.(?:py|js|ts|java|cpp|c|go|rs|rb|html|css|scss|json|yaml|yml|md|txt|sh|toml|ini|cfg)\b'
        return re.findall(pattern, message)

    def _resolve_filename_to_full_path(self, filename: str) -> Optional[str]:
        """Searches the indexed file manifest to find the full relative path for a given filename."""
        if self._indexed_file_paths is None:
            if self.session.vector_store.metadata:
                self._indexed_file_paths = {item['file_path'] for item in self.session.vector_store.metadata}
            else: self._indexed_file_paths = set()
        basename = Path(filename).name
        matches = [p for p in self._indexed_file_paths if p.endswith(f'/{basename}') or p == basename]
        if len(matches) == 1: return matches[0]
        elif len(matches) > 1:
            self.console.print(f"[yellow]Ambiguous file mention: '{basename}' matched {len(matches)} files. Please be more specific.[/yellow]")
            return None
        return None

    async def handle(self, message: str):
        """
        Handles a user's chat message using a hybrid context strategy for speed and accuracy.
        """
        try:
            self._stop_generation = False
            final_context_files = {}

            # --- Stage 1: Prioritize Explicitly Mentioned Files ---
            # These are always included in full.
            mentioned_files = self._extract_filenames_from_message(message)
            if mentioned_files:
                self.console.print(f"[dim]Found file mentions: {', '.join(mentioned_files)}[/dim]")
                for file_path_str in mentioned_files:
                    full_path = self._resolve_filename_to_full_path(file_path_str)
                    if full_path:
                        try:
                            content = await self.session.file_service.read_file(Path(full_path))
                            final_context_files[full_path] = content
                            self.console.print(f"[dim]Loaded full context for: {full_path}[/dim]")
                        except Exception as e:
                            self.console.print(f"[yellow]Warning: Could not read file '{full_path}': {e}[/yellow]")
                    else:
                        self.console.print(f"[yellow]Warning: Could not find '{file_path_str}' in the project index.[/yellow]")

            # --- Stage 2: Use Semantic Search for Supplemental Context ---
            # Find relevant snippets from the rest of the repository.
            with self.console.status("[dim]Searching for relevant code snippets...[/dim]", spinner="aesthetic"):
                relevant_chunks = self.session.vector_store.search(message, k=10)

            for chunk in relevant_chunks:
                file_path = chunk['file_path']
                # Add the snippet only if the entire file wasn't already included
                if file_path not in final_context_files:
                    if file_path not in final_context_files:
                        final_context_files[file_path] = "" # Initialize if new
                    # Append snippet with context marker
                    final_context_files[file_path] += f"\n... (Relevant Snippet) ...\n{chunk['text']}\n"
            
            if not final_context_files:
                self.console.print("[yellow]Could not find specific context. The AI will answer from general knowledge.[/yellow]")

            # --- Stage 3: Assemble the Final Request ---
            self.session.conversation_history.append({"role": "user", "content": message})
            
            request = CodeRequest(
                prompt=message,
                files=final_context_files, # The combined, intelligent context
                repository_files=list(self.session.current_files.keys()), # The full file list for the tree view
                conversation_history=self.session.conversation_history.copy(),
            )

            self._generation_task = asyncio.create_task(self._stream_and_process_response(request))
            await self._generation_task

        except asyncio.CancelledError:
            self.console.print("\n[yellow]Response generation stopped by user.[/yellow]")
        except Exception as e:
            self.console.print(f"[bold red]Error handling chat message: {e}[/bold red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")

    async def _stream_and_process_response(self, request: CodeRequest):
        """Stream AI response and handle post-response actions."""
        response_content = ""
        is_first_chunk = True
        spinner = Spinner("bouncingBall", text=" Thinking...")
        live_panel = Panel(spinner, border_style="green", title="AI Assistant (Press Ctrl+C to stop)", title_align="left")

        try:
            with Live(live_panel, console=self.console, refresh_per_second=10, auto_refresh=True, vertical_overflow="visible") as live:
                async with AIService(self.config) as ai_service:
                    async for chunk in ai_service.stream_generate(request):
                        if self._stop_generation:
                            raise asyncio.CancelledError("Generation stopped by user")
                        if is_first_chunk:
                            response_content = chunk.lstrip()
                            is_first_chunk = False
                        else:
                            response_content += chunk
                        markdown_view = Markdown(response_content, code_theme="monokai", inline_code_theme="monokai")
                        live.update(Panel(markdown_view, border_style="green", title="AI Assistant (Press Ctrl+C to stop)", title_align="left"))
            
            if is_first_chunk and not self._stop_generation:
                self.console.print(Panel("[yellow]The AI did not provide a response. This could be due to a model issue or connection problem.[/yellow]", border_style="yellow"))
                return

            if not self._stop_generation:
                self.session.last_ai_response_content = response_content
                self.session.conversation_history.append({"role": "assistant", "content": response_content})
                code_blocks = extract_code_blocks(response_content)
                if code_blocks:
                    display.show_code_suggestions()
                    
        except asyncio.CancelledError:
            if response_content:
                self.console.print(f"\n[yellow]Partial response received before stopping:[/yellow]")
                self.session.last_ai_response_content = response_content
            raise
        except Exception as e:
            if "timed out" in str(e).lower():
                self.console.print(Panel("[yellow]⏱️ The AI model is taking longer than expected to respond.[/yellow]", border_style="yellow", title="Timeout"))
            else:
                self.console.print(f"[red]Error generating AI response: {e}[/red]")
                import traceback
                self.console.print(f"[dim]{traceback.format_exc()}[/dim]")