#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_ROOT="${REPO_ROOT}/dist"
PROVIDER_DIST="${DIST_ROOT}/provider"
CONSUMER_DIST="${DIST_ROOT}/consumer"

if [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.venv/bin/activate"
fi

echo "Ensuring Python build tooling is available..."
python3 -m pip show build >/dev/null 2>&1 || python3 -m pip install build

echo "Preparing artifact directories..."
mkdir -p "${PROVIDER_DIST}" "${CONSUMER_DIST}"
rm -f "${PROVIDER_DIST}"/* "${CONSUMER_DIST}"/*

echo "Building provider artifacts..."
python3 -m build --sdist --wheel --outdir "${PROVIDER_DIST}" "${REPO_ROOT}/provider"

echo "Building consumer artifacts..."
python3 -m build --sdist --wheel --outdir "${CONSUMER_DIST}" "${REPO_ROOT}/consumer"

echo "Build complete."
echo "Provider artifacts:"
ls -1 "${PROVIDER_DIST}"
echo "Consumer artifacts:"
ls -1 "${CONSUMER_DIST}"

