import asyncio
import json
import time
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.services.embeddings import embed_query
from app.services.vectorstore import query as query_vectorstore

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

MAX_HISTORY_MESSAGES = 20

# Groq's free tier has tight per-minute rate limits -- a back-to-back batch
# of questions (e.g. running the eval suite) can hit a 429 well within
# normal use. Retry with backoff (honoring Retry-After when given) instead
# of surfacing a transient rate limit as a hard failure.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


def _retry_wait_seconds(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return RETRY_BACKOFF_SECONDS * (2**attempt)

SYSTEM_PROMPT = f"""You are an assistant that answers questions about the {{document_title}}.

Answer ONLY using the excerpts provided in the context below. If the context does not \
contain enough information to answer confidently, say you don't have that information in \
the report rather than guessing. Keep answers clear and concise, and cite the relevant page \
number(s) from the excerpts when helpful.

Use the prior conversation turns to understand follow-up questions, but still ground every \
factual claim in the provided context."""


def _system_prompt() -> str:
    return SYSTEM_PROMPT.format(document_title=settings.document_title)


def retrieve(question: str, top_k: int | None = None) -> list[dict]:
    k = top_k or settings.top_k
    embedding = embed_query(question)
    # Over-fetch, then dedupe by (heading, page_start) so overlapping chunk
    # splits from the same long section (e.g. "GPO FINANCES" spans dozens of
    # chunks) don't crowd out other distinct sections.
    rows = query_vectorstore(embedding, k * 3)

    seen: set[tuple[str, int | None]] = set()
    sources = []
    for row in rows:
        heading = row.get("heading", "")
        page_start = row.get("page_start")
        key = (heading, page_start)
        if key in seen:
            continue
        seen.add(key)

        sources.append(
            {
                "title": heading,
                "page_start": page_start,
                "page_end": row.get("page_end"),
                "snippet": row.get("content", ""),
                "score": round(row.get("similarity", 0.0), 4),
            }
        )
        if len(sources) >= k:
            break

    return sources


def _build_prompt(question: str, sources: list[dict]) -> str:
    context = "\n\n---\n\n".join(s["snippet"] for s in sources)
    return f"Context (report excerpts):\n\n{context}\n\n---\n\nQuestion: {question}"


def _build_messages(question: str, sources: list[dict], history: list[dict] | None = None) -> list[dict]:
    messages = [{"role": "system", "content": _system_prompt()}]
    for turn in (history or [])[-MAX_HISTORY_MESSAGES:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": _build_prompt(question, sources)})
    return messages


def _groq_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }


async def answer_stream(question: str, history: list[dict] | None = None) -> AsyncIterator[dict]:
    """Yields dicts of shape {"type": "token", "text": str} for each streamed
    token, followed by a final {"type": "sources", "sources": [...]}."""
    sources = retrieve(question)
    messages = _build_messages(question, sources, history)

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(MAX_RETRIES + 1):
            async with client.stream(
                "POST",
                GROQ_CHAT_URL,
                headers=_groq_headers(),
                json={"model": settings.groq_model, "messages": messages, "stream": True},
            ) as response:
                if response.status_code in (429, 503) and attempt < MAX_RETRIES:
                    await response.aclose()
                    await asyncio.sleep(_retry_wait_seconds(response, attempt))
                    continue
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[len("data: ") :]
                    if payload == "[DONE]":
                        break
                    chunk = json.loads(payload)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield {"type": "token", "text": content}
            break

    yield {"type": "sources", "sources": sources}


def answer_once(question: str, history: list[dict] | None = None) -> dict:
    sources = retrieve(question)
    messages = _build_messages(question, sources, history)

    for attempt in range(MAX_RETRIES + 1):
        response = httpx.post(
            GROQ_CHAT_URL,
            headers=_groq_headers(),
            json={"model": settings.groq_model, "messages": messages, "stream": False},
            timeout=60.0,
        )
        if response.status_code in (429, 503) and attempt < MAX_RETRIES:
            time.sleep(_retry_wait_seconds(response, attempt))
            continue
        response.raise_for_status()
        break

    answer_text = response.json()["choices"][0]["message"]["content"]
    return {"answer": answer_text, "sources": sources}
