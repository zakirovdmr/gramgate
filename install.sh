#!/usr/bin/env bash
set -euo pipefail

# Lando installer — checks dependencies and installs everything needed

PYTHON_MIN="3.10"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }

echo ""
echo "  Lando — Telegram gateway for AI agents"
echo "  ─────────────────────────────────────────"
echo ""

# ── Detect OS ──

OS="unknown"
case "$(uname -s)" in
    Linux*)  OS="linux";;
    Darwin*) OS="mac";;
    *)       fail "Unsupported OS: $(uname -s)"; exit 1;;
esac
ok "OS: $OS ($(uname -m))"

# ── Python ──

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python 3.10+ not found"
    echo ""
    if [ "$OS" = "mac" ]; then
        echo "  Install with Homebrew:"
        echo "    brew install python@3.12"
    else
        echo "  Install with your package manager:"
        echo "    sudo apt install python3 python3-pip python3-venv  # Debian/Ubuntu"
        echo "    sudo dnf install python3 python3-pip               # Fedora"
    fi
    exit 1
fi
ok "Python: $($PYTHON --version)"

# ── pip ──

if ! $PYTHON -m pip --version &>/dev/null; then
    fail "pip not found"
    echo ""
    if [ "$OS" = "mac" ]; then
        echo "  Try: $PYTHON -m ensurepip --upgrade"
    else
        echo "  Try: sudo apt install python3-pip"
    fi
    exit 1
fi
ok "pip: $($PYTHON -m pip --version 2>/dev/null | head -1)"

# ── C compiler (needed for tgcrypto) ──

HAS_CC=false
if command -v gcc &>/dev/null || command -v cc &>/dev/null || command -v clang &>/dev/null; then
    HAS_CC=true
fi

if [ "$HAS_CC" = false ]; then
    warn "C compiler not found (needed to build tgcrypto)"
    echo ""
    if [ "$OS" = "mac" ]; then
        echo "  Installing Xcode Command Line Tools..."
        xcode-select --install 2>/dev/null || true
        echo ""
        echo "  A system dialog should appear. After installation completes, run this script again."
        exit 1
    else
        fail "Install build tools:"
        echo "    sudo apt install build-essential python3-dev  # Debian/Ubuntu"
        echo "    sudo dnf install gcc python3-devel            # Fedora"
        exit 1
    fi
fi
ok "C compiler: $(cc --version 2>/dev/null | head -1 || gcc --version 2>/dev/null | head -1)"

# ── .env ──

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        warn ".env created from .env.example — edit it with your Telegram credentials"
    else
        fail ".env.example not found. Are you in the Lando directory?"
        exit 1
    fi
else
    ok ".env exists"
fi

# ── Check Telegram credentials in .env ──

API_ID=$(grep -E '^TELEGRAM_API_ID=' .env 2>/dev/null | cut -d= -f2 | tr -d ' ')
if [ -z "$API_ID" ] || [ "$API_ID" = "" ]; then
    warn "TELEGRAM_API_ID is empty in .env"
    echo ""
    echo "  Get your credentials at: https://my.telegram.org/apps"
    echo "  Then edit .env and fill in TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_PHONE"
    echo ""
fi

# ── Install ──

echo ""
echo "Installing Lando..."
echo ""
$PYTHON -m pip install -e . 2>&1 | tail -5

echo ""
ok "Lando installed successfully!"
echo ""
echo "  Next steps:"
echo ""
if [ -z "$API_ID" ] || [ "$API_ID" = "" ]; then
    echo "  1. Get Telegram API credentials: https://my.telegram.org/apps"
    echo "  2. Edit .env with your credentials"
    echo "  3. Run: lando"
else
    echo "  Run: lando"
fi
echo ""
echo "  On first run, you'll be asked for your Telegram verification code."
echo "  After that, Lando starts automatically."
echo ""
