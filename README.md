# GPO Annual Report — Baseline RAG

A baseline RAG (Retrieval-Augmented Generation) pipeline that answers questions about the
U.S. Government Publishing Office's FY2025 Annual Report, grounded only in that document.

**Task scope** (per the assigned task): document ingestion, chunking, embeddings, retrieval, and
response generation, validated against a set of sample questions. No frontend/UI is included —
this is the backend pipeline only. See [`EXPLANATION.md`](EXPLANATION.md) for the architecture and
design decisions in more depth.

## Source document

[`backend/data/source_documents/gpo_annual_report_fy2025.pdf`](backend/data/source_documents/gpo_annual_report_fy2025.pdf)
— the real, publicly published U.S. Government Publishing Office Annual Report for Fiscal Year
2025 (released April 2026), downloaded from
[GovInfo](https://www.govinfo.gov/app/details/GOVPUB-GP-9c733daaffcd5befa675d8d0a019bc5f). It's a
work of the U.S. Government and not subject to copyright (17 U.S.C. § 105), so it's checked
straight into the repo.

## How it works

1. `pdf_loader.py` extracts text from the PDF, one page at a time.
2. `chunker.py` splits the document along its own section headings (the same table of contents
   the report itself uses — "A Message from the Director," "GPO Finances," etc.), then further
   splits any section that's still too long for one embedding chunk. Each chunk keeps track of
   exactly which page(s) it came from.
3. `embeddings.py` calls Cohere (`embed-english-v3.0`) to turn each chunk into a 1024-number
   vector.
4. `vectorstore.py` stores chunks + vectors in Postgres/pgvector, hosted on Supabase.
5. At query time, the question is embedded the same way, matched by vector similarity, and the
   top matching excerpts are handed to an LLM (`gpt-oss-20b`, served by Groq) with instructions to
   answer only from that context — streaming the answer back over SSE along with the page(s) it
   used.

This mirrors the architecture of the [`cricket-chatbot`](https://github.com/PratikPatel-bacancy)
project (ingest → chunk → embed → store → retrieve → generate, each step its own swappable
service), adapted for a single real PDF instead of hand-authored Markdown files.

## Tech stack

| Layer        | Technology                                                       |
|--------------|-------------------------------------------------------------------|
| Backend      | Python + FastAPI                                                  |
| PDF parsing  | [pypdf](https://pypdf.readthedocs.io/) (pure Python, no system deps) |
| LLM (chat)   | [Groq](https://groq.com) running `openai/gpt-oss-20b`              |
| Embeddings   | [Cohere](https://cohere.com) `embed-english-v3.0`                  |
| Vector store | [Supabase](https://supabase.com) Postgres + pgvector               |

## Setup

### 1. Gather API keys

You need four values — the same four as `cricket-chatbot`, reusable from those same accounts if
you'd like, or a fresh Supabase project to keep this corpus separate:

1. **Groq API key** — [console.groq.com](https://console.groq.com) → API Keys
2. **Cohere API key** — [dashboard.cohere.com](https://dashboard.cohere.com/welcome/register) → API Keys
3. **Supabase project URL + service_role key** — create a project at
   [supabase.com/dashboard](https://supabase.com/dashboard), then:
   - **Database → Extensions** → enable `vector`
   - **SQL Editor** → run:
     ```sql
     create table gpo_documents (
       id bigserial primary key,
       content text,
       source text,
       heading text,
       page_start int,
       page_end int,
       embedding vector(1024)
     );

     create or replace function match_gpo_documents (
       query_embedding vector(1024),
       match_count int
     )
     returns table (
       id bigint, content text, source text, heading text,
       page_start int, page_end int, similarity float
     )
     language sql stable
     as $$
       select gpo_documents.id, gpo_documents.content, gpo_documents.source, gpo_documents.heading,
              gpo_documents.page_start, gpo_documents.page_end,
              1 - (gpo_documents.embedding <=> query_embedding) as similarity
       from gpo_documents
       order by gpo_documents.embedding <=> query_embedding
       limit match_count;
     $$;
     ```

   > **If reusing the same Supabase project as `cricket-chatbot`**: this creates a separate
   > `gpo_documents` table/function, distinct from cricket-chatbot's `documents` table. Don't
   > rename it to `documents` — ingestion here deletes everything in its target table before
   > re-indexing, and pointing it at cricket-chatbot's table would wipe that project's data.
   - **Project Settings → API** → copy the **Project URL** and the **`service_role`** key

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
```

Edit `backend/.env` and fill in the four values from step 1.

Build the vector index from the PDF (re-run any time the PDF changes):

```bash
python scripts/ingest.py
```

Start the API server:

```bash
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`. Check `http://localhost:8000/api/health`.

## Validating against the sample questions

Since no sample questions were provided with the task, [`backend/eval/sample_questions.json`](backend/eval/sample_questions.json)
contains 12 questions drafted from the report's actual content — spanning finances, headcount,
strategic goals, history, and two deliberately out-of-scope questions that should be declined
rather than guessed at. Replace this file with the real sample questions if/when they're provided.

After running ingestion once:

```bash
cd backend
python eval/run_eval.py
```

This runs each question through the real pipeline (no mocking) and reports PASS/FAIL against
expected keywords (or an expected refusal), plus the top retrieved source and its page number, for
manual review.

## API

- `POST /api/chat` — `{ "question": "...", "history": [{ "role": "user"|"assistant", "content": "..." }] }`
  → streams Server-Sent Events (`token` events with partial text, followed by a final `sources` event).
- `POST /api/ingest` — re-runs ingestion over the source PDF (same as `scripts/ingest.py`, callable over HTTP).
- `GET /api/health` — health check.
