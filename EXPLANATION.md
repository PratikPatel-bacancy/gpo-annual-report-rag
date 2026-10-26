# GPO Annual Report RAG — Explanation Notes

Notes on what this baseline does, how it's built, and the decisions behind it — useful context
for explaining the implementation in a review.

## 1. The task

> Implement RAG for the GPO Annual Report. Focus on document ingestion, chunking, embeddings,
> retrieval, and response generation. Validate the implementation using the sample questions
> provided. Objective: Build a solid baseline RAG pipeline.

No document or sample questions were attached to the task, so both had to be sourced:

- **Document**: the U.S. Government Publishing Office publishes its own real Annual Report
  publicly (it's a government agency whose entire mission is public document access). Used the
  FY2025 edition from [GovInfo](https://www.govinfo.gov/app/details/GOVPUB-GP-9c733daaffcd5befa675d8d0a019bc5f) —
  public domain, 98 pages, real financial/operational content.
- **Sample questions**: drafted 12 in `backend/eval/sample_questions.json` directly from the
  report's own numbers and facts (see `README.md`), so pass/fail is checkable against real,
  verifiable answers rather than vibes. Swap in the actual sample questions if/when provided.

## 2. Why this is architecturally the same problem as the cricket chatbot

Retrieval, embedding, and generation are generic — none of that logic is specific to cricket rules
or government annual reports. The only genuinely document-specific piece is **chunking**: how you
split a particular document into coherent, self-contained pieces depends entirely on that
document's structure. For hand-authored Markdown, that's trivial (split on `##`). For a real PDF,
it's the interesting part of this task.

## 3. Chunking a real PDF by its own headings

The report has a clear table of contents with 9 top-level sections. The chunker (`chunker.py`)
finds each of those heading lines in the extracted page text and splits the document there, same
idea as splitting Markdown on `##` — each chunk is one complete section, not an arbitrary
character cut.

Two real wrinkles came up that don't exist with hand-authored Markdown:

1. **The headings also appear in the Table of Contents itself**, immediately followed by a dot
   leader and a page number (`GPO FINANCES ........... 34`). A naive "find this text" search
   would match the ToC line instead of the real section. Fixed by excluding any page containing
   "TABLE OF CONTENTS" from the heading search.
2. **Some headings are stylized banners that wrap across 2–3 visual lines** in the PDF (e.g. "GPO
   ADVANCED STRATEGIC / GOALS THROUGHOUT / FISCAL YEAR 2025" renders as three separate lines).
   Fixed by whitespace-normalizing each page's text before matching, so line breaks inside a
   heading don't break the match.
3. **"About GPO" is a stylized image banner with no extractable text at all** — pypdf's text
   extraction only gets text layers, not text baked into a graphic. That section's content isn't
   lost, but it currently gets folded into the preceding "A Message from the Director" chunk
   rather than labeled separately. Known baseline limitation (see §6).

Within each of the 9 detected sections, content is further split by character count (1,800 chars,
200-char overlap) exactly like the cricket chunker — "GPO Finances" alone spans pages 38–98 and
produces 79 sub-chunks. Page markers are threaded through that size-based split so **every chunk,
however it was cut, still reports an accurate page range** for citation — a page-numbered PDF
chunk can cite "p. 45" the way a Markdown chunk cites its heading.

## 4. Retrieval and generation

Unchanged in spirit from `cricket-chatbot`: over-fetch (3x the final count), dedupe by
`(heading, page_start)` so near-duplicate chunks from the same long section don't crowd out other
sections, then hand the top-K excerpts to the LLM with a system prompt that says "answer only from
this context, and say you don't know rather than guessing." Conversation history (last 20
messages) is included so follow-ups work. Answers stream back over SSE.

## 5. Validating "it works"

`backend/eval/run_eval.py` runs the 12 sample questions through the real, unmocked pipeline and
checks each answer against expected keywords (drawn from the report's actual numbers) or, for two
deliberately out-of-scope questions, checks that the model *declines* rather than fabricates an
answer — the same "say I don't know" test used in the cricket chatbot.

## 6. Known baseline limitations / next steps

- **"About GPO" has no separately labeled chunk** (§3) — its content is still indexed and
  retrievable, just mislabeled as part of the preceding section. Fixable with layout-aware
  extraction (e.g. `pdfplumber`/`PyMuPDF` font-size heuristics) instead of plain-text heading
  matching.
- **No frontend** — out of scope for this baseline task. Since the API is the same shape as
  `cricket-chatbot`'s (`POST /api/chat` streaming SSE), that project's chat UI could be pointed at
  this backend with minimal changes if a UI is wanted later.
- **Single document** — the schema has a `source` column for multiple documents, but ingestion
  currently only loads one PDF path. Extending to a folder of reports would be a small change to
  `ingest.py`.
- **No re-ranking** — retrieval is pure vector similarity. For a much larger corpus, a re-ranking
  step or hybrid keyword+vector search would likely be the next improvement, same as noted in the
  cricket chatbot's own notes.
