import os
from pathlib import Path
from typing import Optional, List
from rich.console import Console

from github import Github, GithubException, UnknownObjectException
from ..core.config import Config
from ..core.exceptions import GitHubServiceError, NotAGitRepositoryError
from ..models.request import CodeRequest
from ..services.ai_service import AIService
from ..utils.git_utils import GitUtils

console = Console()

class GitHubService:
    """Service for interacting with the GitHub API using PyGithub."""

    def __init__(self, config: Config):
        self.config = config
        self.git_utils = GitUtils()
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise GitHubServiceError("GITHUB_TOKEN is not set in your environment. Please set it in your .env file.")
        
        self.gh = Github(token)
        try:
            self.user = self.gh.get_user()
        except Exception as e:
            raise GitHubServiceError(f"Failed to authenticate with GitHub. Please check your GITHUB_TOKEN. Error: {e}")

    async def get_repository_context(self, repo_path: Path = None) -> dict:
        """
        Restored Method: Gets the local repository context using Git commands.
        """
        repo_path = repo_path or Path.cwd()
        context = {
            "is_git_repo": False,
            "current_branch": "unknown",
            "status": "unknown",
        }
        try:
            if not await self.git_utils.is_git_repo(repo_path):
                return context
            context["is_git_repo"] = True
            context["current_branch"] = await self.git_utils.get_current_branch(repo_path)
            context["status"] = await self.git_utils.get_status(repo_path)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not get full git context for {repo_path}: {e}[/yellow]")
        return context

    async def _get_repo_object(self):
        """Helper to get the PyGithub Repository object for the current directory."""
        repo_path = Path.cwd()
        if not await self.git_utils.is_git_repo(repo_path):
            raise NotAGitRepositoryError(path=repo_path)
        
        remote_url_raw = await self.git_utils._run_git_command(repo_path, ['remote', 'get-url', 'origin'])
        if not remote_url_raw:
            raise GitHubServiceError("Could not determine remote 'origin' URL. Is the repository pushed to GitHub?")
        
        repo_name_full = remote_url_raw.split('/')[-1].replace('.git', '')
        repo_owner = remote_url_raw.split('/')[-2].split(':')[-1]
        repo_slug = f"{repo_owner}/{repo_name_full}"
        
        try:
            return self.gh.get_repo(repo_slug)
        except UnknownObjectException:
            raise GitHubServiceError(f"Repository '{repo_slug}' not found on GitHub or you lack permissions.")

    async def create_repo(self, repo_name: str, private: bool = True, description: str = "") -> str:
        """Creates a new repository on GitHub."""
        try:
            repo = self.user.create_repo(name=repo_name, private=private, description=description, auto_init=True)
            console.print(f"[green]✓ Successfully created repository: {repo.full_name}[/green]")
            return repo.clone_url
        except GithubException as e:
            if e.status == 422: raise GitHubServiceError(f"Repository '{repo_name}' likely already exists.")
            raise GitHubServiceError(f"Failed to create repository: {e.data['message']}")

    async def create_branch(self, branch_name: str, source_branch: str = 'main'):
        """Creates a new branch in the current repository."""
        repo = await self._get_repo_object()
        try:
            source = repo.get_branch(source_branch)
            repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)
            console.print(f"[green]✓ Successfully created branch '{branch_name}' from '{source_branch}'.[/green]")
        except GithubException as e:
            if e.status == 422: raise GitHubServiceError(f"Branch '{branch_name}' already exists.")
            raise GitHubServiceError(f"Failed to create branch: {e}")

    async def create_pull_request(self, title: str, body: str, head_branch: str, base_branch: str) -> str:
        """Creates a pull request."""
        repo = await self._get_repo_object()
        try:
            pr = repo.create_pull(title=title, body=body, head=head_branch, base=base_branch)
            console.print(f"[green]✓ Successfully created Pull Request #{pr.number}: {pr.html_url}[/green]")
            return pr.html_url
        except GithubException as e:
            errors = e.data.get('errors', [{}]); message = errors[0].get('message', 'Could not create PR.')
            raise GitHubServiceError(f"Failed to create Pull Request: {message}")

    async def get_ai_pr_summary(self, pr_number: int) -> str:
        """NEW: Gets an AI-generated summary of a pull request."""
        repo = await self._get_repo_object()
        try:
            pr = repo.get_pull(pr_number)
            files = pr.get_files()
            diff_content = "\n\n".join([f"--- Diff for {file.filename} ---\n{file.patch}" for file in files])
            prompt = (
                f"Please provide a concise review of the following pull request.\n"
                f"PR Title: {pr.title}\n"
                f"PR Body:\n{pr.body}\n\n"
                f"Code Changes (diff):\n{diff_content}\n\n"
                "Your review should summarize the purpose of the changes, highlight the key modifications, "
                "and identify any potential issues, bugs, or areas for improvement. Be constructive."
            )
            request = CodeRequest(prompt=prompt)
            summary = ""
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    summary += chunk
            return summary.strip()
        except UnknownObjectException:
            raise GitHubServiceError(f"Pull Request #{pr_number} not found.")
        except Exception as e:
            raise GitHubServiceError(f"Failed to get PR summary: {e}")

    async def get_ai_repo_summary(self) -> str:
        """NEW: Gets an AI-generated summary of the entire repository."""
        repo = await self._get_repo_object()
        try:
            # Gather context
            repo_context = await self.get_repository_context()
            recent_commits = await self.git_utils.get_recent_commits(Path.cwd(), count=5)
            try:
                readme_content = repo.get_readme().decoded_content.decode('utf-8')
            except UnknownObjectException:
                readme_content = "No README file found."

            prompt = (
                f"Please provide a detailed 'about' summary for the repository '{repo.full_name}'.\n\n"
                f"Current Branch: {repo_context.get('current_branch', 'N/A')}\n"
                f"Recent Commits:\n{recent_commits}\n\n"
                f"README Content:\n---\n{readme_content[:2000]}...\n---\n\n"
                "Based on this context, explain the project's purpose, its key technologies, and its main functionalities. "
                "Provide a clear, high-level overview."
            )
            request = CodeRequest(prompt=prompt)
            summary = ""
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    summary += chunk
            return summary.strip()
        except Exception as e:
            raise GitHubServiceError(f"Failed to generate repository summary: {e}")

    async def create_issue(self, title: str, body: str = "", labels: List[str] = None) -> str:
        """Creates an issue in the repository."""
        repo = await self._get_repo_object()
        try:
            issue = repo.create_issue(title=title, body=body, labels=labels or [])
            console.print(f"[green]✓ Successfully created Issue #{issue.number}: {issue.html_url}[/green]")
            return issue.html_url
        except GithubException as e:
            raise GitHubServiceError(f"Failed to create issue: {e}")