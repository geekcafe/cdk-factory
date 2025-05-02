from pathlib import Path
from typing import List, Optional

import yaml

from cdk_factory.workload.workload_factory import WorkloadConfig


class CommandLoader:
    """
    Loads external command files defined in the workload configuration.
    Supports YAML and shell script formats, with fallback support if a file is
    missing, invalid, or returns no usable commands.
    """

    def __init__(self, workload: WorkloadConfig):
        """
        Initialize the CommandLoader with a list of command definitions.

        :param commands: A list of dictionaries, each containing a 'name' and 'file' key.
        """
        self.workload = workload
        commands = workload.devops.commands
        self.command_map = {
            cmd["name"]: cmd["file"]
            for cmd in commands
            if isinstance(cmd, dict) and "name" in cmd and "file" in cmd
        }

    def get(self, name: str, fallback: Optional[List[str]] = None) -> List[str]:
        """
        Retrieve the list of commands for a given name, loading from the appropriate file type.
        Falls back to the provided fallback commands if file is missing, invalid, or empty.

        :param name: The name of the command (e.g. 'cdk_synth').
        :param fallback: An optional list of fallback commands to use if the file cannot be loaded.
        :return: A list of shell commands as strings.
        """
        file_path = self.command_map.get(name)
        if not file_path:
            print(f"⚠️ Command name '{name}' not found in command map, using fallback.")
            return fallback or []

        path = self.__resolve_path(file_path)
        if not path:
            print(
                f"⚠️ Command file '{file_path}' not found in workload paths, using fallback."
            )
            return fallback or []

        if not path.exists():
            print(f"⚠️ Command file '{path}' not found, using fallback.")
            return fallback or []

        try:
            ext = path.suffix.lower()

            if ext in [".yml", ".yaml"]:
                with open(path, mode="r", encoding="utf-8") as f:
                    parsed = yaml.safe_load(f)
                commands = parsed.get("commands", [])
            elif ext == ".sh":
                with open(path, mode="r", encoding="utf-8") as f:
                    commands = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.strip().startswith("#")
                    ]
            else:
                print(
                    f"⚠️ Unsupported extension '{ext}' for command file '{file_path}', using fallback."
                )
                return fallback or []

            if not commands:
                print(
                    f"⚠️ Command file '{file_path}' is empty or has no usable commands, using fallback."
                )
                return fallback or []

            return commands

        except Exception as e:  # pylint: disable=w0718
            print(f"⚠️ Error loading command file '{file_path}': {e}, using fallback.")
            return fallback or []

    def __resolve_path(self, file_path: str) -> Optional[Path]:
        """
        Find the path for a given command name in the command map.

        :param name: The name of the command.
        :return: The path to the command file, or None if not found.
        """
        path = Path(file_path).resolve()
        if path.exists():
            return path

        for workload_path in self.workload.paths:
            full_path = Path(workload_path).joinpath(file_path).resolve()
            if full_path.exists():
                return full_path
        return None
