#!/usr/bin/env bash
# ================================================================
#  setup.sh — One-time setup for Security News Intelligence System
# ================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
CONFIG_FILE="$SCRIPT_DIR/config.yaml"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🔐  Security News Intelligence System — Setup          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Python check ───────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "❌ python3 not found. Please install Python 3.10+."
    exit 1
fi

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓ Python $PYTHON_VER found"

# ── Virtual environment ────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "✓ Virtual environment created at .venv/"
else
    echo "✓ Virtual environment already exists"
fi

source "$VENV_DIR/bin/activate"

echo "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"
echo "✓ Dependencies installed"

# ── Ollama check ───────────────────────────────────────────────
echo ""
echo "Checking Ollama connection..."
if curl -s --connect-timeout 3 http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✓ Ollama is running at http://localhost:11434"
    echo "  Available models:"
    curl -s http://localhost:11434/api/tags | python3 -c "
import json,sys
data=json.load(sys.stdin)
for m in data.get('models',[]):
    print(f'    • {m[\"name\"]}')
" 2>/dev/null || true
else
    echo "⚠  Ollama not reachable at http://localhost:11434"
    echo "   Make sure Ollama is running before running the pipeline."
fi

# ── Directories ────────────────────────────────────────────────
mkdir -p "$SCRIPT_DIR/output"
mkdir -p "$SCRIPT_DIR/memory"
touch "$SCRIPT_DIR/memory/.gitkeep"
touch "$SCRIPT_DIR/output/.gitkeep"
echo "✓ Output directories created"

# ── GitHub Pages repo ─────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo "  GitHub Pages Repository Setup"
echo "══════════════════════════════════════════════════════════"
echo ""
echo "Your digest will be published to: https://github.com/maksokami/DailyOwned"
echo ""
echo "Options:"
echo "  1) Clone it now (requires SSH key configured for GitHub)"
echo "  2) Skip for now (configure path in config.yaml later)"
echo ""
read -rp "Choice [1/2]: " PAGES_CHOICE

PAGES_DIR="/home/onosan/Documents/Scripts/DailyOwned"

if [ "$PAGES_CHOICE" = "1" ]; then
    if [ -d "$PAGES_DIR/.git" ]; then
        echo "✓ Repo already cloned at $PAGES_DIR"
    else
        echo "Cloning DailyOwned repo via SSH..."
        git clone git@github.com:maksokami/DailyOwned.git "$PAGES_DIR" || {
            echo "❌ Clone failed. Check that your SSH key is added to GitHub."
            echo "   Run: ssh -T git@github.com"
            echo "   Then re-run this setup or clone manually."
        }
    fi

    if [ -d "$PAGES_DIR" ]; then
        echo "Clearing existing repo content..."
        find "$PAGES_DIR" -maxdepth 1 ! -name '.git' ! -path "$PAGES_DIR" -exec rm -rf {} + 2>/dev/null || true

        # Add a placeholder index.html until the first pipeline run
        mkdir -p "$PAGES_DIR/docs"
        cat > "$PAGES_DIR/docs/index.html" << 'PLACEHOLDER'
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Security Digest — Coming Soon</title>
<style>body{font-family:monospace;background:#0a0e14;color:#22c55e;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}</style>
</head><body><div><h1>⬡ Security Intelligence Digest</h1><p>First digest will be generated on the next scheduled run.</p></div></body></html>
PLACEHOLDER

        cd "$PAGES_DIR"
        git add .
        git commit -m "setup: initialize clean GitHub Pages site" 2>/dev/null || true
        git push origin main 2>/dev/null || true
        cd "$SCRIPT_DIR"
        echo "✓ DailyOwned repo cleared and placeholder pushed"
    fi
else
    echo "  Skipping. Edit 'paths.github_pages_repo' in config.yaml when ready."
fi

# ── Liked articles onboarding ──────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo "  Preference Profile Setup"
echo "══════════════════════════════════════════════════════════"
echo ""

LIKED_FILE="$SCRIPT_DIR/liked_articles.txt"
LIKED_COUNT=$(grep -v '^#' "$LIKED_FILE" | grep -v '^$' | wc -l)

if [ "$LIKED_COUNT" -lt 3 ]; then
    echo "Your liked_articles.txt has only $LIKED_COUNT non-comment entries."
    echo "Run the interactive wizard to seed your preferences:"
    echo ""
    echo "  source .venv/bin/activate"
    echo "  python src/feedback.py --onboard"
    echo ""
else
    echo "✓ liked_articles.txt has $LIKED_COUNT entries — profile looks good!"
fi

# ── Final instructions ─────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅  Setup Complete!                                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo ""
echo "  1. Seed your preferences (if not done):"
echo "     source .venv/bin/activate"
echo "     python src/feedback.py --onboard"
echo ""
echo "  2. Test the pipeline (dry run — no git push):"
echo "     source .venv/bin/activate"
echo "     python src/pipeline.py --dry-run"
echo ""
echo "     Then open output/index.html in your browser."
echo ""
echo "  3. Run with publishing enabled:"
echo "     python src/pipeline.py"
echo ""
echo "  4. Start the daily scheduler (7 AM CST by default):"
echo "     python src/scheduler.py"
echo ""
echo "  5. Teach the system as you go:"
echo "     python src/feedback.py --like 'article title or URL'"
echo "     python src/feedback.py --dislike 'not relevant topic'"
echo ""
echo "  Edit config.yaml to change schedule, feeds, and thresholds."
echo ""
