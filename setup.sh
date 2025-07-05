#!/usr/bin/env bash
set -euo pipefail

# setup.sh - Cross-platform setup for python projects

# Default mode: ask the user
FETCH_LATEST="interactive"

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  -u, --update       Automatically pull the latest setup.py (no prompt)
  -n, --no-update    Skip pulling the latest setup.py
  --ci               CI/CD mode (same as --update)
  -h, --help         Show this help message and exit
EOF
  exit 0
}

# --- parse command-line flags ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -u|--update)      FETCH_LATEST="yes" ;;
    -n|--no-update)   FETCH_LATEST="no"  ;;
    --ci)             FETCH_LATEST="yes" ;;
    -h|--help)        usage ;;
    *)  echo "Unknown option: $1" >&2
        usage
        ;;
  esac
  shift
done

# --- interactive prompt if needed ---
if [[ "$FETCH_LATEST" == "interactive" ]]; then
  read -r -p "Pull latest setup.py from repository? [y/N] " answer
  if [[ "$answer" =~ ^[Yy] ]]; then
    FETCH_LATEST="yes"
  else
    FETCH_LATEST="no"
  fi
fi

# --- fetch if requested ---
if [[ "$FETCH_LATEST" == "yes" ]]; then
  echo "🔄 Fetching latest setup.py..."
  curl -sSL \
    https://raw.githubusercontent.com/geekcafe/py-setup-tool/main/setup.py \
    -o setup.py
fi

# --- run the Python installer ---
python3 setup.py
