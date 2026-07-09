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

import copy
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

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

    # --- Pin file validation ---

    def validate_pin_entry(self, entry: Any, index: int) -> Optional[Dict[str, str]]:
        """
        Validate a single pin file entry.

        Args:
            entry: The raw entry from the JSON array.
            index: The 0-based index in the array (for error reporting).

        Returns:
            The validated entry dict if valid, or None if invalid.
            Logs a warning for invalid entries with index and field details.
        """
        if not isinstance(entry, dict):
            logger.warning("Pin entry at index %d is not a dict, skipping", index)
            return None

        ecr = entry.get("ecr")
        if not isinstance(ecr, str) or not ecr:
            logger.warning(
                "Pin entry at index %d has invalid 'ecr' field, skipping", index
            )
            return None

        tag = entry.get("tag")
        if not isinstance(tag, str) or not tag:
            logger.warning(
                "Pin entry at index %d has invalid 'tag' field, skipping", index
            )
            return None

        return {"ecr": ecr, "tag": tag}

    def load_pin_file(self) -> List[Dict[str, str]]:
        """
        Load and validate the pin file from the same directory as the locked versions file.

        Returns:
            List of validated pin entries (each with 'ecr' and 'tag' keys).
            Returns empty list if file doesn't exist, contains invalid JSON,
            or has no valid entries.
        """
        pin_file_path = os.path.join(
            os.path.dirname(self.locked_versions_path),
            ".docker-pinned-versions.json",
        )

        if not os.path.isfile(pin_file_path):
            return []

        try:
            with open(pin_file_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning("Pin file %s contains invalid JSON: %s", pin_file_path, e)
            return []

        if not isinstance(data, list):
            logger.warning("Pin file %s is not a JSON array, skipping", pin_file_path)
            return []

        # Validate each entry and collect valid ones
        valid_entries: List[Dict[str, str]] = []
        seen_ecr: set = set()

        for index, entry in enumerate(data):
            validated = self.validate_pin_entry(entry, index)
            if validated is None:
                continue
            # Deduplicate by ecr field — first match wins
            if validated["ecr"] in seen_ecr:
                continue
            seen_ecr.add(validated["ecr"])
            valid_entries.append(validated)

        if valid_entries:
            pinned_count = sum(1 for e in valid_entries if e["tag"].lower() != "auto")
            auto_count = len(valid_entries) - pinned_count
            parts = []
            if pinned_count:
                parts.append(f"{pinned_count} pinned")
            if auto_count:
                parts.append(f"{auto_count} auto (resolve from ECR)")
            print(
                f"📌 Loaded {len(valid_entries)} pin entries ({', '.join(parts)}) from {pin_file_path}"
            )

        return valid_entries

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

        # --- Load pin file ---
        pin_entries = self.load_pin_file()
        # "auto" means resolve from ECR (not pinned)
        pinned_repos: Dict[str, str] = {
            p["ecr"]: p["tag"] for p in pin_entries if p["tag"].lower() != "auto"
        }
        auto_repos: set[str] = {
            p["ecr"] for p in pin_entries if p["tag"].lower() == "auto"
        }

        # Collect unique ECR repos
        ecr_repos: set[str] = set()
        for entry in entries:
            ecr = entry.get("ecr", "")
            if ecr:
                ecr_repos.add(ecr)

        if not ecr_repos:
            print("No ECR repositories found in locked versions file.")
            return 0

        # Partition repos into pinned vs unresolved (auto entries resolve from ECR)
        pinned_set = ecr_repos & set(pinned_repos.keys())
        unresolved_set = ecr_repos - pinned_set

        # Resolve versions
        repo_versions: Dict[str, str] = {}
        failed_repos: List[str] = []

        # Add pinned repos to repo_versions
        for repo in sorted(pinned_set):
            repo_versions[repo] = pinned_repos[repo]
            print(f"  {repo}... → {pinned_repos[repo]} 📌 PINNED")

        # Only create ECR client and resolve if there are non-pinned repos
        if unresolved_set:
            # Create ECR client (with credential validation)
            try:
                session = boto3.Session(
                    profile_name=self.profile, region_name=self.region
                )
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

            # Resolve latest version for each non-pinned repo
            print(f"Resolving versions for {len(unresolved_set)} ECR repositories...\n")

            for repo in sorted(unresolved_set):
                print(f"  {repo}...", end=" ", flush=True)
                version = self.resolve_latest_version(ecr_client, repo)
                if version:
                    repo_versions[repo] = version
                    print(f"→ {version}")
                else:
                    failed_repos.append(repo)
                    print("→ SKIPPED")

        # Update entries with merged repo_versions (pinned + ECR-resolved)
        updated = self.update_entries(entries, repo_versions)

        # Summary
        resolved_count = len(repo_versions) - len(pinned_set)
        print(
            f"\n📋 Summary: {resolved_count} repos resolved, "
            f"{len(pinned_set)} pinned, "
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


class PinnedVersionUpdater:
    """Updates the .docker-pinned-versions.json file with latest ECR tags.

    Reads the pinned versions file, discovers new ECR repositories under a
    configurable prefix, resolves the latest semver tag for each non-auto entry,
    preserves auto entries unchanged, appends newly discovered repositories,
    and writes the updated file back (or prints a dry-run report).

    Uses composition over inheritance — delegates to DockerVersionLocker
    static-compatible methods where possible and reuses the module-level
    SEMVER_RE pattern.
    """

    def __init__(
        self,
        pinned_versions_path: str,
        profile: str,
        region: str = "us-east-1",
        dry_run: bool = False,
        repo_prefix: str = "aplos-analytics/v3/",
    ) -> None:
        self.pinned_versions_path = pinned_versions_path
        self.profile = profile
        self.region = region
        self.dry_run = dry_run
        self.repo_prefix = repo_prefix

    def load_pinned_versions(self) -> List[Dict[str, Any]]:
        """Load and validate the pinned versions JSON file.

        Reads the JSON file at self.pinned_versions_path, validates that it
        contains a JSON array, and filters entries to only those with a
        non-empty string 'ecr' field.

        Returns:
            List of valid pinned version entry dicts (each has at least
            a non-empty string 'ecr' field).

        Raises:
            SystemExit: If the file is missing, contains invalid JSON,
                or is not a JSON array.
        """
        # Check file exists
        if not os.path.isfile(self.pinned_versions_path):
            print(
                f"Error: Pinned versions file not found: {self.pinned_versions_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Read and parse JSON
        try:
            with open(self.pinned_versions_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(
                f"Error: Invalid JSON in pinned versions file "
                f"{self.pinned_versions_path}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Validate structure is a list
        if not isinstance(data, list):
            print(
                f"Error: Pinned versions file must contain a JSON array: "
                f"{self.pinned_versions_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Filter to valid entries (dicts with non-empty string 'ecr' field)
        valid_entries: List[Dict[str, Any]] = []
        for index, entry in enumerate(data):
            if not isinstance(entry, dict):
                logger.warning(
                    "Pinned entry at index %d is not an object, skipping", index
                )
                continue

            ecr = entry.get("ecr")
            if not isinstance(ecr, str) or not ecr.strip():
                logger.warning(
                    "Pinned entry at index %d has no valid 'ecr' field, skipping",
                    index,
                )
                continue

            valid_entries.append(entry)

        return valid_entries

    def discover_repositories(self, ecr_client: Any) -> List[str]:
        """List all ECR repos matching the prefix via paginated describe_repositories.

        Args:
            ecr_client: A boto3 ECR client.

        Returns:
            Sorted list of repository names matching self.repo_prefix.

        Raises:
            SystemExit: If the ECR API call fails completely.
        """
        discovered: List[str] = []
        try:
            paginator = ecr_client.get_paginator("describe_repositories")
            for page in paginator.paginate():
                for repo in page["repositories"]:
                    if repo["repositoryName"].startswith(self.repo_prefix):
                        discovered.append(repo["repositoryName"])
        except ClientError as e:
            print(
                f"Error: Failed to list ECR repositories: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        return sorted(discovered)

    def resolve_latest_by_timestamp(
        self, ecr_client: Any, repo_name: str
    ) -> Optional[str]:
        """Fallback resolution: find the most recent semver tag by imagePushedAt.

        Queries all images in the repository, filters tags matching the strict
        MAJOR.MINOR.PATCH semver pattern, sorts by imagePushedAt descending,
        and returns the first matching tag.

        This handles repositories where no 'latest' tag has been configured,
        falling back to a timestamp-based selection strategy as specified in
        Requirement 2.2.

        Args:
            ecr_client: A boto3 ECR client.
            repo_name: The ECR repository name.

        Returns:
            The most recent semver tag string, or None if no semver tags exist.
        """
        try:
            paginator = ecr_client.get_paginator("describe_images")
            image_details: List[Dict[str, Any]] = []

            for page in paginator.paginate(repositoryName=repo_name):
                for image in page.get("imageDetails", []):
                    image_details.append(image)

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "RepositoryNotFoundException":
                logger.warning("Repository not found: %s", repo_name)
                return None
            logger.error("ECR error for %s: %s", repo_name, e)
            return None

        # Filter to images that have at least one semver tag, collect (tag, pushedAt) pairs
        semver_images: List[tuple] = []
        for image in image_details:
            pushed_at = image.get("imagePushedAt")
            if not pushed_at:
                continue
            for tag in image.get("imageTags", []):
                if SEMVER_RE.match(tag):
                    semver_images.append((tag, pushed_at))

        if not semver_images:
            logger.warning(
                "No semver tags found in %s (checked %d images)",
                repo_name,
                len(image_details),
            )
            return None

        # Sort by imagePushedAt descending, return the most recent
        semver_images.sort(key=lambda x: x[1], reverse=True)
        return semver_images[0][0]

    def write_pinned_versions(
        self,
        path: str,
        entries: List[Dict[str, Any]],
    ) -> None:
        """Write entries as JSON with 4-space indent and trailing newline.

        Args:
            path: Path to write the pinned versions file.
            entries: List of pinned version entry dicts to write.

        Raises:
            SystemExit: If writing to the file fails due to a filesystem error.
        """
        try:
            with open(path, "w") as f:
                json.dump(entries, f, indent=4)
                f.write("\n")
        except OSError as e:
            print(
                f"Error: Failed to write pinned versions file {path}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    def resolve_entry_tags(
        self,
        ecr_client: Any,
        entries: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Resolve latest tags for non-auto entries.

        For each entry where tag != "auto", attempts to resolve the latest
        semver tag from ECR. Auto entries pass through unchanged.

        Resolution strategy:
        1. Try DockerVersionLocker.resolve_latest_version (finds semver tag
           sharing digest with 'latest' tag)
        2. If that returns None, fall back to resolve_latest_by_timestamp
           (most recent semver tag by imagePushedAt)

        Args:
            ecr_client: A boto3 ECR client.
            entries: List of pinned version entry dicts.

        Returns:
            Tuple of (updated_entries, failed_repos):
            - updated_entries: The full list with resolved tags applied
            - failed_repos: List of repo names that couldn't be resolved
        """
        failed_repos: List[str] = []

        # Create a DockerVersionLocker instance to call resolve_latest_version
        locker = DockerVersionLocker(
            locked_versions_path="",
            profile=self.profile,
            region=self.region,
        )

        # Identify non-auto entries for resolution
        pinned_indices = [
            i for i, entry in enumerate(entries) if entry.get("tag") != "auto"
        ]

        total = len(pinned_indices)
        for position, idx in enumerate(pinned_indices, start=1):
            entry = entries[idx]
            repo_name = entry.get("ecr", "")

            print(f"  {repo_name} ({position} of {total})...", end=" ")

            # Try primary resolution: resolve_latest_version (via 'latest' tag digest)
            resolved_tag = locker.resolve_latest_version(ecr_client, repo_name)

            # Fallback: resolve by most recent imagePushedAt timestamp
            if resolved_tag is None:
                resolved_tag = self.resolve_latest_by_timestamp(ecr_client, repo_name)

            if resolved_tag is not None:
                entries[idx]["tag"] = resolved_tag
                print(f"\u2192 {resolved_tag}")
            else:
                # Retain existing tag on failure
                failed_repos.append(repo_name)
                logger.warning(
                    "Failed to resolve tag for %s, retaining existing tag '%s'",
                    repo_name,
                    entry.get("tag", ""),
                )
                print("\u2192 SKIPPED")

        return entries, failed_repos

    def find_new_repositories(
        self,
        discovered: List[str],
        existing_ecrs: Set[str],
    ) -> List[str]:
        """Return repos in discovered that are not in existing_ecrs.

        Computes the set difference between all discovered ECR repositories
        and those already present in the pinned versions file, returning a
        sorted list of newly found repository names.

        Args:
            discovered: All ECR repos found via describe_repositories.
            existing_ecrs: Set of ECR names already in the pinned file.

        Returns:
            Sorted list of new repository names (set difference).
        """
        return sorted([r for r in discovered if r not in existing_ecrs])

    def resolve_new_entries(
        self,
        ecr_client: Any,
        new_repos: List[str],
    ) -> List[Dict[str, Any]]:
        """Create new entries for discovered repos with resolved tags.

        For each new repo:
        - Try resolve_latest_version first, then resolve_latest_by_timestamp
          fallback
        - If no semver tag found, set tag to "auto" and log warning
        - Print progress for each new repo

        Args:
            ecr_client: A boto3 ECR client.
            new_repos: List of newly discovered repository names.

        Returns:
            List of new entry dicts (each with 'ecr' and 'tag' fields).
        """
        new_entries: List[Dict[str, Any]] = []

        # Create a DockerVersionLocker instance to call resolve_latest_version
        locker = DockerVersionLocker(
            locked_versions_path="",
            profile=self.profile,
            region=self.region,
        )

        for repo_name in new_repos:
            print(f"  [NEW] {repo_name}...", end=" ")

            # Try primary resolution: resolve_latest_version (via 'latest' tag digest)
            resolved_tag = locker.resolve_latest_version(ecr_client, repo_name)

            # Fallback: resolve by most recent imagePushedAt timestamp
            if resolved_tag is None:
                resolved_tag = self.resolve_latest_by_timestamp(ecr_client, repo_name)

            if resolved_tag is not None:
                new_entries.append({"ecr": repo_name, "tag": resolved_tag})
                print(f"→ {resolved_tag}")
            else:
                new_entries.append({"ecr": repo_name, "tag": "auto"})
                logger.warning(
                    "No semver tag found for new repository %s, setting tag to 'auto'",
                    repo_name,
                )
                print("→ auto (no semver tag)")

        return new_entries

    def print_summary(
        self,
        total: int,
        updated: int,
        skipped: int,
        failed: int,
        new_count: int,
    ) -> None:
        """Print final summary counts.

        Displays a one-line summary of the update run, plus additional lines
        for failures and newly discovered repositories when applicable.

        Args:
            total: Total number of existing entries processed.
            updated: Number of entries whose tag changed.
            skipped: Number of entries skipped (auto + unchanged).
            failed: Number of entries that failed ECR resolution.
            new_count: Number of newly discovered repositories appended.
        """
        print(
            f"\U0001f4cb Summary: {total} entries processed, "
            f"{updated} updated, {skipped} skipped, "
            f"{failed} failed, {new_count} new repositories discovered"
        )

        if failed > 0:
            print(f"\u26a0 {failed} repo(s) failed resolution (existing tags retained)")

        if new_count > 0:
            print(f"\U0001f195 {new_count} new repositories discovered and added")

    def print_dry_run_report(
        self,
        original: List[Dict[str, Any]],
        updated: List[Dict[str, Any]],
        new_entries: List[Dict[str, Any]],
    ) -> None:
        """Print a tabular diff showing changes, unchanged, auto, and new repos.

        Compares original[i]["tag"] vs updated[i]["tag"] for each index and
        groups entries into: changed (old → new), unchanged (same tag),
        auto (tag == "auto"). New entries are displayed in a separate section.

        If no changes at all (no updates, no new entries), prints a simple
        "No changes detected" message.

        Args:
            original: The original entries as loaded from file.
            updated: The entries after tag resolution (same length as original).
            new_entries: Newly discovered repositories to be appended.
        """
        changed: List[tuple] = []
        unchanged: List[tuple] = []
        auto: List[tuple] = []

        for i in range(len(original)):
            ecr_name = original[i].get("ecr", "")
            old_tag = original[i].get("tag", "")
            new_tag = updated[i].get("tag", "")

            if old_tag == "auto":
                auto.append((ecr_name, old_tag))
            elif old_tag != new_tag:
                changed.append((ecr_name, old_tag, new_tag))
            else:
                unchanged.append((ecr_name, old_tag))

        # If nothing changed at all, print short message
        if not changed and not new_entries:
            print("\n[DRY RUN] No changes detected.")
            return

        print("\n[DRY RUN] Changes that would be made:\n")

        if changed:
            print("Updated:")
            for ecr_name, old_tag, new_tag in changed:
                print(f"  {ecr_name}: {old_tag} → {new_tag}")
            print()

        if unchanged:
            print("Unchanged:")
            for ecr_name, tag in unchanged:
                print(f"  {ecr_name}: {tag}")
            print()

        if auto:
            print("Auto (skipped):")
            for ecr_name, tag in auto:
                print(f"  {ecr_name}: {tag}")
            print()

        if new_entries:
            print("New repositories:")
            for entry in new_entries:
                ecr_name = entry.get("ecr", "")
                tag = entry.get("tag", "")
                print(f"  {ecr_name}: {tag}")
            print()

    def run(self) -> int:
        """Main entry point. Returns exit code (0=success, non-zero=error).

        Orchestrates the full update-pinned flow:
        1. Load and validate the pinned versions file
        2. Create boto3 session and ECR client with credential validation
        3. Discover ECR repositories matching the prefix
        4. Keep a deep copy of original entries for comparison
        5. Resolve latest tags for pinned entries
        6. Find and resolve newly discovered repositories
        7. Write updated file (or print dry-run report)
        8. Print summary

        Returns:
            0 on success, 1 on critical failure, 2 on credential errors.
        """
        from botocore.config import Config

        # 1. Load pinned versions file
        entries = self.load_pinned_versions()

        # 2. Create boto3 session and ECR client (with credential validation)
        ecr_config = Config(
            read_timeout=30, connect_timeout=10, retries={"max_attempts": 2}
        )

        try:
            session = boto3.Session(profile_name=self.profile, region_name=self.region)
            ecr_client = session.client("ecr", config=ecr_config)
            ecr_client.describe_registry()  # validate credentials
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("ExpiredTokenException", "UnrecognizedClientException"):
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
            print(f"\n❌ Failed to create AWS session: {e}", file=sys.stderr)
            return 2

        # 3. Discover all ECR repos matching the prefix
        print(f"\nDiscovering ECR repositories with prefix '{self.repo_prefix}'...")
        discovered = self.discover_repositories(ecr_client)
        print(f"Found {len(discovered)} repositories.\n")

        # 4. Keep a deep copy of original entries for comparison
        original_entries = copy.deepcopy(entries)

        # 5. Resolve entry tags for non-auto entries
        print("Resolving tags for existing entries...")
        entries, failed_repos = self.resolve_entry_tags(ecr_client, entries)

        # 6. Find new repos (set difference)
        existing_ecrs: Set[str] = {e.get("ecr", "") for e in entries if e.get("ecr")}
        new_repos = self.find_new_repositories(discovered, existing_ecrs)

        # 7. Resolve new entries (if any new repos discovered)
        new_entries: List[Dict[str, Any]] = []
        if new_repos:
            print(f"\nResolving tags for {len(new_repos)} new repositories...")
            new_entries = self.resolve_new_entries(ecr_client, new_repos)

        # 8. Calculate counts
        updated_count = 0
        skipped_count = 0
        for i, entry in enumerate(entries):
            if entry.get("tag") == "auto":
                skipped_count += 1
            elif i < len(original_entries) and entry.get("tag") == original_entries[
                i
            ].get("tag"):
                skipped_count += 1
            else:
                updated_count += 1

        failed_count = len(failed_repos)
        total = len(entries)
        new_count = len(new_entries)

        # 9. Dry-run or write
        if self.dry_run:
            self.print_dry_run_report(original_entries, entries, new_entries)
        else:
            combined = entries + new_entries
            self.write_pinned_versions(self.pinned_versions_path, combined)
            print(f"\n✅ Written to {self.pinned_versions_path}")

        # 10. Print summary
        print()
        self.print_summary(total, updated_count, skipped_count, failed_count, new_count)

        # 11. Return exit code
        return 0


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
        default=None,
        help="Path to the locked versions JSON file.",
    )
    parser.add_argument(
        "--profile",
        required=True,
        help="AWS profile name for ECR access.",
    )
    parser.add_argument(
        "--update-pinned",
        action="store_true",
        default=False,
        help="Update the .docker-pinned-versions.json file with latest ECR tags.",
    )
    parser.add_argument(
        "--pinned-versions",
        default=None,
        help="Path to the pinned versions JSON file (required with --update-pinned).",
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

    # Validate --locked-versions is required when NOT using --update-pinned
    if not args.update_pinned and not args.locked_versions:
        parser.error("--locked-versions is required when not using --update-pinned")

    # Validate --config-dir is provided when --seed is set
    if args.seed and not args.config_dir:
        parser.error("--config-dir is required when --seed is set")

    # --- Update pinned mode: resolve latest ECR tags into pinned versions file ---
    if args.update_pinned:
        if not args.pinned_versions:
            parser.error("--pinned-versions is required when using --update-pinned")
        updater = PinnedVersionUpdater(
            pinned_versions_path=args.pinned_versions,
            profile=args.profile,
            region=args.region,
            dry_run=args.dry_run,
        )
        exit_code = updater.run()
        sys.exit(exit_code)

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
