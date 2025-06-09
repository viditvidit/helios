import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

class GitUtils:
    """Utility class for Git operations"""

    async def get_staged_diff(self, repo_path: Path) -> str:
        """
        Retrieves the diff of staged changes for the repository.
        """
        # Run the git diff command to get the staged (cached) diff.
        proc = await asyncio.create_subprocess_shell(
            f"git -C {repo_path} diff --cached",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise Exception(f"Error getting staged diff: {stderr.decode().strip()}")
        return stdout.decode().strip()

    async def is_git_repo(self, repo_path: Path) -> bool:
        """Check if the directory is a git repository."""
        git_dir = repo_path / ".git"
        return git_dir.exists() and git_dir.is_dir()
    
    async def get_status(self, repo_path: Path) -> str:
        """Get the status of the git repository."""
        try:
            return await self._run_git_command(repo_path, ['status'])
        except Exception:
            return "Could not retrieve repository status."

    async def get_branches(self, repo_path: Path) -> str:
        """Get all local and remote branches."""
        try:
            return await self._run_git_command(repo_path, ['branch', '-a'])
        except Exception:
            return "Could not retrieve branch information."
    
    async def _run_git_command(self, repo_path: Path, command: List[str]) -> str:
        """Run a git command asynchronously"""
        try:
            process = await asyncio.create_subprocess_exec(
                'git', *command,
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, command, output=stdout, stderr=stderr
                )
            
            return stdout.decode('utf-8').strip()
            
        except FileNotFoundError:
            raise Exception("Git not found. Please install Git.")
        except Exception as e:
            raise Exception(f"Git command failed: {e}")
    
    async def get_current_branch(self, repo_path: Path) -> str:
        """Get current git branch"""
        return await self._run_git_command(repo_path, ['branch', '--show-current'])
    
    async def get_recent_commits(self, repo_path: Path, count: int = 10) -> List[Dict]:
        try:
            return await self._run_git_command(repo_path, ['log', f'-{count}', '--oneline'])
        except Exception:
            return "Could not retrieve recent commits."
    
    async def get_changed_files(self, repo_path: Path) -> List[str]:
        """Get list of changed files"""
        try:
            # Get staged files
            staged = await self._run_git_command(repo_path, ['diff', '--cached', '--name-only'])
            staged_files = staged.split('\n') if staged else []
            
            # Get unstaged files
            unstaged = await self._run_git_command(repo_path, ['diff', '--name-only'])
            unstaged_files = unstaged.split('\n') if unstaged else []
            
            # Get untracked files
            untracked = await self._run_git_command(repo_path, ['ls-files', '--others', '--exclude-standard'])
            untracked_files = untracked.split('\n') if untracked else []
            
            # Combine and deduplicate
            all_files = set(staged_files + unstaged_files + untracked_files)
            return [f for f in all_files if f]
            
        except Exception:
            return []
    
    async def get_repo_info(self, repo_path: Path) -> Dict:
        """Get repository information"""
        try:
            remote_url = await self._run_git_command(repo_path, ['remote', 'get-url', 'origin'])
            return {
                'remote_url': remote_url,
                'is_git_repo': True
            }
        except Exception:
            return {'is_git_repo': False}
    
    async def initialize_repository(self, repo_path: Path) -> bool:
        """Initialize a new Git repository in the specified path."""
        try:
            # Check if it's already a git repo to avoid re-initializing (git init is safe but can produce output)
            if await self.is_git_repo(repo_path):
                # print(f"Path {repo_path} is already a Git repository.") # Optional: log or print
                return True # Indicate success or already initialized
            
            await self._run_git_command(repo_path, ['init'])
            # You might want to add a default branch creation here, e.g.:
            # await self._run_git_command(repo_path, ['checkout', '-b', 'main'])
            return True
        except Exception as e:
            # print(f"Failed to initialize repository at {repo_path}: {e}") # Optional: log error
            return False

    async def create_branch(self, repo_path: Path, branch_name: str) -> bool:
        """Create a new branch"""
        try:
            await self._run_git_command(repo_path, ['checkout', '-b', branch_name])
            return True
        except Exception:
            return False
    
    async def add_file(self, repo_path: Path, file_path: str) -> bool:
        """Add file to git staging"""
        try:
            await self._run_git_command(repo_path, ['add', file_path])
            return True
        except Exception:
            return False
    
    async def add_all(self, repo_path: Path) -> None:
        """Add all changes to git staging"""
        # Run the git add command to stage all changes.
        proc = await asyncio.create_subprocess_shell(
            f"git -C {repo_path} add .",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise Exception(f"Error staging changes: {stderr.decode().strip()}")
        return
    
    async def commit(self, repo_path: Path, message: str) -> bool:
        """Commit changes"""
        try:
            await self._run_git_command(repo_path, ['commit', '-m', message])
            return True
        except Exception:
            return False
    
    async def push(self, repo_path: Path, branch: str) -> bool:
        """Push changes to remote"""
        try:
            await self._run_git_command(repo_path, ['push', 'origin', branch])
            return True
        except Exception:
            return False
    
    async def get_file_diff(self, repo_path: Path, file_path: str) -> str:
        """Get diff for a specific file"""
        try:
            return await self._run_git_command(repo_path, ['diff', file_path])
        except Exception:
            return ""

    async def checkout_branch(self, repo_path: Path, branch_name: str) -> bool:
        try:
            await self._run_git_command(repo_path, ['checkout', branch_name])
            return True
        except Exception:
            return False
    
    async def create_and_checkout_branch(self, repo_path: Path, branch_name: str) -> bool:
        try:
            await self._run_git_command(repo_path, ['checkout', '-b', branch_name])
            return True
        except Exception:
            return False