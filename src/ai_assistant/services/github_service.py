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

    async def _get_repo(self):
        """Helper to get the PyGithub Repository object for the current directory."""
        repo_path = Path.cwd()
        if not await self.git_utils.is_git_repo(repo_path):
            raise NotAGitRepositoryError(path=repo_path)
        
        # Get remote URL to derive owner/repo name
        remote_url_raw = await self.git_utils._run_git_command(repo_path, ['remote', 'get-url', 'origin'])
        if not remote_url_raw:
            raise GitHubServiceError("Could not determine the remote 'origin' URL. Is the repository pushed to GitHub?")
        
        # Parses URLs like 'https://github.com/owner/repo.git' or 'git@github.com:owner/repo.git'
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
            repo = self.user.create_repo(
                name=repo_name,
                private=private,
                description=description,
                auto_init=True  # Creates with a README
            )
            console.print(f"[green]✓ Successfully created repository: {repo.full_name}[/green]")
            return repo.clone_url
        except GithubException as e:
            if e.status == 422: # Unprocessable Entity - often means repo already exists
                raise GitHubServiceError(f"Repository '{repo_name}' likely already exists on GitHub.")
            raise GitHubServiceError(f"Failed to create repository: {e.data['message']}")

    async def create_branch(self, branch_name: str, source_branch: str = 'main') -> None:
        """Creates a new branch in the current repository."""
        repo = await self._get_repo()
        try:
            source = repo.get_branch(source_branch)
            repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)
            console.print(f"[green]✓ Successfully created branch '{branch_name}' from '{source_branch}'.[/green]")
        except GithubException as e:
            if e.status == 422:
                raise GitHubServiceError(f"Branch '{branch_name}' already exists.")
            raise GitHubServiceError(f"Failed to create branch: {e}")

    async def create_pull_request(self, title: str, body: str, head_branch: str, base_branch: str) -> str:
        """Creates a pull request."""
        repo = await self._get_repo()
        try:
            pr = repo.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base_branch
            )
            console.print(f"[green]✓ Successfully created Pull Request #{pr.number}: {pr.html_url}[/green]")
            return pr.html_url
        except GithubException as e:
            # e.g., "No commits between main and new-feature"
            errors = e.data.get('errors', [{}])
            message = errors[0].get('message', 'Could not create pull request.')
            raise GitHubServiceError(f"Failed to create Pull Request: {message}")

    async def get_ai_pr_summary(self, pr_number: int) -> str:
        """Gets an AI-generated summary of a pull request."""
        repo = await self._get_repo()
        try:
            pr = repo.get_pull(pr_number)
            
            # Fetch PR diff
            diff = pr.get_files()
            diff_content = ""
            for file in diff:
                diff_content += f"--- Diff for {file.filename} ---\n"
                diff_content += file.patch + "\n\n"

            prompt = (
                f"Please review the following pull request and provide a summary.\n"
                f"PR Title: {pr.title}\n"
                f"PR Body:\n{pr.body}\n\n"
                f"Changes (diff):\n{diff_content}\n\n"
                "Your summary should explain the purpose of the PR, highlight key changes, "
                "and identify potential issues or areas for improvement."
            )

            request = CodeRequest(prompt=prompt)
            summary = ""
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    summary += chunk
            return summary.strip()

        except UnknownObjectException:
            raise GitHubServiceError(f"Pull Request #{pr_number} not found in this repository.")
        except Exception as e:
            raise GitHubServiceError(f"Failed to get PR summary: {e}")

    async def create_issue(self, title: str, body: str = "", labels: List[str] = None) -> str:
        """Creates an issue in the repository."""
        repo = await self._get_repo()
        try:
            issue = repo.create_issue(
                title=title,
                body=body,
                labels=labels or []
            )
            console.print(f"[green]✓ Successfully created Issue #{issue.number}: {issue.html_url}[/green]")
            return issue.html_url
        except GithubException as e:
            raise GitHubServiceError(f"Failed to create issue: {e}")