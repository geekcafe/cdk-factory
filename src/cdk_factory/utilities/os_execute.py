"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List
import subprocess
from aws_lambda_powertools import Logger

logger = Logger()


class OsExecute:
    """OS Execute. Runa command in a subprocess"""

    @staticmethod
    def execute(commands: List[str]) -> str | None:
        """Execute a command"""

        if not commands:
            logger.error("No commands provided")
            return None

        print(f"Executing {commands}")

        try:
            output = subprocess.check_output(commands).strip().decode()
        except subprocess.CalledProcessError:
            string_commands = " ".join(commands)
            logger.exception(f"Error executing {string_commands}")
            return None
        except Exception as e:  # pylint: disable=w0718
            string_commands = " ".join(commands)
            logger.exception(f"Error executing {string_commands}: {e}")
            return None

        return output
