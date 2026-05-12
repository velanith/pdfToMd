"""Logger setup."""

import logging
import sys
from pathlib import Path


def setup_logger(log_file: Path | None = None, name: str = "med2md") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:   # avoid duplicate handlers on re-entry
        return logger

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
