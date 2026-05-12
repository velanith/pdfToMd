"""marker-pdf Python-API engine.

Loads layout + recognition models once into GPU memory and reuses them for
every PDF in the batch. Sequential by design (single GPU-resident converter
shared across calls is not thread-safe).
"""

import time
from logging import Logger
from pathlib import Path
from typing import Callable

from ..config import Options
from ..converter import ConversionResult, EngineError


def build(opts: Options, log: Logger) -> Callable[[Path], ConversionResult]:
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.output import text_from_rendered
    except ImportError as exc:
        raise EngineError(
            f"marker-pdf not installed ({exc.name}).\n"
            "  Run:  pip install marker-pdf"
        ) from exc

    log.info("Loading marker-pdf models ...")
    t0 = time.time()
    pdf_converter = PdfConverter(artifact_dict=create_model_dict())
    log.info(f"Marker ready in {round(time.time() - t0, 1)}s")

    def convert(pdf: Path) -> ConversionResult:
        start = time.time()
        pdf_out = opts.output_dir / pdf.stem
        pdf_out.mkdir(parents=True, exist_ok=True)

        try:
            rendered = pdf_converter(str(pdf))
            text, _meta, images = text_from_rendered(rendered)
        except Exception as exc:
            return ConversionResult(
                file=str(pdf),
                success=False,
                duration=round(time.time() - start, 1),
                error=f"{type(exc).__name__}: {exc}"[:400],
            )

        md_path = pdf_out / f"{pdf.stem}.md"
        md_path.write_text(text, encoding="utf-8")

        for name, img in (images or {}).items():
            target = pdf_out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                img.save(target)
            except Exception:   # noqa: BLE001 — image-save failures are non-fatal
                pass

        return ConversionResult(
            file=str(pdf),
            success=True,
            duration=round(time.time() - start, 1),
            md_path=str(md_path),
        )

    return convert
