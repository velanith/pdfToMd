"""Single-PDF conversion via the mineru CLI."""

import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Options

# mineru's pipeline runs on the GPU; the CPU BLAS thread pools are useless
# overhead and, worse, explode the per-container RLIMIT_NPROC when several
# workers spawn task servers in parallel (vast.ai, Docker, etc).
_THREAD_CAPS = {
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS":      "1",
    "MKL_NUM_THREADS":      "1",
    "NUMEXPR_NUM_THREADS":  "1",
}


@dataclass
class ConversionResult:
    file: str
    success: bool
    duration: float
    md_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def convert_one(pdf: Path, opts: Options, mineru_bin: str) -> ConversionResult:
    """Invoke `mineru` on a single PDF and parse the outcome."""
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


_JSON_ERROR_RE = re.compile(r'\{[^{}]*"task_id"[^{}]*\}')


def _extract_error(raw: str) -> str:
    """Pull the meaningful error out of mineru's verbose CLI output.

    mineru wraps real failures inside a task-status JSON blob; the useful
    field is `error`. Fall back to the tail of stderr when no JSON is found.
    """
    for match in _JSON_ERROR_RE.findall(raw):
        try:
            payload = json.loads(match)
        except json.JSONDecodeError:
            continue
        msg = payload.get("error")
        if msg:
            return f"{msg}  (task {payload.get('task_id', '?')[:8]})"
    return raw[-400:]
