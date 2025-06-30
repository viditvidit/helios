# src/ai_assistant/cli/interactive/chat_handler.py

import asyncio
import re
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner
from rich.markdown import Markdown
from rich.syntax import Syntax
import questionary
from typing import Optional

from ...services.ai_service import AIService
from ...models.request import CodeRequest
from ...utils.parsing_utils import extract_code_blocks
from ...utils.file_utils import build_repo_context, FileUtils
from ...logic.agent.planner import Planner
from ...logic.agent import agent_main

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

    async def _classify_intent(self, message: str) -> dict:
        """Uses an AI call to classify the user's intent."""
        
        planner = Planner(self.session)
        formatted_tools = planner._format_tools_for_prompt()

        intent_prompt = (
            "You are an intent detection expert for a command-line AI assistant. "
            "Your task is to determine if a user's request can be handled by a simple chat response or if it requires a complex, multi-step execution plan using a set of available tools. "
            "A complex task involves actions like creating/modifying files, running shell commands, or interacting with git.\n\n"
            "**Available Tools:**\n"
            f"{formatted_tools}\n\n"
            "**User Request:**\n"
            f'"{message}"\n\n'
            "**Analysis:**\n"
            "1.  **Simple Chat:** The request is a question, a request for explanation, a simple code generation for a single file without saving it, or a general conversation. It can be answered in one go.\n"
            "2.  **Complex Task:** The request implies a sequence of actions. It mentions creating directories, running installers (like npm or pip), generating multiple files and saving them, committing to git, pushing to GitHub, or a combination of these. If the user asks to 'create a project', 'refactor this into a new structure', 'set up a new service', or 'modularize this code', it's a complex task.\n\n"
            "Based on your analysis, respond with ONLY a JSON object with one of two formats:\n"
            '1. For a simple chat: `{"intent": "simple_chat"}`\n'
            '2. For a complex task: `{"intent": "complex_task"}`\n'
            "Your JSON response:"
        )
        
        request = CodeRequest(prompt=intent_prompt)
        response_json_str = ""
        try:
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    response_json_str += chunk
            
            # The AI might add markdown fences or other text. Find the JSON object.
            match = re.search(r'```json\s*(\{.*?\})\s*```', response_json_str, re.DOTALL)
            json_text = ""
            if match:
                json_text = match.group(1)
            else:
                # If no markdown fence, find the first '{' and last '}'
                start = response_json_str.find('{')
                end = response_json_str.rfind('}')
                if start != -1 and end != -1:
                    json_text = response_json_str[start:end+1]
            
            if json_text:
                return json.loads(json_text)
            else:
                raise json.JSONDecodeError("No JSON object found", response_json_str, 0)

        except (json.JSONDecodeError, TypeError):
            # Default to simple_chat if parsing fails, which is a safe fallback.
            console.print("[dim]Intent classification failed. Defaulting to chat mode.[/dim]")
            return {"intent": "simple_chat"}

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

    async def _stream_and_process_response(self, request: CodeRequest):
        """
        A dedicated coroutine to wrap the async generator and handle the streaming logic.
        This is the correct pattern for use with asyncio.create_task.
        """
        response_content = ""
        
        try:
            markdown_renderable = Markdown("", code_theme="vim")
            with Live(markdown_renderable, console=console, refresh_per_second=10, vertical_overflow="visible") as live:
                with console.status("[dim]Thinking...[/dim]", spinner="point"):
                    async with AIService(self.config) as ai_service:
                        async for chunk in ai_service.stream_generate(request):
                            if self._stop_generation:
                                raise asyncio.CancelledError
                            response_content += str(chunk)
                            markdown_renderable.text = response_content
            
            self.session.last_ai_response_content = response_content
            self.session.conversation_history.append({"role": "assistant", "content": response_content})
            await self._handle_code_response(response_content)
        except asyncio.CancelledError:
            # Don't print a message here, the stop_generation method does it.
            pass
        except Exception as e:
            console.print(f"[bold red]Error during response generation: {e}[/bold red]")


    async def handle(self, message: str, session):
        """Main message handler with intent detection."""
        try:
            self._stop_generation = False
            
            # --- INTENT DETECTION ---
            with console.status("[dim]Analyzing request...[/dim]"):
                intent_result = await self._classify_intent(message)
            intent = intent_result.get("intent")

            if intent == "complex_task":
                console.print("\n[bold cyan]Complex task detected. Engaging agent...[/bold cyan]\n")
                await agent_main.run_agentic_workflow(session, message, interactive=False)
                return

            # --- REGULAR CHAT FLOW (if intent is simple_chat or fallback) ---
            
            # --- Robust @mention Logic with File Finder ---
            mentioned_context = {}
            mentions = re.findall(r'@([^\s]+)', message)
            
            if mentions:
                console.print("[dim]Processing @mentions...[/dim]")
                for mention in mentions:
                    # First check if it's a directory path
                    dir_path = self.config.work_dir / mention
                    if dir_path.is_dir():
                        console.print(f" [dim]Adding context from directory: {mention}[/dim]")
                        try:
                            # Use build_repo_context to get all files in the directory
                            dir_context = build_repo_context(dir_path, self.config)
                            for file_path, content in dir_context.items():
                                relative_path = str(Path(file_path).relative_to(self.config.work_dir))
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

    async def _handle_ai_response(self, response_content: str):
        """Process AI response and handle any code blocks or file operations."""
        self.session.last_ai_response_content = response_content
        
        # Check if the response contains code blocks that might need to be applied
        code_blocks = extract_code_blocks(response_content)
        if code_blocks:
            # Check if any code blocks have file paths (indicating they should be saved)
            has_file_paths = any(block.get('filepath') for block in code_blocks)
            
            if has_file_paths:
                console.print("\n[yellow]💡 AI has suggested code changes.[/yellow]")
                console.print("[dim]Use /apply to review and apply changes, or /save <filename> to save manually.[/dim]")
                # DO NOT automatically apply - let user decide
            else:
                console.print("\n[dim]💡 Code generated. Use /save <filename> to save if needed.[/dim]")