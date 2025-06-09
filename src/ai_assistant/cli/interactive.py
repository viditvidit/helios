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
from pyfiglet import Figlet
import os
from ..core.config import Config
from ..services.ai_service import AIService
from ..services.file_service import FileService
from ..services.github_service import GitHubService, GitHubServiceError
from ..models.request import CodeRequest
from ..utils.file_utils import FileUtils
from ..utils.git_utils import GitUtils

console = Console()

def clear_screen():
    # Works on Windows, macOS, Linux
    os.system('cls' if os.name == 'nt' else 'clear')


def print_helios_banner():
    f = Figlet(font='big')
    banner = f.renderText('HELIOS')
    clear_screen()
    console.print(f"[bold orange1]{banner}[/bold orange1]")

print_helios_banner()

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
- /file <path>              - Add file to context
- /files                    - List files in context
- /clear                    - Clear conversation history
- /model <name>             - Switch AI model
- /save_conversation <path> - Save conversation to file (previously /save)
- /save <filename>          - Save the first code block from the last AI response to <filename>
- /git_add <file1> [f2..]   - Stage specified file(s) for commit
- /git_commit <message>     - Commit staged changes with <message>
- /git_push                 - Push committed changes to remote repository
- help                      - Show this help
- exit/quit/q               - Exit interactive mode

