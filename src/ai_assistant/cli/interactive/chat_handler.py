from pathlib import Path
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
        Handle a user's chat message by passing raw context to the AI service.
        """
        try:
            # Gather raw data for the AI service to format
            git_context_dict = await self.session.github_service.get_repository_context(Path.cwd())
            full_repo_files_context = self.session.current_files

            git_context_str = (
                f"Current Branch: {git_context_dict.get('current_branch', 'N/A')}\n"
                f"Status:\n{git_context_dict.get('status', 'N/A') or 'Clean'}"
            )

            self.session.conversation_history.append({"role": "user", "content": message})

            # Create a clean request object. The AIService is responsible for building the final prompt.
            request = CodeRequest(
                prompt=message,
                files=full_repo_files_context,
                git_context=git_context_str,
                conversation_history=self.session.conversation_history.copy(),
            )

            await self._stream_and_process_response(request)

        except Exception as e:
            self.console.print(f"[bold red]Error handling chat message: {e}[/bold red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")

    async def _stream_and_process_response(self, request: CodeRequest):
        """Stream AI response and handle post-response actions, with a loading spinner."""
        response_content = ""
        is_first_chunk = True

        # --- THE FIX ---
        # 1. Create a spinner to be displayed initially.
        spinner = Spinner("dots", text=" Thinking...")

        # 2. Create the Panel with the spinner as its content.
        live_panel = Panel(spinner, border_style="green", title="AI Assistant", title_align="left")

        try:
            with Live(live_panel, console=self.console, refresh_per_second=10, auto_refresh=True, vertical_overflow="visible") as live:
                async with AIService(self.config) as ai_service:
                    async for chunk in ai_service.stream_generate(request):
                        # 3. On the very first chunk of text, replace the spinner with the text.
                        if is_first_chunk:
                            response_content = chunk.lstrip() # Remove leading whitespace
                            # Replace the spinner with a Markdown object INSIDE the panel
                            live.update(Panel(Markdown(response_content, style="default"), border_style="green", title="AI Assistant", title_align="left"))
                            is_first_chunk = False
                        else:
                            response_content += chunk
                            # Update the existing Markdown object by re-creating it INSIDE the panel
                            live.update(Panel(Markdown(response_content, style="default"), border_style="green", title="AI Assistant", title_align="left"))
            
            # After the live display is finished, handle the final state.
            if is_first_chunk:
                self.console.print(Panel("[yellow]The AI did not provide a response. This could be due to a model issue or a very large context.[/yellow]", border_style="yellow"))
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