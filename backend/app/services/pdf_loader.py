from pathlib import Path

from pypdf import PdfReader


def load_pdf_pages(pdf_path: str | Path) -> list[tuple[int, str]]:
    """Returns [(page_number, page_text), ...], 1-indexed, in document order.

    Page-level granularity (rather than one giant string) is what lets the
    chunker later report an accurate page range per chunk, and lets heading
    detection work page-by-page.
    """
    reader = PdfReader(str(pdf_path))
    return [(i, page.extract_text() or "") for i, page in enumerate(reader.pages, start=1)]
