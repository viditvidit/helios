from . import actions, display, stubs

class CommandHandler:
    def __init__(self, session):
        self.session = session
        self.console = display.console

    async def handle(self, command_str: str):
        """Parse and dispatch slash commands."""
        parts = command_str[1:].split()
        cmd = parts[0].lower()
        args = parts[1:]
        
        command_map = {
            'file': (actions.add_file_to_context, 1),
            'new': (stubs.handle_new_file, 1),
            'files': (display.list_files_in_context, 0, True),
            'repo': (actions.show_repository_stats, 0),
            'refresh': (actions.refresh_repo_context, 0),
            'clear': (actions.clear_history, 0),
            'model': (actions.switch_model, 1),
            'save_conversation': (actions.save_conversation, 1),
            'save': (stubs.handle_save_last_code, -1),
            'git_add': (stubs.handle_git_add, 1),
            'git_commit': (stubs.handle_git_commit, 1, False, True),
            'git_push': (stubs.handle_git_push, 0),
        }

        if cmd in command_map:
            func, min_args, pass_dict = command_map[cmd][:3] + (False,) * (3 - len(command_map[cmd]))
            join_args = command_map[cmd][3] if len(command_map[cmd]) > 3 else False

            if min_args == -1: # variable args, like /save [filename]
                pass
            elif len(args) < min_args:
                self.console.print(f"[red]Command '{cmd}' requires at least {min_args} argument(s).[/red]")
                return

            # Prepare arguments
            if pass_dict:
                call_args = (self.session.current_files,)
            elif join_args:
                call_args = (self.session, " ".join(args))
            else:
                call_args = (self.session,) + tuple(args)
            
            await func(*call_args)
        else:
            self.console.print(f"[red]Unknown command: {command_str}[/red]")
            display.show_help()