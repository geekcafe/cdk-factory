#!/usr/bin/env python3
"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import argparse
import sys
from typing import List


class CommandlineArgs:
    """Command Line Args and Parser"""

    def __init__(self) -> None:
        # command line args
        self.parser = argparse.ArgumentParser(
            description="Additional Command Line args for the cdk deployments."
        )

        # Add the arguments
        self.parser.add_argument(
            "-b",
            "--branches",
            nargs="*",
            required=False,
            help="The git branch you want to synth.  This should match a git branch in you config.json file. Use * if you want to synth all.",
        )
        self.parser.add_argument(
            "-c",
            "--config",
            required=False,
            help="Path to your config file.",
        )

        self.parser.add_argument(
            "-o",
            "--cloud-assembly",
            required=False,
            help=(
                "Sets the directory where the synthesized Cloud Assembly "
                "(i.e. CloudFormation templates) will be placed."
            ),
        )

        self.display_directions: bool = True

        self.branches: List[str] | None = []
        self.config: str | None = None
        self.outdir: str | None = None
        self.parse_args()

    def parse_args(self) -> None:
        """
        Parses the args
        """
        # see if we have any arguments
        known_args, unknown_args = self.parser.parse_known_args()

        branches: str | List[str] = known_args.branches
        if isinstance(branches, str):
            print("found string, converting to an array")
            self.branches = [branches]
        else:
            self.branches = branches

        self.config = known_args.config

        # Make sure to remove your custom arguments before CDK processes the rest
        sys.argv = [sys.argv[0]] + unknown_args

        print(f"sys.argv: {sys.argv}")


def main():
    """Main"""
    # example usage
    args = CommandlineArgs()

    print(f"synth branch: {args.branches}")


if __name__ == "__main__":
    main()
