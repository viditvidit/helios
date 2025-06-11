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
            if cmd == 'help':
                display.show_help()
            elif cmd == 'file':
                if not args:
                    self.console.print("[red]Usage: /file <path>[/red]")
                    return
                await actions.add_file_to_context(self.session, args[0])
            elif cmd == 'refresh':
                await actions.refresh_repo_context(self.session)
            elif cmd == 'clear':
                actions.clear_history(self.session)
            elif cmd == 'files':
                display.list_files_in_context(self.session.current_files)
            elif cmd == 'repo':
                await actions.show_repository_stats(self.session)
            elif cmd == 'model':
                if args:
                    # Legacy support for direct model name
                    await actions.switch_model(self.session, args[0])
                else:
                    # Show interactive selector
                    await actions.switch_model(self.session)
            elif cmd == 'save_conversation' and args:
                await actions.save_conversation(self.session, args[0])
            elif cmd == 'new' and args:
                await actions_impl.handle_new_file(self.session, args[0])
            elif cmd == 'save' and args:
                await actions_impl.handle_save_last_code(self.session, args[0])
            elif cmd == 'apply':
                await actions_impl.handle_apply_changes(self.session)
            elif cmd == 'git_add' and args:
                await actions_impl.handle_git_add(self.session, args)
            elif cmd == 'git_commit':
                if not args:
                    self.console.print("[red]Usage: /git_commit <message>[/red]")
                    return
                commit_message = ' '.join(args)
                await actions_impl.handle_git_commit(self.session, commit_message)
            elif cmd == 'git_push':
                await actions_impl.handle_git_push(self.session)
            elif cmd == 'review':
                summary_only = '-s' in args
                if summary_only:
                    # Show only summary
                    await actions_impl.handle_repo_review(self.session, summary_only=True, show_diff=False)
                else:
                    # Show both summary and diff (default)
                    await actions_impl.handle_repo_review(self.session, summary_only=False, show_diff=True)
            elif cmd == 'save_commit' and args:
                if not args:
                    self.console.print("[red]Usage: /save_commit <filename> [commit_message][/red]")
                else:
                    commit_msg = ' '.join(args[1:]) if len(args) > 1 else None
                    await actions_impl.handle_save_and_commit(self.session, args[0], commit_msg)
            else:
                self.console.print(f"[red]Unknown command: /{cmd}[/red]")
                display.show_help()

        except Exception as e:
            import traceback
            self.console.print(f"[red]Error executing command '/{cmd}': {e}[/red]")
            self.console.print(f"[dim]{traceback.format_exc()}[/dim]")