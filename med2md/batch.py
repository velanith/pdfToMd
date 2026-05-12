"""Batch orchestration — wires discovery, engine, and reporting together."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from logging import Logger
from pathlib import Path

from .config import Options
from .converter import ConversionResult
from .discovery import filter_pending, find_pdfs
from .engines import ConvertFn, get_engine
from .reporting import build_report, write_failed_log, write_report


@dataclass
class BatchOutcome:
    results: list[ConversionResult]
    wall_seconds: float


def run_batch(opts: Options, log: Logger) -> int:
    """Run a full batch. Returns POSIX-style exit code (0/1/2)."""
    pdfs = find_pdfs(opts.input_path)
    if not pdfs:
        log.error(f"No PDFs found in: {opts.input_path}")
        return 1

    opts.output_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"Found {len(pdfs)} PDF(s)  →  output: {opts.output_dir}")
    log.info(
        f"Engine: {opts.engine}  |  Backend: {opts.backend}  |  "
        f"Method: {opts.method}  |  Lang: {opts.lang}  |  Workers: {opts.workers}"
    )

    pending = pdfs
    if opts.skip_existing:
        pending, skipped = filter_pending(pdfs, opts.output_dir)
        log.info(f"Pending: {len(pending)}  |  Already done: {skipped}")

    if not pending:
        log.info("Nothing to do.")
        return 0

    # Build engine AFTER discovery — avoids loading models if there's nothing to do.
    convert_fn = get_engine(opts, log)

    outcome = _process(pending, opts, convert_fn, log)
    return _finalize(outcome, opts, log)


def _process(
    pending: list[Path],
    opts: Options,
    convert_fn: ConvertFn,
    log: Logger,
) -> BatchOutcome:
    bar = _make_progress_bar(len(pending))
    results: list[ConversionResult] = []
    wall_start = time.time()

    def task(pdf: Path) -> ConversionResult:
        r = convert_fn(pdf)
        _log_result(pdf, r, log)
        if bar is not None:
            bar.update(1)
        return r

    # The marker engine shares a single GPU-resident model across calls, so
    # it must run sequentially. mineru is a subprocess-per-PDF, so threads
    # are fine — no GIL contention, no spawn-context process pool needed.
    workers = opts.workers
    if opts.engine == "marker" and workers > 1:
        log.warning(f"marker engine is sequential; ignoring -j {workers}")
        workers = 1

    if workers <= 1:
        for pdf in pending:
            results.append(task(pdf))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(task, pdf) for pdf in pending]
            for fut in as_completed(futures):
                results.append(fut.result())

    if bar is not None:
        bar.close()

    return BatchOutcome(results=results, wall_seconds=time.time() - wall_start)


def _finalize(outcome: BatchOutcome, opts: Options, log: Logger) -> int:
    report = build_report(outcome.results, opts, outcome.wall_seconds)

    log.info("─" * 60)
    log.info(
        f"Done.  ✓ {report['success']}  ✗ {report['failed']}  |  "
        f"{report['total_seconds']}s  ({report['pdfs_per_minute']} PDF/min)"
    )

    successes = [r for r in outcome.results if r.success]
    if successes:
        avg = round(sum(r.duration for r in successes) / len(successes), 1)
        log.info(f"Avg per PDF: {avg}s")

    failures = [r for r in outcome.results if not r.success]
    if failures:
        log.warning(f"{len(failures)} failure(s):")
        for r in failures:
            log.warning(f"  {Path(r.file).name}: {(r.error or '')[:200]}")
        if opts.failed_log:
            write_failed_log(outcome.results, opts.failed_log)
            log.info(f"Failed list: {opts.failed_log}")

    report_path = write_report(report, opts.output_dir)
    log.info(f"Report: {report_path}")

    return 0 if not failures else 2


def _make_progress_bar(total: int):
    try:
        from tqdm import tqdm
        return tqdm(total=total, unit="pdf", dynamic_ncols=True)
    except ImportError:
        return None


def _log_result(pdf: Path, r: ConversionResult, log: Logger) -> None:
    if r.success:
        log.info(f"  ✓  {pdf.name}  ({r.duration}s)")
    else:
        short = (r.error or "").replace("\n", " ")[:140]
        log.warning(f"  ✗  {pdf.name}  →  {short}")
