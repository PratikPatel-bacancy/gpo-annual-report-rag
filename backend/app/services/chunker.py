import re
from dataclasses import dataclass

MAX_CHUNK_CHARS = 1800
OVERLAP_CHARS = 200

# The section-heading lines exactly as they're rendered in the report body
# (not the Table of Contents, which repeats the same titles followed by a
# dot leader and a page number). Matching is done against whitespace-
# normalized page text, because some of these are styled as banner
# headlines that wrap across two or three visual lines in the PDF (e.g.
# "GPO ADVANCED STRATEGIC \nGOALS THROUGHOUT \nFISCAL YEAR 2025").
SECTION_HEADINGS = [
    "A Message from the Director",
    "GPO ADVANCED STRATEGIC GOALS THROUGHOUT FISCAL YEAR 2025",
    "GPO AND CONGRESS",
    "GPO AND THE WHITE HOUSE",
    "GPO AND FEDERAL AGENCIES",
    "GPO By the Numbers FY 2025",
    "GPO AND OPEN, TRANSPARENT GOVERNMENT",
    "GPO FINANCES",
]

# Known baseline limitation: "About GPO" (pages ~6-9) is rendered as a
# stylized image banner with no extractable heading text, so it has no entry
# above. Its content isn't lost -- it just ends up folded into the
# "A Message from the Director" chunk that precedes it. See README.

_PAGE_MARK_OPEN = "\x00PAGE"
_PAGE_MARK_CLOSE = "\x00"
_PAGE_MARK_RE = re.compile(r"\x00PAGE(\d+)\x00")
_STRAY_MARK_RE = re.compile(r"\x00PAGE\d*\x00?|\x00")


@dataclass
class Chunk:
    text: str
    heading: str
    page_start: int
    page_end: int


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        parts.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return parts


def _locate_sections(pages: list[tuple[int, str]]) -> list[tuple[str, int]]:
    """Returns [(heading, start_page), ...] in document order.

    Pages containing "TABLE OF CONTENTS" are skipped when searching, since
    the ToC repeats every heading's text immediately followed by a dot
    leader and page number -- without that exclusion, every heading would
    "start" on the ToC page instead of where its section actually begins.
    """
    normalized = [(num, _normalize(text)) for num, text in pages]
    toc_pages = {num for num, norm in normalized if "TABLE OF CONTENTS" in norm.upper()}

    located = []
    for heading in SECTION_HEADINGS:
        for num, norm in normalized:
            if num in toc_pages:
                continue
            if heading in norm:
                located.append((heading, num))
                break
    located.sort(key=lambda h: h[1])
    return located


def chunk_pages(pages: list[tuple[int, str]], doc_title: str) -> list[Chunk]:
    """pages: ordered [(page_number, page_text), ...] from pdf_loader.

    Splits the document into one section per recognized heading (so each
    section is one complete, coherent topic -- the same idea as chunking a
    markdown knowledge base by "##" heading), then further splits any
    section that's still too long for a single embedding chunk, the same
    way the markdown chunker does. Page markers are threaded through the
    size-based split so every resulting chunk still knows exactly which
    page(s) it came from, for citation.
    """
    if not pages:
        return []

    sections = _locate_sections(pages)
    if not sections:
        # Fallback if heading detection finds nothing at all (e.g. a very
        # differently-formatted document): treat the whole PDF as one
        # section so ingestion still produces usable chunks.
        sections = [(doc_title, pages[0][0])]

    page_text = dict(pages)
    page_numbers = sorted(page_text)
    last_page = page_numbers[-1]

    chunks: list[Chunk] = []
    for idx, (heading, start_page) in enumerate(sections):
        end_page = sections[idx + 1][1] - 1 if idx + 1 < len(sections) else last_page
        end_page = max(end_page, start_page)

        nums_in_range = [n for n in page_numbers if start_page <= n <= end_page]
        marked = "".join(f"{_PAGE_MARK_OPEN}{n}{_PAGE_MARK_CLOSE}{page_text[n]}" for n in nums_in_range)

        for piece in _split_long_text(marked, MAX_CHUNK_CHARS, OVERLAP_CHARS):
            page_hits = [int(m) for m in _PAGE_MARK_RE.findall(piece)]
            p_start = min(page_hits) if page_hits else start_page
            p_end = max(page_hits) if page_hits else end_page
            clean = _STRAY_MARK_RE.sub("", piece).strip()
            if not clean:
                continue

            page_label = f"p. {p_start}" if p_end == p_start else f"pp. {p_start}–{p_end}"
            chunk_text = f"{doc_title} — {heading} ({page_label})\n\n{clean}"
            chunks.append(Chunk(text=chunk_text, heading=heading, page_start=p_start, page_end=p_end))

    return chunks
