"""PDF discovery: turn --input into a concrete list of paths."""

from pathlib import Path


def find_pdfs(input_path: Path) -> list[Path]:
    """Resolve --input into a concrete list of PDF paths.

    Accepted forms:
      * a single .pdf file
      * a directory (searched recursively)
      * a text file with one PDF path per line (e.g. failed.txt from a prior run)
    """
    if input_path.is_file():
        if input_path.suffix.lower() == ".pdf":
            return [input_path]
        return _read_path_list(input_path)
    return sorted(input_path.rglob("*.pdf"))


def _read_path_list(text_file: Path) -> list[Path]:
    paths: list[Path] = []
    for raw in text_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            paths.append(Path(line))
    return paths


def filter_pending(pdfs: list[Path], output_dir: Path) -> tuple[list[Path], int]:
    """Split PDFs into (pending, already_done_count) based on output presence."""
    pending: list[Path] = []
    skipped = 0
    for p in pdfs:
        if (output_dir / p.stem / f"{p.stem}.md").exists():
            skipped += 1
        else:
            pending.append(p)
    return pending, skipped
