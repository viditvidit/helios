import questionary

from ...logic import file_logic, git_logic, github_logic

# --- File Operations ---
async def handle_new_file(session, file_path: str):
    await file_logic.new_file(file_path, session.current_files)

async def handle_save_last_code(session, filename: str):
    await file_logic.save_code(session, filename)

async def handle_apply_changes(session):
    await file_logic.apply_changes(session)

# --- Git & GitHub Operations ---
async def handle_git_add(session, files: list[str]):
    await git_logic.add(files)

async def handle_git_commit(session, message: str):
    await git_logic.commit(message)
    
async def handle_git_switch(session, branch: str):
    await git_logic.switch(branch)
    
async def handle_git_pull(session):
    await git_logic.pull()

async def handle_git_push(session):
    await git_logic.push()

async def handle_review(session, show_diff: bool = False):
    """Dispatcher for the review and commit workflow."""
    commit_success = await git_logic.review_and_commit(show_diff=show_diff)
    if commit_success:
        if await questionary.confirm("Create a Pull Request for this commit?", default=True, auto_enter=False).ask_async():
            await github_logic.interactive_pr_creation(session)

async def handle_create_repo(session):
    await github_logic.create_repo(session)

async def handle_create_branch(session):
    await github_logic.create_branch(session)

async def handle_create_issue(session):
    await github_logic.create_issue(session)

async def handle_create_pr(session):
    """Dispatcher for the interactive PR creation workflow."""
    await github_logic.interactive_pr_creation(session)

async def handle_repo_summary(session):
    """Dispatcher for the repo summary workflow."""
    await github_logic.repo_summary(session)

async def handle_pr_review(session, pr_number_str: str):
    """Dispatcher for the interactive PR review workflow."""
    await github_logic.interactive_pr_review(session, pr_number_str)