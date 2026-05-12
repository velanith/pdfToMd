"""Single-PDF conversion via the mineru CLI."""

import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Options


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
    proc = subprocess.run(cmd, capture_output=True, text=True)
    duration = round(time.time() - start, 1)

    if proc.returncode == 0:
        md_files = list(pdf_out.rglob("*.md"))
        return ConversionResult(
            file=str(pdf),
            success=True,
            duration=duration,
            md_path=str(md_files[0]) if md_files else None,
        )

    err = (proc.stderr or proc.stdout).strip() or "unknown error"
    return ConversionResult(
        file=str(pdf),
        success=False,
        duration=duration,
        error=err[-600:],
    )
