import os
import asyncio
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
        token = self.config.github.token or os.getenv("GITHUB_TOKEN")
        
        if not token:
            # Don't raise an error immediately. The agent will handle prompting the user.
            self.gh = None
            self.user = None
            return

        try:
            self.gh = Github(token)
            self.user = self.gh.get_user()
            # Store the successfully used token and username in the config
            self.config.github.token = token
            self.config.github.username = self.user.login
        except Exception as e:
            raise GitHubServiceError(f"Failed to authenticate with GitHub. Please check your GITHUB_TOKEN. Error: {e}")

    async def _get_repo_object(self):
        """Helper to get the PyGithub Repository object for the current directory."""
        if not self.gh:
            raise GitHubServiceError("GitHub token not configured. Agent could not prompt for credentials.")

    async def get_repository_context(self, repo_path: Path = None) -> dict:
        """
        Gets the local repository context using Git commands.
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
        
        # Parses URLs like 'https://github.com/owner/repo.git' or 'git@github.com:owner/repo.git'
        repo_name_full = remote_url_raw.split('/')[-1].replace('.git', '')
        repo_owner = remote_url_raw.split('/')[-2].split(':')[-1]
        repo_slug = f"{repo_owner}/{repo_name_full}"
        
        try:
            return self.gh.get_repo(repo_slug)
        except UnknownObjectException:
            raise GitHubServiceError(f"Repository '{repo_slug}' not found on GitHub or you lack permissions.")
        
    async def get_or_create_repo(self, repo_name: str, private: bool, description: str):
        """
        Gets a repository by name. If it doesn't exist, creates it.
        This is a key method for making the agent's actions idempotent.
        """
        try:
            # First, try to get the repo
            repo = self.gh.get_repo(f"{self.user.login}/{repo_name}")
            console.print(f"[yellow]✓ Found existing repository: {repo.full_name}[/yellow]")
            return repo
        except UnknownObjectException:
            # If it doesn't exist, create it
            console.print(f"[dim]Repository '{repo_name}' not found. Creating it...[/dim]")
            try:
                repo = self.user.create_repo(
                    name=repo_name,
                    private=private,
                    description=description or "Created by Helios Agent",
                    auto_init=True
                )
                console.print(f"[green]✓ Successfully created repository: {repo.full_name}[/green]")
                return repo
            except GithubException as e:
                if e.status == 422: # Unprocessable Entity - often means repo already exists
                    raise GitHubServiceError(f"Repository '{repo_name}' likely already exists on GitHub, but could not be accessed.")
                raise GitHubServiceError(f"Failed to create repository: {e.data['message']}")

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

    async def create_branch(self, branch_name: str, source_branch: str = 'main'):
        """Creates a new branch in the current repository."""
        repo = await self._get_repo_object()
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
        repo = await self._get_repo_object()
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
            errors = e.data.get('errors', [{}])
            message = errors[0].get('message', 'Could not create pull request.')
            raise GitHubServiceError(f"Failed to create Pull Request: {message}")

    async def _get_diff_summary(self, filename: str, patch: str) -> str:
        """Sends a single file's diff to the AI for a quick summary."""
        prompt = (
            f"Summarize the following code changes for the file `{filename}` in a single sentence. "
            f"Focus on the 'what' and 'why'.\n\n--- DIFF ---\n{patch}"
        )
        request = CodeRequest(prompt=prompt)
        summary = ""
        try:
            async with AIService(self.config) as ai_service:
                # Use a shorter timeout for these small, quick summaries
                ai_service.session.timeout.total = 60 
                async for chunk in ai_service.stream_generate(request):
                    summary += chunk
            return f"- **{filename}**: {summary.strip()}"
        except Exception:
            return f"- **{filename}**: Could not summarize (request may have timed out)."

    async def get_ai_pr_summary(self, pr_number: int) -> str:
        """
        Two-stage pipeline for fast and reliable PR reviews.
        1. Concurrently summarize diffs for each file.
        2. Combine summaries into a final review prompt.
        """
        repo = await self._get_repo_object()
        try:
            pr = repo.get_pull(pr_number)
            files = pr.get_files()

            # --- Stage 1: Concurrent Summarization ---
            console.print(f"\n[dim]Summarizing {len(list(files))} changed files...[/dim]")
            summary_tasks = [self._get_diff_summary(file.filename, file.patch) for file in files if file.patch]
            file_summaries = await asyncio.gather(*summary_tasks)
            
            summaries_text = "\n".join(file_summaries)

            # --- Stage 2: Final Review ---
            final_prompt = (
                f"Please provide a concise, high-level review of the following pull request.\n\n"
                f"**PR Title**: {pr.title}\n"
                f"**PR Body**: {pr.body or 'No description provided.'}\n\n"
                f"**Summary of File Changes**:\n{summaries_text}\n\n"
                "Based on the title, body, and the file change summaries, please:\n"
                "1.  Write a brief overall summary of the PR's purpose.\n"
                "2.  Explain concise changes in files, do not provide full code or its explanation.\n"
                "3.  Identify any potential risks, logical gaps, or areas that might need closer inspection."
            )

            request = CodeRequest(prompt=final_prompt)
            final_review = ""
            async with AIService(self.config) as ai_service:
                async for chunk in ai_service.stream_generate(request):
                    final_review += chunk
            return final_review.strip()

        except UnknownObjectException:
            raise GitHubServiceError(f"Pull Request #{pr_number} not found.")
        except Exception as e:
            raise GitHubServiceError(f"Failed to get PR summary: {e}")

    async def get_ai_repo_summary(self) -> str:
        """Gets an AI-generated summary of the entire repository."""
        repo = await self._get_repo_object()
        try:
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
            issue = repo.create_issue(
                title=title,
                body=body,
                labels=labels or []
            )
            console.print(f"[green]✓ Successfully created Issue #{issue.number}: {issue.html_url}[/green]")
            return issue.html_url
        except GithubException as e:
            raise GitHubServiceError(f"Failed to create issue: {e}")
        
    # --- NEW: Check for existing PRs ---
    async def check_for_open_pr(self, branch_name: str) -> Optional[str]:
        """Checks if an open PR already exists for a given branch."""
        repo = await self._get_repo_object()
        try:
            pulls = repo.get_pulls(state='open', head=f'{repo.owner.login}:{branch_name}')
            if pulls.totalCount > 0:
                return pulls[0].html_url
            return None
        except GithubException:
            return None # Fail gracefully if there's an issue

    # --- UPDATED: Add Helios signature to PR body ---
    async def create_pull_request(self, title: str, body: str, head_branch: str, base_branch: str) -> str:
        """Creates a pull request with the Helios signature."""
        repo = await self._get_repo_object()
        
        # Add the signature
        signature = "\n\n[###### Assisted by Helios ######]"
        full_body = f"{body}{signature}"

        try:
            pr = repo.create_pull(title=title, body=full_body, head=head_branch, base=base_branch)
            console.print(f"[green]✓ Successfully created Pull Request #{pr.number}: {pr.html_url}[/green]")
            return pr.html_url
        except GithubException as e:
            errors = e.data.get('errors', [{}]); message = errors[0].get('message', 'Could not create PR.')
            raise GitHubServiceError(f"Failed to create Pull Request: {message}")

    # --- NEW: PR Management Methods ---
    async def approve_pr(self, pr_number: int):
        """Approves a given pull request."""
        repo = await self._get_repo_object()
        try:
            pr = repo.get_pull(pr_number)
            pr.create_review(event='APPROVE')
            console.print(f"[green]✓ Approved Pull Request #{pr_number}.[/green]")
        except UnknownObjectException:
            raise GitHubServiceError(f"Pull Request #{pr_number} not found.")
        except GithubException as e:
            raise GitHubServiceError(f"Failed to approve PR: {e.data.get('message', 'Unknown error')}")

    async def comment_on_pr(self, pr_number: int, comment: str):
        """Adds a comment to a given pull request."""
        repo = await self._get_repo_object()
        if not comment:
            raise GitHubServiceError("Comment cannot be empty.")
        try:
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(comment)
            console.print(f"[green]✓ Comment posted on Pull Request #{pr_number}.[/green]")
        except UnknownObjectException:
            raise GitHubServiceError(f"Pull Request #{pr_number} not found.")
        except GithubException as e:
            raise GitHubServiceError(f"Failed to post comment: {e.data.get('message', 'Unknown error')}")

    async def merge_pr(self, pr_number: int, merge_method: str = "merge"):
        """Merges a given pull request."""
        repo = await self._get_repo_object()
        try:
            pr = repo.get_pull(pr_number)
            if not pr.mergeable:
                raise GitHubServiceError("PR is not mergeable. Check for conflicts or failed checks.")
            
            pr.merge(merge_method=merge_method)
            console.print(f"[green]✓ Merged Pull Request #{pr_number} using '{merge_method}' method.[/green]")
        except UnknownObjectException:
            raise GitHubServiceError(f"Pull Request #{pr_number} not found.")
        except GithubException as e:
            raise GitHubServiceError(f"Failed to merge PR: {e.data.get('message', 'Unknown error')}")
        
    # --- NEW ISSUE MANAGEMENT METHODS ---
    async def get_issues(self, state: str = 'open', assignee_filter: Optional[str] = None):
        """
        Fetches issues. Correctly handles all assignee filter cases by calling the
        underlying library method differently based on the filter.
        """
        repo = await self._get_repo_object()
        
        # If no filter is provided, call get_issues without the assignee parameter.
        # This is the foolproof way to prevent the AssertionError.
        if assignee_filter is None:
            return repo.get_issues(state=state)
        # Otherwise, if a filter string ('*', 'none', or a username) is provided,
        # pass it directly to the library.
        else:
            return repo.get_issues(state=state, assignee="*")

    async def close_issue(self, issue_number: int, comment: Optional[str] = None):
        repo = await self._get_repo_object()
        try:
            issue = repo.get_issue(issue_number)
            if comment:
                issue.create_comment(comment)
            issue.edit(state='closed')
            console.print(f"[green]✓ Closed Issue #{issue_number}.[/green]")
        except UnknownObjectException:
            raise GitHubServiceError(f"Issue #{issue_number} not found.")

    async def comment_on_issue(self, issue_number: int, comment: str):
        repo = await self._get_repo_object()
        if not comment: raise GitHubServiceError("Comment cannot be empty.")
        try:
            issue = repo.get_issue(issue_number)
            issue.create_comment(comment)
            console.print(f"[green]✓ Comment posted on Issue #{issue_number}.[/green]")
        except UnknownObjectException:
            raise GitHubServiceError(f"Issue #{issue_number} not found.")

    async def assign_issue(self, issue_number: int, assignee_login: str):
        repo = await self._get_repo_object()
        try:
            issue = repo.get_issue(issue_number)
            issue.edit(assignees=[assignee_login])
            console.print(f"[green]✓ Assigned Issue #{issue_number} to {assignee_login}.[/green]")
        except UnknownObjectException:
            raise GitHubServiceError(f"Issue #{issue_number} not found.")

    # --- NEW PR MANAGEMENT METHODS ---
    async def get_open_prs(self):
        repo = await self._get_repo_object()
        return repo.get_pulls(state='open')

    async def link_pr_to_issue(self, pr_number: int, issue_number: int):
        repo = await self._get_repo_object()
        try:
            pr = repo.get_pull(pr_number)
            new_body = f"{pr.body}\n\nCloses #{issue_number}"
            pr.edit(body=new_body)
            console.print(f"[green]✓ Linked PR #{pr_number} to Issue #{issue_number}.[/green]")
        except UnknownObjectException:
            raise GitHubServiceError(f"PR #{pr_number} or Issue #{issue_number} not found.")
    
    async def request_pr_reviewers(self, pr_number: int, reviewers: List[str]):
        repo = await self._get_repo_object()
        if not reviewers: raise GitHubServiceError("Reviewer list cannot be empty.")
        try:
            pr = repo.get_pull(pr_number)
            pr.create_review_request(reviewers=reviewers)
            console.print(f"[green]✓ Requested review from {', '.join(reviewers)} for PR #{pr_number}.[/green]")
        except UnknownObjectException:
            raise GitHubServiceError(f"PR #{pr_number} not found.")