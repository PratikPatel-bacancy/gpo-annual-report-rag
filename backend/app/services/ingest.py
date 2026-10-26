from pathlib import Path

from app.config import settings
from app.services.chunker import chunk_pages
from app.services.embeddings import embed_texts
from app.services.pdf_loader import load_pdf_pages
from app.services.vectorstore import add_chunks, reset_collection


def run_ingestion() -> dict:
    pdf_path = Path(settings.source_pdf_path)
    if not pdf_path.exists():
        return {"pages_processed": 0, "chunks_indexed": 0}

    pages = load_pdf_pages(pdf_path)
    chunks = chunk_pages(pages, doc_title=settings.document_title)

    if not chunks:
        return {"pages_processed": len(pages), "chunks_indexed": 0}

    reset_collection()

    texts = [c.text for c in chunks]
    embeddings = embed_texts(texts, input_type="search_document")

    rows = [
        {
            "content": c.text,
            "source": pdf_path.name,
            "heading": c.heading,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "embedding": embedding,
        }
        for c, embedding in zip(chunks, embeddings)
    ]
    add_chunks(rows)

    return {"pages_processed": len(pages), "chunks_indexed": len(chunks)}
