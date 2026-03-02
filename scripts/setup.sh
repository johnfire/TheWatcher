#!/usr/bin/env bash
set -euo pipefail

echo "Setting up bdd-vision development environment..."

# ── Python version check ─────────────────────────────────────────────────────
python_version=$(python3 --version 2>&1 | awk '{print $2}')
major=$(echo "$python_version" | cut -d. -f1)
minor=$(echo "$python_version" | cut -d. -f2)

if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 12 ]; }; then
    echo "ERROR: Python 3.12+ required (found $python_version)"
    exit 1
fi
echo "✓ Python $python_version"

# ── uv ───────────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Reload PATH in case uv was just installed
    export PATH="$HOME/.cargo/bin:$PATH"
fi
echo "✓ uv $(uv --version)"

# ── System dependencies (Ubuntu / Debian) ────────────────────────────────────
if command -v apt-get &>/dev/null; then
    echo "Installing system dependencies..."
    sudo apt-get install -y \
        python3-xlib \
        scrot \
        xdotool \
        2>/dev/null || echo "  (skipped some system deps — install manually if needed)"
fi

# ── Python dependencies ───────────────────────────────────────────────────────
echo "Installing Python dependencies..."
uv pip install -e ".[dev]"
echo "✓ Python dependencies installed"

# ── .env ─────────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ Created .env from .env.example — add your API keys before running"
else
    echo "✓ .env already exists"
fi

# ── Directories ───────────────────────────────────────────────────────────────
mkdir -p ~/logs
mkdir -p data/{specs,sitemaps,sessions,screenshots,reports}
echo "✓ Runtime directories ready (data/, ~/logs/)"

echo ""
echo "Setup complete. Next steps:"
echo "  1. Add your API keys to .env"
echo "  2. bdd-vision init --url https://example.com --name my-project"
