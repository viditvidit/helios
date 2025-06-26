# src/ai_assistant/cli/interactive/orchestrator.py

import asyncio
import re
from rich.console import Console

console = Console()

class Orchestrator:
    def __init__(self, session):
        self.session = session

    def _extract_commands(self, text: str) -> tuple[str, list[str]]:
        # This function is good, no changes needed.
        command_pattern = re.compile(r'(/[\w_]+(?:\s+[^/]+)*)')
        commands = command_pattern.findall(text)
        cleaned_text = re.sub(r'\s{2,}', ' ', command_pattern.sub("", text)).strip()
        return cleaned_text, [c.strip() for c in commands]

    async def handle(self, user_input: str):
        """
        New orchestrator logic:
        1. If only commands, run them for display.
        2. If chat/mixed, run commands SILENTLY, capture their output,
           then feed it all into a final, context-aware AI prompt.
        """
        cleaned_prompt, commands = self._extract_commands(user_input)

        # --- SCENARIO 1: Pure command(s) for display ---
        if not cleaned_prompt and commands:
            for cmd in commands:
                # `capture_output=False` is the default, so they will print
                await self.session.command_handler.handle(cmd)
            return

        # --- SCENARIO 2: Pure chat (no commands) ---
        if not commands:
            # Just pass to the normal chat handler
            await self.session.chat_handler.handle(user_input, self.session)
            return
            
        # --- SCENARIO 3: The "Smart Context-Gathering" Mixed-Intent Request ---
        if cleaned_prompt and commands:
            console.print(f"[cyan]Orchestrating request:[/cyan] [dim]'{user_input}'[/dim]")
            
            captured_outputs = {}
            
            # Step 1: Execute all commands silently to gather their output.
            with console.status("[bold yellow]Gathering context from commands...[/bold yellow]"):
                for cmd in commands:
                    # Execute with `capture_output=True`
                    output = await self.session.command_handler.handle(cmd, capture_output=True)
                    captured_outputs[cmd] = output or "Command produced no output."
            
            console.print("[cyan]Context gathered. Synthesizing final response...[/cyan]")

            # Step 2: Build a new, context-rich prompt for the final generation step.
            final_prompt_parts = [
                "You are an expert AI assistant. The user has a complex request. "
                "You must use the context provided below from the commands that were pre-executed to fulfill the user's final request.",
                "\n--- Context from Executed Commands ---"
            ]

            for command, output in captured_outputs.items():
                final_prompt_parts.append(f"### Output from `{command}`:\n{output}\n")
            
            final_prompt_parts.append("--- End of Context ---")
            final_prompt_parts.append("\n**User's Final Request:**")
            final_prompt_parts.append(f"Based on the context above, please fulfill this request: '{cleaned_prompt}'")
            
            final_prompt = "\n".join(final_prompt_parts)

            # Step 3: Call the standard chat handler with this powerful new prompt.
            # The chat handler doesn't need to change. It just receives a more detailed prompt.
            await self.session.chat_handler.handle(final_prompt, self.session)