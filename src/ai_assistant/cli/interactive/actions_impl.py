import questionary

from ...logic import file_logic, git_logic, github_logic, indexing_logic, code_logic
from ...services.github_service import GitHubService
from ...utils.git_utils import GitUtils
from rich.console import Console

console = Console()

# --- File Operations ---
async def handle_new_file(session, file_path: str):
    await file_logic.new_file(file_path, session.current_files)
    # Ask to re-index
    if await questionary.confirm("Re-index repository to include this new file?", default=True, auto_enter=False).ask_async():
        await handle_index(session)

async def handle_save_last_code(session, filename: str):
    success = await file_logic.save_code(session, filename)
    # Ask to re-index
    if success and await questionary.confirm("Re-index repository to include these changes?", default=True, auto_enter=False).ask_async():
        await handle_index(session)

async def handle_apply_changes(session):
    await file_logic.apply_changes(session)

async def handle_index(session):
    """Dispatcher for the manual indexing command."""
    file_contents = await indexing_logic.run_indexing(session.config)
    if file_contents:
        session.current_files.clear()
        session.current_files.update(file_contents)

async def handle_optimize_file(session, filename: str):
    """Handler for the /optimize command."""
    if not filename: return console.print("[red]Usage: /optimize <filename>[/red]")
    
    optimized_content = await code_logic.optimize_file(session, filename)
    if optimized_content:
        # Piggyback on the main chat handler's code review UI
        await session.chat_handler._handle_code_response(optimized_content)

async def handle_scan(session):
    """Handler for the /scan command."""
    await code_logic.scan_repository(session)

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
    """Dispatcher for the review -> commit -> push -> PR workflow."""
    commit_success, branch_name = await git_logic.review_and_commit(show_diff=show_diff)
    if not commit_success:
        return

    # --- NEW PUSH -> PR FLOW ---
    if await questionary.confirm("Push these changes to the remote?", default=True, auto_enter=False).ask_async():
        git_utils = GitUtils()
        with console.status(f"Pushing '{branch_name}'..."):
            await git_utils.push(session.config.work_dir, branch_name, set_upstream=True)
        console.print(f"[green]✓ Branch '{branch_name}' pushed successfully.[/green]")

        # Now, intelligently ask about PR creation
        service = GitHubService(session.config)
        existing_pr_url = await service.check_for_open_pr(branch_name)

        if existing_pr_url:
            console.print(f"[yellow]An open Pull Request already exists for this branch:[/yellow] {existing_pr_url}")
            return
            
        if await questionary.confirm("Create a Pull Request for this branch?", default=True, auto_enter=False).ask_async():
            await github_logic.interactive_pr_creation(session)

async def handle_pr_approve(session, pr_number_str: str):
    await github_logic.approve_pr(session, pr_number_str)

async def handle_pr_comment(session, pr_number_str: str):
    await github_logic.comment_on_pr(session, pr_number_str)

async def handle_pr_merge(session, pr_number_str: str):
    await github_logic.merge_pr(session, pr_number_str)

async def handle_create_repo(session):
    await github_logic.create_repo(session)

async def handle_git_create_branch(session):
    """Creates and switches to a new local branch."""
    git_utils = GitUtils()
    repo_path = Path.cwd()
    if not await git_utils.is_git_repo(repo_path): return console.print("[red]Not a git repository.[/red]")
    
    branch_name = await questionary.text("Enter name for new local branch:").ask_async()
    if not branch_name: return console.print("[red]Branch name cannot be empty.[/red]")
    
    if await git_utils.switch_branch(repo_path, branch_name, create=True):
        console.print(f"[green]✓ Created and switched to new branch '{branch_name}'.[/green]")
    else:
        console.print(f"[red]Failed to create branch '{branch_name}'. It might already exist.[/red]")

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
    await github_logic.pr_review(session, pr_number_str)

# --- Git ---
async def handle_git_log(session):
    await git_logic.log()

# --- GitHub ---
async def handle_issue_list(session, args):
    """Dispatcher for listing issues with filter handling."""
    assignee = None # Default is None, which logic layer will treat as '*'
    
    if args and args[0].lower() == '--filter' and len(args) > 1:
        filter_value = args[1].lower()
        if filter_value == 'all':
            # 'all' means no filter, so we pass None to the logic layer
            assignee = None
        else:
            # Pass 'none', '*', or a username directly
            assignee = filter_value
    # Retain legacy support for /issue_list <username>
    elif args and not args[0].startswith('--'):
        assignee = args[0]
    
    # NEW: If no args, default to '*'
    if not args:
        assignee = '*'
        
    await github_logic.list_issues(session, assignee)

async def handle_pr_list(session):
    await github_logic.list_prs(session)

async def handle_issue_close(session, args):
    issue_number = args[0] if args else ""
    comment = ' '.join(args[1:]) if len(args) > 1 else ""
    await github_logic.close_issue(session, issue_number, comment)

async def handle_issue_comment(session, args):
    issue_number = args[0] if args else ""
    comment = ' '.join(args[1:])
    await github_logic.comment_on_issue(session, issue_number, comment)

async def handle_issue_assign(session, args):
    issue_number = args[0] if len(args) > 0 else ""
    assignee = args[1] if len(args) > 1 else ""
    await github_logic.assign_issue(session, issue_number, assignee)

async def handle_pr_link_issue(session, args):
    pr_number = args[0] if len(args) > 0 else ""
    issue_number = args[1] if len(args) > 1 else ""
    await github_logic.link_pr_to_issue(session, pr_number, issue_number)

async def handle_pr_request_review(session, args):
    pr_number = args[0] if len(args) > 0 else ""
    reviewers = args[1:]
    await github_logic.request_pr_reviewers(session, pr_number, reviewers)