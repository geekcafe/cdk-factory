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


class ProjectSetup:
    CA_CONFIG = Path("setup.json")
    
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

    def _setup_repositories(self):
        """Configure package repositories based on user input."""
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
        
        # Ask about each repository type
        self._maybe_setup_codeartifact()
        self._maybe_setup_artifactory()
        self._maybe_setup_nexus()
        self._maybe_setup_github_packages()
        self._maybe_setup_azure_artifacts()
        self._maybe_setup_google_artifact_registry()
        
        # Save the updated settings
        self.CA_CONFIG.write_text(json.dumps(self.ca_settings, indent=2))
        print_success(f"Repository configuration saved to {self.CA_CONFIG}")
        
        # Update pip.conf with the repository configuration
        self._update_pip_conf_with_repos()
        
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

    def _maybe_setup_codeartifact(self)-> bool:
        """Configure AWS CodeArtifact repository."""
        # Check if CodeArtifact is already configured
        ca_repo = self.ca_settings.get("repositories", {}).get("codeartifact", {})
        
        if ca_repo:
            print_info("AWS CodeArtifact configuration found.")
            reuse = input("Do you want to use AWS CodeArtifact? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                ca_repo["enabled"] = False
                self.ca_settings["repositories"]["codeartifact"] = ca_repo
                return False
            else:
                # Enable the repository
                ca_repo["enabled"] = True
                self.ca_settings["repositories"]["codeartifact"] = ca_repo
        else:
            # Ask if user wants to configure CodeArtifact
            ans = input("📦 Configure AWS CodeArtifact? (y/N): ").strip().lower()
            if ans != "y":
                return False
                
            # Initialize CodeArtifact repository settings
            ca_repo = {
                "type": "codeartifact",
                "enabled": True,
                "tool": input("   Tool (pip/poetry) [pip]: ").strip().lower() or "pip",
                "domain": input("   Domain name: ").strip(),
                "repository": input("   Repository name: ").strip(),
                "region": input("   AWS region [us-east-1]: ").strip() or "us-east-1",
                "profile": input("   AWS CLI profile (optional): ").strip() or None,
                "trusted": True
            }
            
            # Add to repositories
            if "repositories" not in self.ca_settings:
                self.ca_settings["repositories"] = {}
            self.ca_settings["repositories"]["codeartifact"] = ca_repo

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
            ca_repo["tool"],
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
        if ".codeartifact" in out or "codeartifact" in out:
            return self._maybe_setup_codeartifact()
        elif "artifactory" in out:
            return self._maybe_setup_artifactory()
        elif "nexus" in out:
            return self._maybe_setup_nexus()
        elif "github.com" in out or "ghcr.io" in out or "github packages" in out:
            return self._maybe_setup_github_packages()
        elif "azure" in out or "pkgs.dev.azure.com" in out:
            return self._maybe_setup_azure_artifacts()
        elif "pkg.dev" in out or "artifact registry" in out or "gcp" in out:
            return self._maybe_setup_google_artifact_registry()
        else:
            print_info("No known repository type detected in output; skipping custom login.")
            return False

    def _maybe_setup_artifactory(self) -> bool:
        """Configure JFrog Artifactory repository."""
        # Check if Artifactory is already configured
        art_repo = self.ca_settings.get("repositories", {}).get("artifactory", {})
        
        if art_repo:
            print_info("Artifactory configuration found.")
            reuse = input("Do you want to use Artifactory? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                art_repo["enabled"] = False
                self.ca_settings["repositories"]["artifactory"] = art_repo
                return False
            else:
                # Enable the repository
                art_repo["enabled"] = True
                self.ca_settings["repositories"]["artifactory"] = art_repo
        else:
            # Ask if user wants to configure Artifactory
            ans = input("📦 Configure JFrog Artifactory? (y/N): ").strip().lower()
            if ans != "y":
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

    def _maybe_setup_nexus(self) -> bool:
        """Configure Sonatype Nexus repository."""
        # Check if Nexus is already configured
        nexus_repo = self.ca_settings.get("repositories", {}).get("nexus", {})
        
        if nexus_repo:
            print_info("Nexus configuration found.")
            reuse = input("Do you want to use Nexus? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                nexus_repo["enabled"] = False
                self.ca_settings["repositories"]["nexus"] = nexus_repo
                return False
            else:
                # Enable the repository
                nexus_repo["enabled"] = True
                self.ca_settings["repositories"]["nexus"] = nexus_repo
        else:
            # Ask if user wants to configure Nexus
            ans = input("📦 Configure Sonatype Nexus? (y/N): ").strip().lower()
            if ans != "y":
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

    def _maybe_setup_github_packages(self) -> bool:
        """Configure GitHub Packages repository."""
        # Check if GitHub Packages is already configured
        gh_repo = self.ca_settings.get("repositories", {}).get("github", {})
        
        if gh_repo:
            print_info("GitHub Packages configuration found.")
            reuse = input("Do you want to use GitHub Packages? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                gh_repo["enabled"] = False
                self.ca_settings["repositories"]["github"] = gh_repo
                return False
            else:
                # Enable the repository
                gh_repo["enabled"] = True
                self.ca_settings["repositories"]["github"] = gh_repo
        else:
            # Ask if user wants to configure GitHub Packages
            ans = input("📦 Configure GitHub Packages? (y/N): ").strip().lower()
            if ans != "y":
                return False
                
            # Initialize GitHub Packages repository settings
            gh_repo = {
                "type": "github",
                "enabled": True,
                "url": input("   Repository URL (e.g. https://pypi.pkg.github.com/OWNER/index): ").strip(),
                "token": input("   Personal Access Token: ").strip(),
                "trusted": input("   Trust this host? (Y/n): ").strip().lower() != "n"
            }
            
            # Add to repositories
            if "repositories" not in self.ca_settings:
                self.ca_settings["repositories"] = {}
            self.ca_settings["repositories"]["github"] = gh_repo

        # If enabled, perform login
        if gh_repo.get("enabled", False):
            return self._login_to_github_packages(gh_repo)
        return False
        
    def _login_to_github_packages(self, gh_repo):
        """Login to GitHub Packages with the provided settings."""
        try:
            # Create or update pip.conf with credentials
            url = gh_repo["url"]
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

    def _maybe_setup_azure_artifacts(self) -> bool:
        """Configure Azure Artifacts repository."""
        # Check if Azure Artifacts is already configured
        azure_repo = self.ca_settings.get("repositories", {}).get("azure", {})
        
        if azure_repo:
            print_info("Azure Artifacts configuration found.")
            reuse = input("Do you want to use Azure Artifacts? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                azure_repo["enabled"] = False
                self.ca_settings["repositories"]["azure"] = azure_repo
                return False
            else:
                # Enable the repository
                azure_repo["enabled"] = True
                self.ca_settings["repositories"]["azure"] = azure_repo
        else:
            # Ask if user wants to configure Azure Artifacts
            ans = input("📦 Configure Azure Artifacts? (y/N): ").strip().lower()
            if ans != "y":
                return False
                
            # Initialize Azure Artifacts repository settings
            azure_repo = {
                "type": "azure",
                "enabled": True,
                "url": input("   Repository URL (e.g. https://pkgs.dev.azure.com/org/project/_packaging/feed/pypi/simple/): ").strip(),
                "username": input("   Username (usually just 'azure'): ").strip() or "azure",
                "token": input("   Personal Access Token: ").strip(),
                "trusted": input("   Trust this host? (Y/n): ").strip().lower() != "n"
            }
            
            # Add to repositories
            if "repositories" not in self.ca_settings:
                self.ca_settings["repositories"] = {}
            self.ca_settings["repositories"]["azure"] = azure_repo

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

    def _maybe_setup_google_artifact_registry(self) -> bool:
        """Configure Google Artifact Registry repository."""
        # Check if Google Artifact Registry is already configured
        gcp_repo = self.ca_settings.get("repositories", {}).get("google", {})
        
        if gcp_repo:
            print_info("Google Artifact Registry configuration found.")
            reuse = input("Do you want to use Google Artifact Registry? (Y/n): ").strip().lower() or "y"
            if reuse != "y":
                # Disable the repository but keep the settings
                gcp_repo["enabled"] = False
                self.ca_settings["repositories"]["google"] = gcp_repo
                return False
            else:
                # Enable the repository
                gcp_repo["enabled"] = True
                self.ca_settings["repositories"]["google"] = gcp_repo
        else:
            # Ask if user wants to configure Google Artifact Registry
            ans = input("📦 Configure Google Artifact Registry? (y/N): ").strip().lower()
            if ans != "y":
                return False
                
            # Initialize Google Artifact Registry repository settings
            gcp_repo = {
                "type": "google",
                "enabled": True,
                "url": input("   Repository URL (e.g. https://us-central1-python.pkg.dev/project-id/repo-name/simple/): ").strip(),
                "trusted": input("   Trust this host? (Y/n): ").strip().lower() != "n"
            }
            
            # Add to repositories
            if "repositories" not in self.ca_settings:
                self.ca_settings["repositories"] = {}
            self.ca_settings["repositories"]["google"] = gcp_repo

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

        project_tool = self._detect_project_tool()
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
            moto
        """

    def setup(self):
        self._detect_platform()
        self._create_pyproject_toml()
        (self._setup_poetry if self._use_poetry else self._setup_pip)()
        self.print_env_info()
        print("\n🎉 Setup complete!")
        if not self._use_poetry:
            print(
                f"➡️  Run 'source {VENV}/bin/activate' to activate the virtual environment."
            )

    def _check_venv_path_integrity(self) -> bool:
        """Check if the virtual environment has correct path references.
        
        Returns:
            bool: True if venv is healthy or doesn't exist, False if corrupted
        """
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
                
            # Extract the python path from shebang
            if shebang.startswith('#!'):
                python_path = shebang[2:]  # Remove #!
                
                # Get expected paths from settings
                expected_paths = self.ca_settings.get("python_paths", [])
                if not expected_paths:  # Fallback if not found in settings
                    expected_paths = [
                        str(Path.cwd() / VENV / "bin" / "python"),
                        str(Path.cwd() / VENV / "bin" / "python3")
                    ]
                
                # Check if the shebang points to the current directory structure
                if python_path not in expected_paths:
                    print_error(f"Virtual environment has incorrect path references:")
                    print(f"   Expected one of: {expected_paths}")
                    print(f"   Found:           {python_path}")
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
            try:
                import shutil
                print(f"🗑️  Removing corrupted virtual environment at {VENV}...")
                shutil.rmtree(VENV)
                print_success(f"Removed {VENV}")
                return True
            except Exception as e:
                print_error(f"Failed to remove {VENV}: {e}")
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
                        self._setup_repositories()
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

    def _store_python_interpreter_path(self):
        """Detect and store the actual Python interpreter path in the virtual environment."""
        venv_path = Path(VENV)
        python_paths = set()  # Use a set to avoid duplicates
        
        # Check for common Python interpreter names
        for python_name in ["python", "python3"]:
            python_path = venv_path / "bin" / python_name
            if python_path.exists():
                # Get the full absolute path
                abs_path = str(python_path.resolve())
                if abs_path not in python_paths:
                    python_paths.add(abs_path)
                    print_info(f"Detected Python interpreter: {abs_path}")
        
        # Also try to find the specific Python version (e.g., python3.10, python3.11)
        bin_dir = venv_path / "bin"
        if bin_dir.exists():
            for item in bin_dir.iterdir():
                if item.name.startswith("python3.") and item.is_file() and os.access(item, os.X_OK):
                    abs_path = str(item.resolve())
                    if abs_path not in python_paths:
                        python_paths.add(abs_path)
                        print_info(f"Detected versioned Python interpreter: {abs_path}")
        
        if python_paths:
            # Update settings with the detected paths (convert set back to list)
            self.ca_settings["python_paths"] = list(python_paths)
            
            # Save to setup.json
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
            
    def _setup_pip(self):
        # Check for virtual environment path integrity issues
        if not self._check_venv_path_integrity():
            if not self._handle_corrupted_venv():
                sys.exit(1)

        print(f"🐍 Setting up Python virtual environment at {VENV}...")
        try:
            # Only create venv if it doesn't exist
            if not Path(VENV).exists():
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
                self._run_pip_command_with_progress(
                    ["install", "-r", req_file, "--upgrade"],
                    f"Installing packages from {req_file}"
                )

            # Install local package in editable mode with progress indication
            self._run_pip_command_with_progress(
                ["install", "-e", "."],
                "Installing local package in editable mode"
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


def main():
    ps = ProjectSetup()
    ps.setup()


if __name__ == "__main__":
    main()
