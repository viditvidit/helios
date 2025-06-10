import click  # <-- FIX: Added missing import for click.confirm
from pathlib import Path
from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner

from ...services.ai_service import AIService
from ...models.request import CodeRequest
from ...utils.parsing_utils import build_file_tree, extract_code_blocks
from . import display, stubs

class ChatHandler:
    def __init__(self, session):
        self.session = session
        self.config = session.config
        self.console = display.console

    async def handle(self, message: str):
        """Handle a user's chat message."""
        try:
            repo_context = await self.session.github_service.get_repository_context(Path.cwd())
            
            # This import needs to be relative to the cli/ folder
            from ..commands import CodeCommands
            full_repo_context = CodeCommands.build_repo_context(str(Path.cwd()))
            
            combined_files = {**full_repo_context, **self.session.current_files}
            file_count = len(full_repo_context)
            total_lines = sum(len(content.split('\n')) for content in full_repo_context.values())

            context_summary = (
                f"Repository Context:\n"
                f"- Current Branch: {repo_context.get('current_branch', 'N/A')}\n"
                f"- Status: {repo_context.get('status', 'N/A')}\n"
                f"- Recent Commits: {', '.join(repo_context.get('recent_commits', []))}\n"
                f"- Total Files: {file_count} files ({total_lines} total lines)\n"
                f"- File Structure: {build_file_tree(full_repo_context)}\n\n"
            )
            
            if self.session.conversation_history:
                # Using a more descriptive message
                context_summary += "Previous conversation context is included.\n\n"
            
            augmented_prompt = f"{context_summary}User Message: {message}"
            
            self.session.conversation_history.append({"role": "user", "content": message})
            
            request = CodeRequest(
                prompt=augmented_prompt,
                files=combined_files,
                conversation_history=self.session.conversation_history.copy(),
                git_context=str(repo_context)
            )
            
            await self._stream_and_process_response(request)

        except Exception as e:
            self.console.print(f"[bold red]Error handling chat message: {e}[/bold red]")

    async def _stream_and_process_response(self, request: CodeRequest):
        """Stream AI response and handle post-response actions."""
        # FIX: Re-introduced the streaming logic with rich.live.Live
        self.console.print("\n[bold green]AI Assistant[/bold green]:")
        
        response_content = ""
        try:
            with Live(Spinner("dots", text="Thinking..."), console=self.console, refresh_per_second=4, auto_refresh=True) as live:
                async with AIService(self.config) as ai_service:
                    # Use the streaming method, not the one-shot method
                    async for chunk in ai_service.stream_generate(request):
                        response_content += chunk
                        live.update(Panel(response_content, border_style="green"))

            # After the stream is complete, store the full response
            self.session.last_ai_response_content = response_content
            self.session.conversation_history.append({"role": "assistant", "content": response_content})

            # Check for code blocks and suggest actions
            code_blocks = extract_code_blocks(response_content)
            if code_blocks:
                display.show_code_suggestions()

            # Ask for repository review
            if click.confirm("Would you like to review repository changes (stage, commit, push) in the current repo?", default=False):
                await stubs.handle_repo_review(self.session)
                
        except Exception as e:
            self.console.print(f"[red]Error generating AI response: {e}[/red]")