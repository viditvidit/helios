import asyncio
import re
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from ...utils.file_utils import FileUtils
from ...services.ai_service import AIService
from ...models.request import CodeRequest
from ...utils.parsing_utils import extract_file_content_from_response

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

    async def _handle_file_apply_logic(self, response_content: str):
        """Interactively handles the diff and apply logic for file blocks."""
        file_blocks = extract_file_content_from_response(response_content)
        if not file_blocks:
            return
        console.print("\n[bold cyan]AI has suggested file changes. Review now or use /apply later.[/bold cyan]")

    async def _stream_and_render_response(self, request: CodeRequest):
        """
        Streams the AI response to a buffer while showing a spinner,
        then renders the complete, final response beautifully.
        """
        response_content = ""
        status_task = None
        try:
            status_task = asyncio.create_task(self._show_status("[cyan]Helios is thinking[/cyan]"))
            
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    if self._stop_generation:
                        raise asyncio.CancelledError
                    response_content += str(chunk)
            
            if status_task and not status_task.done():
                status_task.cancel()
                try:
                    await status_task
                except asyncio.CancelledError:
                    pass
            
            if not response_content:
                return

            self.session.last_ai_response_content = response_content
            self.session.conversation_history.append({"role": "assistant", "content": response_content})
            
            file_blocks = extract_file_content_from_response(response_content)
            
            console.print()

            if not file_blocks:
                console.print(Markdown(response_content, code_theme="vim"))
            else:
                for block in file_blocks:
                    syntax_lang = FileUtils.get_language_from_extension(Path(block['filename']).suffix)
                    
                    syntax_content = Syntax(
                        block['code'], 
                        lexer=syntax_lang or "python",
                        theme="vim",
                        line_numbers=True,
                        word_wrap=True,
                        background_color="default"
                    )
                    
                    console.print(Panel(
                        syntax_content,
                        title=f"[bold cyan]File: {block['filename']}[/bold cyan]",
                        border_style="blue",
                        expand=False,
                        padding=(1, 2)
                    ))
            
            if file_blocks:
                console.print("\n[yellow]AI has suggested file changes. Use `/apply` to review and apply them.[/yellow]")

        except asyncio.CancelledError:
            if status_task and not status_task.done():
                status_task.cancel()
                try:
                    await status_task
                except asyncio.CancelledError:
                    pass
            console.print()
        except Exception as e:
            if status_task and not status_task.done():
                status_task.cancel()
                try:
                    await status_task
                except asyncio.CancelledError:
                    pass
            console.print(f"[bold red]Error during response generation: {e}[/bold red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")

    async def _show_status(self, message):
        """Show status spinner that can be cancelled"""
        try:
            with console.status(message, spinner="point", spinner_style="cyan"):
                while True:
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    async def handle(self, message: str, session):
        """Main message handler with robust path detection and multimodal support."""
        try:
            self._stop_generation = False
            
            mentioned_context = {}
            
            path_pattern = re.compile(r"""
                @([^\s]+) |                                      # @-mentions (Group 1)
                (['"]) (.*?) \2 |                                  # Quoted paths (Group 2, 3)
                (?<!\S) ( [^\s]*[/\\][^\s]* | [^\s]+\.[^\s]+ ) (?=\s|$) # Bare paths with slashes or a dot (Group 4)
            """, re.VERBOSE)
            
            found_paths = [m.group(1) or m.group(3) or m.group(4) for m in path_pattern.finditer(message)]

            if found_paths:
                console.print("[dim]Processing mentions...[/dim]")
                for mention in set(found_paths):
                    mention = mention.lstrip('@')
                    possible_path = Path(mention).expanduser()
                    if not possible_path.is_absolute():
                        full_path = self.config.work_dir / mention
                    else:
                        full_path = possible_path

                    if not full_path.exists():
                        console.print(f"[yellow]Warning: Mentioned path '{mention}' does not exist.[/yellow]")
                        continue

                    if full_path.is_dir():
                        console.print(f" [dim]Adding context from directory: {mention}[/dim]")
                        dir_context = build_repo_context(full_path, self.config)
                        for file_path, content in dir_context.items():
                            relative_path = str(Path(file_path).relative_to(self.config.work_dir))
                            mentioned_context[relative_path] = content
                    elif full_path.is_file():
                        console.print(f" [dim]Adding context from file: {mention}[/dim]")
                        try:
                            content = await self.session.file_service.read_file(full_path)
                            mentioned_context[str(full_path.relative_to(self.config.work_dir))] = content
                        except Exception as e:
                            console.print(f"[yellow]Warning: Could not read file {mention}: {e}[/yellow]")

            rag_context = {}
            with console.status("[dim]Searching for relevant code snippets...[/dim]", spinner="point", spinner_style="[dim]cyan[/dim]"):
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

            self._generation_task = asyncio.create_task(self._stream_and_render_response(request))
            await self._generation_task

        except re.error as e:
            console.print(f"[bold red]Regex Error: {e}[/bold red]")
        except Exception as e:
            console.print(f"[bold red]Error handling chat message: {e}[/bold red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")