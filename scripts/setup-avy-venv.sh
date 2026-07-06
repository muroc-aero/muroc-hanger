#!/bin/bash
# Create the isolated Aviary venv (.venv-avy at the repo root).
#
# Aviary >=1.0.1 requires openmdao>=3.43 (numpy>=2), while the openconcept
# pin caps numpy<2, so Aviary cannot live in the main workspace venv/lock.
# This venv holds only hangar-sdk + hangar-avy + aviary (editable from the
# pinned upstream/Aviary clone) and is what avy-server, avy-cli, and the
# avy test/parity suites run in:
#
#   .venv-avy/bin/avy-server
#   .venv-avy/bin/python -m pytest packages/avy/tests packages/avy/examples/single_aisle_sizing/tests
#
# The hangar-avy Docker image installs the same trio, so the container needs
# no special casing. Re-run this script after bumping AVY_REF.

set -e
cd "$(dirname "$0")/.."

if [ ! -f upstream/Aviary/pyproject.toml ]; then
    echo "upstream/Aviary missing; running scripts/setup-upstream.sh --required..."
    bash scripts/setup-upstream.sh --required
fi

echo "Creating .venv-avy..."
uv venv .venv-avy --python 3.11

echo "Installing hangar-sdk + hangar-avy + aviary (editable)..."
VIRTUAL_ENV="$PWD/.venv-avy" uv pip install \
    -e "packages/sdk[all]" \
    -e packages/avy \
    -e upstream/Aviary \
    pytest pytest-asyncio

echo "Done. Aviary runtime: .venv-avy/bin/python"
