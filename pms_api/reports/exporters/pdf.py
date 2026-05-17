"""
PDF exporter — ReportLab Platypus.

Builds the document in two passes: rows are collected into an in-memory list
of Platypus flowables, then `finalize()` renders them via SimpleDocTemplate.
ReportLab can't truly stream like openpyxl can, so callers must cap
PDF exports (`REPORT_MAX_ROWS_PDF`) before kicking off the task.
"""

import tempfile
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.pagesizes import landscape
from reportlab.lib.pagesizes import portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph
from reportlab.platypus import SimpleDocTemplate
from reportlab.platypus import Spacer
from reportlab.platypus import Table
from reportlab.platypus import TableStyle

from .base import Exporter

_PAGE_SIZES = {"A4": A4, "Letter": LETTER}


class PdfExporter(Exporter):
    extension = "pdf"
    content_type = "application/pdf"

    HEADER_BG = colors.HexColor("#2C3E50")
    HEADER_FG = colors.white
    ROW_ALT_BG = colors.HexColor("#F4F6F8")
    GRID = colors.HexColor("#BDC3C7")

    def __init__(self, definition) -> None:
        super().__init__(definition)
        self._rows: list[list[str]] = []
        self._summary: dict = {}
        styles = getSampleStyleSheet()
        self._title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontSize=14,
            leading=18,
            alignment=1,  # center
            spaceAfter=8,
        )
        self._meta_style = ParagraphStyle(
            "ReportMeta",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.grey,
            alignment=1,
            spaceAfter=10,
        )
        self._summary_label_style = ParagraphStyle(
            "ReportSummaryLabel",
            parent=styles["Normal"],
            fontSize=10,
            spaceBefore=12,
            spaceAfter=4,
        )

    def begin(self) -> None:
        # Header rows live as the first table row; column labels are stacked tri-lingually
        # the same way the Excel version does it.
        headers = []
        for col in self.definition.columns:
            parts = [p for p in (col.label_en, col.label_am, col.label_or) if p]
            headers.append("\n".join(parts))
        self._rows = [headers]

    def write_chunk(self, rows: list[dict]) -> None:
        for row in rows:
            self._rows.append(
                [self._cell(col, row.get(col.key)) for col in self.definition.columns],
            )

    @staticmethod
    def _cell(col, value) -> str:
        if value is None:
            return ""
        if col.formatter is not None:
            try:
                return str(col.formatter(value))
            except (TypeError, ValueError):
                pass
        return str(value)

    def write_summary(self, summary: dict) -> None:
        self._summary = summary or {}

    def finalize(self) -> tuple[Path, int]:
        with tempfile.NamedTemporaryFile(
            prefix="report_",
            suffix=".pdf",
            delete=False,
        ) as tmp:
            self._path = Path(tmp.name)

        page_size = _PAGE_SIZES.get(self.definition.pdf_page_size, A4)
        orient = landscape if self.definition.pdf_orientation.lower() == "landscape" else portrait
        doc = SimpleDocTemplate(
            str(self._path),
            pagesize=orient(page_size),
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title=self.definition.name_en or self.definition.code,
            author="PMS",
        )

        story = self._build_story()
        doc.build(story, onFirstPage=self._page_footer, onLaterPages=self._page_footer)
        size = self._path.stat().st_size
        return self._path, size

    def _build_story(self):
        story = [Paragraph(self.definition.name_en or self.definition.code, self._title_style)]
        if self.definition.description:
            story.append(Paragraph(self.definition.description, self._meta_style))

        # The table style is built around the alignment hints declared per column
        # plus our standard banding so reports remain visually consistent.
        align_map = {"LEFT": "LEFT", "CENTER": "CENTER", "RIGHT": "RIGHT"}
        col_aligns = [align_map.get(c.pdf_align.upper(), "LEFT") for c in self.definition.columns]

        table = Table(self._rows, repeatRows=1)
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), self.HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), self.HEADER_FG),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, self.GRID),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, self.ROW_ALT_BG]),
        ]
        for col_idx, align in enumerate(col_aligns):
            commands.append(("ALIGN", (col_idx, 1), (col_idx, -1), align))
        table.setStyle(TableStyle(commands))
        story.append(table)

        if self._summary:
            story.append(Spacer(1, 10))
            story.append(Paragraph("<b>Summary</b>", self._summary_label_style))
            summary_rows = [
                [key.replace("_", " ").title(), str(value)] for key, value in self._summary.items()
            ]
            summary_table = Table(summary_rows, hAlign="LEFT")
            summary_table.setStyle(
                TableStyle(
                    [
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.25, self.GRID),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ],
                ),
            )
            story.append(summary_table)

        return story

    @staticmethod
    def _page_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        footer = f"Page {doc.page}"
        canvas.drawRightString(doc.pagesize[0] - 10 * mm, 8 * mm, footer)
        canvas.restoreState()
