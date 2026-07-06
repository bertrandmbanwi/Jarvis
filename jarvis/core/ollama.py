"""Shared Ollama client helper: query installed models via the /api/tags endpoint.

Consolidates the three near-identical `GET {base}/api/tags` probes that lived in
the LLM router health check and the settings API status/test endpoints.
"""
import httpx


async def list_ollama_models(
    base_url: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 5.0,
) -> list[str]:
    """Return the names of installed Ollama models.

    Uses the provided client if given (so callers can reuse a pooled connection),
    otherwise opens a short-lived one. Raises httpx errors when Ollama is
    unreachable or returns a non-2xx status, so callers decide how to degrade.
    """
    url = f"{base_url.rstrip('/')}/api/tags"
    if client is not None:
        response = await client.get(url)
    else:
        async with httpx.AsyncClient(timeout=timeout) as temp_client:
            response = await temp_client.get(url)
    response.raise_for_status()
    data = response.json()
    return [model.get("name", "") for model in data.get("models", [])]
