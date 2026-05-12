#!/usr/bin/env python3
"""
med2md — Batch PDF → Markdown converter using MinerU (GPU-optimised)
Usage:
    python med2md.py -i ./papers/ -o ./output/
    python med2md.py -i ./papers/ -o ./output/ --workers 4 --failed-log failed.txt
"""

import argparse
import json
import logging
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# ── logging ───────────────────────────────────────────────────────────────────

def setup_logging(log_file: Path | None = None) -> logging.Logger:
    logger = logging.getLogger("med2md")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


# ── per-worker model warm-up ──────────────────────────────────────────────────
# Each worker process calls this once so the model is loaded into GPU memory
# before any PDFs arrive — avoids cold-start penalty per PDF.

_WORKER_MODE: str = "auto"
_WORKER_CONVERT_FN = None   # cached reference to MinerU's convert function

# Map our --mode values to mineru's -b/--backend CLI flag values.
# mineru's -m/--method is a separate concept (auto|txt|ocr) for parse strategy
# within the pipeline/hybrid backends; we always let it default to 'auto'.
_BACKEND_MAP: dict[str, str] = {
    "pipeline": "pipeline",
    "vlm":      "vlm-auto-engine",
    "auto":     "pipeline",   # pipeline is the most general/stable backend
}


def _worker_init(mode: str) -> None:
    global _WORKER_MODE, _WORKER_CONVERT_FN
    _WORKER_MODE = mode
    try:
        from mineru.api import convert_pdf_to_markdown
        _WORKER_CONVERT_FN = convert_pdf_to_markdown
    except Exception as exc:
        import warnings
        warnings.warn(f"mineru Python API unavailable ({exc}); falling back to CLI", stacklevel=1)
        _WORKER_CONVERT_FN = None


# ── single-PDF converter ──────────────────────────────────────────────────────

def _convert_one(args: tuple) -> dict:
    """Runs inside a worker process. Uses cached model when available."""
    pdf_path_str, output_dir_str = args
    pdf_path = Path(pdf_path_str)
    output_dir = Path(output_dir_str)

    start = time.time()
    pdf_out = output_dir / pdf_path.stem
    pdf_out.mkdir(parents=True, exist_ok=True)

    def _elapsed() -> float:
        return round(time.time() - start, 1)

    # ── Python API path (model already loaded in this process) ───────────────
    if _WORKER_CONVERT_FN is not None:
        try:
            md_text, _assets = _WORKER_CONVERT_FN(
                str(pdf_path),
                output_dir=str(pdf_out),
                backend=_BACKEND_MAP.get(_WORKER_MODE, "pipeline"),
            )
            md_path = pdf_out / f"{pdf_path.stem}.md"
            md_path.write_text(md_text, encoding="utf-8")
            return {"file": pdf_path_str, "success": True,
                    "md_path": str(md_path), "duration": _elapsed()}
        except Exception as exc:
            return {"file": pdf_path_str, "success": False,
                    "error": str(exc), "duration": _elapsed()}

    # ── subprocess fallback (MinerU Python API not available) ────────────────
    import shutil
    import subprocess

    mineru_bin = shutil.which("mineru") or shutil.which("magic-pdf")
    if not mineru_bin:
        return {"file": pdf_path_str, "success": False,
                "error": "mineru CLI not found on PATH and Python API unavailable",
                "duration": _elapsed()}

    backend = _BACKEND_MAP.get(_WORKER_MODE, "pipeline")
    result = subprocess.run(
        [mineru_bin,
         "-p", str(pdf_path), "-o", str(pdf_out), "-b", backend],
        capture_output=True, text=True,
    )
    dur = _elapsed()
    if result.returncode == 0:
        candidates = list(pdf_out.rglob("*.md"))
        return {"file": pdf_path_str, "success": True,
                "md_path": str(candidates[0]) if candidates else None,
                "duration": dur}
    else:
        err = (result.stderr or result.stdout).strip()[-300:]
        return {"file": pdf_path_str, "success": False,
                "error": err, "duration": dur}


# ── batch runner ──────────────────────────────────────────────────────────────

