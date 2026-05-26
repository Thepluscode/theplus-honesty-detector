#!/usr/bin/env bash
set -euo pipefail

# theplus-honesty-detector — first-time setup
# Usage: ./setup.sh

echo "=== theplus-honesty-detector setup ==="

# Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "Error: python3 is required (3.9+)."; exit 1; }

PYTHON_VERSION=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PYTHON_VERSION" -lt 9 ]; then
    echo "Error: Python 3.9 or higher is required (found 3.${PYTHON_VERSION})."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate
# shellcheck disable=SC1091
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Environment file — only needed for alpha_zoo/alpaca_to_csv.py
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
    echo "  (Only needed if you use tools/alpha_zoo/alpaca_to_csv.py — Alpaca credentials)"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Activate the environment:"
echo "  source .venv/bin/activate"
echo ""
echo "Three self-contained tools you can run immediately:"
echo ""
echo "  # Hypothesis 2 — funding-rate arb (Binance public API, no credentials)"
echo "  python tools/funding_arb_feasibility.py --symbol BTCUSDT"
echo ""
echo "  # Hypothesis 4 — PEAD pre-check (yfinance, no credentials)"
echo "  python tools/pead_precheck.py"
echo ""
echo "  # Hypothesis 5 — index reconstitution pre-check (Wikipedia + yfinance, no credentials)"
echo "  python tools/index_recon_precheck.py"
echo ""
echo "Pre-computed results for all 5 hypotheses are in reports/ and EDGE_FINDINGS.md."
echo "The full case study is at docs/products/CASE_STUDY_we_killed_our_own_bots.md."
