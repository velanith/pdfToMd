"""Configuration types and constants."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Engine = Literal["mineru", "marker"]
Backend = Literal["pipeline", "vlm-auto-engine", "hybrid-auto-engine"]
Method = Literal["auto", "txt", "ocr"]

BACKENDS: tuple[str, ...] = ("pipeline", "vlm-auto-engine", "hybrid-auto-engine")
METHODS: tuple[str, ...] = ("auto", "txt", "ocr")


@dataclass(frozen=True)
class Options:
    """Resolved CLI options passed through the batch pipeline."""

    input_path: Path
    output_dir: Path
    engine: Engine = "mineru"
    backend: Backend = "pipeline"
    method: Method = "auto"
    lang: str = "en"
    workers: int = 1
    skip_existing: bool = True
    failed_log: Path | None = None
    log_file: Path | None = None
