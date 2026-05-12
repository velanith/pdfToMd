"""Build the JSON report and the failed-paths log."""

import json
from datetime import datetime
from pathlib import Path

from .config import Options
from .converter import ConversionResult


def build_report(
    results: list[ConversionResult],
    opts: Options,
    total_seconds: float,
) -> dict:
    ok = [r for r in results if r.success]
    bad = [r for r in results if not r.success]
    rate = round(len(ok) / (total_seconds / 60), 1) if total_seconds > 0 else 0.0
    return {
        "timestamp": datetime.now().isoformat(),
        "engine": opts.engine,
        "backend": opts.backend,
        "method": opts.method,
        "lang": opts.lang,
        "workers": opts.workers,
        "total": len(results),
        "success": len(ok),
        "failed": len(bad),
        "total_seconds": round(total_seconds, 1),
        "pdfs_per_minute": rate,
        "results": [r.to_dict() for r in results],
    }


def write_report(report: dict, output_dir: Path) -> Path:
    path = output_dir / "conversion_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_failed_log(results: list[ConversionResult], path: Path) -> None:
    failures = [r.file for r in results if not r.success]
    path.write_text("\n".join(failures), encoding="utf-8")
