"""Conversion engines: dispatch by --engine flag."""

from logging import Logger
from pathlib import Path
from typing import Callable

from ..config import Options
from ..converter import ConversionResult

ENGINES: tuple[str, ...] = ("mineru", "marker")

ConvertFn = Callable[[Path], ConversionResult]


def get_engine(opts: Options, log: Logger) -> ConvertFn:
    """Build and return a single-PDF converter for the selected engine.

    Engine modules expose a `build(opts, log) -> ConvertFn` factory. The
    returned callable is reused for every PDF in the batch, so any expensive
    one-time setup (model loading, CLI discovery) happens here.
    """
    if opts.engine == "mineru":
        from .mineru import build
    elif opts.engine == "marker":
        from .marker import build
    else:
        raise ValueError(f"Unknown engine: {opts.engine!r}")
    return build(opts, log)
