"""MinerU CLI subprocess engine."""

import json
import os
import re
import shutil
import subprocess
import time
from logging import Logger
from pathlib import Path
from typing import Callable

from ..config import Options
from ..converter import ConversionResult, EngineError

# mineru's pipeline backend runs on the GPU; the CPU BLAS thread pools are
# wasted work and, with multiple workers, explode the container's
# RLIMIT_NPROC / cgroup pids.max on vast.ai-like hosts. Cap them to 1.
_THREAD_CAPS = {
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS":      "1",
    "MKL_NUM_THREADS":      "1",
    "NUMEXPR_NUM_THREADS":  "1",
}

# mineru wraps real errors inside a task-status JSON blob. Pull it out.
_JSON_ERROR_RE = re.compile(r'\{[^{}]*"task_id"[^{}]*\}')


def _find_binary() -> str:
    binary = shutil.which("mineru")
    if not binary:
        raise EngineError(
            "mineru CLI not found on PATH.\n"
            "  Run:  bash setup.sh\n"
            "  Or:   pip install mineru 'transformers<5' accelerate shapely "
            "pyclipper albumentations ftfy omegaconf"
        )
    return binary


def _extract_error(raw: str) -> str:
    for match in _JSON_ERROR_RE.findall(raw):
        try:
            payload = json.loads(match)
        except json.JSONDecodeError:
            continue
        msg = payload.get("error")
        if msg:
            return f"{msg}  (task {payload.get('task_id', '?')[:8]})"
    return raw[-400:]


def build(opts: Options, log: Logger) -> Callable[[Path], ConversionResult]:
    mineru_bin = _find_binary()
    log.info(f"mineru CLI: {mineru_bin}")

    def convert(pdf: Path) -> ConversionResult:
        start = time.time()
        pdf_out = opts.output_dir / pdf.stem
        pdf_out.mkdir(parents=True, exist_ok=True)

        cmd = [
            mineru_bin,
            "-p", str(pdf),
            "-o", str(pdf_out),
            "-b", opts.backend,
            "-m", opts.method,
            "-l", opts.lang,
        ]
        env = {**os.environ, **_THREAD_CAPS}
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        duration = round(time.time() - start, 1)

        if proc.returncode == 0:
            md_files = list(pdf_out.rglob("*.md"))
            return ConversionResult(
                file=str(pdf),
                success=True,
                duration=duration,
                md_path=str(md_files[0]) if md_files else None,
            )

        raw = (proc.stderr or proc.stdout).strip() or "unknown error"
        return ConversionResult(
            file=str(pdf),
            success=False,
            duration=duration,
            error=_extract_error(raw),
        )

    return convert
