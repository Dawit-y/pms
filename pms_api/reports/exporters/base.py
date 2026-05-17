"""
Exporter contract.

The Celery task drives the lifecycle: `begin()` → `write_chunk()` (many) →
`write_summary()` (optional) → `finalize()`. Subclasses encapsulate the
format-specific machinery (openpyxl workbook vs. ReportLab document).
"""

import contextlib
from abc import ABC
from abc import abstractmethod
from pathlib import Path

from pms_api.reports.base import ReportDefinition


class Exporter(ABC):
    extension: str = ""
    content_type: str = ""

    def __init__(self, definition: ReportDefinition) -> None:
        self.definition = definition
        self._path: Path | None = None

    @abstractmethod
    def begin(self) -> None:
        """Open the file and write any header rows."""

    @abstractmethod
    def write_chunk(self, rows: list[dict]) -> None:
        """Stream a batch of rows. Called many times during a single export."""

    def write_summary(self, summary: dict) -> None:  # noqa: B027
        """Optionally append a summary section. Default: no-op."""

    @abstractmethod
    def finalize(self) -> tuple[Path, int]:
        """Close the file and return (path, size_in_bytes)."""

    def cleanup(self) -> None:
        """Remove the temp file on failure. Best-effort."""
        if self._path is not None and self._path.exists():
            with contextlib.suppress(OSError):
                self._path.unlink()
