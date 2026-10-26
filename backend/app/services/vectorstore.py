import httpx

from app.config import settings


def _headers(extra: dict | None = None) -> dict:
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def reset_collection():
    response = httpx.delete(
        f"{settings.supabase_url}/rest/v1/{settings.supabase_table}",
        headers=_headers(),
        params={"id": "gte.0"},
        timeout=30.0,
    )
    response.raise_for_status()


def add_chunks(rows: list[dict]):
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/{settings.supabase_table}",
        headers=_headers({"Prefer": "return=minimal"}),
        json=rows,
        timeout=60.0,
    )
    response.raise_for_status()


def query(embedding: list[float], top_k: int) -> list[dict]:
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/rpc/{settings.match_function}",
        headers=_headers(),
        json={"query_embedding": embedding, "match_count": top_k},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()
