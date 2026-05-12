#!/usr/bin/env python3
"""
med2md — Batch PDF → Markdown converter using MinerU CLI.

Usage:
    python med2md.py -i ./papers/ -o ./output/
    python med2md.py -i paper.pdf -o ./output/
    python med2md.py -i ./papers/ -o ./output/ -j 3 -b pipeline
"""

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


def setup_logging(log_file: Path | None) -> logging.Logger:
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


def find_mineru() -> str:
    """Locate the mineru CLI binary in the active environment."""
    binary = shutil.which("mineru")
    if binary:
        return binary
    sys.stderr.write(
        "ERROR: mineru CLI not found on PATH.\n"
        "Run:   bash setup.sh\n"
        "Or:    pip install 'mineru[full]' transformers accelerate\n"
    )
    sys.exit(1)


def find_pdfs(input_path: Path) -> list[Path]:
    """Resolve --input into a list of PDF files.

    Accepts: a single .pdf file, a directory (recursive), or a text file
    listing one PDF path per line (e.g. failed.txt from a previous run).
    """
    if input_path.is_file():
        if input_path.suffix.lower() == ".pdf":
            return [input_path]
        # Treat as a list-of-paths file
        paths = []
        for line in input_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                paths.append(Path(line))
        return paths
    return sorted(input_path.rglob("*.pdf"))


def filter_pending(pdfs: list[Path], output_dir: Path) -> tuple[list[Path], int]:
    pending, skipped = [], 0
    for p in pdfs:
        if (output_dir / p.stem / f"{p.stem}.md").exists():
            skipped += 1
        else:
            pending.append(p)
    return pending, skipped


def convert_one(
    pdf: Path,
    output_dir: Path,
    mineru_bin: str,
    backend: str,
    method: str,
    lang: str,
) -> dict:
    """Run mineru CLI on a single PDF."""
    start = time.time()
    pdf_out = output_dir / pdf.stem
    pdf_out.mkdir(parents=True, exist_ok=True)

    cmd = [
        mineru_bin,
        "-p", str(pdf),
        "-o", str(pdf_out),
        "-b", backend,
        "-m", method,
        "-l", lang,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    duration = round(time.time() - start, 1)

    if proc.returncode == 0:
        md_files = list(pdf_out.rglob("*.md"))
        return {
            "file": str(pdf),
            "success": True,
            "md_path": str(md_files[0]) if md_files else None,
            "duration": duration,
        }

    err = (proc.stderr or proc.stdout).strip() or "unknown error"
    return {
        "file": str(pdf),
        "success": False,
        "error": err[-600:],   # keep the tail; mineru is verbose
        "duration": duration,
    }


def run_batch(
    input_path: Path,
    output_dir: Path,
    workers: int,
    backend: str,
    method: str,
    lang: str,
    skip_existing: bool,
    failed_log: Path | None,
    log: logging.Logger,
) -> int:
    mineru_bin = find_mineru()
    log.info(f"mineru CLI: {mineru_bin}")

    pdfs = find_pdfs(input_path)
    if not pdfs:
        log.error(f"No PDFs found in: {input_path}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"Found {len(pdfs)} PDF(s)  →  output: {output_dir}")
    log.info(f"Backend: {backend}  |  Method: {method}  |  Lang: {lang}  |  Workers: {workers}")

    if skip_existing:
        pending, skipped = filter_pending(pdfs, output_dir)
        log.info(f"Pending: {len(pending)}  |  Already done: {skipped}")
    else:
        pending = pdfs

    if not pending:
        log.info("Nothing to do.")
        return 0

    try:
        from tqdm import tqdm
        bar = tqdm(total=len(pending), unit="pdf", dynamic_ncols=True)
    except ImportError:
        bar = None

    results: list[dict] = []
    wall_start = time.time()

    def _do(pdf: Path) -> dict:
        r = convert_one(pdf, output_dir, mineru_bin, backend, method, lang)
        if r["success"]:
            log.info(f"  ✓  {pdf.name}  ({r['duration']}s)")
        else:
            short = r["error"].replace("\n", " ")[:140]
            log.warning(f"  ✗  {pdf.name}  →  {short}")
        if bar:
            bar.update(1)
        return r

    if workers <= 1:
        for pdf in pending:
            results.append(_do(pdf))
    else:
        # mineru is a subprocess → threads are fine. We just need parallelism
        # for I/O and to overlap GPU stalls between PDFs.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_do, pdf) for pdf in pending]
            for fut in as_completed(futures):
                results.append(fut.result())

    if bar:
        bar.close()

    ok = [r for r in results if r["success"]]
    bad = [r for r in results if not r["success"]]
    total = round(time.time() - wall_start, 1)
    rate = round(len(ok) / (total / 60), 1) if total > 0 else 0

    log.info("─" * 60)
    log.info(f"Done.  ✓ {len(ok)}  ✗ {len(bad)}  |  {total}s  ({rate} PDF/min)")
    if ok:
        avg = round(sum(r["duration"] for r in ok) / len(ok), 1)
        log.info(f"Avg per PDF: {avg}s")

    if bad:
        log.warning(f"{len(bad)} failure(s):")
        for r in bad:
            name = Path(r["file"]).name
            log.warning(f"  {name}: {r['error'][:200]}")
        if failed_log:
            failed_log.write_text("\n".join(r["file"] for r in bad), encoding="utf-8")
            log.info(f"Failed list: {failed_log}")

    report = {
        "timestamp": datetime.now().isoformat(),
        "backend": backend,
        "method": method,
        "lang": lang,
        "workers": workers,
        "total": len(results),
        "success": len(ok),
        "failed": len(bad),
        "total_seconds": total,
        "pdfs_per_minute": rate,
        "results": results,
    }
    report_path = output_dir / "conversion_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Report: {report_path}")

    return 0 if not bad else 2


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="med2md",
        description="Batch convert PDFs to Markdown using MinerU.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-i", "--input", required=True, type=Path,
                   help="PDF file, directory (recursive), or text file of PDF paths")
    p.add_argument("-o", "--output", required=True, type=Path,
                   help="Output directory; each PDF gets its own subfolder")
    p.add_argument("-b", "--backend", default="pipeline",
                   choices=["pipeline", "vlm-auto-engine", "hybrid-auto-engine"],
                   help="MinerU backend")
    p.add_argument("-m", "--method", default="auto",
                   choices=["auto", "txt", "ocr"],
                   help="Parse method (pipeline/hybrid backends only)")
    p.add_argument("-l", "--lang", default="en",
                   help="Document language (en, ch, japan, korean, ...)")
    p.add_argument("-j", "--workers", type=int, default=1,
                   help="Parallel workers. On 24 GB GPU: 1–3 for pipeline, 1 for vlm")
    p.add_argument("--no-skip", action="store_true",
                   help="Reconvert PDFs even if output .md already exists")
    p.add_argument("--failed-log", type=Path,
                   help="Write failed PDF paths to this file")
    p.add_argument("--log-file", type=Path,
                   help="Also write logs to this file")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    log = setup_logging(args.log_file)
    return run_batch(
        input_path=args.input,
        output_dir=args.output,
        workers=args.workers,
        backend=args.backend,
        method=args.method,
        lang=args.lang,
        skip_existing=not args.no_skip,
        failed_log=args.failed_log,
        log=log,
    )


if __name__ == "__main__":
    sys.exit(main())
