#!/usr/bin/env bash
# Sets up the med2md environment from scratch.
#
# Usage:
#   bash setup.sh                # creates .venv in current dir
#   bash setup.sh /venv/main     # uses (or creates) custom venv path
#   CUDA=cu121 bash setup.sh     # override CUDA wheel index (default cu124)
#   CUDA=cpu   bash setup.sh     # CPU-only install
set -euo pipefail

VENV="${1:-.venv}"
CUDA="${CUDA:-cu124}"

echo "==> Setup"
echo "    venv: $VENV"
echo "    CUDA: $CUDA"

# ── create or reuse venv ──────────────────────────────────────────────────────
if [ -f "$VENV/bin/activate" ]; then
    echo "==> Reusing existing venv"
else
    echo "==> Creating venv"
    python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# ── pip baseline ──────────────────────────────────────────────────────────────
echo "==> Upgrading pip / wheel"
pip install -q --upgrade pip wheel setuptools

# ── PyTorch ───────────────────────────────────────────────────────────────────
echo "==> Installing PyTorch ($CUDA)"
if [ "$CUDA" = "cpu" ]; then
    pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
else
    pip install -q torch torchvision --index-url "https://download.pytorch.org/whl/$CUDA"
fi

# ── MinerU + ML stack ─────────────────────────────────────────────────────────
# transformers/accelerate installed explicitly because mineru's spawned
# api-service has historically failed to resolve them through extras alone.
echo "==> Installing MinerU + ML stack"
pip install -q "mineru[full]" transformers accelerate tqdm

# ── verify ────────────────────────────────────────────────────────────────────
echo "==> Verifying"
python - <<'PY'
import shutil, sys

def _line(label, value):
    print(f"    {label:<14} {value}")

import torch
_line("python",       sys.version.split()[0])
_line("torch",        torch.__version__)
_line("CUDA",         torch.cuda.get_device_name(0) if torch.cuda.is_available() else "unavailable")

import mineru
_line("mineru",       getattr(mineru, "__version__", "?"))

import transformers
_line("transformers", transformers.__version__)

_line("mineru CLI",   shutil.which("mineru") or "NOT FOUND")

import med2md
_line("med2md pkg",   f"v{med2md.__version__}")
PY

echo ""
echo "Setup complete."
echo ""
echo "Next:"
echo "  source $VENV/bin/activate"
echo "  python -m med2md -i ./papers/ -o ./output/"
