import httpx

from app.config import settings

COHERE_EMBED_URL = "https://api.cohere.com/v1/embed"
MAX_BATCH_SIZE = 90


def _embed_batch(texts: list[str], input_type: str) -> list[list[float]]:
    response = httpx.post(
        COHERE_EMBED_URL,
        headers={"Authorization": f"Bearer {settings.cohere_api_key}"},
        json={"texts": texts, "model": settings.cohere_model, "input_type": input_type},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["embeddings"]


def embed_texts(texts: list[str], input_type: str = "search_document") -> list[list[float]]:
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), MAX_BATCH_SIZE):
        embeddings.extend(_embed_batch(texts[i : i + MAX_BATCH_SIZE], input_type))
    return embeddings


def embed_query(text: str) -> list[float]:
    return embed_texts([text], input_type="search_query")[0]
