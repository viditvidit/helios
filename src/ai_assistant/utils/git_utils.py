# src/ai_assistant/utils/git_utils.py

import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict

class GitUtils:
    """Utility class for Git operations"""

    async def init_repo(self, repo_path: Path):
        """Initializes a new Git repository in the specified path."""
        try:
            await self._run_git_command(repo_path, ['init'])
            return True
        except Exception:
            return False

    async def get_staged_diff(self, repo_path: Path) -> str:
        """Retrieves the entire diff of staged changes as a single string."""
        return await self._run_git_command(repo_path, ['diff', '--cached'])

    async def get_staged_diff_by_file(self, repo_path: Path) -> Dict[str, str]:
        """
        Retrieves staged changes and returns a dictionary mapping
        filename to its specific diff content.
        """
        file_diffs = {}
        staged_files = await self.get_staged_files(repo_path)
        
        for file in staged_files:
            # Get the diff for each file individually
            diff_content = await self._run_git_command(repo_path, ['diff', '--cached', '--', file])
            if diff_content:
                file_diffs[file] = diff_content
        return file_diffs

    async def get_staged_files(self, repo_path: Path) -> List[str]:
        """Get a list of staged file paths."""
        result = await self._run_git_command(repo_path, ['diff', '--cached', '--name-only'])
        return [line for line in result.splitlines() if line]
    
    async def get_unstaged_files(self, repo_path: Path) -> List[str]:
        """Get a list of files that are modified but not staged."""
        result = await self._run_git_command(repo_path, ['status', '--porcelain'])
        return [line.strip().split(" ", 1)[1] for line in result.splitlines() if line.strip()]

    async def get_local_branches(self, repo_path: Path) -> List[str]:
        """Get a list of local branch names."""
        # --- FIX: Fetch first to ensure the list is up to date ---
        try:
            await self._run_git_command(repo_path, ['fetch', 'origin'])
        except Exception:
            pass # Continue even if fetch fails
        result = await self._run_git_command(repo_path, ['branch', '--list'])
        return [b.replace('*', '').strip() for b in result.splitlines()]

    async def get_all_branches(self, repo_path: Path) -> List[str]:
        """Get a list of all remote branch names."""
        try:
            await self._run_git_command(repo_path, ['fetch', 'origin'])
        except Exception:
            pass

        result = await self._run_git_command(repo_path, ['branch', '-r'])
        branches = []
        for line in result.splitlines():
            branch = line.strip()
            if branch.startswith('origin/') and 'HEAD ->' not in branch:
                branch_name = branch.replace('origin/', '')
                branches.append(branch_name)
        return branches

    async def switch_branch(self, repo_path: Path, branch_name: str, create: bool = False) -> bool:
        """Switches to an existing local or remote branch, or creates a new one."""
        
        # --- THE CORE FIX ---
        # 1. Always fetch the latest from the remote to know about all branches.
        try:
            await self._run_git_command(repo_path, ['fetch', 'origin'])
        except Exception:
            pass  # Not fatal, a local branch switch might still work.

        # 2. If creating a new branch, just do it and exit.
        if create:
            try:
                await self._run_git_command(repo_path, ['switch', '-c', branch_name])
                return True
            except Exception:
                return False

        # 3. Try to switch directly. This works for existing local branches
        #    and for remote branches if tracking is already set up.
        try:
            await self._run_git_command(repo_path, ['switch', branch_name])
            return True
        except Exception:
            # This is expected to fail if the local branch doesn't exist yet.
            pass
            
        # 4. If direct switch fails, it's likely a remote branch that needs a
        #    local tracking branch created. This is the common case.
        try:
            await self._run_git_command(repo_path, ['switch', '--track', f'origin/{branch_name}'])
            return True
        except Exception:
            return False # If all attempts fail, return False.


    async def pull(self, repo_path: Path) -> bool:
        """Pulls latest changes for the current branch."""
        try:
            await self._run_git_command(repo_path, ['pull'])
            return True
        except Exception:
            return False

    async def is_git_repo(self, repo_path: Path) -> bool:
        """Check if the directory is a git repository."""
        return (repo_path / ".git").is_dir()
    
    async def get_status(self, repo_path: Path) -> str:
        """Get the status of the git repository."""
        return await self._run_git_command(repo_path, ['status', '--porcelain'])

    async def get_branches(self, repo_path: Path) -> str:
        """Get all local and remote branches."""
        return await self._run_git_command(repo_path, ['branch', '-a'])

    async def get_current_branch(self, repo_path: Path) -> str:
        """Get current git branch"""
        return await self._run_git_command(repo_path, ['branch', '--show-current'])
    
    async def get_recent_commits(self, repo_path: Path, count: int = 10) -> str:
        """Returns recent commits as a single string."""
        return await self._run_git_command(repo_path, ['log', f'-{count}', '--oneline'])
    
    async def add_files(self, repo_path: Path, file_paths: List[str]) -> bool:
        """Add multiple files to git staging."""
        try:
            await self._run_git_command(repo_path, ['add'] + file_paths)
            return True
        except Exception:
            return False

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
        
    async def get_formatted_log(self, repo_path: Path, count: int = 15) -> str:
        """Gets a nicely formatted git log."""
        format_str = "%C(yellow)%h%C(reset) %C(green)(%cr)%C(reset) %C(bold blue)<%an>%C(reset) %s"
        return await self._run_git_command(repo_path, ['log', f'--pretty=format:{format_str}', f'-n{count}'])
    
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

             stdout_str = stdout.decode('utf-8', errors='ignore').strip()
             stderr_str = stderr.decode('utf-8', errors='ignore').strip()

             if process.returncode != 0:
                 # raise so we can catch below with full output
                 raise subprocess.CalledProcessError(
                     process.returncode, command, output=stdout, stderr=stderr
                )

             return stdout_str
         except FileNotFoundError:
             raise Exception("Git not found. Please install Git.")
         except subprocess.CalledProcessError as e:
             out = e.output.decode('utf-8', errors='ignore').strip() if e.output else ""
             err = e.stderr.decode('utf-8', errors='ignore').strip() if e.stderr else ""
             msg = err or out or f"exit code {e.returncode}"
             raise Exception(f"Git command failed: {msg}")
         except Exception as e:
             raise Exception(f"An unexpected error occurred with git: {e}")

    async def commit(self, repo_path: Path, message: str) -> bool:
        """Commit changes. Returns True if a commit was made, False otherwise."""
        try:
            result = await self._run_git_command(repo_path, ['commit', '-m', message])
            
            if "nothing to commit" in result or "no changes added to commit" in result:
                return False
            return True
        except Exception as e:
            if "nothing to commit" in str(e).lower():
                return False
            raise e