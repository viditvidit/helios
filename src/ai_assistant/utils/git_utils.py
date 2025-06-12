import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

class GitUtils:
    """Utility class for Git operations"""

    async def get_staged_diff(self, repo_path: Path) -> str:
        """Retrieves the diff of staged changes for the repository."""
        return await self._run_git_command(repo_path, ['diff', '--cached'])

    async def get_staged_files(self, repo_path: Path) -> List[str]:
        """Get a list of staged file paths."""
        result = await self._run_git_command(repo_path, ['diff', '--cached', '--name-only'])
        return [line for line in result.splitlines() if line]
    
    async def get_unstaged_files(self, repo_path: Path) -> List[str]:
        """Get a list of files that are modified but not staged."""
        result = await self._run_git_command(repo_path, ['status', '--porcelain'])
        return [line.strip().split(" ", 1)[1] for line in result.splitlines()]

    async def get_local_branches(self, repo_path: Path) -> List[str]:
        """Get a list of local branch names."""
        result = await self._run_git_command(repo_path, ['branch', '--list'])
        # The output might contain '* ' for the current branch, so we clean it up
        return [b.replace('*', '').strip() for b in result.splitlines()]

    async def switch_branch(self, repo_path: Path, branch_name: str, create: bool = False) -> bool:
        """Switches to an existing branch or creates a new one."""
        command = ['switch']
        if create:
            command.append('-c')
        command.append(branch_name)
        try:
            await self._run_git_command(repo_path, command)
            return True
        except Exception:
            return False

    async def pull(self, repo_path: Path) -> bool:
        """Pulls latest changes for the current branch."""
        try:
            await self._run_git_command(repo_path, ['pull'])
            return True
        except Exception:
            return False

    async def is_git_repo(self, repo_path: Path) -> bool:
        """Check if the directory is a git repository."""
        git_dir = repo_path / ".git"
        return git_dir.exists() and git_dir.is_dir()
    
    async def get_status(self, repo_path: Path) -> str:
        """Get the status of the git repository."""
        return await self._run_git_command(repo_path, ['status', '--porcelain'])

    async def get_branches(self, repo_path: Path) -> str:
        """Get all local and remote branches."""
        return await self._run_git_command(repo_path, ['branch', '-a'])
    
    async def _run_git_command(self, repo_path: Path, command: List[str]) -> str:
        """Runs a git command asynchronously using the safer exec method."""
        try:
            process = await asyncio.create_subprocess_exec(
                'git', *command,
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                if not (command[0] == 'commit' and b'nothing to commit' in stdout):
                    raise subprocess.CalledProcessError(process.returncode, command, output=stdout, stderr=stderr)
            return stdout.decode('utf-8').strip()
        except FileNotFoundError:
            raise Exception("Git not found. Please install Git and ensure it's in your PATH.")
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.decode('utf-8').strip()
            raise Exception(f"Git command failed: {error_message}")
        except Exception as e:
            raise Exception(f"An unexpected error occurred with git: {e}")
    
    async def get_current_branch(self, repo_path: Path) -> str:
        """Get current git branch"""
        return await self._run_git_command(repo_path, ['branch', '--show-current'])
    
    async def get_recent_commits(self, repo_path: Path, count: int = 10) -> str:
        """Returns recent commits as a single string."""
        return await self._run_git_command(repo_path, ['log', f'-{count}', '--oneline'])
    
    async def add_file(self, repo_path: Path, file_path: str) -> bool:
        """Add a single file to git staging."""
        try:
            await self._run_git_command(repo_path, ['add', file_path])
            return True
        except Exception:
            return False

    async def add_files(self, repo_path: Path, file_paths: List[str]) -> bool:
        """Add multiple files to git staging."""
        try:
            await self._run_git_command(repo_path, ['add'] + file_paths)
            return True
        except Exception:
            return False
    
    async def commit(self, repo_path: Path, message: str) -> bool:
        """Commit changes"""
        try:
            await self._run_git_command(repo_path, ['commit', '-m', message])
            return "nothing to commit" not in await self.get_status(repo_path)
        except Exception as e:
            if "nothing to commit" in str(e):
                return False
            raise e
    
    async def push(self, repo_path: Path, branch: str, set_upstream: bool = False) -> bool:
        """Push changes to remote."""
        command = ['push', 'origin', branch]
        if set_upstream:
            command.insert(1, '--set-upstream')
        try:
            await self._run_git_command(repo_path, command)
            return True
        except Exception as e:
            raise Exception(f"Failed to push to remote: {e}")