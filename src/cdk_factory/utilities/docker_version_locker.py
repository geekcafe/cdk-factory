#!/usr/bin/env python3
"""
Docker Version Locker — Resolve ECR "latest" tags to semver versions.

Queries ECR to find the semver tag sharing a digest with the "latest" tag
for each unique repository referenced in a locked versions file, then
writes the resolved versions back.

Usage:
    # Normal mode (resolve versions)
    python -m cdk_factory.utilities.docker_version_locker \
        --locked-versions /path/to/.docker-locked-versions.json \
        --profile <aws-profile> [--region us-east-1] [--dry-run]

    # Seed mode (generate initial file from config directory)
    python -m cdk_factory.utilities.docker_version_locker \
        --locked-versions /path/to/.docker-locked-versions.json \
        --profile <aws-profile> --seed --config-dir /path/to/configs
"""

import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Matches semver tags like 3.0.185, 1.17.44, 0.1.19
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class DockerVersionLocker:
    """Resolves ECR 'latest' tags to semver versions and updates a locked versions file."""

    def __init__(
        self,
        locked_versions_path: str,
        profile: str,
        region: str = "us-east-1",
        dry_run: bool = False,
        seed: bool = False,
        config_dir: Optional[str] = None,
    ) -> None:
        self.locked_versions_path = locked_versions_path
        self.profile = profile
        self.region = region
        self.dry_run = dry_run
        self.seed = seed
        self.config_dir = config_dir

    # --- File I/O ---

    def load_locked_versions(self, path: str) -> List[Dict[str, Any]]:
        """
        Load and validate the locked versions JSON array.

        Args:
            path: Path to the locked versions JSON file.

        Returns:
            List of locked version entry dicts.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is not valid JSON or not a JSON array.
        """
        with open(path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSON in locked versions file {path}: {e}"
                ) from e

        if not isinstance(data, list):
            raise ValueError(f"Locked versions file must contain a JSON array: {path}")

        return data

    def write_locked_versions(self, path: str, entries: List[Dict[str, Any]]) -> None:
        """
        Write entries as JSON with 4-space indent and trailing newline.

        Args:
            path: Path to write the locked versions file.
            entries: List of locked version entry dicts.
        """
        with open(path, "w") as f:
            json.dump(entries, f, indent=4)
            f.write("\n")

    # --- Core resolution ---

    def resolve_latest_version(self, ecr_client: Any, repo_name: str) -> Optional[str]:
        """
        Find the semver tag sharing a digest with the 'latest' tag.

        Args:
            ecr_client: A boto3 ECR client.
            repo_name: The ECR repository name.

        Returns:
            The semver tag string, or None if resolution failed.
        """
        try:
            resp = ecr_client.describe_images(
                repositoryName=repo_name,
                imageIds=[{"imageTag": "latest"}],
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "RepositoryNotFoundException":
                logger.warning("Repository not found: %s", repo_name)
                return None
            if error_code == "ImageNotFoundException":
                logger.warning("No 'latest' tag found in %s", repo_name)
                return None
            # Transient / unexpected errors
            logger.error("ECR error for %s: %s", repo_name, e)
            return None

        images = resp.get("imageDetails", [])
        if not images:
            logger.warning("No image details for 'latest' in %s", repo_name)
            return None

        image = images[0]
        tags = image.get("imageTags", [])

        for tag in tags:
            if SEMVER_RE.match(tag):
                return tag

        logger.warning(
            "'latest' image in %s has no semver tag (tags: %s)",
            repo_name,
            tags,
        )
        return None

    # --- Update logic ---

    def update_entries(
        self,
        entries: List[Dict[str, Any]],
        repo_versions: Dict[str, str],
    ) -> int:
        """
        Update tag fields for entries matching resolved repos.

        Args:
            entries: List of locked version entry dicts (mutated in place).
            repo_versions: Mapping of ECR repo name → resolved semver tag.

        Returns:
            The number of entries updated.
        """
        updated = 0
        for entry in entries:
            ecr = entry.get("ecr", "")
            if ecr in repo_versions:
                entry["tag"] = repo_versions[ecr]
                updated += 1
        return updated

    # --- Seed mode ---

    def scan_config_directory(self, config_dir: str) -> List[Dict[str, Any]]:
        """
        Recursively scan for Docker Lambda configs, return seed entries.

        Walks the config directory tree looking for JSON files that define
        Docker Lambdas. A file qualifies if it contains:
        - ``"docker": {"image": true}`` (at top level or within a resource)
        - A valid (non-empty) ``ecr.name`` field

        Handles two JSON structures:
        1. Individual resource files with top-level ``name``, ``docker``, and ``ecr`` fields.
        2. Stack-level files with a ``resources`` array containing resource objects.

        Args:
            config_dir: Root directory to scan recursively.

        Returns:
            List of seed entry dicts with ``name``, ``tag`` (empty string), and ``ecr`` keys.
        """
        entries: List[Dict[str, Any]] = []

        for dirpath, _dirnames, filenames in os.walk(config_dir):
            for filename in filenames:
                if not filename.endswith(".json"):
                    continue

                filepath = os.path.join(dirpath, filename)
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Skipping %s: %s", filepath, e)
                    continue

                if not isinstance(data, dict):
                    continue

                # Check for a resources array (stack-level file)
                resources = data.get("resources")
                if isinstance(resources, list):
                    for resource in resources:
                        if isinstance(resource, dict):
                            entry = self._extract_docker_entry(resource)
                            if entry:
                                entries.append(entry)
                else:
                    # Individual resource file — check top-level fields
                    entry = self._extract_docker_entry(data)
                    if entry:
                        entries.append(entry)

        return entries

    def merge_entries(
        self,
        existing: List[Dict[str, Any]],
        discovered: List[Dict[str, Any]],
    ) -> tuple:
        """
        Merge discovered entries into the existing list.

        - Preserves existing entries that have a non-empty ``tag`` value
          (never overwrites a pinned version).
        - Adds new entries (by ``name``) that don't exist in the current list.

        Args:
            existing: Current locked version entries.
            discovered: Newly discovered entries from config scanning.

        Returns:
            A tuple of ``(merged_list, new_count, preserved_count)``.
        """
        existing_by_name: Dict[str, Dict[str, Any]] = {e["name"]: e for e in existing}

        new_count = 0
        preserved_count = 0

        for entry in discovered:
            name = entry["name"]
            if name in existing_by_name:
                # Entry already exists — preserve if it has a non-empty tag
                if existing_by_name[name].get("tag", ""):
                    preserved_count += 1
            else:
                # New entry — add it
                existing_by_name[name] = entry
                new_count += 1

        merged = list(existing_by_name.values())

        logger.info(
            "Merge complete: %d new entries added, %d existing entries preserved",
            new_count,
            preserved_count,
        )

        return (merged, new_count, preserved_count)

    @staticmethod
    def _extract_docker_entry(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract a seed entry from a resource dict if it's a Docker Lambda.

        Returns:
            A ``{"name": ..., "tag": "", "ecr": ...}`` dict, or ``None``.
        """
        docker = data.get("docker")
        if not isinstance(docker, dict) or docker.get("image") is not True:
            return None

        ecr = data.get("ecr")
        if not isinstance(ecr, dict):
            return None

        ecr_name = ecr.get("name")
        if not ecr_name or not isinstance(ecr_name, str):
            return None

        name = data.get("name")
        if not name or not isinstance(name, str):
            return None

        return {"name": name, "tag": "", "ecr": ecr_name}

    # --- List / discovery ---

    def list_mappings(self, entries: List[Dict[str, Any]]) -> None:
        """
        Print a summary of ECR repo → Lambda mappings grouped by repository.

        Args:
            entries: List of locked version entry dicts.
        """
        # Group lambdas by ECR repo
        repo_map: Dict[str, List[str]] = {}
        for entry in entries:
            ecr = entry.get("ecr", "")
            name = entry.get("name", "")
            if ecr and name:
                repo_map.setdefault(ecr, []).append(name)

        total_repos = len(repo_map)
        total_lambdas = sum(len(names) for names in repo_map.values())

        print(
            f"\n📦 ECR Repository Mapping ({total_repos} repos, {total_lambdas} lambdas):\n"
        )

        for repo in sorted(repo_map.keys()):
            names = sorted(repo_map[repo])
            tag = ""
            # Find the tag for this repo (all entries for same repo share the tag)
            for entry in entries:
                if entry.get("ecr") == repo and entry.get("tag"):
                    tag = entry["tag"]
                    break
            tag_display = f" @ {tag}" if tag else ""
            print(f"  {repo}{tag_display} ({len(names)} lambdas)")
            # Show lambda names, wrapping at ~80 chars
            line = "    "
            for i, name in enumerate(names):
                suffix = ", " if i < len(names) - 1 else ""
                if len(line) + len(name) + len(suffix) > 80:
                    print(line.rstrip(", "))
                    line = "    "
                line += name + suffix
            if line.strip():
                print(line.rstrip(", "))
            print()

    # --- Apply to deployment ---

    def apply_to_deployment(
        self, deployment_path: str, entries: List[Dict[str, Any]]
    ) -> int:
        """
        Create a deployment-specific locked versions file.

        Copies the resolved locked versions to a file named after the
        deployment (e.g., ``locked-versions-demo.json``) in the same
        directory as the source locked versions file. This file is
        checked into git so the pipeline synth can find it.

        Args:
            deployment_path: Deployment name or path (used to derive the filename).
            entries: Locked version entries to write.

        Returns:
            0 on success, 1 on error.
        """
        # Derive the deployment name from the path
        name = deployment_path
        if "/" in name or "\\" in name:
            name = os.path.basename(name)
        name = name.replace("deployment.", "").replace(".json", "")

        # Write to the same directory as the locked versions file
        base_dir = os.path.dirname(self.locked_versions_path)
        target_path = os.path.join(base_dir, f"locked-versions-{name}.json")

        # Filter to only entries with tags
        pinned = [e for e in entries if e.get("name") and e.get("tag")]

        try:
            self.write_locked_versions(target_path, pinned)
        except OSError as e:
            print(f"Error writing {target_path}: {e}", file=sys.stderr)
            return 1

        print(f"🔒 Created {target_path} with {len(pinned)} pinned version(s)")
        print()
        print(f"   Set LOCKED_VERSIONS_PATH in your deployment config:")
        print(
            f'   "LOCKED_VERSIONS_PATH": "configs/pipelines/locked-versions-{name}.json"'
        )
        return 0

    # --- Main entry point ---

    def run(self) -> int:
        """
        Main entry point. Returns exit code (0 = success).

        Seed flow (when self.seed is True and self.config_dir is set):
        1. Scan config directory for Docker Lambdas
        2. If locked versions file exists, load and merge; otherwise create new entries
        3. Write merged/new entries to the locked versions file
        4. Proceed with normal ECR resolution on the resulting entries

        Normal (non-seed) flow:
        1. Load locked versions file
        2. Collect unique ECR repos
        3. Resolve each repo's latest → semver
        4. Update entries with resolved versions
        5. Write file (or dry-run print)
        """
        # --- Seed mode ---
        if self.seed and self.config_dir:
            discovered = self.scan_config_directory(self.config_dir)
            print(
                f"Seed: discovered {len(discovered)} Docker Lambda(s) in {self.config_dir}"
            )

            if os.path.isfile(self.locked_versions_path):
                try:
                    existing = self.load_locked_versions(self.locked_versions_path)
                except ValueError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    return 1

                entries, new_count, preserved_count = self.merge_entries(
                    existing, discovered
                )
                print(
                    f"Seed merge: {new_count} new entries added, "
                    f"{preserved_count} existing entries preserved"
                )
            else:
                entries = discovered
                print(
                    f"Seed: creating new locked versions file with {len(entries)} entries"
                )

            try:
                self.write_locked_versions(self.locked_versions_path, entries)
                print(f"Seed: written to {self.locked_versions_path}")
            except OSError as e:
                print(f"Error writing file: {e}", file=sys.stderr)
                return 1

        # --- Load locked versions (normal path or post-seed) ---
        try:
            entries = self.load_locked_versions(self.locked_versions_path)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        # Collect unique ECR repos
        ecr_repos: set[str] = set()
        for entry in entries:
            ecr = entry.get("ecr", "")
            if ecr:
                ecr_repos.add(ecr)

        if not ecr_repos:
            print("No ECR repositories found in locked versions file.")
            return 0

        # Create ECR client (with credential validation)
        try:
            session = boto3.Session(profile_name=self.profile, region_name=self.region)
            ecr_client = session.client("ecr")
            # Validate credentials by making a lightweight call
            ecr_client.describe_registry()
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in (
                "ExpiredTokenException",
                "UnrecognizedClientException",
            ):
                print(
                    f"\n❌ AWS credentials expired or invalid for profile '{self.profile}'.",
                    file=sys.stderr,
                )
                print(
                    f"   Run: aws sso login --profile {self.profile}",
                    file=sys.stderr,
                )
                return 2
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "token" in error_msg and (
                "expired" in error_msg or "refresh failed" in error_msg
            ):
                print(
                    f"\n❌ SSO token expired for profile '{self.profile}'.",
                    file=sys.stderr,
                )
                print(
                    f"   Run: aws sso login --profile {self.profile}",
                    file=sys.stderr,
                )
                return 2
            if (
                "could not find profile" in error_msg
                or "NoCredentialProviders" in error_msg
            ):
                print(
                    f"\n❌ AWS profile '{self.profile}' not found or has no credentials.",
                    file=sys.stderr,
                )
                print(
                    f"   Check your ~/.aws/config and run: aws sso login --profile {self.profile}",
                    file=sys.stderr,
                )
                return 2
            print(f"\n❌ Failed to create AWS session: {e}", file=sys.stderr)
            return 2

        # Resolve latest version for each unique repo
        print(f"Resolving versions for {len(ecr_repos)} ECR repositories...\n")
        repo_versions: Dict[str, str] = {}
        failed_repos: List[str] = []

        for repo in sorted(ecr_repos):
            print(f"  {repo}...", end=" ", flush=True)
            version = self.resolve_latest_version(ecr_client, repo)
            if version:
                repo_versions[repo] = version
                print(f"→ {version}")
            else:
                failed_repos.append(repo)
                print("→ SKIPPED")

        # Update entries
        updated = self.update_entries(entries, repo_versions)

        # Summary
        print(
            f"\n📋 Summary: {len(repo_versions)} repos resolved, "
            f"{updated} entries updated"
        )
        if failed_repos:
            print(f"⚠ {len(failed_repos)} repos failed: " f"{', '.join(failed_repos)}")

        # Write or dry-run
        if self.dry_run:
            print("\n[DRY RUN] Would write:")
            print(json.dumps(entries, indent=4))
        else:
            try:
                self.write_locked_versions(self.locked_versions_path, entries)
                print(f"Written to {self.locked_versions_path}")
            except OSError as e:
                print(f"Error writing file: {e}", file=sys.stderr)
                return 1

        # Exit non-zero if any repos failed
        return 1 if failed_repos else 0


def main(argv: Optional[List[str]] = None) -> None:
    """
    CLI entry point: parse args, create DockerVersionLocker, call run(),
    and sys.exit with the appropriate code.

    Args:
        argv: Optional argument list (defaults to sys.argv[1:])
    """
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Resolve ECR 'latest' tags to semver versions and update a locked versions file.",
    )
    parser.add_argument(
        "--locked-versions",
        required=True,
        help="Path to the locked versions JSON file.",
    )
    parser.add_argument(
        "--profile",
        required=True,
        help="AWS profile name for ECR access.",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region (default: us-east-1).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print resolved versions without writing the file.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        default=False,
        dest="list_mode",
        help="List ECR repo → Lambda mappings and exit. Uses locked versions file, or --config-dir if --seed is also set.",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        default=False,
        help="Enable seed mode to generate/merge entries from a config directory.",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help="Directory to scan for Lambda configs (required when --seed is set).",
    )
    parser.add_argument(
        "--apply",
        default=None,
        metavar="DEPLOYMENT_JSON",
        help="Apply locked versions to a deployment JSON file by writing a 'lambdas' array into it.",
    )

    args = parser.parse_args(argv)

    # Validate --config-dir is provided when --seed is set
    if args.seed and not args.config_dir:
        parser.error("--config-dir is required when --seed is set")

    # --- List mode: print mappings and exit ---
    if args.list_mode:
        locker = DockerVersionLocker(
            locked_versions_path=args.locked_versions,
            profile=args.profile,
            region=args.region,
        )
        # Prefer scanning config dir if provided, otherwise use locked versions file
        if args.config_dir:
            entries = locker.scan_config_directory(args.config_dir)
            print(f"Scanned: {args.config_dir}")
        else:
            try:
                entries = locker.load_locked_versions(args.locked_versions)
                print(f"Source: {args.locked_versions}")
            except (FileNotFoundError, ValueError) as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
        locker.list_mappings(entries)
        sys.exit(0)

    # --- Apply mode: write lambdas into deployment JSON ---
    if args.apply:
        locker = DockerVersionLocker(
            locked_versions_path=args.locked_versions,
            profile=args.profile,
            region=args.region,
        )
        try:
            entries = locker.load_locked_versions(args.locked_versions)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        exit_code = locker.apply_to_deployment(args.apply, entries)
        sys.exit(exit_code)

    locker = DockerVersionLocker(
        locked_versions_path=args.locked_versions,
        profile=args.profile,
        region=args.region,
        dry_run=args.dry_run,
        seed=args.seed,
        config_dir=args.config_dir,
    )

    exit_code = locker.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
