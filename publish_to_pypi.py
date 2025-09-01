#!/usr/bin/env python3
"""
PyPI Publishing Script

This script builds and publishes the package to PyPI or TestPyPI.
It prompts for the target repository and handles the build and upload process.
"""
import os
import shutil
import subprocess
import sys
import hashlib
import urllib.request
import time
import socket
from pathlib import Path


def print_colored(message, color_code):
    """Print colored text to the console."""
    print(f"\033[{color_code}m{message}\033[0m")


def print_success(message):
    """Print success message in green."""
    print_colored(f"✅ {message}", "92")


def print_error(message):
    """Print error message in red."""
    print_colored(f"❌ {message}", "91")


def print_info(message):
    """Print info message in blue."""
    print_colored(f"ℹ️ {message}", "94")


def print_warning(message):
    """Print warning message in yellow."""
    print_colored(f"⚠️ {message}", "93")


def print_header(message):
    """Print header message."""
    print("\n" + "=" * 60)
    print_colored(f"  {message}", "96")
    print("=" * 60)


def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import build
        import twine
        return True
    except ImportError as e:
        print_error(f"Missing required dependency: {e.name}")
        print_info("Installing required dependencies...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "build", "twine"], check=True)
            return True
        except subprocess.CalledProcessError:
            print_error("Failed to install dependencies. Please install them manually:")
            print("pip install build twine")
            return False


def clean_dist_directory():
    """Clean the dist directory."""
    dist_dir = Path("dist")
    if dist_dir.exists():
        print_info("Cleaning dist directory...")
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(exist_ok=True)


def update_version_file():
    """Create or update version file based on pyproject.toml version."""
    _, version = get_package_info()
    if not version:
        print_warning("Could not find version in pyproject.toml. Skipping version file update.")
        return False
    
    print_header("Updating Version File")
    
    # Determine package structure
    pkg_name = get_package_name()
    if not pkg_name:
        print_warning("Could not determine package name. Skipping version file update.")
        return False
    
    # Define file paths to check in priority order
    version_file_paths = [
        Path("version.py"),  # Standalone version.py has highest priority if it exists
        Path(f"{pkg_name}/version.py"),
        Path(f"src/{pkg_name}/version.py"),
        Path(f"{pkg_name.replace('-', '_')}/version.py"),
        Path(f"src/{pkg_name.replace('-', '_')}/version.py"),
        Path(f"{pkg_name}/__init__.py"),  # Then check __init__.py files
        Path(f"src/{pkg_name}/__init__.py"),
        Path(f"{pkg_name.replace('-', '_')}/__init__.py"),
        Path(f"src/{pkg_name.replace('-', '_')}/__init__.py"),
        Path("VERSION"),  # Simple VERSION file has lowest priority
    ]
    
    # First pass: find existing version files with version info
    existing_file = None
    for file_path in version_file_paths:
        if file_path.exists():
            # Check if file contains version info
            with open(file_path, "r") as f:
                content = f.read()
                if "__version__" in content or "VERSION" in content:
                    existing_file = file_path
                    print_info(f"Found existing version file: {file_path}")
                    break
    
    # Second pass: if no version info found, use any existing file that matches our patterns
    if not existing_file:
        for file_path in version_file_paths:
            if file_path.exists():
                existing_file = file_path
                print_info(f"Found existing file to add version info: {file_path}")
                break
    
    if existing_file:
        # Update existing version file
        with open(existing_file, "r") as f:
            content = f.read()
        
        if existing_file.name == "VERSION":
            # Simple VERSION file
            new_content = version
            with open(existing_file, "w") as f:
                f.write(new_content)
        else:
            # Python file with __version__
            if "__version__" in content:
                # Replace existing __version__ line
                pattern = r"__version__\s*=\s*['\"]([^'\"]*)['\"]" 
                new_content = re.sub(pattern, f"__version__ = \"{version}\"", content)
                with open(existing_file, "w") as f:
                    f.write(new_content)
            else:
                # Append __version__ to the file
                with open(existing_file, "a") as f:
                    f.write(f"\n__version__ = \"{version}\"\n")
        
        print_success(f"Updated version to {version} in {existing_file}")
    else:
        # Create new version file
        # First check if any package directories exist
        pkg_dirs = [
            Path(pkg_name),
            Path(f"src/{pkg_name}"),
            Path(pkg_name.replace("-", "_")),
            Path(f"src/{pkg_name.replace('-', '_')}"),
        ]
        
        target_file = None
        
        # Check if any package directory exists
        pkg_dir_exists = False
        for pkg_dir in pkg_dirs:
            if pkg_dir.is_dir():
                pkg_dir_exists = True
                break
        
        # If package directory exists, create version.py there
        if pkg_dir_exists:
            for pkg_dir in pkg_dirs:
                if pkg_dir.is_dir():
                    # First check if version.py already exists
                    version_file = pkg_dir / "version.py"
                    if not version_file.exists():
                        with open(version_file, "w") as f:
                            f.write(f'''"""Version information for {pkg_name}."""

__version__ = "{version}"
''')
                        target_file = version_file
                        break
                    
                    # If version.py exists but __init__.py doesn't, create __init__.py
                    init_file = pkg_dir / "__init__.py"
                    if not init_file.exists():
                        with open(init_file, "w") as f:
                            f.write(f'''"""Package {pkg_name}."""

from .version import __version__
''')
                    elif not "__version__" in open(init_file).read():
                        # Add import if __init__.py exists but doesn't have version
                        with open(init_file, "a") as f:
                            f.write(f"\nfrom .version import __version__\n")
        
        # If no target file yet, check for existing __init__.py files
        if not target_file:
            for pkg_dir in pkg_dirs:
                if pkg_dir.is_dir():
                    init_file = pkg_dir / "__init__.py"
                    if init_file.exists():
                        # Append to existing __init__.py
                        with open(init_file, "a") as f:
                            f.write(f"\n__version__ = \"{version}\"\n")
                        target_file = init_file
                        break
                    else:
                        # Create new __init__.py
                        with open(init_file, "w") as f:
                            f.write(f'''"""Package {pkg_name}."""

__version__ = "{version}"
''')
                        target_file = init_file
                        break
        
        # If still no target file, create standalone version.py in root
        if not target_file:
            version_py = Path("version.py")
            with open(version_py, "w") as f:
                f.write(f'''"""Version information."""

__version__ = "{version}"
''')
            target_file = version_py
        
        print_success(f"Created version file at {target_file} with version {version}")
    
    return True

# Make sure re module is imported
import re

def build_package():
    """Build the package."""
    print_header("Building Package")
    
    # Update version file before building
    update_version_file()
    
    try:
        # Run the build command and capture output
        result = subprocess.run(
            [sys.executable, "-m", "build"],
            check=True,
            capture_output=True,
            text=True
        )
        print_success("Package built successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print_error("Failed to build package.")
        
        # Check for AWS CodeArtifact credential errors
        output = e.stdout + e.stderr if e.stdout and e.stderr else ""
        if "401 Error" in output and "codeartifact" in output.lower():
            print_warning("\nAWS CodeArtifact credential issue detected!")
            print_info("This error occurs when your AWS CodeArtifact credentials have expired or are invalid.")
            print_info("The global pip configuration is trying to use AWS CodeArtifact instead of PyPI.")
            
            # Check for common pip config locations
            pip_configs = [
                Path.home() / ".config/pip/pip.conf",  # Linux/macOS
                Path.home() / "pip/pip.ini",          # Windows
                Path.home() / ".pip/pip.conf"         # Alternative location
            ]
            
            found_configs = []
            for config in pip_configs:
                if config.exists():
                    found_configs.append(config)
                    with open(config, "r") as f:
                        content = f.read()
                        if "codeartifact" in content.lower():
                            print_info(f"\nFound AWS CodeArtifact configuration in: {config}")
                            print_info("Content preview:")
                            print("---")
                            print(content[:500] + ("..." if len(content) > 500 else ""))
                            print("---")
            
            if found_configs:
                fix_config = input("\nWould you like to temporarily rename these pip config files for this build? (y/N): ").strip().lower()
                if fix_config == 'y':
                    for config in found_configs:
                        backup = config.with_suffix(config.suffix + ".bak")
                        try:
                            config.rename(backup)
                            print_success(f"Renamed {config} to {backup}")
                        except Exception as rename_err:
                            print_error(f"Failed to rename {config}: {rename_err}")
                    
                    print_info("\nLet's try building again with the config files renamed...")
                    try:
                        # Try building again
                        subprocess.run([sys.executable, "-m", "build"], check=True)
                        print_success("Package built successfully on second attempt!")
                        
                        # Ask if user wants to restore the config files
                        restore = input("\nWould you like to restore the original pip config files? (Y/n): ").strip().lower()
                        if restore != 'n':
                            for config in found_configs:
                                backup = config.with_suffix(config.suffix + ".bak")
                                if backup.exists():
                                    try:
                                        backup.rename(config)
                                        print_success(f"Restored {backup} to {config}")
                                    except Exception as restore_err:
                                        print_error(f"Failed to restore {backup}: {restore_err}")
                        
                        return True
                    except subprocess.CalledProcessError:
                        print_error("Failed to build package on second attempt.")
                        
                        # Restore config files if the second attempt failed
                        print_info("Restoring original pip config files...")
                        for config in found_configs:
                            backup = config.with_suffix(config.suffix + ".bak")
                            if backup.exists():
                                try:
                                    backup.rename(config)
                                    print_info(f"Restored {backup} to {config}")
                                except Exception as restore_err:
                                    print_error(f"Failed to restore {backup}: {restore_err}")
            else:
                print_info("\nNo global pip config files with AWS CodeArtifact settings were found.")
                print_info("You might want to check for environment variables like AWS_PROFILE or custom pip configurations.")
                
            print_info("\nAlternative solutions:")
            print_info("1. Create a local virtual environment with 'python -m venv .venv' and activate it")
            print_info("2. Use '--no-build-isolation' flag with pip if you're installing locally")
            print_info("3. Temporarily set PIP_INDEX_URL environment variable: export PIP_INDEX_URL=https://pypi.org/simple/")
            
            # Offer to create a local pip.conf file
            create_local = input("\nWould you like to create a local pip.conf file that points to PyPI? (y/N): ").strip().lower()
            if create_local == 'y':
                try:
                    # Create pip directory if it doesn't exist
                    pip_dir = Path(".pip")
                    pip_dir.mkdir(exist_ok=True)
                    
                    # Create local pip.conf file
                    pip_conf = pip_dir / "pip.conf"
                    with open(pip_conf, "w") as f:
                        f.write("""[global]
index-url = https://pypi.org/simple/
trusted-host = pypi.org
""")
                    
                    print_success(f"Created local pip.conf file at {pip_conf.absolute()}")
                    print_info("This configuration will take precedence over global settings when running pip in this directory.")
                    
                    # Add to .gitignore
                    gitignore_path = Path(".gitignore")
                    if gitignore_path.exists():
                        with open(gitignore_path, "r") as f:
                            gitignore_content = f.read()
                        
                        if ".pip/" not in gitignore_content:
                            with open(gitignore_path, "a") as f:
                                if not gitignore_content.endswith("\n"):
                                    f.write("\n")
                                f.write(".pip/\n")
                            print_info("Added .pip/ to .gitignore")
                    else:
                        with open(gitignore_path, "w") as f:
                            f.write(".pip/\n")
                        print_info("Created .gitignore with .pip/ entry")
                    
                    # Try building again with local pip.conf
                    print_info("\nLet's try building again with the local pip.conf...")
                    try:
                        # Set environment variable to ensure pip uses the local config
                        env = os.environ.copy()
                        env["PIP_CONFIG_FILE"] = str(pip_conf.absolute())
                        
                        # Try building again
                        subprocess.run([sys.executable, "-m", "build"], check=True, env=env)
                        print_success("Package built successfully with local pip.conf!")
                        return True
                    except subprocess.CalledProcessError:
                        print_error("Failed to build package even with local pip.conf.")
                except Exception as e:
                    print_error(f"Failed to create local pip.conf: {e}")

        
        return False


def create_local_pypirc():
    """Create a local .pypirc file in the project directory."""
    print_header("Creating Local .pypirc File")
    
    pypirc_content = """\
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = 

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = 
"""
    
    with open(".pypirc", "w") as f:
        f.write(pypirc_content)
    
    print_info("Created .pypirc template in the project directory.")
    print_info("Please edit the file and add your API tokens for PyPI and TestPyPI.")
    print_info("You can generate tokens at https://pypi.org/manage/account/ and https://test.pypi.org/manage/account/")
    
    # Add to .gitignore if it exists
    gitignore_path = Path(".gitignore")
    if gitignore_path.exists():
        with open(gitignore_path, "r") as f:
            gitignore_content = f.read()
        
        if ".pypirc" not in gitignore_content:
            with open(gitignore_path, "a") as f:
                if not gitignore_content.endswith("\n"):
                    f.write("\n")
                f.write(".pypirc\n")
            print_info("Added .pypirc to .gitignore")
    else:
        with open(gitignore_path, "w") as f:
            f.write(".pypirc\n")
        print_info("Created .gitignore with .pypirc entry")
    
    # Try to open the file in an editor
    try:
        if sys.platform == "win32":
            os.startfile(".pypirc")
        elif sys.platform == "darwin":  # macOS
            subprocess.run(["open", ".pypirc"])
        else:  # Linux
            subprocess.run(["xdg-open", ".pypirc"])
    except:
        print_info("Please edit ./.pypirc manually to add your tokens.")
        input("Press Enter when you've edited the file...")


def upload_to_pypi(repository, config_file=None):
    """Upload the package to PyPI or TestPyPI."""
    print_header(f"Uploading to {'TestPyPI' if repository == 'testpypi' else 'PyPI'}")
    
    cmd = [sys.executable, "-m", "twine", "upload"]
    
    if repository == "testpypi":
        cmd.extend(["--repository", "testpypi"])
    
    if config_file:
        cmd.extend(["--config-file", config_file])
    
    cmd.append("dist/*")
    
    cmd_str = " ".join(cmd)
    print_info(f"Running: {cmd_str}")
    
    try:
        # Use shell=True to properly handle the glob pattern
        subprocess.run(cmd_str, shell=True, check=True)
        
        print_success("Package uploaded successfully!")
        
        if repository == "testpypi":
            package_name = get_package_name()
            print_info(f"\nTo install from TestPyPI, run:")
            print(f"pip install --index-url https://test.pypi.org/simple/ {package_name}")
        else:
            package_name = get_package_name()
            print_info(f"\nTo install from PyPI, run:")
            print(f"pip install {package_name}")
            
        return True
    except subprocess.CalledProcessError:
        print_error("Failed to upload package.")
        return False


def get_package_info():
    """Get the package name and version from pyproject.toml."""
    try:
        import toml
        with open("pyproject.toml", "r") as f:
            data = toml.load(f)
            name = data.get("project", {}).get("name", None)
            version = data.get("project", {}).get("version", None)
            return name, version
    except ImportError:
        print_error("Failed to import toml module. Installing it...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "toml"])
            # Try again after installing
            import toml
            with open("pyproject.toml", "r") as f:
                data = toml.load(f)
                name = data.get("project", {}).get("name", None)
                version = data.get("project", {}).get("version", None)
                return name, version
        except Exception as e:
            print_error(f"Failed to install toml module: {e}")
            exit(1)
    except FileNotFoundError:
        print_error("pyproject.toml not found.")
        exit(1)
    except Exception as e:
        print_error(f"Failed to read pyproject.toml: {e}")
        exit(1)

def get_package_name():
    """Get the package name from pyproject.toml."""
    name, _ = get_package_info()
    return name


def fetch_url_with_retry(url, max_retries=3, retry_delay=2):
    """Fetch URL content with retry logic."""
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


def check_for_script_updates():
    """Check if there are updates available for the scripts."""
    # Skip update check in CI mode or if disabled via environment variable
    if "--ci" in sys.argv or os.environ.get("PYPI_SKIP_UPDATE_CHECK", "").lower() in ("1", "true", "yes"):
        print_info("CI mode or PYPI_SKIP_UPDATE_CHECK detected - skipping update check")
        return
        
    print_header("Checking for Script Updates")
    
    # URLs for the scripts
    py_url = "https://raw.githubusercontent.com/geekcafe/publish-to-pypi-scripts/refs/heads/main/publish_to_pypi.py"
    sh_url = "https://raw.githubusercontent.com/geekcafe/publish-to-pypi-scripts/refs/heads/main/publish_to_pypi.sh"
    
    updates_available = False
    local_py_hash = None
    remote_py_content = None
    local_sh_hash = None
    remote_sh_content = None
    
    # Check Python script
    if Path("publish_to_pypi.py").exists():
        try:
            # Get local file hash
            with open("publish_to_pypi.py", "rb") as f:
                local_py_hash = hashlib.md5(f.read()).hexdigest()
            
            # Get remote file hash with retry logic
            remote_py_content = fetch_url_with_retry(py_url)
            remote_py_hash = hashlib.md5(remote_py_content).hexdigest()
            
            if local_py_hash != remote_py_hash:
                print_warning("A new version of publish_to_pypi.py is available.")
                updates_available = True
        except Exception as e:
            print_warning(f"Could not check for Python script updates: {e}")
    
    # Check Shell script
    sh_needs_update = False
    if Path("publish_to_pypi.sh").exists():
        try:
            # Get local file hash
            with open("publish_to_pypi.sh", "rb") as f:
                local_sh_hash = hashlib.md5(f.read()).hexdigest()
            
            # Get remote file hash with retry logic
            remote_sh_content = fetch_url_with_retry(sh_url)
            remote_sh_hash = hashlib.md5(remote_sh_content).hexdigest()
            
            if local_sh_hash != remote_sh_hash:
                print_warning("A new version of publish_to_pypi.sh is available.")
                updates_available = True
                sh_needs_update = True
        except Exception as e:
            print_warning(f"Could not check for Shell script updates: {e}")
    
    if updates_available:
        print_info("Updates are available for one or more scripts.")
        update = input("Do you want to update the scripts now? (y/n): ")
        if update.lower() == 'y':
            # Download the shell script if it exists and needs updating
            if sh_needs_update and remote_sh_content:
                print_info("Downloading latest shell script...")
                try:
                    # Download to temporary file first for atomic replacement
                    tmp_sh_file = Path("publish_to_pypi.sh.tmp")
                    with open(tmp_sh_file, "wb") as f:
                        f.write(remote_sh_content)
                    
                    # Make it executable
                    tmp_sh_file.chmod(tmp_sh_file.stat().st_mode | 0o111)  # Add executable bit
                    
                    # Move file atomically
                    tmp_sh_file.replace(Path("publish_to_pypi.sh"))
                    print_success("Successfully updated shell script.")
                except Exception as e:
                    print_error(f"Failed to update shell script: {e}")
            
            print_info("Please run the shell script again to run with the updated script.")
            print_info("Run: ./publish_to_pypi.sh")
            sys.exit(0)
        else:
            print_info("Continuing with current versions...")
    else:
        print_success("All scripts are up to date.")


def main():
    """Main function."""
    print_header("PyPI Publishing Script")
    
    # Check for script updates
    check_for_script_updates()
    
    if not check_dependencies():
        sys.exit(1)
    
    # Check for local .pypirc file
    pypirc_path = None
    local_pypirc = Path(".pypirc")
    
    if local_pypirc.exists():
        print_info("Found local .pypirc file in project directory.")
        use_local = input("Do you want to use this local .pypirc file? (Y/n): ").strip()
        if use_local.lower() != 'n':
            pypirc_path = str(local_pypirc.absolute())
            print_success(f"Using local .pypirc file: {pypirc_path}")
    else:
        print_info("No local .pypirc file found. You can create one in the project directory.")
        create_new = input("Do you want to create a local .pypirc file now? (y/n): ")
        if create_new.lower() == 'y':
            create_local_pypirc()
            pypirc_path = str(local_pypirc.absolute())
    
    # Check if user is authenticated (only if not using local .pypirc)
    if not pypirc_path:
        try:
            subprocess.run([sys.executable, "-m", "twine", "check", "--strict", "README.md"], 
                          check=True, capture_output=True)
        except subprocess.CalledProcessError:
            print_warning("You might not be authenticated with PyPI.")
            print_info("Please make sure you have a ~/.pypirc file or environment variables set.")
            print_info("For more information, visit: https://twine.readthedocs.io/en/latest/#configuration")
            
            proceed = input("Do you want to proceed anyway? (y/n): ")
            if proceed.lower() != 'y':
                sys.exit(0)
    
    # Prompt for repository
    print_info("\nWhere do you want to publish the package?")
    print("1. TestPyPI (recommended for testing)")
    print("2. PyPI (public package index)")
    
    choice = input("\nEnter your choice (1/2): ")
    
    repository = "testpypi" if choice == "1" else "pypi"
    
    if repository == "pypi":
        print_warning("\nYou are about to publish to the public PyPI repository.")
        confirm = input("Are you sure you want to proceed? (y/n): ")
        if confirm.lower() != 'y':
            print_info("Operation cancelled.")
            sys.exit(0)
    
    # Clean dist directory
    clean_dist_directory()
    
    # Build package
    if not build_package():
        sys.exit(1)
    
    # Upload to PyPI
    if not upload_to_pypi(repository, pypirc_path):
        sys.exit(1)


if __name__ == "__main__":
    main()
