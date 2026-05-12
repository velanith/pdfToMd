"""Shared types for conversion engines."""

from dataclasses import asdict, dataclass


class EngineError(RuntimeError):
    """Raised when an engine cannot be initialised (missing CLI / package)."""


@dataclass
class ConversionResult:
    file: str
    success: bool
    duration: float
    md_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
