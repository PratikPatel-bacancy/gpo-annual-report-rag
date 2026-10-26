"""One-off CLI: load the GPO Annual Report PDF -> chunk -> embed -> store in Supabase/pgvector.

Run with:  python scripts/ingest.py
Re-run any time the source PDF under data/source_documents/ changes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ingest import run_ingestion  # noqa: E402


def main():
    result = run_ingestion()
    if result["pages_processed"] == 0:
        print("Source PDF not found. Check SOURCE_PDF_PATH in .env.")
        return
    print(f"Processed {result['pages_processed']} pages, indexed {result['chunks_indexed']} chunks.")


if __name__ == "__main__":
    main()
