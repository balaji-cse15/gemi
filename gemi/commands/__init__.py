"""Command system — slash commands for the REPL."""
from .registry import COMMANDS, handle_command, is_command

__all__ = ["COMMANDS", "handle_command", "is_command"]
