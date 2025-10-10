import os
import subprocess
import sys
import site
import platform
import configparser
from pathlib import Path
from shutil import which
from typing import List
import json
import threading
import time
import re

VENV = ".venv"

# ANSI escape codes for colored output
RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"


def print_success(msg):
    print(f"{GREEN}✅ {msg}{RESET}")


def print_error(msg):
    print(f"{RED}❌ {msg}{RESET}")


def print_info(msg):
    print(f"👉 {msg}")


def print_header(msg):
    print(f"\n🔎 {msg}\n{'=' * 30}")


def _remove_directory(path, retries=3, retry_delay=0.5):
    """Safely remove a directory with retries and fallbacks.
    
    Args:
        path: Path to the directory to remove
        retries: Number of times to retry if initial removal fails
        retry_delay: Delay in seconds between retries
        
    Returns:
        bool: True if directory was removed successfully, False otherwise
    """
    import shutil
    import time
    import os
    import stat
    import platform
    
    path = Path(path)
    if not path.exists():
        return True
    
    # First attempt: standard rmtree
    try:
        shutil.rmtree(path)
        return True
    except Exception as e:
        print_info(f"Standard directory removal failed: {e}")
    
    # Second attempt: Set write permissions and retry
    def handle_readonly(func, path, exc_info):
        # Make the file/dir writable and try again
        os.chmod(path, stat.S_IWRITE)
        func(path)
    
    for i in range(retries):
        try:
            print_info(f"Retrying with permission fix (attempt {i+1}/{retries})...")
            shutil.rmtree(path, onerror=handle_readonly)
            return True
        except Exception as e:
            print_info(f"Retry {i+1} failed: {e}")
            time.sleep(retry_delay)
    
    # Final attempt: Use platform-specific commands
    try:
        print_info("Attempting platform-specific directory removal...")
        if platform.system() == "Windows":
            os.system(f'rd /s /q "{path}"')
        else:  # Unix-like systems (macOS, Linux)
            os.system(f'rm -rf "{path}"')
        
        # Check if directory was actually removed
        if not path.exists():
            return True
    except Exception as e:
        print_info(f"Platform-specific removal failed: {e}")
    
    print_error(f"Failed to remove directory: {path}")
    print_info("Continuing anyway. You may need to manually remove the directory later.")
    return False


