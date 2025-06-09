import asyncio
import re
from pathlib import Path
from typing import List, Optional, Dict
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.live import Live
from rich.spinner import Spinner
import click

from ..core.config import Config
from ..services.ai_service import AIService
from ..services.file_service import FileService
from ..services.github_service import GitHubService, GitHubServiceError
from ..models.request import CodeRequest
from ..utils.file_utils import FileUtils
from ..utils.git_utils import GitUtils

console = Console()

class InteractiveMode:
    """Interactive chat mode for AI assistant"""
    
    def __init__(self, config: Config):
        self.config = config
        self.file_service = FileService(config)
        self.github_service = GitHubService(config, Path.cwd())
        self.conversation_history = []
        self.current_files = {}
        self.file_utils = FileUtils()
        self.last_ai_response_content: Optional[str] = None # To store last AI response
    
    async def start(self):
        """Start interactive mode"""
        console.print(Panel.fit(
            "[bold green]Interactive AI Assistant[/bold green]\n"
            "Type 'help' for commands, 'exit' to quit",
            title="Chat Mode"
        ))
        
        while True:
            try:
                user_input = Prompt.ask("\n[bold blue]You[/bold blue]")
                
                if user_input.lower() in ['exit', 'quit', 'q']:
                    break
                elif user_input.lower() == 'help':
                    self._show_help()
                elif user_input.startswith('/'):
                    await self._handle_command(user_input)
                else:
                    self.last_ai_response_content = None # Clear before new chat
                    await self._handle_chat(user_input)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
    
    def _show_help(self):
        """Show help information"""
        help_text = """
[bold]Available Commands:[/bold]
  - /file <path>              - Add an existing file to context.
  - /new <path>               - Create a new file in the repository.
  - /files                    - List files currently added to context.
  - /repo                     - Show repository statistics and overview.
  - /refresh                  - Refresh repository context for next message.
  - /clear                    - Clear conversation history and file context.
  - /model <name>             - Switch AI model.
  - /save_conversation <path> - Save conversation to file.
  - /save <filename>          - Save the first code block from the last AI response to a file.
  - /git_add <file1> [f2..]   - Stage specified file(s) for commit.
  - /git_commit <message>     - Commit staged changes with a commit message.
  - /git_push                 - Push committed changes to remote repository.
  - help                      - Show this help.
  - exit/quit/q               - Exit interactive mode.

[bold]Chat:[/bold]
Just type your message to chat with the AI. The assistant has full access to your repository
context and can help you understand, modify, and work with your codebase.
"""
        console.print(Panel(help_text, title="Help", border_style="green"))

    async def _add_file(self, file_path: str):
        """Add file to context"""
        try:
            path = Path(file_path)
            if not path.exists():
                console.print(f"[red]File not found: {file_path}[/red]")
                return
            
            content = await self.file_service.read_file(path)
            self.current_files[file_path] = content
            console.print(f"[green]Added file to context: {file_path}[/green]")
            
        except Exception as e:
            console.print(f"[red]Error adding file: {e}[/red]")
    
    def _list_files(self):
        """List files in current context"""
        if not self.current_files:
            console.print("[yellow]No files in context[/yellow]")
            return
        
        files_info = []
        for file_path, content in self.current_files.items():
            lines = len(content.split('\n'))
            files_info.append(f"- {file_path} ({lines} lines)")
        
        console.print(Panel(
            '\n'.join(files_info),
            title="Files in Context",
            border_style="blue"
        ))
    
    def _clear_history(self):
        """Clear conversation history"""
        self.conversation_history.clear()
        self.current_files.clear()
        console.print("[green]Conversation history cleared[/green]")
    
    def _switch_model(self, model_name: str):
        """Switch AI model"""
        if model_name in self.config.models:
            self.config.model_name = model_name
            console.print(f"[green]Switched to model: {model_name}[/green]")
        else:
            console.print(f"[red]Model not found: {model_name}[/red]")
            available = ', '.join(self.config.models.keys())
            console.print(f"Available models: {available}")
    
    async def _save_conversation(self, file_path: str):
        """Save conversation to file"""
        try:
            path = Path(file_path)
            content = self._format_conversation()
            await self.file_service.write_file(path, content)
            console.print(f"[green]Conversation saved to: {file_path}[/green]")
        except Exception as e:
            console.print(f"[red]Error saving conversation: {e}[/red]")
    
    def _extract_code_blocks(self, text: str) -> List[Dict[str, str]]:
        """
        Extracts code blocks from text.
        Looks for ```language filename="path/to/file.ext" ... or ```language path/to/file.ext ...
        Returns a list of dictionaries, each with 'language', 'filename', and 'code'.
        'filename' can be None if not found.
        """
        # Updated regex to include periods in the first token
        code_block_regex = re.compile(
            r"```(?:([\w+-.]+))?(?:\s+filename=[\"']([^\"']+)[\"'])?(?:\s+([^\s]+))?\s*\n(.*?)\n```",
            re.DOTALL
        )
        extracted_items = []
        for match in code_block_regex.finditer(text):
            token1 = match.group(1)  # Could be a language tag or an inline filename if it contains a dot
            token2 = match.group(2)  # Filename provided with filename="..."
            token3 = match.group(3)  # Filename provided on a separate line after the language tag
            code = match.group(4).strip()

            # Determine the filename:
            if token2:
                filename = token2
            elif token3:
                filename = token3
            elif token1 and '.' in token1:
                # If token1 contains a dot, it's likely a filename.
                filename = token1
            else:
                filename = None

            # Determine the language:
            if token1 and not (filename == token1 and '.' in token1):
                language = token1
            else:
                language = None
            
            extracted_items.append({
                "language": language,
                "filename": filename,
                "code": code
            })
        return extracted_items

    async def _handle_command(self, command_str: str):
        """Handle slash commands"""
        parts = command_str[1:].split()
        cmd = parts[0].lower()
        args = parts[1:]
        
        if cmd == 'file' and args:
            await self._add_file(args[0])
        elif cmd == 'new' and args:
            await self._handle_new_file(args[0])
        elif cmd == 'files':
            self._list_files()
        elif cmd == 'repo':
            await self._show_repo_stats()
        elif cmd == 'refresh':
            await self._refresh_repo_context()
        elif cmd == 'clear':
            self._clear_history()
        elif cmd == 'model' and args:
            self._switch_model(args[0])
        elif cmd == 'save_conversation' and args:
            await self._save_conversation(args[0])
        elif cmd == 'save':
            await self._handle_save_last_code(args[0] if args else None)
        elif cmd == 'git_add' and args:
            await self._handle_git_add(args)
        elif cmd == 'git_commit' and args:
            await self._handle_git_commit(" ".join(args))
        elif cmd == 'git_push':
            await self._handle_git_push()
        else:
            console.print(f"[red]Unknown command or missing arguments: {command_str}[/red]")
            self._show_help()

    async def _show_repo_stats(self):
        """Show repository statistics and structure"""
        try:
            from .commands import CodeCommands
            repo_context = CodeCommands.build_repo_context(str(Path.cwd()))
            git_context = await self.github_service.get_repository_context(Path.cwd())
            
            # Calculate statistics
            file_count = len(repo_context)
            total_lines = sum(len(content.split('\n')) for content in repo_context.values())
            
            # Group files by extension
            extensions = {}
            for file_path in repo_context.keys():
                ext = Path(file_path).suffix or 'no extension'
                extensions[ext] = extensions.get(ext, 0) + 1
            
            # Build statistics display
            stats_text = f"""
Repository Statistics:
- Total Files: {file_count}
- Total Lines: {total_lines}
- Current Branch: {git_context.get('current_branch', 'N/A')}
- Git Status: {git_context.get('status', 'N/A')}

File Types:
{chr(10).join([f"- {ext}: {count} files" for ext, count in sorted(extensions.items())])}

Recent Files:
{chr(10).join([f"- {Path(p).name}" for p in list(repo_context.keys())[:10]])}
{f"... and {file_count - 10} more files" if file_count > 10 else ""}
"""
            
            console.print(Panel(stats_text, title="Repository Overview", border_style="blue"))
            
        except Exception as e:
            console.print(f"[red]Error getting repository stats: {e}[/red]")

    async def _refresh_repo_context(self):
        """Refresh repository context"""
        console.print("[yellow]Refreshing repository context...[/yellow]")
        # Context will be refreshed on next chat message
        console.print("[green]Repository context will be refreshed on next message[/green]")

    async def _handle_chat(self, message: str):
        """Handle chat message"""
        try:
            # Get full repository context
            repo_context = await self.github_service.get_repository_context(Path.cwd())
            
            # Build complete file context from repository
            from .commands import CodeCommands
            full_repo_context = CodeCommands.build_repo_context(str(Path.cwd()))
            
            # Merge current files with full repo context
            combined_files = {**full_repo_context, **self.current_files}
            
            # Create summary of repository structure
            file_count = len(full_repo_context)
            total_lines = sum(len(content.split('\n')) for content in full_repo_context.values())
            
            # Build enhanced prompt with full context
            context_summary = (
                f"Repository Context:\n"
                f"- Current Branch: {repo_context.get('current_branch', 'N/A')}\n"
                f"- Status: {repo_context.get('status', 'N/A')}\n"
                f"- Recent Commits: {', '.join(repo_context.get('recent_commits', []))}\n"
                f"- Total Files: {file_count} files ({total_lines} total lines)\n"
                f"- File Structure: {self._build_file_tree(full_repo_context)}\n\n"
            )
            
            # Add conversation history context
            if self.conversation_history:
                context_summary += "Previous conversation context available.\n\n"
            
            augmented_prompt = f"{context_summary}User Message: {message}"
            
            # Add user message to conversation history
            self.conversation_history.append({
                "role": "user", 
                "content": message
            })
            
            request = CodeRequest(
                prompt=augmented_prompt,
                files=combined_files,
                conversation_history=self.conversation_history.copy(),
                git_context=str(repo_context)
            )
            
            # Generate response with streaming
            async with AIService(self.config) as ai_service:
                console.print("\n[bold green]AI Assistant[/bold green]:")
                
                response_content = ""
                with Live(Spinner("dots", text="Thinking..."), console=console, refresh_per_second=4) as live:
                    async for chunk in ai_service.stream_generate(request):
                        response_content += chunk
                        live.update(Panel(response_content, border_style="green"))
                
                # Store the full response content
                self.last_ai_response_content = response_content

                # Add to conversation history
                self.conversation_history.append({
                    "role": "assistant", 
                    "content": response_content
                })

                # Check if the AI response contains code blocks and suggest commands
                code_blocks = self._extract_code_blocks(response_content)
                if code_blocks:
                    suggestion_message = (
                        "AI response contains code suggestions.\n"
                        "You can use the following commands:\n"
                        "- `/save <your_filename.ext>` to save the first code block.\n"
                        "- `/git_add <your_filename.ext>`\n"
                        "- `/git_commit Your commit message`\n"
                        "- `/git_push`"
                    )
                    console.print(
                        Panel(
                            suggestion_message,
                            title="[yellow]Code Actions Suggested[/yellow]",
                            border_style="yellow",
                            expand=False
                        )
                    )

                # After displaying the AI response, ask if you want to review repository changes.
                if click.confirm("Would you like to review repository changes (stage, commit, push) in the current repo?", default=False):
                    await self._handle_repo_review()
            
        except Exception as e:
            console.print(f"[red]Error in chat: {e}[/red]")

    def _build_file_tree(self, file_context: Dict[str, str], max_files: int = 20) -> str:
        """Build a concise file tree representation"""
        file_paths = list(file_context.keys())
        
        if len(file_paths) <= max_files:
            return ", ".join([Path(p).name for p in file_paths])
        else:
            shown_files = [Path(p).name for p in file_paths[:max_files]]
            return f"{', '.join(shown_files)}, and {len(file_paths) - max_files} more files"