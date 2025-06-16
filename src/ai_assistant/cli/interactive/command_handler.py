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
            if cmd == 'help': display.show_help()
            elif cmd == 'knight':
                await actions_impl.handle_knight_mode(self.session, ' '.join(args))
            elif cmd == 'knight_hybrid':
                await actions_impl.handle_knight_hybrid_mode(self.session, ' '.join(args))
            elif cmd == 'index':
                await actions_impl.handle_index(self.session)
            elif cmd == 'file': await actions.add_file_to_context(self.session, args[0] if args else "")
            elif cmd == 'refresh': await actions.refresh_repo_context(self.session)
            elif cmd == 'clear': actions.clear_history(self.session)
            elif cmd == 'files': display.list_files_in_context(self.session.current_files)
            elif cmd == 'repo': await actions.show_repository_stats(self.session)
            elif cmd == 'model': await actions.switch_model(self.session, args[0] if args else None)
            elif cmd == 'save_conversation': await actions.save_conversation(self.session, args[0] if args else "")
            elif cmd == 'new': await actions_impl.handle_new_file(self.session, ' '.join(args))
            elif cmd == 'save': await actions_impl.handle_save_last_code(self.session, args[0] if args else "")
            elif cmd == 'apply': await actions_impl.handle_apply_changes(self.session)
            
            # Git & GitHub Commands
            elif cmd == 'git_add': await actions_impl.handle_git_add(self.session, args)
            elif cmd == 'git_commit': await actions_impl.handle_git_commit(self.session, ' '.join(args))
            elif cmd == 'git_switch': await actions_impl.handle_git_switch(self.session, args[0] if args else "")
            elif cmd == 'git_pull': await actions_impl.handle_git_pull(self.session)
            elif cmd == 'git_push': await actions_impl.handle_git_push(self.session)
            elif cmd == 'review':
                show_diff = '-d' in args
                await actions_impl.handle_review(self.session, show_diff=show_diff)
            elif cmd == 'create_branch': await actions_impl.handle_git_create_branch(self.session)
            elif cmd == 'create_pr': await actions_impl.handle_create_pr(self.session)
            elif cmd == 'pr_approve':
                await actions_impl.handle_pr_approve(self.session, args[0] if args else "")
            elif cmd == 'pr_comment':
                await actions_impl.handle_pr_comment(self.session, args[0] if args else "")
            elif cmd == 'pr_merge':
                await actions_impl.handle_pr_merge(self.session, args[0] if args else "")
            elif cmd == 'create_issue': await actions_impl.handle_create_issue(self.session)
            elif cmd == 'create_repo': await actions_impl.handle_create_repo(self.session)
            elif cmd == 'git_log': await actions_impl.handle_git_log(self.session)
            elif cmd == 'issue_list': await actions_impl.handle_issue_list(self.session, args)
            elif cmd == 'pr_list': await actions_impl.handle_pr_list(self.session)
            elif cmd == 'issue_close': await actions_impl.handle_issue_close(self.session, args)
            elif cmd == 'issue_comment': await actions_impl.handle_issue_comment(self.session, args)
            elif cmd == 'issue_assign': await actions_impl.handle_issue_assign(self.session, args)
            elif cmd == 'pr_link_issue': await actions_impl.handle_pr_link_issue(self.session, args)
            elif cmd == 'pr_request_review': await actions_impl.handle_pr_request_review(self.session, args)
            
            # New AI Review Commands
            elif cmd == 'repo_summary': await actions_impl.handle_repo_summary(self.session)
            elif cmd == 'pr_review': await actions_impl.handle_pr_review(self.session, args[0] if args else "")

            # Code Quality Commands
            elif cmd == 'optimize':
                filename_arg = args[0] if args else ""
                # Allow using @mention syntax for the file
                if filename_arg.startswith('@'):
                    filename_arg = filename_arg[1:]
                await actions_impl.handle_optimize_file(self.session, filename_arg)
            elif cmd == 'scan': await actions_impl.handle_scan(self.session)

            else:
                self.console.print(f"[red]Unknown command: /{cmd}[/red]")
                display.show_help()

        except Exception as e:
            import traceback
            self.console.print(f"[red]Error executing command '/{cmd}': {e}[/red]")
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")