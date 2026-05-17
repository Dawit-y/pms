from .base import Exporter
from .excel import ExcelExporter
from .pdf import PdfExporter

__all__ = ("ExcelExporter", "Exporter", "PdfExporter")


def get_exporter(format_: str, definition):
    """Pick the right exporter for the requested file format."""
    if format_ == "xlsx":
        return ExcelExporter(definition)
    if format_ == "pdf":
        return PdfExporter(definition)
    msg = f"Unsupported export format: {format_}"
    raise ValueError(msg)
