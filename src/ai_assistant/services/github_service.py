import asyncio
import os
import requests
from pathlib import Path
from typing import List, Optional, Dict
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..core.config import Config
from ..core.exceptions import AIAssistantError, NotAGitRepositoryError
from ..services.ai_service import AIService
from ..services.file_service import FileService
from ..models.request import CodeRequest
from ..utils.file_utils import FileUtils
from ..utils.git_utils import GitUtils

console = Console()

class GitHubServiceError(AIAssistantError):
    """Custom exception for GitHubService errors."""
    pass

class GitHubService:
    """Implementation of code-related commands"""
    
    def __init__(self, config: Config, repo_path: Path = None):
        self.config = config
        self.file_service = FileService(config)
        self.file_utils = FileUtils()
        self.repo_path = repo_path or Path.cwd()

    async def create_github_repo(self, repo_name: str, private: bool = True) -> Optional[str]:
        """Create a new GitHub repository using the GitHub API."""
        token = os.getenv("GITHUB_TOKEN")
        username = os.getenv("GITHUB_USERNAME")
        url = "https://api.github.com/user/repos"
        headers = {"Authorization": f"token {token}"}
        data = {
            "owner": username,
            "name": repo_name,
            "private": private,
            "auto_init": True
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 201:
            return response.json()["clone_url"]
        else:
            print("Failed to create repo:", response.json())
            return None

    async def get_repository_context(self, repo_path: Path = None) -> dict:
        repo_path = repo_path or self.repo_path
        git_utils = GitUtils()
        context = {
            "is_git_repo": False,
            "current_branch": "unknown",
            "status": "unknown",
            "recent_commits": [],
            "all_branches": "unknown",
            "repo_path": str(repo_path.resolve())
        }
        try:
            if not await git_utils.is_git_repo(repo_path):
                return context
            context["is_git_repo"] = True
            context["current_branch"] = await git_utils.get_current_branch(repo_path)
            context["status"] = await git_utils.get_status(repo_path)
            raw_commits = await git_utils.get_recent_commits(repo_path, count=5)
            context["recent_commits"] = raw_commits.splitlines() if isinstance(raw_commits, str) else raw_commits
            context["all_branches"] = await git_utils.get_branches(repo_path)
        except Exception as e:
            console.print(f"[yellow]Warning: Error getting full git context for {repo_path}: {e}[/yellow]")
            pass
        return context

    async def get_ai_repo_summary(self, repo_path: Path = None) -> str:
        """Gets repository context and asks AI to summarize it."""
        actual_repo_path = repo_path or self.repo_path
        repo_context_dict = await self.get_repository_context(actual_repo_path)

        if not repo_context_dict["is_git_repo"]:
            raise NotAGitRepositoryError(path=actual_repo_path)

        # Attempt to read a README file from the repository root (if present)
        readme_content = ""
        readme_path = actual_repo_path / "README.md"
        if readme_path.exists():
            try:
                with open(readme_path, "r", encoding="utf-8") as f:
                    readme_content = f.read()
            except Exception as e:
                readme_content = f"Error reading README: {e}"

        # Truncate the README content for brevity (if too long)
        if len(readme_content) > 1000:
            readme_content = readme_content[:1000] + "\n...[truncated]"

        prompt_lines = [
            f"Please provide a detailed 'about' summary and overview of the project repository located at '{repo_context_dict['repo_path']}'. Include its purpose, main features, and key components.",
            f"- Current Branch: {repo_context_dict['current_branch']}",
            f"- Status:\n{repo_context_dict['status']}",
            f"- Recent Commits (last 5):\n" + "\n".join([f"  - {c}" for c in repo_context_dict['recent_commits']]),
            f"- All Branches:\n{repo_context_dict['all_branches']}"
        ]
        if readme_content:
            prompt_lines.append(f"- Project Description (from README):\n{readme_content}")
        prompt_lines.append("\nProvide an 'about' summary for this project, explaining what this repository is for, its key technologies, and its main functionalities.")
        prompt = "\n".join(prompt_lines)

        try:
            request = CodeRequest(prompt=prompt)
            summary = ""
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    summary += chunk
            return summary.strip()
        except Exception as e:
            return f"Error generating AI summary: {e}"

    async def generate_code(self, prompt: str, files: List[str], 
                          show_diff: bool = False, apply_changes: bool = False):
        """Generate code based on prompt and context"""
        try:
            # Prepare request
            request = await self._prepare_request(prompt, files)
            
            # Generate code
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Generating code...", total=None)
                
                async with AIService(self.config) as ai_service:
                    response_content = ""
                    async for chunk in ai_service.stream_generate(request):
                           response_content += chunk
                
                progress.update(task, completed=True)
            
            # Display response
            await self._display_response(response_content, show_diff, apply_changes)
            
        except Exception as e:
            raise AIAssistantError(f"Error generating code: {e}")
    
    async def review_changes(self, create_branch: Optional[str] = None,
                           commit_changes: bool = False, push_changes: bool = False):
        """Review and manage code changes"""
        try:
            
            async with GitHubService(self.config) as github_service:
                # Get repository context
                context = await github_service.get_repository_context()
                
                # Display current status
                self._display_repo_status(context)
                
                # Create branch if requested
                if create_branch:
                    await github_service.create_branch(create_branch)
                    console.print(f"[green]Created branch: {create_branch}[/green]")
                
                # Commit changes if requested
                if commit_changes:
                    message = self._generate_commit_message(context)
                    await github_service.commit_changes(message)
                    console.print(f"[green]Committed changes: {message}[/green]")
                
                # Push changes if requested
                if push_changes:
                    await github_service.push_changes()
                    console.print("[green]Pushed changes to remote[/green]")
                    
        except Exception as e:
            raise AIAssistantError(f"Error reviewing changes: {e}")
    
    async def _prepare_request(self, prompt: str, files: List[str]) -> CodeRequest:
        """Prepare AI request with context"""
        file_contents = {}
        git_context = ""
        
        # Load file contents
        for file_path in files:
            try:
                content = await self.file_service.read_file(Path(file_path))
                file_contents[file_path] = content
            except Exception as e:
                console.print(f"[yellow]Warning: Could not read {file_path}: {e}[/yellow]")
        
        # Get git context if in a git repo
        try:
            async with GitHubService(self.config) as github_service:
                context = await github_service.get_repository_context(Path.cwd())
                git_context = f"Branch: {context.get('current_branch', 'unknown')}"
        except:
            pass  # Not in a git repo or error getting context
        
        return CodeRequest(
            prompt=prompt,
            files=file_contents,
            git_context=git_context,
            instructions="Provide clear, production-ready code with proper error handling and documentation."
        )
    
    async def _display_response(self, response, show_diff: bool, apply_changes: bool):
        """Display AI response with proper formatting"""
        # Display the response
        console.print(Panel(
            Syntax(response.content, "python", theme="github-dark", line_numbers=True),
            title="AI Generated Code",
            border_style="blue"
        ))
        
        # Show usage info
        if response.usage:
            console.print(f"[dim]Tokens used: {response.usage.get('total_tokens', 'unknown')}[/dim]")
        
        # Handle diff and apply logic
        if show_diff or apply_changes:
            # Extract code blocks and file paths from response
            code_blocks = self._extract_code_blocks(response.content)
            
            for file_path, code in code_blocks.items():
                if show_diff:
                    await self._show_file_diff(file_path, code)
                
                if apply_changes:
                    await self._apply_code_changes(file_path, code)
    
    def _extract_code_blocks(self, content: str) -> Dict[str, str]:
        """Extract code blocks with file paths from AI response"""
        # This is a simplified implementation
        # You might want to use more sophisticated parsing
        code_blocks = {}
        
        lines = content.split('\n')
        current_file = None
        current_code = []
        in_code_block = False
        
        for line in lines:
            if line.startswith('```') and not in_code_block:
                in_code_block = True
                # Try to extract filename from markdown code block
                parts = line.split()
                if len(parts) > 1 and '.' in parts[-1]:
                    current_file = parts[-1]
            elif line.startswith('```') and in_code_block:
                if current_file:
                    code_blocks[current_file] = '\n'.join(current_code)
                current_file = None
                current_code = []
                in_code_block = False
            elif in_code_block:
                current_code.append(line)
        
        return code_blocks
    
    async def _show_file_diff(self, file_path: str, new_code: str):
        """Show diff for file changes"""
        try:
            path = Path(file_path)
            if path.exists():
                original_code = await self.file_service.read_file(path)
                diff = self.file_utils.generate_diff(original_code, new_code, file_path)
                console.print(Panel(
                    Syntax(diff, "diff", theme="github-dark"),
                    title=f"Diff for {file_path}",
                    border_style="yellow"
                ))
            else:
                console.print(f"[green]New file: {file_path}[/green]")
                console.print(Panel(
                    Syntax(new_code, self._get_language_from_extension(path.suffix), 
                          theme="github-dark", line_numbers=True),
                    title=f"New file: {file_path}",
                    border_style="green"
                ))
        except Exception as e:
            console.print(f"[red]Error showing diff for {file_path}: {e}[/red]")
    
    async def _apply_code_changes(self, file_path: str, code: str):
        """Apply code changes to file"""
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            await self.file_service.write_file(path, code)
            console.print(f"[green]Applied changes to {file_path}[/green]")
            
        except Exception as e:
            console.print(f"[red]Error applying changes to {file_path}: {e}[/red]")
    
    def _get_language_from_extension(self, ext: str) -> str:
        """Get syntax highlighting language from file extension"""
        lang_map = {
            '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
            '.java': 'java', '.cpp': 'cpp', '.c': 'c', '.go': 'go',
            '.rs': 'rust', '.rb': 'ruby', '.php': 'php',
            '.html': 'html', '.css': 'css', '.scss': 'scss',
            '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml',
            '.md': 'markdown', '.txt': 'text'
        }
        return lang_map.get(ext.lower(), 'text')
    
    def _display_repo_status(self, context: Dict):
        """Display repository status information"""
        status_info = []
        
        if context.get('current_branch'):
            status_info.append(f"Branch: {context['current_branch']}")
        
        if context.get('changed_files'):
            status_info.append(f"Changed files: {len(context['changed_files'])}")
        
        if context.get('recent_commits'):
            status_info.append(f"Recent commits: {len(context['recent_commits'])}")
        
        console.print(Panel(
            '\n'.join(status_info),
            title="Repository Status",
            border_style="blue"
        ))
    
    def _generate_commit_message(self, context: Dict) -> str:
        """Generate a commit message based on context"""
        changed_files = context.get('changed_files', [])
        if not changed_files:
            return "AI Assistant: Code changes"
        
        if len(changed_files) == 1:
            return f"AI Assistant: Update {changed_files[0]}"
        else:
            return f"AI Assistant: Update {len(changed_files)} files"

    async def get_staged_diff(self, repo_path: Optional[Path] = None) -> str:
        """
        Retrieves the diff of staged changes for the repository.
        """
        git_utils = GitUtils()
        target_repo = repo_path if repo_path else self.repo_path
        return await git_utils.get_staged_diff(target_repo)