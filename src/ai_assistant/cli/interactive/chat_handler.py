from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
import asyncio
import threading
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

    def stop_generation(self):
        """Stop the current AI response generation."""
        self._stop_generation = True
        if self._generation_task and not self._generation_task.done():
            self._generation_task.cancel()

    def _enhance_markdown_with_syntax_highlighting(self, content: str):
        """Replace code blocks in markdown with syntax-highlighted versions."""
        # Pattern to match code blocks with optional language specification
        code_block_pattern = r'```(\w+)?\n(.*?)\n```'
        
        def replace_code_block(match):
            language = match.group(1) or "text"
            code = match.group(2)
            
            # Create syntax-highlighted code
            try:
                syntax = Syntax(code, language, theme="monokai", line_numbers=False, word_wrap=True)
                return str(syntax)
            except Exception:
                # Fallback to plain text if syntax highlighting fails
                return f"```{language}\n{code}\n```"
        
        # Replace code blocks with syntax-highlighted versions
        enhanced_content = re.sub(code_block_pattern, replace_code_block, content, flags=re.DOTALL)
        return enhanced_content

    async def handle(self, message: str):
        """Handle a user's chat message using the RAG pipeline."""
        try:
            self._stop_generation = False
            
            # 1. Retrieve relevant context from the vector store
            with self.console.status("[dim]Searching for relevant context...[/dim]"):
                relevant_chunks = self.session.vector_store.search(message)

            if not relevant_chunks:
                self.console.print("[yellow]Could not find specific context in the index. The AI will answer from general knowledge.[/yellow]")
            
            # 2. Assemble the context from the retrieved chunks
            context_files = {}
            for chunk in relevant_chunks:
                file_path = chunk['file_path']
                if file_path not in context_files:
                    context_files[file_path] = ""
                context_files[file_path] += f"... (context from {file_path}) ...\n" + chunk['text'] + "\n\n"

            # 3. Add user's message to history and create the request
            self.session.conversation_history.append({"role": "user", "content": message})
            
            request = CodeRequest(
                prompt=message,
                files=context_files,
                conversation_history=self.session.conversation_history.copy(),
            )

            # Create and track the generation task
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
        spinner = Spinner("dots", text=" Thinking...")
        live_panel = Panel(spinner, border_style="green", title="AI Assistant (Press Ctrl+C to stop)", title_align="left")

        try:
            with Live(live_panel, console=self.console, refresh_per_second=10, auto_refresh=True, vertical_overflow="visible") as live:
                async with AIService(self.config) as ai_service:
                    async for chunk in ai_service.stream_generate(request):
                        if self._stop_generation:
                            raise asyncio.CancelledError("Generation stopped by user")
                            
                        if is_first_chunk:
                            response_content = chunk.lstrip()
                            # Check if content contains complete code blocks for syntax highlighting
                            if '```' in response_content and response_content.count('```') >= 2:
                                enhanced_content = self._enhance_markdown_with_syntax_highlighting(response_content)
                                live.update(Panel(Markdown(enhanced_content, style="default"), border_style="green", title="AI Assistant (Press Ctrl+C to stop)", title_align="left"))
                            else:
                                live.update(Panel(Markdown(response_content, style="default"), border_style="green", title="AI Assistant (Press Ctrl+C to stop)", title_align="left"))
                            is_first_chunk = False
                        else:
                            response_content += chunk
                            # Only apply syntax highlighting when we have complete code blocks
                            if '```' in response_content and response_content.count('```') >= 2:
                                enhanced_content = self._enhance_markdown_with_syntax_highlighting(response_content)
                                live.update(Panel(Markdown(enhanced_content, style="default"), border_style="green", title="AI Assistant (Press Ctrl+C to stop)", title_align="left"))
                            else:
                                live.update(Panel(Markdown(response_content, style="default"), border_style="green", title="AI Assistant (Press Ctrl+C to stop)", title_align="left"))
            
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
                self.console.print(Panel(
                    "[yellow]⏱️ The AI model is taking longer than expected to respond.\n"
                    "This might be due to:\n"
                    "• Large context size requiring more processing time\n"
                    "• Model still loading or warming up\n"
                    "• Try reducing the context or using a smaller model[/yellow]",
                    border_style="yellow",
                    title="Timeout"
                ))
            else:
                self.console.print(f"[red]Error generating AI response: {e}[/red]")
                import traceback
                self.console.print(f"[dim]{traceback.format_exc()}[/dim]")