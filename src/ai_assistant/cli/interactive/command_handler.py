from . import actions, display, actions_impl

class CommandHandler:
    def __init__(self, session):
        self.session = session
        self.console = display.console

    async def handle(self, command_str: str):
        """Parse and dispatch slash commands."""
        parts = command_str[1:].strip().split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            # General Commands
            if cmd == 'help':
                display.show_help()
            elif cmd == 'file':
                await actions.add_file_to_context(self.session, args[0] if args else "")
            elif cmd == 'refresh':
                await actions.refresh_repo_context(self.session)
            elif cmd == 'clear':
                actions.clear_history(self.session)
            elif cmd == 'files':
                display.list_files_in_context(self.session.current_files)
            elif cmd == 'repo':
                await actions.show_repository_stats(self.session)
            elif cmd == 'model':
                await actions.switch_model(self.session, args[0] if args else None)
            elif cmd == 'save_conversation':
                await actions.save_conversation(self.session, args[0] if args else "")
            elif cmd == 'new':
                await actions_impl.handle_new_file(self.session, args[0] if args else "")
            elif cmd == 'save':
                await actions_impl.handle_save_last_code(self.session, args[0] if args else "")
            elif cmd == 'apply':
                await actions_impl.handle_apply_changes(self.session)
            
            # Git & GitHub Commands
            elif cmd == 'git_add':
                await actions_impl.handle_git_add(self.session, args)
            elif cmd == 'git_commit':
                await actions_impl.handle_git_commit(self.session, ' '.join(args))
            elif cmd == 'git_push':
                await actions_impl.handle_git_push(self.session)
            elif cmd == 'review':
                await actions_impl.handle_review(self.session)
            elif cmd == 'create_repo':
                await actions_impl.handle_create_repo(self.session)
            elif cmd == 'create_branch':
                await actions_impl.handle_create_branch(self.session)
            elif cmd == 'create_pr':
                await actions_impl.handle_create_pr(self.session)
            elif cmd == 'create_issue':
                await actions_impl.handle_create_issue(self.session)

            else:
                self.console.print(f"[red]Unknown command: /{cmd}[/red]")
                display.show_help()

        except Exception as e:
            import traceback
            self.console.print(f"[red]Error executing command '/{cmd}': {e}[/red]")
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")