class ProjectSetup:
    CA_CONFIG = Path(".pysetup.json")
    
    # Authentication error patterns to detect in pip output
    AUTH_ERROR_PATTERNS = [
        "401 client error: unauthorized",
        "403 client error: forbidden",
        "authentication failed",
        "401 unauthorized",
        "403 forbidden",
        "invalid credentials",
        "unable to authenticate",
        "bad credentials",
        "the repository requires authentication",
        "warning: 401 error, credentials not correct for",
        "artifactory returned http 401",
        "nexus returned http 401",
        "the feed requires authentication",
        "authentication required"
    ]
    
    # Package not found error patterns
    PACKAGE_NOT_FOUND_PATTERNS = [
        "no matching distribution found for",
        "could not find a version that satisfies the requirement",
        "no such package",
        "package not found"
    ]

    def __init__(self):
        self._use_poetry: bool = False
        self._package_name: str = ""
        self.__exit_notes: List[str] = []

        # Default settings with Python paths and repositories
        self.ca_settings = {
            "python_paths": [
                str(Path.cwd() / VENV / "bin" / "python"),
                str(Path.cwd() / VENV / "bin" / "python3"),
            ],
            "setup_prompted": {
                "gitignore": False  # Track if user has been prompted about gitignore
            },
            "repositories": {
                "pypi": {
                    "type": "pypi",
                    "enabled": True,
                    "url": "https://pypi.org/simple",
                    "trusted": True
                }
            }
        }
        
        if self.CA_CONFIG.exists():
            try:
                self.ca_settings = json.loads(self.CA_CONFIG.read_text())
                # Ensure repositories structure exists
                if "repositories" not in self.ca_settings:
                    self.ca_settings["repositories"] = {
                        "pypi": {
                            "type": "pypi",
                            "enabled": True,
                            "url": "https://pypi.org/simple",
                            "trusted": True
                        }
                    }
                print_info(f"🔒 Loaded settings from {self.CA_CONFIG}")
            except json.JSONDecodeError:
                print_error(f"Could not parse {self.CA_CONFIG}; ignoring it.")

    def _setup_repositories(self, force_prompt=False):
        """Configure package repositories based on user input.
        
        Args:
            force_prompt: If True, prompt for all repositories even if already configured.
                         If False, only prompt for repositories that aren't configured yet.
        """
        print_header("Package Repository Setup")
        print("Let's configure the package repositories you want to use.")
        print("PyPI is enabled by default. You can add additional repositories.")
        
        # Always ensure PyPI is in the repositories
        if "repositories" not in self.ca_settings:
            self.ca_settings["repositories"] = {}
            
        if "pypi" not in self.ca_settings["repositories"]:
            self.ca_settings["repositories"]["pypi"] = {
                "type": "pypi",
                "enabled": True,
                "url": "https://pypi.org/simple",
                "trusted": True
            }
            # Save the updated settings with PyPI
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
        
        # Ask about each repository type
        # Each method now saves its own configuration changes
        self._maybe_setup_codeartifact(force_prompt)
        self._maybe_setup_artifactory(force_prompt)
        self._maybe_setup_nexus(force_prompt)
        self._maybe_setup_github_packages(force_prompt)
        self._maybe_setup_azure_artifacts(force_prompt)
        self._maybe_setup_google_artifact_registry(force_prompt)
        
        # Update pip.conf with the repository configuration
        # This uses the latest configuration from all repository setups
        self._update_pip_conf_with_repos()
        print_success("Repository configuration complete.")

        
    def _update_pip_conf_with_repos(self):
        """Update pip.conf with the configured repositories."""
        pip_conf_path = Path(VENV) / "pip.conf"
        
        # Basic pip.conf template
        pip_conf = "[global]\n"
        
        # Add index URLs based on configured repositories
        primary_repo = None
        extra_repos = []
        trusted_hosts = set()
        
        for repo_id, repo in self.ca_settings.get("repositories", {}).items():
            if not repo.get("enabled", False):
                continue
                
            repo_url = repo.get("url")
            if not repo_url:
                continue
                
            # Extract hostname for trusted-host
            try:
                from urllib.parse import urlparse
                hostname = urlparse(repo_url).netloc
                if hostname and repo.get("trusted", False):
                    trusted_hosts.add(hostname)
            except Exception:
                pass
                
            # First enabled repo becomes the primary index
            if primary_repo is None:
                primary_repo = repo_url
            else:
                extra_repos.append(repo_url)
        
        # Add the repositories to pip.conf
        if primary_repo:
            pip_conf += f"index-url={primary_repo}\n"
            
        if extra_repos:
            pip_conf += f"extra-index-url={' '.join(extra_repos)}\n"
            
        if trusted_hosts:
            pip_conf += f"trusted-host = {' '.join(trusted_hosts)}\n"
            
        # Add break-system-packages
        pip_conf += "break-system-packages = true\n"
        
        # Write the pip.conf file
        with open(pip_conf_path, "w", encoding="utf-8") as file:
            file.write(pip_conf)
            
        print_success(f"Updated pip.conf with repository configuration")

    def _maybe_setup_codeartifact(self, force_prompt=False):
        """Configure AWS CodeArtifact repository.
        
        Args:
            force_prompt: If True, prompt for configuration even if already configured.
                         If False, use existing configuration without prompting.
        """
        # Check if CodeArtifact is already configured
        ca_repo = self.ca_settings.get("repositories", {}).get("codeartifact", {})
        
        if ca_repo and not force_prompt:
            # Use existing configuration without prompting
            print_info("Using existing AWS CodeArtifact configuration.")
            # Keep the enabled status as is
        elif ca_repo:
            print_info("AWS CodeArtifact configuration found.")
            reuse = input("Do you want to use AWS CodeArtifact? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                ca_repo["enabled"] = False
                self.ca_settings["repositories"]["codeartifact"] = ca_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("AWS CodeArtifact disabled and saved to configuration.")
                return False
            else:
                # Enable the repository
                ca_repo["enabled"] = True
                self.ca_settings["repositories"]["codeartifact"] = ca_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("AWS CodeArtifact enabled and saved to configuration.")
        else:
            # Ask if user wants to configure CodeArtifact
            ans = input("☁️ Configure AWS CodeArtifact? (y/N): ").strip().lower()
            if ans != "y":
                # Add a disabled entry to repositories
                if "repositories" not in self.ca_settings:
                    self.ca_settings["repositories"] = {}
                self.ca_settings["repositories"]["codeartifact"] = {
                    "type": "codeartifact",
                    "enabled": False
                }
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("AWS CodeArtifact disabled and saved to configuration.")
                return False
                
            # Initialize CodeArtifact repository settings
            ca_repo = {
                "type": "codeartifact",
                "enabled": True,
                "tool": input("   Tool (pip/poetry) [pip]: ").strip().lower() or "pip",
                "domain_owner": input("   Domain Owner (AWS Account ID): ").strip(),
                "domain": input("   Domain: ").strip(),                
                "repository": input("   Repository Name: ").strip(),
                "region": input("   AWS Region [us-east-1]: ").strip() or "us-east-1",
                "profile": input("   AWS Profile (optional): ").strip() or None,
                "trusted": True
            }
            
            # Add to repositories
            if "repositories" not in self.ca_settings:
                self.ca_settings["repositories"] = {}
            self.ca_settings["repositories"]["codeartifact"] = ca_repo
            # Save the updated settings
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
            print_info("AWS CodeArtifact configuration saved.")

        # If enabled, perform login
        if ca_repo.get("enabled", False):
            return self._login_to_codeartifact(ca_repo)
        return False
        
    def _login_to_codeartifact(self, ca_repo):
        """Login to AWS CodeArtifact with the provided settings."""
        # Check for AWS CLI
        if which("aws") is None:
            print_error("AWS CLI not found; cannot configure CodeArtifact.")
            return False

        # Build AWS CLI command
        cmd = [
            "aws",
            "codeartifact",
            "login",
            "--tool",
            "pip",
            "--domain",
            ca_repo["domain"],            
            "--repository",
            ca_repo["repository"],
            "--region",
            ca_repo["region"],
        ]
        if ca_repo.get("profile"):
            cmd += ["--profile", ca_repo["profile"]]

        print_info(f"→ aws codeartifact login {' '.join(cmd[3:])}")
        try:
            # Ensure our virtualenv's pip is picked up
            env = os.environ.copy()
            venv_bin = os.path.abspath(f"{VENV}/bin")
            if os.path.isdir(venv_bin):
                env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
            subprocess.run(cmd, check=True, env=env)

            # Get the repository URL from the login output
            result = subprocess.run(
                cmd + ["--dry-run"], 
                capture_output=True, 
                text=True,
                env=env
            )
            # Extract URL from output if possible
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "index-url" in line:
                        url = line.split("index-url", 1)[1].strip()
                        ca_repo["url"] = url
                        break

            print_success("CodeArtifact login succeeded.")
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"CodeArtifact login failed: {e}")
            return False

    def _output_has_auth_error(self, output: str) -> bool:
        """Return True if output contains any known auth error pattern."""
        output_lower = output.lower()
        for pattern in self.AUTH_ERROR_PATTERNS:
            if pattern in output_lower:
                return True
        return False
        
    def _output_has_package_not_found(self, output: str) -> bool:
        """Return True if output indicates a package not found error rather than auth error."""
        output_lower = output.lower()
        for pattern in self.PACKAGE_NOT_FOUND_PATTERNS:
            if pattern in output_lower:
                return True
        return False
        
    def _extract_package_name_from_error(self, output: str) -> str:
        """Extract package name from error output.
        
        Attempts to extract the package name from common error patterns like:
        - No matching distribution found for package-name==1.0.0
        - Could not find a version that satisfies the requirement package-name
        
        Returns the package name or empty string if not found.
        """
        output_lower = output.lower()
        
        # Try to match 'no matching distribution found for X' pattern
        if "no matching distribution found for" in output_lower:
            pattern = r"no matching distribution found for ([\w\d\._-]+)(?:==|>=|<=|~=|!=|<|>|\s|$)"
            match = re.search(pattern, output_lower)
            if match:
                return match.group(1)
        
        # Try to match 'could not find a version that satisfies the requirement X' pattern
        if "could not find a version that satisfies the requirement" in output_lower:
            pattern = r"could not find a version that satisfies the requirement ([\w\d\._-]+)(?:==|>=|<=|~=|!=|<|>|\s|$)"
            match = re.search(pattern, output_lower)
            if match:
                return match.group(1)
        
        return ""

    # Note: _run_with_ca_retry functionality has been merged into _run_pip_with_progress

    def _handle_repo_auth_error(self, output: str) -> bool:
        """Dispatch to the correct repository login/setup method based on output."""
        out = output.lower()
        # When handling auth errors, we always want to force prompting
        # since we need to re-authenticate
        force_prompt = True
        
        if ".codeartifact" in out or "codeartifact" in out:
            return self._maybe_setup_codeartifact(force_prompt)
        elif "artifactory" in out:
            return self._maybe_setup_artifactory(force_prompt)
        elif "nexus" in out:
            return self._maybe_setup_nexus(force_prompt)
        elif "github.com" in out or "ghcr.io" in out or "github packages" in out:
            return self._maybe_setup_github_packages(force_prompt)
        elif "azure" in out or "pkgs.dev.azure.com" in out:
            return self._maybe_setup_azure_artifacts(force_prompt)
        elif "pkg.dev" in out or "artifact registry" in out or "gcp" in out:
            return self._maybe_setup_google_artifact_registry(force_prompt)
        else:
            print_info("No known repository type detected in output; skipping custom login.")
            return False

    def _maybe_setup_artifactory(self, force_prompt=False) -> bool:
        """Configure JFrog Artifactory repository.
        
        Args:
            force_prompt: If True, prompt for configuration even if already configured.
                         If False, use existing configuration without prompting.
        """
        # Check if Artifactory is already configured
        art_repo = self.ca_settings.get("repositories", {}).get("artifactory", {})
        
        if art_repo and not force_prompt:
            # Use existing configuration without prompting
            print_info("Using existing Artifactory configuration.")
            # Keep the enabled status as is
        elif art_repo:
            # Configuration exists but we're forcing a prompt
            print_info("Artifactory configuration found.")
            reuse = input("Do you want to use Artifactory? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                art_repo["enabled"] = False
                self.ca_settings["repositories"]["artifactory"] = art_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Artifactory disabled and saved to configuration.")
                return False
            else:
                # Enable the repository
                art_repo["enabled"] = True
                self.ca_settings["repositories"]["artifactory"] = art_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Artifactory enabled and saved to configuration.")
        else:
            # No configuration exists, ask if user wants to configure Artifactory
            ans = input("📦 Configure JFrog Artifactory? (y/N): ").strip().lower()
            if ans != "y":
                # Add a disabled entry to repositories
                if "repositories" not in self.ca_settings:
                    self.ca_settings["repositories"] = {}
                self.ca_settings["repositories"]["artifactory"] = {
                    "type": "artifactory",
                    "enabled": False
                }
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Artifactory disabled and saved to configuration.")
                return False
                
            # Initialize Artifactory repository settings
            art_repo = {
                "type": "artifactory",
                "enabled": True,
                "url": input("   Repository URL (e.g. https://artifactory.example.com/api/pypi/pypi-local/simple): ").strip(),
                "username": input("   Username: ").strip(),
                "password": input("   Password/API Key: ").strip(),
                "trusted": input("   Trust this host? (Y/n): ").strip().lower() != "n"
            }
            
            # Add to repositories
            if "repositories" not in self.ca_settings:
                self.ca_settings["repositories"] = {}
            self.ca_settings["repositories"]["artifactory"] = art_repo
            # Save the updated settings
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
            print_info("Artifactory configuration saved.")

        # If enabled, perform login
        if art_repo.get("enabled", False):
            return self._login_to_artifactory(art_repo)
        return False
        
    def _login_to_artifactory(self, art_repo):
        """Login to Artifactory with the provided settings."""
        try:
            # Create or update pip.conf with credentials
            url = art_repo["url"]
            username = art_repo["username"]
            password = art_repo["password"]
            
            # Create .netrc file for authentication
            netrc_path = os.path.expanduser("~/.netrc")
            hostname = ""
            
            try:
                from urllib.parse import urlparse
                hostname = urlparse(url).netloc
            except Exception:
                hostname = url.split("/")[2] if url.startswith("http") else url
            
            if hostname:
                # Check if entry already exists
                existing_content = ""
                if os.path.exists(netrc_path):
                    with open(netrc_path, "r") as f:
                        existing_content = f.read()
                
                # Only add if not already present
                if hostname not in existing_content:
                    with open(netrc_path, "a") as f:
                        f.write(f"\nmachine {hostname}\n")
                        f.write(f"login {username}\n")
                        f.write(f"password {password}\n")
                    
                    # Set permissions
                    os.chmod(netrc_path, 0o600)
                    print_success(f"Added Artifactory credentials to ~/.netrc for {hostname}")
                else:
                    print_info(f"Credentials for {hostname} already exist in ~/.netrc")
            
            print_success("Artifactory login configured.")
            return True
        except Exception as e:
            print_error(f"Artifactory login failed: {e}")
            return False

    def _maybe_setup_nexus(self, force_prompt=False) -> bool:
        """Configure Sonatype Nexus repository.
        
        Args:
            force_prompt: If True, prompt for configuration even if already configured.
                         If False, use existing configuration without prompting.
        """
        # Check if Nexus is already configured
        nexus_repo = self.ca_settings.get("repositories", {}).get("nexus", {})
        
        if nexus_repo and not force_prompt:
            # Use existing configuration without prompting
            print_info("Using existing Nexus configuration.")
            # Keep the enabled status as is
        elif nexus_repo:
            print_info("Nexus configuration found.")
            reuse = input("Do you want to use Nexus? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                nexus_repo["enabled"] = False
                self.ca_settings["repositories"]["nexus"] = nexus_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Nexus disabled and saved to configuration.")
                return False
            else:
                # Enable the repository
                nexus_repo["enabled"] = True
                self.ca_settings["repositories"]["nexus"] = nexus_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Nexus enabled and saved to configuration.")
        else:
            # Ask if user wants to configure Nexus
            ans = input("🔄 Configure Sonatype Nexus? (y/N): ").strip().lower()
            if ans != "y":
                # Add a disabled entry to repositories
                if "repositories" not in self.ca_settings:
                    self.ca_settings["repositories"] = {}
                self.ca_settings["repositories"]["nexus"] = {
                    "type": "nexus",
                    "enabled": False
                }
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Nexus disabled and saved to configuration.")
                return False
                
            # Initialize Nexus repository settings
            nexus_repo = {
                "type": "nexus",
                "enabled": True,
                "url": input("   Repository URL (e.g. https://nexus.example.com/repository/pypi/simple): ").strip(),
                "username": input("   Username: ").strip(),
                "password": input("   Password: ").strip(),
                "trusted": input("   Trust this host? (Y/n): ").strip().lower() != "n"
            }
            
            # Add to repositories
            if "repositories" not in self.ca_settings:
                self.ca_settings["repositories"] = {}
            self.ca_settings["repositories"]["nexus"] = nexus_repo
            # Save the updated settings
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
            print_info("Nexus configuration saved.")

        # If enabled, perform login
        if nexus_repo.get("enabled", False):
            return self._login_to_nexus(nexus_repo)
        return False
        
    def _login_to_nexus(self, nexus_repo):
        """Login to Nexus with the provided settings."""
        try:
            # Create or update pip.conf with credentials
            url = nexus_repo["url"]
            username = nexus_repo["username"]
            password = nexus_repo["password"]
            
            # Create .netrc file for authentication
            netrc_path = os.path.expanduser("~/.netrc")
            hostname = ""
            
            try:
                from urllib.parse import urlparse
                hostname = urlparse(url).netloc
            except Exception:
                hostname = url.split("/")[2] if url.startswith("http") else url
            
            if hostname:
                # Check if entry already exists
                existing_content = ""
                if os.path.exists(netrc_path):
                    with open(netrc_path, "r") as f:
                        existing_content = f.read()
                
                # Only add if not already present
                if hostname not in existing_content:
                    with open(netrc_path, "a") as f:
                        f.write(f"\nmachine {hostname}\n")
                        f.write(f"login {username}\n")
                        f.write(f"password {password}\n")
                    
                    # Set permissions
                    os.chmod(netrc_path, 0o600)
                    print_success(f"Added Nexus credentials to ~/.netrc for {hostname}")
                else:
                    print_info(f"Credentials for {hostname} already exist in ~/.netrc")
            
            print_success("Nexus login configured.")
            return True
        except Exception as e:
            print_error(f"Nexus login failed: {e}")
            return False

    def _maybe_setup_github_packages(self, force_prompt=False) -> bool:
        """Configure GitHub Packages repository.
        
        Args:
            force_prompt: If True, prompt for configuration even if already configured.
                         If False, use existing configuration without prompting.
        """
        # Check if GitHub Packages is already configured
        gh_repo = self.ca_settings.get("repositories", {}).get("github", {})
        
        if gh_repo and not force_prompt:
            # Use existing configuration without prompting
            print_info("Using existing GitHub Packages configuration.")
            # Keep the enabled status as is
        elif gh_repo:
            print_info("GitHub Packages configuration found.")
            reuse = input("Do you want to use GitHub Packages? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                gh_repo["enabled"] = False
                self.ca_settings["repositories"]["github"] = gh_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("GitHub Packages disabled and saved to configuration.")
                return False
            else:
                # Enable the repository
                gh_repo["enabled"] = True
                self.ca_settings["repositories"]["github"] = gh_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("GitHub Packages enabled and saved to configuration.")
        else:
            # Ask if user wants to configure GitHub Packages
            ans = input("🐙 Configure GitHub Packages? (y/N): ").strip().lower()
            if ans != "y":
                # Add a disabled entry to repositories
                if "repositories" not in self.ca_settings:
                    self.ca_settings["repositories"] = {}
                self.ca_settings["repositories"]["github"] = {
                    "type": "github",
                    "enabled": False
                }
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("GitHub Packages disabled and saved to configuration.")
                return False
                
            # Initialize GitHub Packages repository settings
            gh_repo = {
                "type": "github",
                "enabled": True,
                "url": "https://pypi.pkg.github.com/OWNER/simple/",
                "username": input("   GitHub Username: ").strip(),
                "token": input("   GitHub Personal Access Token: ").strip(),
                "owner": input("   Repository Owner (organization or username): ").strip(),
                "trusted": True
            }
            
            # Update URL with the correct owner
            gh_repo["url"] = gh_repo["url"].replace("OWNER", gh_repo["owner"])
            
            # Add to repositories
            if "repositories" not in self.ca_settings:
                self.ca_settings["repositories"] = {}
            self.ca_settings["repositories"]["github"] = gh_repo
            # Save the updated settings
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
            print_info("GitHub Packages configuration saved.")

        # If enabled, perform login
        if gh_repo.get("enabled", False):
            return self._login_to_github_packages(gh_repo)
        return False
        
    def _login_to_github_packages(self, gh_repo):
        """Login to GitHub Packages with the provided settings."""
        try:
            # Create or update pip.conf with credentials
            url = gh_repo["url"]
            username = gh_repo["username"]
            token = gh_repo["token"]
            
            # Create .netrc file for authentication
            netrc_path = os.path.expanduser("~/.netrc")
            hostname = ""
            
            try:
                from urllib.parse import urlparse
                hostname = urlparse(url).netloc
            except Exception:
                hostname = url.split("/")[2] if url.startswith("http") else url
            
            if hostname:
                # Check if entry already exists
                existing_content = ""
                if os.path.exists(netrc_path):
                    with open(netrc_path, "r") as f:
                        existing_content = f.read()
                
                # Only add if not already present
                if hostname not in existing_content:
                    with open(netrc_path, "a") as f:
                        f.write(f"\nmachine {hostname}\n")
                        f.write(f"login token\n")
                        f.write(f"password {token}\n")
                    
                    # Set permissions
                    os.chmod(netrc_path, 0o600)
                    print_success(f"Added GitHub Packages credentials to ~/.netrc for {hostname}")
                else:
                    print_info(f"Credentials for {hostname} already exist in ~/.netrc")
            
            print_success("GitHub Packages login configured.")
            return True
        except Exception as e:
            print_error(f"GitHub Packages login failed: {e}")
            return False

    def _maybe_setup_azure_artifacts(self, force_prompt=False) -> bool:
        """Configure Azure Artifacts repository.
        
        Args:
            force_prompt: If True, prompt for configuration even if already configured.
                         If False, use existing configuration without prompting.
        """
        # Check if Azure Artifacts is already configured
        azure_repo = self.ca_settings.get("repositories", {}).get("azure", {})
        
        if azure_repo and not force_prompt:
            # Use existing configuration without prompting
            print_info("Using existing Azure Artifacts configuration.")
            # Keep the enabled status as is
        elif azure_repo:
            print_info("Azure Artifacts configuration found.")
            reuse = input("Do you want to use Azure Artifacts? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                azure_repo["enabled"] = False
                self.ca_settings["repositories"]["azure"] = azure_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Azure Artifacts disabled and saved to configuration.")
                return False
            else:
                # Enable the repository
                azure_repo["enabled"] = True
                self.ca_settings["repositories"]["azure"] = azure_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Azure Artifacts enabled and saved to configuration.")
        else:
            # Ask if user wants to configure Azure Artifacts
            ans = input("☁️ Configure Azure Artifacts? (y/N): ").strip().lower()
            if ans != "y":
                # Add a disabled entry to repositories
                if "repositories" not in self.ca_settings:
                    self.ca_settings["repositories"] = {}
                self.ca_settings["repositories"]["azure"] = {
                    "type": "azure",
                    "enabled": False
                }
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Azure Artifacts disabled and saved to configuration.")
                return False
                
            # Initialize Azure Artifacts repository settings
            azure_repo = {
                "type": "azure",
                "enabled": True,
                "organization": input("   Azure DevOps Organization: ").strip(),
                "project": input("   Project Name: ").strip(),
                "feed": input("   Feed Name: ").strip(),
                "username": input("   Username (typically just use any string): ").strip() or "azure",
                "token": input("   Personal Access Token: ").strip(),
                "trusted": True
            }
            
            # Build the URL from components
            azure_repo["url"] = f"https://pkgs.dev.azure.com/{azure_repo['organization']}/{azure_repo['project']}/_packaging/{azure_repo['feed']}/pypi/simple/"
            
            # Add to repositories
            if "repositories" not in self.ca_settings:
                self.ca_settings["repositories"] = {}
            self.ca_settings["repositories"]["azure"] = azure_repo
            # Save the updated settings
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
            print_info("Azure Artifacts configuration saved.")

        # If enabled, perform login
        if azure_repo.get("enabled", False):
            return self._login_to_azure_artifacts(azure_repo)
        return False
        
    def _login_to_azure_artifacts(self, azure_repo):
        """Login to Azure Artifacts with the provided settings."""
        try:
            # Create or update pip.conf with credentials
            url = azure_repo["url"]
            username = azure_repo["username"]
            token = azure_repo["token"]
            
            # Create .netrc file for authentication
            netrc_path = os.path.expanduser("~/.netrc")
            hostname = ""
            
            try:
                from urllib.parse import urlparse
                hostname = urlparse(url).netloc
            except Exception:
                hostname = url.split("/")[2] if url.startswith("http") else url
            
            if hostname:
                # Check if entry already exists
                existing_content = ""
                if os.path.exists(netrc_path):
                    with open(netrc_path, "r") as f:
                        existing_content = f.read()
                
                # Only add if not already present
                if hostname not in existing_content:
                    with open(netrc_path, "a") as f:
                        f.write(f"\nmachine {hostname}\n")
                        f.write(f"login {username}\n")
                        f.write(f"password {token}\n")
                    
                    # Set permissions
                    os.chmod(netrc_path, 0o600)
                    print_success(f"Added Azure Artifacts credentials to ~/.netrc for {hostname}")
                else:
                    print_info(f"Credentials for {hostname} already exist in ~/.netrc")
            
            print_success("Azure Artifacts login configured.")
            return True
        except Exception as e:
            print_error(f"Azure Artifacts login failed: {e}")
            return False

    def _maybe_setup_google_artifact_registry(self, force_prompt=False) -> bool:
        """Configure Google Artifact Registry repository.
        
        Args:
            force_prompt: If True, prompt for configuration even if already configured.
                         If False, use existing configuration without prompting.
        """
        # Check if Google Artifact Registry is already configured
        gcp_repo = self.ca_settings.get("repositories", {}).get("google", {})
        
        if gcp_repo and not force_prompt:
            # Use existing configuration without prompting
            print_info("Using existing Google Artifact Registry configuration.")
            # Keep the enabled status as is
        elif gcp_repo:
            print_info("Google Artifact Registry configuration found.")
            reuse = input("Do you want to use Google Artifact Registry? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                gcp_repo["enabled"] = False
                self.ca_settings["repositories"]["google"] = gcp_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Google Artifact Registry disabled and saved to configuration.")
                return False
            else:
                # Enable the repository
                gcp_repo["enabled"] = True
                self.ca_settings["repositories"]["google"] = gcp_repo
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Google Artifact Registry enabled and saved to configuration.")
        else:
            # Ask if user wants to configure Google Artifact Registry
            ans = input("☁️ Configure Google Artifact Registry? (y/N): ").strip().lower()
            if ans != "y":
                # Add a disabled entry to repositories
                if "repositories" not in self.ca_settings:
                    self.ca_settings["repositories"] = {}
                self.ca_settings["repositories"]["google"] = {
                    "type": "google",
                    "enabled": False
                }
                # Save the updated settings
                self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                print_info("Google Artifact Registry disabled and saved to configuration.")
                return False
                
            # Initialize Google Artifact Registry repository settings
            gcp_repo = {
                "type": "google",
                "enabled": True,
                "project": input("   GCP Project ID: ").strip(),
                "location": input("   Location (e.g., us-west1): ").strip(),
                "repository": input("   Repository Name: ").strip(),
                "trusted": True
            }
            
            # Build the URL from components
            gcp_repo["url"] = f"https://{gcp_repo['location']}-python.pkg.dev/{gcp_repo['project']}/{gcp_repo['repository']}/simple/"
            
            # Add to repositories
            if "repositories" not in self.ca_settings:
                self.ca_settings["repositories"] = {}
            self.ca_settings["repositories"]["google"] = gcp_repo
            # Save the updated settings
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
            print_info("Google Artifact Registry configuration saved.")

        # If enabled, perform login
        if gcp_repo.get("enabled", False):
            return self._login_to_google_artifact_registry(gcp_repo)
        return False
        
    def _login_to_google_artifact_registry(self, gcp_repo):
        """Login to Google Artifact Registry with the provided settings."""
        try:
            # Check for gcloud CLI
            if which("gcloud") is None:
                print_error("gcloud CLI not found; cannot configure Google Artifact Registry.")
                print_info("Please install the Google Cloud SDK: https://cloud.google.com/sdk/docs/install")
                return False
                
            # Authenticate with gcloud
            print_info("Authenticating with Google Cloud...")
            print_info("This will open a browser window to complete authentication.")
            
            # Run gcloud auth login
            subprocess.run(["gcloud", "auth", "login"], check=True)
            
            # Configure pip to use the repository
            url = gcp_repo["url"]
            
            # Get application default credentials
            print_info("Setting up application default credentials...")
            subprocess.run(["gcloud", "auth", "application-default", "login"], check=True)
            
            print_success("Google Artifact Registry login configured.")
            return True
        except Exception as e:
            print_error(f"Google Artifact Registry login failed: {e}")
            return False

    def _print_contribution_request(self):
        
        self.__exit_notes.append("Need any changes?")
        self.__exit_notes.append("👉 Please open an issue at https://github.com/geekcafe/py-setup-tool/issues/new")
        self.__exit_notes.append("👉 Or help us make it better by submitting a pull request.")

    def _detect_platform(self):
        sysname = os.uname().sysname
        arch = os.uname().machine
        print("🧠 Detecting OS and architecture...")

        os_type = "unknown"
        if sysname == "Darwin":
            os_type = "mac"
        elif sysname == "Linux":
            os_type = "debian" if os.path.exists("/etc/debian_version") else "linux"
        else:
            print_error(f"Unsupported OS: {sysname}")
            sys.exit(1)
        
        print(f"📟 OS: {os_type} | Architecture: {arch}")
        # Detect project tool from pyproject.toml or requirements.txt
        project_tool = self._detect_project_tool()
        
        # In CI mode, use detected package manager without prompting
        if hasattr(self, '_ci_mode') and self._ci_mode:
            if project_tool == "poetry":
                self._use_poetry = True
                print_info("CI mode: Using Poetry as detected from pyproject.toml.")
            elif project_tool in ["hatch", "flit", "pip"]:
                self._use_poetry = False
                print_info(f"CI mode: Using {project_tool} as detected from project files.")
            else:
                # If no tool detected in CI mode, default to pip
                self._use_poetry = False
                print_info("CI mode: No package manager detected, defaulting to pip.")
        else:
            # Interactive mode - use detected tool or prompt if none detected
            if project_tool == "poetry":
                self._use_poetry = True
                print_info("Detected Poetry project from pyproject.toml.")
            elif project_tool == "hatch":
                self._use_poetry = False
                print_info("Detected Hatch project from pyproject.toml.")
            elif project_tool == "flit":
                self._use_poetry = False
                print_info("Detected Flit project from pyproject.toml.")
            elif project_tool == "pip":
                self._use_poetry = False
                print_info("Defaulting to pip project from requirements.txt.")
            else:
                pip_or_poetry = (
                    input("📦 Do you want to use pip or poetry? (default: pip): ") or "pip"
                )
                self._use_poetry = pip_or_poetry.lower() == "poetry"
        
        return os_type

    def _detect_project_tool(self):
        if not os.path.exists("pyproject.toml"):

            if os.path.exists("requirements.txt"):
                return "pip"
            else:

                return None
        try:
            with open("pyproject.toml", "r", encoding="utf-8") as f:
                contents = f.read()
                if "[tool.poetry]" in contents:
                    return "poetry"
                elif "[tool.hatch]" in contents:
                    return "hatch"
                elif "[tool.flit]" in contents:
                    return "flit"
                else:
                    return "pip"
        except Exception:
            return None
        return None

    def _convert_requirements_to_poetry(self) -> str:
        deps = []
        if os.path.exists("requirements.txt"):
            with open("requirements.txt", "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        deps.append(line)
        return "\n".join([f"{dep}" for dep in deps])

    def _create_pyproject_toml(self):
        if os.path.exists("pyproject.toml"):
            print_success("pyproject.toml already exists.")
            return

        print_info("pyproject.toml not found. Let's create one.")
        self._package_name = self._get_default_package_name()
        package_name_input = input(f"Package name (default: {self._package_name}): ")
        if package_name_input:
            self._package_name = (
                package_name_input.replace(" ", "-").lower().replace("-", "_")
            )

        package_version = input("Package version (default: 0.1.0): ") or "0.1.0"
        package_description = input("Package description: ")
        author_name = self._get_git_config("user.name") or "unnamed developer"
        author_email = self._get_git_config("user.email") or "developer@example.com"

        author_name = input(f"Author name (default: {author_name}): ") or author_name
        author_email = (
            input(f"Author email (default: {author_email}): ") or author_email
        )

        src_package_path = Path(f"src/{self._package_name}")
        src_package_path.mkdir(parents=True, exist_ok=True)
        init_file = src_package_path / "__init__.py"
        init_file.touch(exist_ok=True)

        if self._use_poetry:
            deps_block = self._convert_requirements_to_poetry()
            content = f"""
                [tool.poetry]
                name = "{self._package_name}"
                version = "{package_version}"
                description = "{package_description}"
                authors = ["{author_name} <{author_email}>"]

                [tool.poetry.dependencies]
                python = "^3.8"
{self._indent_dependencies(deps_block)}

                [tool.poetry.group.dev.dependencies]
                pytest = "^7.0"

                [build-system]
                requires = ["poetry-core>=1.0.0"]
                build-backend = "poetry.core.masonry.api"
            """
        else:
            build_system = input("Build system (default: hatchling): ") or "hatchling"
            content = f"""
                [project]
                name = "{self._package_name}"
                version = "{package_version}"
                description = "{package_description}"
                authors = [{{name="{author_name}", email="{author_email}"}}]
                requires-python = ">=3.8"

                [tool.pytest.ini_options]
                pythonpath = ["src"]
                testpaths = ["tests", "src"]
                markers = [
                    "integration: marks tests as integration (deselect with '-m \\"not integration\\"')"
                ]
                addopts = "-m 'not integration'"

                [build-system]
                requires = ["{build_system}"]
                build-backend = "{build_system}.build"

                [tool.hatch.build.targets.wheel]
                packages = ["src/{self._package_name}"]

                [tool.hatch.build.targets.sdist]
                exclude = [
                    ".unittest/",
                    ".venv/",
                    "tests/",
                    "samples/",
                    "docs/",
                    ".git/",
                    ".gitignore",
                    ".vscode/",
                    "*.pyc",
                    "__pycache__/",
                    "*.egg-info/",
                    "dist/",
                    "build/"
                ]
            """
            os.makedirs("tests", exist_ok=True)

        with open("pyproject.toml", "w", encoding="utf-8") as file:
            file.write(self._strip_content(content))
        print_success("pyproject.toml created.")

    def _indent_dependencies(self, deps: str) -> str:
        return "\n".join([" " * 4 + dep for dep in deps.splitlines() if dep.strip()])

    def _get_default_package_name(self):
        return Path(os.getcwd()).name.lower().replace(" ", "_").replace("-", "_")

    def _get_git_config(self, key: str) -> str:
        try:
            result = subprocess.run(
                ["git", "config", "--get", key], capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            return None
        return None

    def _strip_content(self, content: str) -> str:
        return "\n".join(
            line.strip().replace("\t", "")
            for line in content.split("\n")
            if line.strip()
        )

    def _setup_requirements(self):
        self._write_if_missing("requirements.txt", "# project requirements")
        self._write_if_missing(
            "requirements.dev.txt",
            self._strip_content(self._dev_requirements_content()),
        )

    def _write_if_missing(self, filename: str, content: str):
        if not os.path.exists(filename):
            print_info(f"{filename} not found. Let's create one.")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            print_success(f"{filename} created.")
        else:
            print_success(f"{filename} already exists.")

    def _dev_requirements_content(self) -> str:
        return """
            # dev and testing requirements
            pytest
            mypy
            types-python-dateutil
            build
            toml
            twine
            wheel
            pkginfo
            hatchling            
        """

    def setup(self, force_update_sh=False, ci_mode=False):
        # Store CI mode for use in other methods
        self._ci_mode = ci_mode
        
        # Check for and fetch the latest pysetup.sh first
        if self._check_and_fetch_setup_sh(force_update=force_update_sh):
            # If pysetup.sh was updated, exit and instruct the user to restart
            sys.exit(0)
            
        self._detect_platform()
        self._create_pyproject_toml()
        (self._setup_poetry if self._use_poetry else self._setup_pip)()
        self.print_env_info()
        
        # Check if README.md exists and create it if needed
        self._check_readme_setup()
        
        # Check if .pysetup.json should be excluded from git
        self._check_gitignore_setup()
        
        # Check if Git is initialized and set it up if needed
        self._check_git_setup()
        
        # Create an activation helper script for convenience
        self._create_activation_helper()
        
        print("\n🎉 Setup complete!")
        if not self._use_poetry:
            # Check if virtual environment is already active
            if os.environ.get('VIRTUAL_ENV') == os.path.abspath(VENV):
                print(f"\n👍 Virtual environment '{VENV}' is already active!")
            else:
                print(f"\n👉 To activate the virtual environment, run one of these commands:")
                print(f"   source {VENV}/bin/activate")
                print(f"   source activate.sh")
                print(f"\n💡 The activate.sh script has been created for your convenience.")

    def _check_venv_path_integrity(self) -> bool:
        """Check if the virtual environment has correct path references.
        
        Returns:
            bool: True if venv is healthy or doesn't exist, False if corrupted
        """
        # In CI mode, skip this check since we're using 'clean' mode anyway
        if hasattr(self, '_ci_mode') and self._ci_mode:
            print_info("Running in CI mode, skipping virtual environment path integrity check.")
            return True
            
        venv_path = Path(VENV)
        if not venv_path.exists():
            return True  # No venv exists, so no corruption possible
            
        # Check if the pip script exists and has correct shebang
        pip_script = venv_path / "bin" / "pip"
        if not pip_script.exists():
            return True  # No pip script, let normal creation handle it
            
        try:
            # Read the first line (shebang) of the pip script
            with open(pip_script, 'r') as f:
                shebang = f.readline().strip()
                
            # Extract the interpreter path from the shebang
            python_path = shebang[2:] if shebang.startswith('#!') else shebang
            python_path_obj = Path(python_path)
            
            # First check: Does the interpreter path in the shebang actually exist?
            # This catches project directory renames where the path is now invalid
            if not python_path_obj.exists() or not os.access(python_path, os.X_OK):
                print_error(f"Virtual environment interpreter not found:")
                print(f"   Path in shebang: {python_path}")
                print("   This usually happens when the project directory was renamed or moved.")
                return False
                
            # Get expected paths from settings
            expected_paths = self.ca_settings.get("python_paths", [])
            
            # If no paths are stored or we're using the old format, generate default paths
            if not expected_paths:  
                # Use absolute paths for the fallback
                abs_venv_path = Path(VENV).resolve()
                expected_paths = [
                    f"#!{str(abs_venv_path / 'bin' / 'python')}",
                    f"#!{str(abs_venv_path / 'bin' / 'python3')}"
                ]
                
                # Also look for specific Python versions
                bin_dir = abs_venv_path / "bin"
                if bin_dir.exists():
                    for item in bin_dir.iterdir():
                        if item.name.startswith("python3.") and item.is_file() and os.access(item, os.X_OK):
                            expected_paths.append(f"#!{str(item)}")
            
            # Direct match - this should work with the new format
            if shebang in expected_paths:
                # Even if there's a match, verify the path exists (handles directory renames)
                if python_path_obj.exists() and os.access(python_path, os.X_OK):
                    return True
                else:
                    # Path matches but doesn't exist - likely a directory rename
                    print_error(f"Virtual environment interpreter not found:")
                    print(f"   Path in shebang: {python_path}")
                    print("   This usually happens when the project directory was renamed or moved.")
                    return False
                
            # No direct match, try more flexible matching for compatibility
            # with both old and new formats
            
            # Extract paths from expected_paths (removing #! if present)
            resolved_expected_paths = [path[2:] if path.startswith('#!') else path for path in expected_paths]
            
            # Check if the path matches any expected path
            if python_path in resolved_expected_paths:
                # Even if there's a match, verify the path exists
                if python_path_obj.exists() and os.access(python_path, os.X_OK):
                    return True
                else:
                    # Path matches but doesn't exist - likely a directory rename
                    print_error(f"Virtual environment interpreter not found:")
                    print(f"   Path in shebang: {python_path}")
                    print("   This usually happens when the project directory was renamed or moved.")
                    return False
                
            # Check if the basename matches (most flexible, last resort)
            python_basename = os.path.basename(python_path)
            for exp_path in resolved_expected_paths:
                if os.path.basename(exp_path) == python_basename:
                    exp_path_obj = Path(exp_path)
                    if exp_path_obj.exists() and os.access(exp_path, os.X_OK):
                        # Found a match by basename that exists, update the stored paths for next time
                        new_shebang = f"#!{exp_path}"
                        if new_shebang not in expected_paths:
                            expected_paths.append(new_shebang)
                            self.ca_settings["python_paths"] = expected_paths
                            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                            print_info(f"Updated Python interpreter paths in {self.CA_CONFIG}")
                        return True
            
            # If we get here, no valid match was found
            print_error(f"Virtual environment has incorrect path references:")
            print(f"   Expected one of: {expected_paths}")
            print(f"   Found:           {shebang}")
            print("   This usually happens when the project directory was renamed or moved.")
            return False
                    
        except (IOError, OSError) as e:
            print_error(f"Could not check virtual environment integrity: {e}")
            return False
            
        return True

    def _handle_corrupted_venv(self) -> bool:
        """Handle a corrupted virtual environment by prompting user for action.
        
        Returns:
            bool: True if user wants to recreate, False to abort
        """
        print("\n🔧 Virtual Environment Path Issue Detected")
        print("=" * 45)
        print("The virtual environment contains hardcoded paths that don't match")
        print("the current project directory. This can happen when:")
        print("  • The project directory was renamed")
        print("  • The project was moved to a different location")
        print("  • The virtual environment was copied from another location")
        print()
        
        response = input("Would you like to remove the current virtual environment and recreate it? (Y/n): ").strip().lower()
        if response in ('', 'y', 'yes'):
            print(f"🗑️  Removing corrupted virtual environment at {VENV}...")
            if _remove_directory(VENV):
                print_success(f"Removed {VENV}")
                return True
            else:
                print_error(f"Failed to completely remove {VENV}")
                return False
        else:
            print("⚠️  Setup aborted. Please manually fix the virtual environment or remove it.")
            return False

    def _run_pip_with_progress(self, cmd: List[str], description: str) -> bool:
        """Run a pip command with live progress indication and clean output.
        
        Args:
            cmd: The pip command to run
            description: Description of what's being installed
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Function to execute pip command with progress tracking
        def execute_pip_command():
            # Animation characters for spinner
            spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
            spinner_idx = 0
            
            # Start the process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Track current package being installed
            current_package = ""
            packages_installed = []
            last_line_length = 0  # Track length of last printed line
            full_output = []  # Collect all output for auth error detection
            
            # Print initial message
            print(f"🔗 {description}")
            
            # Read output line by line
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                    
                if output:
                    # Store full output for later auth error detection
                    full_output.append(output)
                    
                    # Extract package name from pip output
                    line = output.strip()
                    
                    # Look for "Collecting" or "Installing" patterns
                    if "Collecting" in line:
                        match = re.search(r'Collecting ([^\s>=<]+)', line)
                        if match:
                            current_package = match.group(1)
                    elif "Installing collected packages:" in line:
                        # Extract package names from the installation line
                        packages_match = re.search(r'Installing collected packages: (.+)', line)
                        if packages_match:
                            packages_installed = [pkg.strip() for pkg in packages_match.group(1).split(',')]
                    elif "Successfully installed" in line:
                        # Extract successfully installed packages
                        success_match = re.search(r'Successfully installed (.+)', line)
                        if success_match:
                            packages_installed = [pkg.split('-')[0] for pkg in success_match.group(1).split()]
                    
                    # Show spinner with current package
                    if current_package:
                        spinner = spinner_chars[spinner_idx % len(spinner_chars)]
                        status_line = f"   {spinner} Installing {current_package}..."
                        
                        # Clear previous line completely
                        if last_line_length > 0:
                            print("\r" + " " * last_line_length + "\r", end='', flush=True)
                        
                        # Print new status line
                        print(status_line, end='', flush=True)
                        last_line_length = len(status_line)
                        
                        spinner_idx += 1
                        time.sleep(0.1)
            
            # Wait for process to complete
            return_code = process.wait()
            
            # Clear the spinner line completely
            if last_line_length > 0:
                print("\r" + " " * last_line_length + "\r", end='', flush=True)
            
            # Return results including full output for auth error detection
            return {
                "return_code": return_code,
                "packages_installed": packages_installed,
                "full_output": ''.join(full_output)
            }
        
        # Execute pip command and get results
        try:
            result = execute_pip_command()
            return_code = result["return_code"]
            packages_installed = result["packages_installed"]
            full_output = result["full_output"]
            
            # Check for package not found errors first
            if return_code != 0 and self._output_has_package_not_found(full_output):
                package_name = self._extract_package_name_from_error(full_output)
                if package_name:
                    print_error(f"Package not found: {package_name}")
                    print_info("This appears to be a missing package error, not an authentication issue.")
                    print_info("Check that the package name is correct and available in the configured repositories.")
                    
                    # Ask if user wants to configure additional repositories
                    setup_repos = input("Would you like to configure additional package repositories? (y/N): ").strip().lower()
                    if setup_repos == "y":
                        self._setup_repositories(force_prompt=True)
                        print_info(f"Retrying installation of {package_name}...")
                        # Retry the command after setting up repositories
                        retry_result = execute_pip_command()
                        return_code = retry_result["return_code"]
                        packages_installed = retry_result["packages_installed"]
                        full_output = retry_result["full_output"]
                        
                        # Process the retry result
                        if return_code == 0:
                            if packages_installed:
                                package_list = ", ".join(packages_installed[:3])
                                if len(packages_installed) > 3:
                                    package_list += f" and {len(packages_installed) - 3} more"
                                print_success(f"Successfully installed {package_list} after repository setup")
                                return True
                        else:
                            print_error(f"Package {package_name} still not found after repository setup")
                else:
                    print_error("Package not found error detected.")
                    print_info("You may need to configure additional package repositories.")
                    setup_repos = input("Would you like to configure additional package repositories? (y/N): ").strip().lower()
                    if setup_repos == "y":
                        self._setup_repositories()
                return False
                
            # Check for authentication errors
            elif return_code != 0 and self._output_has_auth_error(full_output):
                print_info("Detected repository authentication error.")
                if self._handle_repo_auth_error(full_output):
                    print_info("Authentication refreshed. Retrying pip command...")
                    # Retry the command after authentication
                    retry_result = execute_pip_command()
                    return_code = retry_result["return_code"]
                    packages_installed = retry_result["packages_installed"]
                    full_output = retry_result["full_output"]
                else:
                    print_error("Repository login failed after authentication warning.")
                    return False
            
            # Process final result
            if return_code == 0:
                if packages_installed:
                    package_list = ", ".join(packages_installed[:3])  # Show first 3 packages
                    if len(packages_installed) > 3:
                        package_list += f" and {len(packages_installed) - 3} more"
                    print_success(f"Installed {package_list}")
                else:
                    print_success("Command completed successfully")
                return True
            else:
                print_error(f"Command failed with return code {return_code}")
                return False
                
        except Exception as e:
            print_error(f"Error executing pip command: {e}")
            return False

    def _run_pip_command_with_progress(self, pip_args: List[str], description: str):
        """Wrapper to run pip commands with progress indication.
        
        Args:
            pip_args: Arguments to pass to pip (without the pip executable)
            description: Description of the operation
        """
        cmd = [f"{VENV}/bin/pip"] + pip_args
        
        if not self._run_pip_with_progress(cmd, description):
            raise subprocess.CalledProcessError(1, cmd)

    def _check_readme_setup(self):
        """Check if README.md exists and create it if needed."""
        # Check if README.md exists
        readme_path = Path("README.md")
        
        # If README.md doesn't exist, create a default one
        if not readme_path.exists():
            print_header("Project Documentation")
            print("No README.md file found. Creating a default README.md file.")
            
            # Get the project name from the current directory
            project_name = Path.cwd().name
            
            # Try to get project description from pyproject.toml if it exists
            project_description = "Your project description here."
            pyproject_path = Path("pyproject.toml")
            
            if pyproject_path.exists():
                try:
                    with open(pyproject_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        
                        # Try to extract description from poetry section
                        poetry_match = re.search(r'\[tool\.poetry\][^\[]*description\s*=\s*"([^"]*)"', content)
                        if poetry_match:
                            project_description = poetry_match.group(1)
                        else:
                            # Try to extract from project section (PEP 621)
                            project_match = re.search(r'\[project\][^\[]*description\s*=\s*"([^"]*)"', content)
                            if project_match:
                                project_description = project_match.group(1)
                except Exception as e:
                    print_info(f"Could not extract project description from pyproject.toml: {e}")
            
            # Create a default README.md template
            readme_content = f"""# {project_name}

## Description
{project_description}

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/{project_name}.git
cd {project_name}

# Setup the environment
./pysetup.sh
```

## Usage

Describe how to use your project here.

## Features

- Feature 1
- Feature 2
- Feature 3

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
We welcome bug reports and feature requests.

## License

Add your license here.
"""
            
            # Write the default README.md file
            with open(readme_path, "w") as f:
                f.write(readme_content)
            print_success("Created default README.md file")
            
            # Track that we've created a README.md file
            if "setup_prompted" not in self.ca_settings:
                self.ca_settings["setup_prompted"] = {}
            self.ca_settings["setup_prompted"]["readme_created"] = True
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
    
    def _check_git_setup(self):
        """Check if Git is initialized in the project and set it up if needed.
        
        If in CI mode, this will skip any prompts and not initialize Git.
        Otherwise, it will prompt the user to initialize Git and optionally make the first commit.
        """
        # Check if .git directory exists
        git_dir = Path(".git")
        
        # Skip Git setup in CI mode
        if self._ci_mode:
            print_info("Running in CI mode, skipping Git setup.")
            return
        
        # If .git doesn't exist, prompt to initialize Git
        if not git_dir.exists():
            print_header("Git Repository")
            print("No Git repository found in this directory.")
            response = input("Would you like to initialize a Git repository? (Y/n): ").strip().lower() or 'y'
            
            if response.startswith('y'):
                try:
                    # Initialize Git repository
                    subprocess.run(["git", "init"], check=True)
                    print_success("Git repository initialized.")
                    
                    # Track that we've initialized Git
                    if "setup_prompted" not in self.ca_settings:
                        self.ca_settings["setup_prompted"] = {}
                    self.ca_settings["setup_prompted"]["git_initialized"] = True
                    self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
                    
                    # Ask if user wants to make the first commit
                    commit_response = input("Would you like to make the initial commit? (Y/n): ").strip().lower() or 'y'
                    
                    if commit_response.startswith('y'):
                        # Add all files
                        subprocess.run(["git", "add", "."], check=True)
                        
                        # Make the initial commit
                        commit_message = input("Enter commit message (default: 'Initial commit'): ").strip() or "Initial commit"
                        subprocess.run(["git", "commit", "-m", commit_message], check=True)
                        print_success(f"Initial commit created with message: '{commit_message}'")
                        
                        # Ask if user wants to add a remote repository
                        remote_response = input("Would you like to add a remote repository? (y/N): ").strip().lower()
                        
                        if remote_response.startswith('y'):
                            remote_url = input("Enter the remote repository URL: ").strip()
                            if remote_url:
                                subprocess.run(["git", "remote", "add", "origin", remote_url], check=True)
                                print_success(f"Remote repository added: {remote_url}")
                except subprocess.CalledProcessError as e:
                    print_error(f"Error setting up Git: {e}")
            else:
                print_info("Git initialization skipped.")
        else:
            print_info("Git repository already initialized.")
    
    def _create_activation_helper(self):
        """Create a convenient activation script for the virtual environment.
        
        This creates an activate.sh script in the project root that users can source
        to activate the virtual environment without having to remember the full path.
        """
        if self._use_poetry:
            # Poetry has its own activation mechanism
            return
            
        # Create the activation script
        activate_script = Path("activate.sh")
        
        # Don't overwrite if it already exists and has custom content
        if activate_script.exists():
            with open(activate_script, "r") as f:
                content = f.read()
                if f"source {VENV}/bin/activate" not in content:
                    print_info("Custom activate.sh already exists, not overwriting.")
                    return
        
        # Create or update the activation script
        with open(activate_script, "w") as f:
            f.write(f"#!/bin/bash\n\n# Auto-generated by pysetup.py\n# Activates the Python virtual environment\n\nsource {VENV}/bin/activate\n\n# Display Python version and environment info\necho \"\n🐍 Python \$(python --version | cut -d' ' -f2) activated in \$(basename \$VIRTUAL_ENV) environment\"\necho \"\n👉 Run 'deactivate' to exit the virtual environment\"\n")
        
        # Make it executable
        os.chmod(activate_script, 0o755)
        
        # Add to .gitignore if it's not already there
        if Path(".gitignore").exists():
            with open(".gitignore", "r") as f:
                gitignore_content = f.read()
                
            if "activate.sh" not in gitignore_content:
                with open(".gitignore", "a") as f:
                    f.write("\nactivate.sh\n")
        else:
            with open(".gitignore", "w") as f:
                f.write("activate.sh\n")
    
    def _check_gitignore_setup(self):
        """Check if .gitignore exists and create it if needed, also check if .pysetup.json should be added."""
        # First, check if .gitignore exists
        gitignore_path = Path(".gitignore")
        
        # If .gitignore doesn't exist, create a default Python .gitignore
        if not gitignore_path.exists():
            print_header("Git Configuration")
            print("No .gitignore file found. Creating a default Python .gitignore file.")
            
            # Fetch the standard Python .gitignore content from GitHub
            python_gitignore = """
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[codz]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
#  Usually these files are written by a python script from a template
#  before PyInstaller builds the exe, so as to inject date/other infos into it.
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py.cover
.hypothesis/
.pytest_cache/
cover/

# Translations
*.mo
*.pot

# Django stuff:
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal

# Flask stuff:
instance/
.webassets-cache

# Scrapy stuff:
.scrapy

# Sphinx documentation
docs/_build/

# PyBuilder
.pybuilder/
target/

# Jupyter Notebook
.ipynb_checkpoints

# IPython
profile_default/
ipython_config.py

# pyenv
#   For a library or package, you might want to ignore these files since the code is
#   intended to run in multiple environments; otherwise, check them in:
# .python-version

# pipenv
#   According to pypa/pipenv#598, it is recommended to include Pipfile.lock in version control.
#   However, in case of collaboration, if having platform-specific dependencies or dependencies
#   having no cross-platform support, pipenv may install dependencies that don't work, or not
#   install all needed dependencies.
#Pipfile.lock

# poetry
#   Similar to Pipfile.lock, it is generally recommended to include poetry.lock in version control.
#   This is especially recommended for binary packages to ensure reproducibility, and is more
#   commonly ignored for libraries.
#   https://python-poetry.org/docs/basic-usage/#commit-your-poetrylock-file-to-version-control
#poetry.lock

# Environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Spyder project settings
.spyderproject
.spyproject

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Pyre type checker
.pyre/

# pytype static type analyzer
.pytype/

# Cython debug symbols
cython_debug/

# PyCharm
#.idea/

# VS Code
#.vscode/
"""
            
            # Write the default Python .gitignore file
            with open(gitignore_path, "w") as f:
                f.write(python_gitignore)
            print_success("Created default Python .gitignore file")
            
            # Track that we've created a gitignore file, but don't mark pysetup.json as prompted
            if "setup_prompted" not in self.ca_settings:
                self.ca_settings["setup_prompted"] = {}
            self.ca_settings["setup_prompted"]["gitignore_created"] = True
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
        
        # First check if .pysetup.json is already in the .gitignore file
        content = gitignore_path.read_text()
        
        # If .pysetup.json is already in the .gitignore, mark it as prompted and skip
        if ".pysetup.json" in content:
            # Ensure setup_prompted structure exists
            if "setup_prompted" not in self.ca_settings:
                self.ca_settings["setup_prompted"] = {}
                
            # Mark that we've handled .pysetup.json gitignore without prompting
            self.ca_settings["setup_prompted"]["pysetup_json_gitignore"] = True
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
            print_info(".pysetup.json is already in .gitignore")
        # Otherwise, check if user has already been prompted about adding .pysetup.json to gitignore
        elif not self.ca_settings.get("setup_prompted", {}).get("pysetup_json_gitignore", False):
            print_header("Git Configuration")
            print(".pysetup.json contains configuration that may be specific to your environment.")
            print("This can cause issues when working with other developers.")
            response = input("Would you like to exclude .pysetup.json from git tracking? (Y/n): ").strip().lower() or 'y'
            
            # Ensure setup_prompted structure exists
            if "setup_prompted" not in self.ca_settings:
                self.ca_settings["setup_prompted"] = {}
            
            # Mark that we've prompted the user about .pysetup.json specifically
            self.ca_settings["setup_prompted"]["pysetup_json_gitignore"] = True
            
            if response.startswith('y'):
                # Add .pysetup.json to .gitignore
                with open(gitignore_path, "a") as f:
                    if not content.endswith("\n"):
                        f.write("\n")
                    f.write("# Local configuration\n.pysetup.json\n")
                print_success("Added .pysetup.json to .gitignore")
            else:
                print_info(".pysetup.json will be tracked by git")
                
            # Save the updated settings
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
    
    def _store_python_interpreter_path(self):
        """Detect and store the actual Python interpreter path in the virtual environment."""
        venv_path = Path(VENV).resolve()  # Get absolute path to venv
        python_paths = set()  # Use a set to avoid duplicates
        
        # Check for common Python interpreter names
        for python_name in ["python", "python3"]:
            python_path = venv_path / "bin" / python_name
            if python_path.exists():
                # Store the absolute path with shebang prefix as it would appear in scripts
                venv_python_path = f"#!{str(python_path.absolute())}"
                if venv_python_path not in python_paths:
                    python_paths.add(venv_python_path)
                    print_info(f"Detected Python interpreter: {venv_python_path}")
        
        # Also try to find the specific Python version (e.g., python3.10, python3.11)
        bin_dir = venv_path / "bin"
        if bin_dir.exists():
            for item in bin_dir.iterdir():
                if item.name.startswith("python3.") and item.is_file() and os.access(item, os.X_OK):
                    venv_python_path = f"#!{str(item.absolute())}"
                    if venv_python_path not in python_paths:
                        python_paths.add(venv_python_path)
                        print_info(f"Detected versioned Python interpreter: {venv_python_path}")
        
        if python_paths:
            # Update settings with the detected paths (convert set back to list and sort alphabetically)
            self.ca_settings["python_paths"] = sorted(list(python_paths))
            
            # Save to .pysetup.json
            self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
            print_success(f"Stored Python interpreter paths in {self.CA_CONFIG}")
        else:
            print_error("Could not detect Python interpreter in virtual environment")

    def _create_pip_conf(self):
        """Create pip.conf in the virtual environment if it doesn't exist."""
        if os.path.exists(f"{VENV}/pip.conf"):
            print_info("pip.conf already exists")
            return

        # Basic pip.conf template
        pip_conf = """
[global]
index-url=https://pypi.org/simple 
extra-index-url=https://pypi.org/simple 
trusted-host = pypi.org
break-system-packages = true
"""

        # Write the pip.conf file
        with open(f"{VENV}/pip.conf", "w", encoding="utf-8") as file:
            file.write(pip_conf)

        print_success("Created pip.conf with break-system-packages enabled")
            
    def _check_and_fetch_setup_sh(self, force_update=False) -> bool:
        """Check for and fetch the latest pysetup.sh from repository.
        
        Args:
            force_update: If True, update pysetup.sh regardless of content comparison
            
        Returns:
            bool: True if pysetup.sh was updated, False otherwise
        """
        # Skip check in CI mode
        if hasattr(self, '_ci_mode') and self._ci_mode:
            print_info("Running in CI mode, skipping pysetup.sh update check.")
            return False
            
        # Get the user's preference for updating pysetup.sh
        update_preference = self._get_setup_sh_update_preference()
        
        if update_preference == "no":
            print_info("Skipping pysetup.sh update check based on user preference.")
            return False
            
        if update_preference == "interactive":
            response = input("\nCheck for latest pysetup.sh from repository? [y/N]: ").strip().lower()
            if response not in ('y', 'yes'):
                return False
        
        print_info("Checking for latest pysetup.sh...")
        
        # URL for the latest pysetup.sh
        setup_sh_url = "https://raw.githubusercontent.com/geekcafe/py-setup-tool/main/pysetup.sh"
        
        try:
            # Fetch the latest pysetup.sh content with retry logic
            latest_setup_sh_bytes = fetch_url_with_retry(setup_sh_url)
            latest_setup_sh = latest_setup_sh_bytes.decode('utf-8')
                
            # Check if pysetup.sh exists locally
            setup_sh_path = Path("pysetup.sh")
            if setup_sh_path.exists():
                # Compare with current pysetup.sh
                with open(setup_sh_path, 'r', encoding='utf-8') as f:
                    current_setup_sh = f.read()
                    
                if current_setup_sh == latest_setup_sh and not force_update:
                    print_info("pysetup.sh is already up to date.")
                    return False
                elif force_update:
                    print_info("Force updating pysetup.sh regardless of content comparison.")
                else:
                    # Debug info to help troubleshoot update issues
                    print_info("Detected differences between local and remote pysetup.sh.")
                    
                    # Calculate content length difference
                    local_len = len(current_setup_sh)
                    remote_len = len(latest_setup_sh)
                    print_info(f"Local file size: {local_len} bytes, Remote file size: {remote_len} bytes")
                    
                    # Show first difference position
                    for i, (local_char, remote_char) in enumerate(zip(current_setup_sh, latest_setup_sh)):
                        if local_char != remote_char:
                            print_info(f"First difference at position {i}: Local '{local_char}' vs Remote '{remote_char}'")
                            break
                    
                # Backup the current pysetup.sh
                backup_path = Path("pysetup.sh.bak")
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(current_setup_sh)
                print_info(f"Current pysetup.sh backed up to {backup_path}")
            
            # Write the latest pysetup.sh
            with open(setup_sh_path, 'w', encoding='utf-8') as f:
                f.write(latest_setup_sh)
                
            # Make it executable
            import os
            os.chmod(setup_sh_path, 0o755)
            
            print_success("pysetup.sh has been updated to the latest version.")
            print("\n⚠️  Please restart the setup process by running:\n    ./pysetup.sh")
            return True
            
        except Exception as e:
            print_error(f"Failed to fetch or update pysetup.sh: {e}")
            return False
    
    def _get_setup_sh_update_preference(self, force_prompt=False) -> str:
        """Get the user's preference for checking for updates to pysetup.sh.
        
        Args:
            force_prompt: If True, prompt for preference even if already configured.
                         If False, use existing preference without prompting.
                         
        Returns:
            str: The pysetup.sh update preference ('yes', 'no', or 'interactive')
        """
        # Check if pysetup.sh update preference is already configured
        update_preference = self.ca_settings.get("setup_sh_update_preference")
        
        if update_preference and not force_prompt:
            # Use existing preference without prompting
            print_info(f"Using stored pysetup.sh update preference: {update_preference}")
            return update_preference
        
        # In CI mode, default to 'no' without prompting
        if hasattr(self, '_ci_mode') and self._ci_mode:
            update_preference = 'no'
            print_info("CI mode: Setting pysetup.sh update preference to 'no' (no updates)")
        else:
            # Prompt for pysetup.sh update preference in interactive mode
            print("\n🔄 pysetup.sh Update Preference")
            print("=" * 45)
            print("Choose how to handle pysetup.sh updates:")
            print("  • yes        : Always check for the latest pysetup.sh from repository")
            print("  • no         : Never check for updates to pysetup.sh")
            print("  • interactive: Ask each time (default)")
            print()
            
            while True:
                response = input("pysetup.sh update preference [interactive/yes/no]: ").strip().lower()
                if response in ('', 'interactive'):
                    update_preference = 'interactive'
                    break
                elif response in ('yes', 'y'):
                    update_preference = 'yes'
                    break
                elif response in ('no', 'n'):
                    update_preference = 'no'
                    break
                else:
                    print_error("Invalid choice. Please enter 'interactive', 'yes', or 'no'.")
        
        # Save the preference
        self.ca_settings["setup_sh_update_preference"] = update_preference
        self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
        print_success(f"Saved pysetup.sh update preference: {update_preference}")
        
        return update_preference
    
    def _get_repo_update_preference(self, force_prompt=False) -> str:
        """Get the user's preference for pulling the latest pysetup.py from repository.
        
        Args:
            force_prompt: If True, prompt for preference even if already configured.
                         If False, use existing preference without prompting.
                         
        Returns:
            str: The repository update preference ('yes', 'no', or 'interactive')
        """
        # Check if repository update preference is already configured
        update_preference = self.ca_settings.get("repo_update_preference")
        
        if update_preference and not force_prompt:
            # Use existing preference without prompting
            print_info(f"Using stored repository update preference: {update_preference}")
            return update_preference
        
        # In CI mode, default to 'no' without prompting
        if hasattr(self, '_ci_mode') and self._ci_mode:
            update_preference = 'no'
            print_info("CI mode: Setting repository update preference to 'no' (no updates)")
        else:
            # Prompt for repository update preference in interactive mode
            print("\n🔄 Repository Update Preference")
            print("=" * 45)
            print("Choose how to handle repository updates:")
            print("  • yes        : Always pull the latest pysetup.py from repository")
            print("  • no         : Never pull the latest pysetup.py")
            print("  • interactive: Ask each time (default)")
            print()
            
            while True:
                response = input("Repository update preference [interactive/yes/no]: ").strip().lower()
                if response in ('', 'interactive'):
                    update_preference = 'interactive'
                    break
                elif response in ('yes', 'y'):
                    update_preference = 'yes'
                    break
                elif response in ('no', 'n'):
                    update_preference = 'no'
                    break
                else:
                    print_error("Invalid choice. Please enter 'interactive', 'yes', or 'no'.")
        
        # Save the preference
        self.ca_settings["repo_update_preference"] = update_preference
        self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
        print_success(f"Saved repository update preference: {update_preference}")
        
        return update_preference
    
    def _get_env_action_preference(self, force_prompt=False) -> str:
        """Get the user's preference for environment action (clean, reuse, upgrade).
        
        Args:
            force_prompt: If True, prompt for preference even if already configured.
                         If False, use existing preference without prompting.
                         
        Returns:
            str: The environment action preference ('clean', 'reuse', or 'upgrade')
        """
        # In CI mode, always use 'clean' without prompting
        if hasattr(self, '_ci_mode') and self._ci_mode:
            print_info("Running in CI mode, using 'clean' environment action preference.")
            return 'clean'
            
        # Check if environment action preference is already configured
        env_preference = self.ca_settings.get("env_action_preference")
        
        if env_preference and not force_prompt:
            print_info(f"Using existing environment action preference: {env_preference}")
            return env_preference
            
        # Prompt for preference
        print_header("Environment Setup")
        print("How would you like to handle the virtual environment?")
        print("  reuse  - Use the existing environment if it exists")
        print("  clean  - Remove and recreate the environment")
        print("  upgrade - Keep the environment but upgrade all packages")
        
        while True:
            response = input("Environment action preference [reuse/clean/upgrade]: ").strip().lower()
            if response in ('reuse', ''):
                env_preference = 'reuse'
                break
            elif response in ('clean'):
                env_preference = 'clean'
                break
            elif response in ('upgrade'):
                env_preference = 'upgrade'
                break
            else:
                print_error("Invalid choice. Please enter 'reuse', 'clean', or 'upgrade'.")
        
        # Save the preference
        self.ca_settings["env_action_preference"] = env_preference
        self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
        print_success(f"Saved environment action preference: {env_preference}")
        
        return env_preference
        
    def _setup_pip(self):
        # Get environment action preference
        env_preference = self._get_env_action_preference()
        
        # Check for virtual environment path integrity issues
        if not self._check_venv_path_integrity():
            if not self._handle_corrupted_venv():
                sys.exit(1)

        print(f"🐍 Setting up Python virtual environment at {VENV}...")
        try:
            # Handle environment based on preference
            if env_preference == 'clean' and Path(VENV).exists():
                print(f"🗑️  Removing existing virtual environment at {VENV}...")
                if _remove_directory(VENV):
                    print_success(f"Removed {VENV}")
                subprocess.run(["python3", "-m", "venv", VENV], check=True)
                self._store_python_interpreter_path()
            elif not Path(VENV).exists():
                subprocess.run(["python3", "-m", "venv", VENV], check=True)
                # After creating the venv, detect and store the actual Python path
                self._store_python_interpreter_path()
            else:
                print_info(f"Virtual environment {VENV} already exists")
            
            # Configure package repositories before installing packages
            self._setup_repositories()
            
            # Create pip.conf with repository settings
            self._create_pip_conf()
            
            # Upgrade pip with progress indication
            self._run_pip_command_with_progress(
                ["install", "--upgrade", "pip"],
                "Upgrading pip"
            )

            self._setup_requirements()

            # Install from requirements files with progress indication
            for req_file in self.get_list_of_requirements_files():
                # Add --upgrade flag if preference is 'upgrade'
                upgrade_flag = "--upgrade" if env_preference == "upgrade" else ""
                pip_args = ["install", "-r", req_file]
                if upgrade_flag:
                    pip_args.append(upgrade_flag)
                    
                self._run_pip_command_with_progress(
                    pip_args,
                    f"Installing packages from {req_file}{' (with upgrade)' if upgrade_flag else ''}"
                )

            # Install local package in editable mode with progress indication
            self._run_pip_command_with_progress(
                ["install", "-e", "."] + (["--upgrade"] if env_preference == "upgrade" else []),
                f"Installing local package in editable mode{' (with upgrade)' if env_preference == 'upgrade' else ''}"
            )

        except subprocess.CalledProcessError as e:
            print_error(f"pip setup failed: {e}")
            sys.exit(1)

    def _setup_poetry(self):
        print("📚  Using Poetry for environment setup...")
        try:
            # 1) Detect existing installation
            if which("poetry") is not None:
                result = subprocess.run(
                    ["poetry", "--version"], capture_output=True, text=True, check=True
                )
                version = result.stdout.strip()
                self.__exit_notes.append(
                    f"✅ Poetry already installed ({version}), skipping installer."
                )
            else:
                # 2) Install Poetry
                print("⬇️ Installing Poetry…")
                subprocess.run(
                    "curl -sSL https://install.python-poetry.org | python3 -",
                    shell=True,
                    check=True,
                )

                # make it available right now
                poetry_bin = os.path.expanduser("~/.local/bin")
                os.environ["PATH"] = poetry_bin + os.pathsep + os.environ["PATH"]

                # detect shell and append to RC file
                shell = os.path.basename(os.environ.get("SHELL", ""))
                if shell in ("bash", "zsh"):
                    rc_file = os.path.expanduser(f"~/.{shell}rc")
                    export_line = (
                        "\n# >>> poetry installer >>>\n"
                        f'export PATH="{poetry_bin}:$PATH"\n'
                        "# <<< poetry installer <<<\n"
                    )
                    self.__exit_notes.append(
                        f"✍️  Appending Poetry to PATH in {rc_file}"
                    )
                    with open(rc_file, "a") as f:
                        f.write(export_line)
                    self.__exit_notes.append(f"👌  Added to {rc_file}.")
                    # 3) Add reload hint
                    self.__exit_notes.append(
                        f"🔄 To apply changes now, run:\n    source {rc_file}\n"
                        "  or: exec $SHELL -l"
                    )
                else:
                    self.__exit_notes.append("⚠️  Couldn't detect bash/zsh shell.")
                    self.__exit_notes.append(
                        f'Please add to your shell profile manually:\n    export PATH="{poetry_bin}:$PATH"'
                    )
                    self.__exit_notes.append(
                        "🔄 Then reload your shell (e.g. exec $SHELL -l)."
                    )

            # 4) Verify Poetry now exists
            print("🔎  Verifying Poetry installation…")
            result = subprocess.run(
                ["poetry", "--version"], capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"❌ Poetry installation failed:\n{result.stderr.strip()}")
                sys.exit(1)
            print(f"✅ {result.stdout.strip()}")

            # 5) Install project deps
            print("🔧 Creating virtual environment with Poetry...")
            subprocess.run(["poetry", "install"], check=True)

        except subprocess.CalledProcessError as e:
            print(f"❌ Poetry setup failed: {e}")
            sys.exit(1)

    def get_list_of_requirements_files(self) -> List[str]:
        return [
            f
            for f in os.listdir(Path(__file__).parent)
            if f.startswith("requirements") and f.endswith(".txt")
        ]

    def print_env_info(self):
        print_header("Python Environment Info")
        print(f"📦 Python Version     : {platform.python_version()}")
        print(f"🐍 Python Executable  : {sys.executable}")
        print(f"📂 sys.prefix         : {sys.prefix}")
        print(f"📂 Base Prefix        : {getattr(sys, 'base_prefix', sys.prefix)}")
        site_packages = (
            site.getsitepackages()[0] if hasattr(site, "getsitepackages") else "N/A"
        )
        print(f"🧠 site-packages path : {site_packages}")
        in_venv = self.is_virtual_environment()
        print(f"✅ In Virtual Env     : {'Yes' if in_venv else 'No'}")
        if in_venv:
            print(f"📁 Virtual Env Name   : {Path(sys.prefix).name}")
        package_manager = self._detect_project_tool()
        print(f"🎁 Package Manager    : {package_manager}")

        for note in self.__exit_notes:
            print(note)

    def is_virtual_environment(self):
        return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def fetch_url_with_retry(url, max_retries=3, retry_delay=2):
    """Fetch URL content with retry logic."""
    import urllib.request
    import socket
    import time
    
    # Add cache-busting query parameter with current timestamp to avoid caching issues
    cache_buster = int(time.time())
    url_with_cache_buster = f"{url}?_cb={cache_buster}"
    
    for attempt in range(max_retries):
        try:
            # Create a request with headers that prevent caching
            request = urllib.request.Request(
                url_with_cache_buster,
                headers={
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.read()
        except (urllib.error.URLError, socket.timeout) as e:
            if attempt < max_retries - 1:
                print_warning(f"Network error: {e}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                raise Exception(f"Failed to fetch {url} after {max_retries} attempts: {e}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Python project setup tool")
    parser.add_argument("--force-update-sh", action="store_true", help="Force update pysetup.sh regardless of content comparison")
    parser.add_argument("--ci", action="store_true", help="Run in CI mode (non-interactive)")
    
    args = parser.parse_args()
    
    ps = ProjectSetup()
    ps.setup(force_update_sh=args.force_update_sh, ci_mode=args.ci)


if __name__ == "__main__":
    main()