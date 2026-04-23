"""
Synth Messages — Singleton collector for warnings and info during CDK synthesis.

Stacks and utilities can add messages during synth, and the summary is printed
at the end after the resource counts.

Usage:
    from cdk_factory.utilities.synth_messages import synth_messages

    # Add messages from anywhere during synth
    synth_messages.warning("Route conflict: GET /app/configuration exists in both sources")
    synth_messages.info("Discovered route: GET /app/configuration -> app-configurations")

    # Print summary (called by CdkAppFactory after synth)
    synth_messages.print_summary()

Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import List, Tuple


class SynthMessages:
    """Collects warnings and info messages during CDK synthesis for a summary report."""

    def __init__(self) -> None:
        self._messages: List[Tuple[str, str]] = []  # (level, message)

    def warning(self, message: str) -> None:
        """Add a warning message."""
        self._messages.append(("warning", message))

    def info(self, message: str) -> None:
        """Add an info message."""
        self._messages.append(("info", message))

    def error(self, message: str) -> None:
        """Add an error message."""
        self._messages.append(("error", message))

    @property
    def warnings(self) -> List[str]:
        """All warning messages."""
        return [msg for level, msg in self._messages if level == "warning"]

    @property
    def errors(self) -> List[str]:
        """All error messages."""
        return [msg for level, msg in self._messages if level == "error"]

    @property
    def has_warnings(self) -> bool:
        return any(level == "warning" for level, _ in self._messages)

    @property
    def has_errors(self) -> bool:
        return any(level == "error" for level, _ in self._messages)

    def clear(self) -> None:
        """Reset all messages."""
        self._messages.clear()

    def print_summary(self) -> None:
        """Print a formatted summary of all collected messages."""
        if not self._messages:
            return

        warnings = [msg for level, msg in self._messages if level == "warning"]
        errors = [msg for level, msg in self._messages if level == "error"]
        infos = [msg for level, msg in self._messages if level == "info"]

        print(f"\n📋 Synth Messages Summary")
        print(f"   {'─' * 45}")

        if infos:
            print(f"\n   ℹ️  Info ({len(infos)}):")
            for msg in infos:
                print(f"      • {msg}")

        if warnings:
            print(f"\n   ⚠️  Warnings ({len(warnings)}):")
            for msg in warnings:
                print(f"      • {msg}")

        if errors:
            print(f"\n   ❌ Errors ({len(errors)}):")
            for msg in errors:
                print(f"      • {msg}")

        print()


# Module-level singleton instance
synth_messages = SynthMessages()