[bold]Chat:[/bold]
Just type your message to chat with the AI assistant.
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
        elif cmd == 'files':
            self._list_files()
        elif cmd == 'clear':
            self._clear_history()
        elif cmd == 'model' and args:
            self._switch_model(args[0])
        elif cmd == 'save_conversation' and args: # Renamed from 'save' to avoid conflict
            await self._save_conversation(args[0])
        elif cmd == 'save': # Can now be called with or without a filename
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

    async def _handle_save_last_code(self, file_path_str: Optional[str]):
        """Saves the first code block from the last AI response to a file."""
        if not self.last_ai_response_content:
            console.print("[yellow]No AI response available to save.[/yellow]")
            return

        code_blocks = self._extract_code_blocks(self.last_ai_response_content)
        if not code_blocks:
            console.print("[yellow]No code blocks found in the last AI response.[/yellow]")
            return

        if len(code_blocks) == 1:
            # If only one code block is found, proceed as before.
            block = code_blocks[0]
            suggested_filename = block.get("filename")

            if not file_path_str:
                prompt_message = "Please enter the file name to save the AI suggested code"
                if suggested_filename:
                    prompt_message += f" (press enter to use suggested: {suggested_filename})"
                file_path_str = Prompt.ask(prompt_message, default=suggested_filename or "")

            if not file_path_str:
                console.print("[red]No file name provided. Aborting save operation.[/red]")
            return

            if '.' not in file_path_str:
                if suggested_filename and '.' in suggested_filename:
                    file_path_str += suggested_filename[suggested_filename.rfind('.'):]
                else:
                    file_path_str += ".txt"

            await self.file_service.write_file(Path(file_path_str), block.get("code"))
            console.print(f"[green]AI suggested code saved to: {file_path_str}.[/green]")
        else:
            # Multiple code blocks found: prompt user to select which ones to save.
            console.print(f"[yellow]Multiple code blocks ({len(code_blocks)}) detected.[/yellow]")
            indices_str = Prompt.ask("Enter the indices of code blocks to save (comma separated) or type 'all' to save all", default="all")
            if indices_str.strip().lower() == "all":
                indices = list(range(1, len(code_blocks) + 1))
            else:
                try:
                    indices = [int(x.strip()) for x in indices_str.split(",") if x.strip().isdigit()]
                except Exception as e:
                    console.print("[red]Invalid input. Aborting save operation.[/red]")
                    return
        
            for idx in indices:
                if idx < 1 or idx > len(code_blocks):
                    console.print(f"[red]Index {idx} is out of range. Skipping.[/red]")
                    continue
                block = code_blocks[idx - 1]
                suggested_filename = block.get("filename")
                individual_filename = Prompt.ask(f"Enter file name for code block {idx} (press enter to use suggested: {suggested_filename})", default=suggested_filename or f"output_{idx}.txt")

                if not individual_filename:
                    console.print(f"[red]No file name provided for code block {idx}. Skipping this block.[/red]")
                    continue

                if '.' not in individual_filename:
                    if suggested_filename and '.' in suggested_filename:
                        individual_filename += suggested_filename[suggested_filename.rfind('.'):]
                    else:
                        individual_filename += ".txt"

                await self.file_service.write_file(Path(individual_filename), block.get("code"))
                console.print(f"[green]Code block {idx} saved to: {individual_filename}.[/green]")

        # Git Integration: Prompt to initialize a Git repository and then commit/push the saved file.
        repo_path = Path.cwd()
        git_utils = GitUtils()
        if not await git_utils.is_git_repo(repo_path):
            if click.confirm("This directory is not a Git repository. Do you want to initialize one?", default=True):
                await git_utils.initialize_repository(repo_path)
                console.print("[green]Git repository initialized.[/green]")
            else:
                console.print("[yellow]Git repository was not initialized. File saved locally only.[/yellow]")
                return

        if click.confirm("Do you want to commit and push the saved file to Git?", default=False):
            await git_utils.add_file(repo_path, file_path_str)
            commit_message = click.prompt("Enter commit message", default="Update via AI Assistant")
            await git_utils.commit(repo_path, commit_message)
            branch = await git_utils.get_current_branch(repo_path)
            await git_utils.push(repo_path, branch)
            console.print("[green]Changes committed and pushed to Git repository.[/green]")
        else:
            console.print("[yellow]Saved file was not committed to Git.[/yellow]")

    async def _handle_git_add(self, file_paths: List[str]):
        """Stages specified files for commit."""
        if not file_paths:
            console.print("[red]No files specified for git add.[/red]")
            return
        try:
            await self.github_service.git_utils.add([Path(p) for p in file_paths])
            console.print(f"[green]✓ Files added to staging: {', '.join(file_paths)}[/green]")
        except GitHubServiceError as e:
            console.print(f"[red]Git add failed: {e}[/red]")
        except Exception as e:
            console.print(f"[red]An unexpected error occurred during git add: {e}[/red]")

    async def _handle_git_commit(self, message: str):
        """Commits staged changes with the given message."""
        if not message:
            console.print("[red]Commit message cannot be empty.[/red]")
            return
        try:
            await self.github_service.git_utils.commit(message)
            console.print(f"[green]✓ Changes committed with message: {message}[/green]")
        except GitHubServiceError as e:
            console.print(f"[red]Git commit failed: {e}[/red]")
        except Exception as e:
            console.print(f"[red]An unexpected error occurred during git commit: {e}[/red]")

    async def _handle_git_push(self):
        """Pushes committed changes to the remote repository."""
        try:
            await self.github_service.git_utils.push()
            console.print("[green]✓ Changes pushed to remote.[/green]")
        except GitHubServiceError as e:
            console.print(f"[red]Git push failed: {e}[/red]")
        except Exception as e:
            console.print(f"[red]An unexpected error occurred during git push: {e}[/red]")

    async def _handle_chat(self, message: str):
        """Handle chat message"""
        try:
            # Add to conversation history
            self.conversation_history.append({"role": "user", "content": message})
            
            # Prepare request
            request = CodeRequest(
                prompt=message,
                files=self.current_files.copy(),
                conversation_history=self.conversation_history.copy()
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
            
        except Exception as e:
            console.print(f"[red]Error in chat: {e}[/red]")

    def _format_conversation(self) -> str:
        """Format conversation for saving"""
        formatted = []
        formatted.append("# AI Assistant Conversation")
        formatted.append(f"Model: {self.config.model_name}")
        formatted.append("")
        
        for entry in self.conversation_history:
            role = entry['role'].title()
            content = entry['content']
            formatted.append(f"## {role}")
            formatted.append(content)
            formatted.append("")
        
        return '\n'.join(formatted)