#!/usr/bin/env bash
# Shared helpers for the POSIX entry points. Sourced, never executed directly.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Git Bash on Windows uses the same .venv with a different layout.
if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
    PYTHON=".venv/Scripts/python.exe"
else
    PYTHON=""
fi

require_python() {
    if [ -z "$PYTHON" ]; then
        echo "Sanal ortam bulunamadi. Once README'deki kurulum adimlarini tamamlayin." >&2
        exit 1
    fi
}

require_web_deps() {
    if [ ! -d "web/node_modules" ]; then
        echo "Web bagimliliklari bulunamadi. Once web klasorunde npm ci calistirin." >&2
        exit 1
    fi
}

