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
        # THE FIX: Wrap the repo_path in quotes to handle spaces in the path.
        cmd = f'git -C "{repo_path}" diff --cached'
        proc = await asyncio.create_subprocess_shell(
            cmd,
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
            return await self._run_git_command(repo_path, ['status', '--porcelain'])
        except Exception:
            return "Could not retrieve repository status."

    async def get_branches(self, repo_path: Path) -> str:
        """Get all local and remote branches."""
        try:
            return await self._run_git_command(repo_path, ['branch', '-a'])
        except Exception:
            return "Could not retrieve branch information."
    
    async def _run_git_command(self, repo_path: Path, command: List[str]) -> str:
        """
        Run a git command asynchronously using the safer exec method.
        This method is not vulnerable to shell injection as it doesn't use the shell.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                'git', *command,
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Allow some commands to fail gracefully (e.g., commit with nothing to commit)
            if process.returncode != 0 and not (command[0] == 'commit' and b'nothing to commit' in stdout):
                raise subprocess.CalledProcessError(
                    process.returncode, command, output=stdout, stderr=stderr
                )
            
            return stdout.decode('utf-8').strip()
            
        except FileNotFoundError:
            raise Exception("Git not found. Please install Git.")
        except subprocess.CalledProcessError as e:
            # Provide a more informative error message
            raise Exception(f"Git command failed: {' '.join(e.cmd)}\nError: {e.stderr.decode('utf-8').strip()}")
        except Exception as e:
            raise Exception(f"Git command failed: {e}")
    
    async def get_current_branch(self, repo_path: Path) -> str:
        """Get current git branch"""
        return await self._run_git_command(repo_path, ['branch', '--show-current'])
    
    async def get_recent_commits(self, repo_path: Path, count: int = 10) -> str:
        """Returns recent commits as a single string."""
        try:
            return await self._run_git_command(repo_path, ['log', f'-{count}', '--oneline'])
        except Exception:
            return "Could not retrieve recent commits."
    
    async def add_file(self, repo_path: Path, file_path: str) -> bool:
        """Add file to git staging"""
        try:
            await self._run_git_command(repo_path, ['add', file_path])
            return True
        except Exception:
            return False
    
    async def add_all(self, repo_path: Path) -> None:
        """Add all changes to git staging"""
        # THE FIX: Wrap the repo_path in quotes to handle spaces in the path.
        cmd = f'git -C "{repo_path}" add .'
        proc = await asyncio.create_subprocess_shell(
            cmd,
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
        except Exception as e:
            # A commit can fail if there are no staged changes, which is not a critical error.
            if "nothing to commit" in str(e):
                return False
            raise e
    
    async def push(self, repo_path: Path, branch: str) -> bool:
        """Push changes to remote"""
        try:
            await self._run_git_command(repo_path, ['push', 'origin', branch])
            return True
        except Exception:
            return False