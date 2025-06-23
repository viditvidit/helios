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

import base64
import mimetypes
from typing import Optional

from ...services.ai_service import AIService
from ...models.request import CodeRequest, ContentPart
from ...utils.parsing_utils import extract_code_blocks
from ...utils.file_utils import build_repo_context, FileUtils

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
        """Interactively handles code blocks in the AI's response."""
        code_blocks = [b for b in extract_code_blocks(response_content) if b.get('filename')]
        if not code_blocks: return

        console.print("\n[bold cyan]AI has suggested code changes. Reviewing now...[/bold cyan]")
        
        files_to_apply = {}
        apply_all, skip_all = False, False

        for block in code_blocks:
            if skip_all: break
            filename, new_code = block['filename'], block['code']
            file_path = Path.cwd() / filename
            
            diff_text = FileUtils.generate_diff(
                await self.session.file_service.read_file(file_path) if file_path.exists() else "",
                new_code,
                filename
            )
            console.print(Panel(Syntax(diff_text, "diff", theme="vim"), title=f"Changes for {filename}", 
                                border_style="#3776A1"))
            
            if apply_all:
                files_to_apply[filename] = new_code
                continue

            choice = await questionary.select(
                f"Apply changes to {filename}?",
                choices=["Yes", "No", "Apply All Remaining", "Skip All Remaining"],
                use_indicator=True,
                style=questionary.Style([
                    ('selected', 'bg:#003A6B #89CFF1'),
                    ('pointer', '#6EB1D6 bold'),
                    ('instruction', '#5293BB'),
                    ('answer', '#89CFF1 bold'),
                    ('question', '#6EB1D6 bold')
                ])
            ).ask_async()

            if choice == "Yes": files_to_apply[filename] = new_code
            elif choice == "Apply All Remaining": apply_all = True; files_to_apply[filename] = new_code
            elif choice == "Skip All Remaining": skip_all = True
        
        if not files_to_apply: return console.print("[yellow]No changes were applied.[/yellow]")

        for filename, code in files_to_apply.items():
            try:
                await self.session.file_service.write_file(Path.cwd() / filename, code)
                console.print(f"[green]✓ Applied changes to {filename}[/green]")
            except Exception as e:
                console.print(f"[red]Error applying changes to {filename}: {e}[/red]")

    async def _process_input_to_content_parts(self, message: str) -> list[ContentPart]:
        """
        Processes user input string into a list of ContentParts.
        Recognizes local file paths as images and text as text.
        """
        parts = []
        tokens = message.split()
        text_buffer = []

        for token in tokens:
            path = Path(token).expanduser()
            if path.is_file():
                if text_buffer:
                    parts.append(ContentPart(type='text', content=" ".join(text_buffer)))
                    text_buffer = []
                
                mime_type, _ = mimetypes.guess_type(path)
                if mime_type and mime_type.startswith('image/'):
                    console.print(f"[dim]Processing image: {path.name}[/dim]")
                    try:
                        with open(path, "rb") as image_file:
                            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        parts.append(ContentPart(type='image', content=encoded_string, mime_type=mime_type))
                    except Exception as e:
                        console.print(f"[red]Error reading image file {path}: {e}[/red]")
                else: # It's a file but not an image, treat as a text token
                    text_buffer.append(token)
            else:
                text_buffer.append(token)
        
        if text_buffer:
            parts.append(ContentPart(type='text', content=" ".join(text_buffer)))
        
        return parts

    async def _stream_and_process_response(self, request: CodeRequest):
        """
        A dedicated coroutine to wrap the async generator and handle the streaming logic.
        This is the correct pattern for use with asyncio.create_task.
        """
        response_content = ""
        
        try:
            async with AIService(self.config) as ai_service:
                with Live(Spinner("point", text="Thinking"), console=console, refresh_per_second=10, vertical_overflow="visible") as live:
                    async for chunk in ai_service.stream_generate(request):
                        if self._stop_generation:
                            raise asyncio.CancelledError
                        response_content += str(chunk)
                        # Only update the live display, don't create new panels
                        live.update(Markdown(response_content, code_theme="vim"))
                
                # Print the final response after streaming is complete
                console.print(Markdown(response_content, code_theme="vim"))
            
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

            prompt_parts = await self._process_input_to_content_parts(message)
            if not prompt_parts: return

            has_image = any(p.type == 'image' for p in prompt_parts)
            current_model_name = self.config.get_current_model().name
            # A simple check, assuming vision models have 'llava' or 'vision' in their name.
            # This should be made more robust in a real application.
            is_vision_model = 'llava' in current_model_name or 'vision' in current_model_name
            
            if has_image and not is_vision_model:
                console.print(Panel(
                    f"[yellow]Warning:[/yellow] An image was provided, but the current model ([bold]{current_model_name}[/bold]) may not be able to process it.\n"
                    "For best results, consider switching to a multimodal model (e.g., one with 'llava' in the name) using the `/model` command.",
                    border_style="yellow",
                    title="Model Capability Warning"
                ))

            text_for_history_and_rag = " ".join([p.content for p in prompt_parts if p.type == 'text'])
            session.conversation_history.append({"role": "user", "content": text_for_history_and_rag})
            
            # --- Robust @mention Logic with File Finder ---
            mentioned_context = {}
            mentions = re.findall(r'@([^\s]+)', message)
            
            if mentions:
                for mention in mentions:
                    # First check if it's a directory path
                    dir_path = self.config.work_dir / mention
                    if dir_path.is_dir():
                        console.print(f" [dim]Adding context from directory: {mention}[/dim]")
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
                            console.print(f" [dim]Adding context from file: {mention}[/dim]")
                            try:
                                content = await self.session.file_service.read_file(file_path)
                                mentioned_context[mention] = content
                            except Exception as e:
                                console.print(f"[yellow]Warning: Could not read file {mention}: {e}[/yellow]")
                        else:
                            # Try to find the file using fuzzy search
                            found_path = await self._find_file_in_project(mention)
                            if found_path:
                                console.print(f" [dim]Adding context from file: {found_path.relative_to(self.config.work_dir)}[/dim]")
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
                prompt=prompt_parts,
                files=final_context,
                repository_files=list(session.current_files.keys()),
                conversation_history=session.conversation_history.copy(),
            )

            self._generation_task = asyncio.create_task(self._stream_and_process_response(request))
            await self._generation_task

        except asyncio.CancelledError:
            pass
        except Exception as e:
            console.print(f"[bold red]Error handling chat message: {e}[/bold red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")

    async def _handle_ai_response(self, response_content: str):
        """Process AI response and handle any code blocks or file operations."""
        self.session.last_ai_response_content = response_content
        
        # Check if the response contains code blocks that might need to be applied
        code_blocks = extract_code_blocks(response_content)
        if code_blocks:
            # Check if any code blocks have file paths (indicating they should be saved)
            has_file_paths = any(block.get('filepath') for block in code_blocks)
            
            if has_file_paths:
                console.print("\n[yellow]AI has suggested code changes.[/yellow]")
                console.print("[dim]Use /apply to review and apply changes, or /save <filename> to save manually.[/dim]")
                # DO NOT automatically apply - let user decide
            else:
                console.print("\n[dim]Code generated. Use /save <filename> to save if needed.[/dim]")