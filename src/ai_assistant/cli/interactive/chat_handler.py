from pathlib import Path
from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner
from rich.markdown import Markdown

from ...services.ai_service import AIService
from ...models.request import CodeRequest
from ...utils.parsing_utils import build_file_tree, extract_code_blocks
from . import display

class ChatHandler:
    def __init__(self, session):
        self.session = session
        self.config = session.config
        self.console = display.console

    async def handle(self, message: str):
        """Handle a user's chat message using the full repository context."""
        try:
            repo_context_summary = await self.session.github_service.get_repository_context(Path.cwd())

            # The full file content is now in `self.session.current_files`
            full_repo_files_context = self.session.current_files

            # Construct a high-level summary for the prompt, not the full content
            file_count = len(full_repo_files_context)
            total_lines = sum(len(content.split('\n')) for content in full_repo_files_context.values())

            context_summary_for_prompt = (
                f"Repository Context:\n"
                f"- Current Branch: {repo_context_summary.get('current_branch', 'N/A')}\n"
                f"- Git Status: {repo_context_summary.get('status', 'N/A')}\n"
                f"- Total Files in Context: {file_count} files ({total_lines} total lines)\n"
                f"- File Structure Overview: {build_file_tree(full_repo_files_context)}\n\n"
            )

            # Add conversation history to the prompt
            if self.session.conversation_history:
                context_summary_for_prompt += "Previous conversation history is included.\n\n"

            augmented_prompt = f"{context_summary_for_prompt}User Message: {message}"

            self.session.conversation_history.append({"role": "user", "content": message})

            request = CodeRequest(
                prompt=augmented_prompt,
                files=full_repo_files_context,  # Pass all file contents to the AI service
                conversation_history=self.session.conversation_history.copy(),
            )

            await self._stream_and_process_response(request)

        except Exception as e:
            self.console.print(f"[bold red]Error handling chat message: {e}[/bold red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")

    async def _stream_and_process_response(self, request: CodeRequest):
        """Stream AI response and handle post-response actions."""
        self.console.print("\n[bold green]AI Assistant[/bold green]:")
        response_content = ""
        # ** THE FIX **: Initialize a blank Panel for the Live display to manage.
        live_panel = Panel("", border_style="green")
        try:
            with Live(live_panel, console=self.console, refresh_per_second=10, auto_refresh=True, vertical_overflow="visible") as live:
                async with AIService(self.config) as ai_service:
                    async for chunk in ai_service.stream_generate(request):
                        response_content += chunk
                        # Update the live display with a new Panel containing the rendered Markdown
                        live.update(Panel(Markdown(response_content, style="default"), border_style="green"))

            self.session.last_ai_response_content = response_content
            self.session.conversation_history.append({"role": "assistant", "content": response_content})

            code_blocks = extract_code_blocks(response_content)
            if code_blocks:
                display.show_code_suggestions()

        except Exception as e:
            self.console.print(f"[red]Error generating AI response: {e}[/red]")
            import traceback
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")