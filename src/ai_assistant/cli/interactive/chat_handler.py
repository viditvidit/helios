from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner
from rich.markdown import Markdown

from ...services.ai_service import AIService
from ...models.request import CodeRequest
from ...utils.parsing_utils import extract_code_blocks
from . import display

class ChatHandler:
    def __init__(self, session):
        self.session = session
        self.config = session.config
        self.console = display.console

    async def handle(self, message: str):
        """
        Handle a user's chat message using the RAG pipeline.
        """
        try:
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
                # Add a note that this is a relevant chunk
                context_files[file_path] += f"... (context from {file_path}) ...\n" + chunk['text'] + "\n\n"

            # 3. Add user's message to history and create the request
            self.session.conversation_history.append({"role": "user", "content": message})
            
            # The 'files' parameter now contains only the most relevant chunks
            request = CodeRequest(
                prompt=message,
                files=context_files,
                conversation_history=self.session.conversation_history.copy(),
            )

            await self._stream_and_process_response(request)

        except Exception as e:
            self.console.print(f"[bold red]Error handling chat message: {e}[/bold red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")

    async def _stream_and_process_response(self, request: CodeRequest):
        """Stream AI response and handle post-response actions."""
        response_content = ""
        is_first_chunk = True
        spinner = Spinner("dots", text=" Thinking...")
        live_panel = Panel(spinner, border_style="green", title="AI Assistant", title_align="left")

        try:
            with Live(live_panel, console=self.console, refresh_per_second=10, auto_refresh=True, vertical_overflow="visible") as live:
                async with AIService(self.config) as ai_service:
                    async for chunk in ai_service.stream_generate(request):
                        if is_first_chunk:
                            response_content = chunk.lstrip()
                            live.update(Panel(Markdown(response_content, style="default"), border_style="green", title="AI Assistant", title_align="left"))
                            is_first_chunk = False
                        else:
                            response_content += chunk
                            live.update(Panel(Markdown(response_content, style="default"), border_style="green", title="AI Assistant", title_align="left"))
            
            if is_first_chunk:
                self.console.print(Panel("[yellow]The AI did not provide a response. This could be due to a model issue or connection problem.[/yellow]", border_style="yellow"))
                return

            self.session.last_ai_response_content = response_content
            self.session.conversation_history.append({"role": "assistant", "content": response_content})

            code_blocks = extract_code_blocks(response_content)
            if code_blocks:
                display.show_code_suggestions()
        except Exception as e:
            self.console.print(f"[red]Error generating AI response: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")