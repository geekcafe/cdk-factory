import os
import subprocess
import sys
import site
import platform
from pathlib import Path

VENV = ".venv"
USE_POETRY = False  # set to True if you want to use poetry instead of pip

requirements_files = [
    "requirements.txt",
    "requirements.dev.txt",
    "requirements.iac.txt",
    "requirements.tests.txt",
]


def detect_platform():
    os_type = "unknown"
    arch = os.uname().machine

    sysname = os.uname().sysname
    print("🧠 Detecting OS and architecture...")

    if sysname == "Darwin":
        os_type = "mac"
    elif sysname == "Linux":
        if os.path.exists("/etc/debian_version"):
            os_type = "debian"
        else:
            os_type = "linux"
    else:
        print(f"❌ Unsupported OS: {sysname}")
        sys.exit(1)

    print(f"📟 OS: {os_type} | Architecture: {arch}")
    return os_type


def create_pyproject_toml():
    if not os.path.exists("pyproject.toml"):
        print("👉 pyproject.toml not found. Let's create one.")

        package_name = input("Package name: ")
        package_version = input("Package version (default: 0.1.0): ") or "0.1.0"
        package_description = input("Package description: ")
        author_name = input("Author name: ")
        author_email = input("Author email: ")

        if USE_POETRY:
            content = f"""
[tool.poetry]
name = "{package_name}"
version = "{package_version}"
description = "{package_description}"
authors = ["{author_name} <{author_email}>"]

[tool.poetry.dependencies]
python = "^3.12"

[tool.poetry.dev-dependencies]
pytest = "^7.0"

[build-system]
requires = ["poetry-core>=1.0.0"]
build-backend = "poetry.core.masonry.api"
"""
        else:
            build_system = input("Build system (default: hatchling): ") or "hatchling"
            content = f"""
[project]
name = "{package_name}"
version = "{package_version}"
description = "{package_description}"
authors = [{{name="{author_name}", email="{author_email}"}}]
requires-python = ">=3.12"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests/unit"]
addopts = "-m 'not integration'"
markers = [
    "integration: marks tests as integration (deselect with '-m \"not integration\"')"
]

[build-system]
requires = ["{build_system}"]
build-backend = "{build_system}.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{package_name}"]
"""
            os.makedirs(f"src/{package_name}", exist_ok=True)
            os.makedirs("tests/unit", exist_ok=True)
            os.makedirs("tests/integration", exist_ok=True)

        with open("pyproject.toml", "w") as file:
            file.write(content)

        print("✅ pyproject.toml created.")
    else:
        print("✅ pyproject.toml already exists.")


def setup_dev_requirements():
    if not os.path.exists("requirements.dev.txt"):
        print("👉 requirements.dev.txt not found. Let's create one.")
        with open("requirements.dev.txt", "w") as file:
            content = dev_requirements_content()
            file.write(content)
        print("✅ requirements.dev.txt created.")
    else:
        print("✅ requirements.dev.txt already exists.")


def dev_requirements_content():
    return """
pytest
pytest-mock
mypy
build
toml
twine
wheel
pkginfo
"""


def setup_poetry():
    create_pyproject_toml()
    print("📚  Using Poetry for environment setup...")

    if (
        subprocess.call(
            ["which", "poetry"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        != 0
    ):
        print("⬇️ Installing Poetry...")
        subprocess.run(
            "curl -sSL https://install.python-poetry.org | python3 -",
            shell=True,
            check=True,
        )
        os.environ["PATH"] = (
            f"{os.path.expanduser('~')}/.local/bin:" + os.environ["PATH"]
        )

    print("🔧 Creating virtual environment with Poetry...")
    subprocess.run(["poetry", "install"], check=True)


def setup_pip():
    create_pyproject_toml()
    print(f"🐍 Setting up Python virtual environment at {VENV}...")
    subprocess.run(["python3", "-m", "venv", VENV], check=True)

    # create a pip.conf file in the virtual environment
    if not os.path.exists(os.path.join(VENV, "pip.conf")):
        print("👉 pip.conf not found. Let's create one.")
        with open(os.path.join(VENV, "pip.conf"), "w") as f:
            f.write("[global]\n")

    venv_activate = os.path.join(VENV, "bin", "activate_this.py")
    if os.path.exists(venv_activate):
        with open(venv_activate) as f:
            exec(f.read(), {"__file__": venv_activate})

    print("⬆️ Upgrading pip...")
    subprocess.run([f"{VENV}/bin/pip", "install", "--upgrade", "pip"], check=True)

    for req_file in requirements_files:
        if os.path.exists(req_file):
            print(f"🔗 Installing packages from {req_file}...")
            subprocess.run(
                [f"{VENV}/bin/pip", "install", "-r", req_file, "--upgrade"], check=True
            )
        else:
            print(f"👉 {req_file} not found. Skipping.")

    print("🔗 Installing local package in editable mode...")
    subprocess.run([f"{VENV}/bin/pip", "install", "-e", "."], check=True)


def print_env_info():
    print("🔎 Python Environment Info")
    print("=" * 30)

    print(f"📦 Python Version     : {platform.python_version()}")
    print(f"🐍 Python Executable  : {sys.executable}")
    print(f"📂 sys.prefix         : {sys.prefix}")
    print(f"📂 Base Prefix        : {getattr(sys, 'base_prefix', sys.prefix)}")
    print(
        f"🧠 site-packages path : {site.getsitepackages()[0] if hasattr(site, 'getsitepackages') else 'N/A'}"
    )

    in_venv = is_virtual_environment()
    print(f"✅ In Virtual Env     : {'Yes' if in_venv else 'No'}")

    if in_venv:
        venv_name = Path(sys.prefix).name
        print(f"📁 Virtual Env Name   : {venv_name}")


def is_virtual_environment():
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def main():
    os_type = detect_platform()
    setup_dev_requirements()
    if USE_POETRY:
        setup_poetry()
    else:
        setup_pip()

    print("\n\n")
    print_env_info()

    print("\n\n🎉 Setup complete!")
    if not USE_POETRY:
        print(
            f"➡️  Run 'source {VENV}/bin/activate' to activate the virtual environment."
        )


if __name__ == "__main__":
    main()
