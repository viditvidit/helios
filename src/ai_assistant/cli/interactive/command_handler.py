from . import actions, display, actions_impl

class CommandHandler:
    def __init__(self, session):
        self.session = session
        self.console = display.console

    async def handle(self, command_str: str):
        """Parse and dispatch slash commands."""
        parts = command_str[1:].strip().split()
        if not parts: return
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            
            # General Commands
            if cmd in ['help', 'h']: display.show_help()
            elif cmd in ['knight', 'k']:
                await actions_impl.handle_knight_mode(self.session, ' '.join(args))
            elif cmd in ['index', 'i']:
                await actions_impl.handle_index(self.session)
            elif cmd in ['file', 'f']: await actions.add_file_to_context(self.session, args[0] if args else "")
            elif cmd in ['refresh', 'r']: await actions.refresh_repo_context(self.session)
            elif cmd in ['clear', 'c']: actions.clear_history(self.session)
            elif cmd in ['repo', 'rp']: await actions.show_repository_stats(self.session)
            elif cmd in ['model', 'm']: await actions.switch_model(self.session, args[0] if args else None)
            elif cmd in ['save_conversation', 'sc']: await actions.save_conversation(self.session, args[0] if args else "")
            elif cmd in ['new', 'n']: await actions_impl.handle_new_file(self.session, ' '.join(args))
            elif cmd in ['save', 's']: await actions_impl.handle_save_last_code(self.session, args[0] if args else "")
            elif cmd in ['apply', 'a']: await actions_impl.handle_apply_changes(self.session)
            
            # Git & GitHub Commands
            elif cmd in ['git_add', 'ga']: await actions_impl.handle_git_add(self.session, args)
            elif cmd in ['git_commit', 'gc']: await actions_impl.handle_git_commit(self.session, ' '.join(args))
            elif cmd in ['git_switch', 'gs']: await actions_impl.handle_git_switch(self.session, args[0] if args else "")
            elif cmd in ['git_pull', 'gp']: await actions_impl.handle_git_pull(self.session)
            elif cmd in ['git_push', 'gph']: await actions_impl.handle_git_push(self.session)
            elif cmd in ['review', 'rv']:
                show_diff = '-d' in args
                await actions_impl.handle_review(self.session, show_diff=show_diff)
            elif cmd in ['create_branch', 'cb']: await actions_impl.handle_git_create_branch(self.session)
            elif cmd in ['create_pr', 'pr']: await actions_impl.handle_create_pr(self.session)
            elif cmd in ['pr_approve', 'pa']:
                await actions_impl.handle_pr_approve(self.session, args[0] if args else "")
            elif cmd in ['pr_comment', 'pc']:
                await actions_impl.handle_pr_comment(self.session, args[0] if args else "")
            elif cmd in ['pr_merge', 'pm']:
                await actions_impl.handle_pr_merge(self.session, args[0] if args else "")
            elif cmd in ['create_issue', 'ci']: await actions_impl.handle_create_issue(self.session)
            elif cmd in ['create_repo', 'cr']: await actions_impl.handle_create_repo(self.session)
            elif cmd in ['git_log', 'gl']: await actions_impl.handle_git_log(self.session)
            elif cmd in ['issue_list', 'il']: await actions_impl.handle_issue_list(self.session, args)
            elif cmd in ['pr_list', 'pl']: await actions_impl.handle_pr_list(self.session)
            elif cmd in ['issue_close', 'ic']: await actions_impl.handle_issue_close(self.session, args)
            elif cmd in ['issue_comment', 'ico']: await actions_impl.handle_issue_comment(self.session, args)
            elif cmd in ['issue_assign', 'ia']: await actions_impl.handle_issue_assign(self.session, args)
            elif cmd in ['pr_link_issue', 'pli']: await actions_impl.handle_pr_link_issue(self.session, args)
            elif cmd in ['pr_request_review', 'prr']: await actions_impl.handle_pr_request_review(self.session, args)
            
            # New AI Review Commands
            elif cmd in ['repo_summary', 'rs']: await actions_impl.handle_repo_summary(self.session)
            elif cmd in ['pr_review', 'prv']: await actions_impl.handle_pr_review(self.session, args[0] if args else "")

            # Code Quality Commands
            elif cmd in ['optimize', 'o']:
                filename_arg = args[0] if args else ""
                # Allow using @mention syntax for the file
                if filename_arg.startswith('@'):
                    filename_arg = filename_arg[1:]
                await actions_impl.handle_optimize_file(self.session, filename_arg)
            elif cmd in ['scan', 'sc']: await actions_impl.handle_scan(self.session)

            else:
                self.console.print(f"[red]Unknown command: /{cmd}[/red]")
                display.show_help()

        except Exception as e:
            import traceback
            self.console.print(f"[red]Error executing command '/{cmd}': {e}[/red]")
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")