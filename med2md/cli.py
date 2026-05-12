"""Command-line interface for med2md."""

import argparse
import sys
from pathlib import Path

from .batch import run_batch
from .config import BACKENDS, METHODS, Options
from .converter import EngineError
from .engines import ENGINES
from .log import setup_logger


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="med2md",
        description="Batch convert PDFs to Markdown using MinerU or marker-pdf.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-i", "--input", required=True, type=Path,
                   help="PDF file, directory (recursive), or text file of PDF paths")
    p.add_argument("-o", "--output", required=True, type=Path,
                   help="Output directory; each PDF gets its own subfolder")
    p.add_argument("-e", "--engine", default="mineru", choices=ENGINES,
                   help="Conversion engine")
    p.add_argument("-b", "--backend", default="pipeline", choices=BACKENDS,
                   help="MinerU backend (ignored for marker)")
    p.add_argument("-m", "--method", default="auto", choices=METHODS,
                   help="MinerU parse method (ignored for marker)")
    p.add_argument("-l", "--lang", default="en",
                   help="Document language (mineru only)")
    p.add_argument("-j", "--workers", type=int, default=1,
                   help="Parallel workers (mineru only; marker is sequential)")
    p.add_argument("--no-skip", action="store_true",
                   help="Reconvert PDFs even if output .md already exists")
    p.add_argument("--failed-log", type=Path,
                   help="Write failed PDF paths to this file")
    p.add_argument("--log-file", type=Path,
                   help="Also write logs to this file")
    return p.parse_args(argv)


def options_from_args(args: argparse.Namespace) -> Options:
    return Options(
        input_path=args.input,
        output_dir=args.output,
        engine=args.engine,
        backend=args.backend,
        method=args.method,
        lang=args.lang,
        workers=args.workers,
        skip_existing=not args.no_skip,
        failed_log=args.failed_log,
        log_file=args.log_file,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log = setup_logger(args.log_file)
    opts = options_from_args(args)
    try:
        return run_batch(opts, log)
    except EngineError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1