def batch_convert(
    input_path: Path,
    output_dir: Path,
    mode: str = "auto",
    workers: int = 4,
    skip_existing: bool = True,
    failed_log: Path | None = None,
    logger: logging.Logger = None,
) -> None:
    log = logger or logging.getLogger("med2md")

    pdfs = [input_path] if input_path.is_file() else sorted(input_path.rglob("*.pdf"))
    if not pdfs:
        log.error(f"No PDF files found in: {input_path}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"Found {len(pdfs)} PDF(s)  →  output: {output_dir}")
    log.info(f"Mode: {mode}  |  Workers: {workers}  |  Skip existing: {skip_existing}")

    if skip_existing:
        pending, skipped = [], 0
        for p in pdfs:
            if (output_dir / p.stem / f"{p.stem}.md").exists():
                skipped += 1
            else:
                pending.append(p)
        log.info(f"Pending: {len(pending)}  |  Skipped: {skipped}")
    else:
        pending = pdfs

    if not pending:
        log.info("Nothing to do.")
        return

    # tqdm is optional — degrades gracefully if not installed
    try:
        from tqdm import tqdm
        progress = tqdm(total=len(pending), unit="pdf", dynamic_ncols=True)
    except ImportError:
        progress = None

    results: list[dict] = []
    wall_start = time.time()
    job_args = [(str(p), str(output_dir)) for p in pending]

    if workers == 1:
        # Single-process: warm up in-process
        _worker_init(mode)
        for arg in job_args:
            r = _convert_one(arg)
            results.append(r)
            _log_result(r, log)
            if progress:
                progress.update(1)
    else:
        ctx = mp.get_context("spawn")   # spawn keeps GPU state clean across workers
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=ctx,
            initializer=_worker_init,
            initargs=(mode,),
        ) as pool:
            futures = {pool.submit(_convert_one, arg): arg for arg in job_args}
            for future in as_completed(futures):
                r = future.result()
                results.append(r)
                _log_result(r, log)
                if progress:
                    progress.update(1)

    if progress:
        progress.close()

    # ── summary ───────────────────────────────────────────────────────────────
    ok   = [r for r in results if r["success"]]
    fail = [r for r in results if not r["success"]]
    total_time = round(time.time() - wall_start, 1)
    throughput = round(len(ok) / (total_time / 60), 1) if total_time > 0 else 0

    log.info("─" * 52)
    log.info(
        f"Done  ✓ {len(ok)}  ✗ {len(fail)}  |  "
        f"{total_time}s  ({throughput} PDF/min)"
    )
    if ok:
        avg = round(sum(r["duration"] for r in ok) / len(ok), 1)
        log.info(f"Avg per PDF: {avg}s")

    if fail:
        log.warning(f"{len(fail)} file(s) failed:")
        for r in fail:
            log.warning(f"  {Path(r['file']).name}: {r.get('error','?')[:120]}")
        if failed_log:
            failed_log.write_text(
                "\n".join(r["file"] for r in fail), encoding="utf-8"
            )
            log.info(f"Failed list → {failed_log}")

    report = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "workers": workers,
        "total": len(results),
        "success": len(ok),
        "failed": len(fail),
        "total_seconds": total_time,
        "pdfs_per_minute": throughput,
        "results": results,
    }
    rp = output_dir / "conversion_report.json"
    rp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Report → {rp}")


def _log_result(r: dict, log: logging.Logger) -> None:
    name = Path(r["file"]).name
    if r["success"]:
        log.info(f"  ✓  {name}  ({r['duration']}s)")
    else:
        log.warning(f"  ✗  {name}  →  {r.get('error','?')[:100]}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="med2md",
        description="Batch convert PDF papers to Markdown using MinerU (GPU-optimised).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("-i", "--input",  required=True, type=Path,
                   help="Input PDF file OR directory (recursive).")
    p.add_argument("-o", "--output", required=True, type=Path,
                   help="Output directory. Each PDF gets its own subfolder.")
    p.add_argument("-m", "--mode", default="auto",
                   choices=["auto", "pipeline", "vlm"],
                   help=(
                       "MinerU backend:\n"
                       "  auto     — MinerU decides (default)\n"
                       "  pipeline — rule-based, fastest\n"
                       "  vlm      — vision-language model, best on complex layouts"
                   ))
    p.add_argument("-w", "--workers", type=int, default=3,
                   help=(
                       "Parallel worker processes.\n"
                       "RTX 4090 (24 GB): 3 workers for pipeline, 1–2 for vlm. (default: 3)"
                   ))
    p.add_argument("--no-skip",    action="store_true",
                   help="Re-convert even if .md output already exists.")
    p.add_argument("--failed-log", type=Path, default=None,
                   help="Write failed PDF paths to this file for easy retry.")
    p.add_argument("--log-file",   type=Path, default=None,
                   help="Also write logs to this file.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    logger = setup_logging(args.log_file)

    try:
        import mineru  # noqa: F401
    except ImportError:
        logger.error(
            "MinerU is not installed.\n"
            "Install with:  pip install mineru[full]\n"
            "Docs: https://github.com/opendatalab/MinerU"
        )
        sys.exit(1)

    batch_convert(
        input_path=args.input,
        output_dir=args.output,
        mode=args.mode,
        workers=args.workers,
        skip_existing=not args.no_skip,
        failed_log=args.failed_log,
        logger=logger,
    )


if __name__ == "__main__":
    main()
