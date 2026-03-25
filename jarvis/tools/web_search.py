"""JARVIS Web Search: free web search using DuckDuckGo (no API key required)."""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger("jarvis.tools.web_search")

try:
    from ddgs import DDGS
    HAS_DDG = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        HAS_DDG = True
    except ImportError:
        HAS_DDG = False
        logger.warning("No DuckDuckGo search package found. Install with: pip install ddgs")


async def search_web(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo (free, no API key)."""
    if not HAS_DDG:
        return "Web search is not available. Install with: pip install ddgs"

    query = query.strip().rstrip("?!.")

    logger.info("Web search: '%s' (max %d results)", query, max_results)

    loop = asyncio.get_event_loop()

    def do_search():
        try:
            results = DDGS().text(query, max_results=max_results)
            return list(results) if results else []
        except Exception as e:
            logger.error("DuckDuckGo text search error: %s", e)
            try:
                results = DDGS().answers(query)
                return list(results) if results else []
            except Exception as e2:
                logger.error("DuckDuckGo answers fallback error: %s", e2)
                return None

    results = await loop.run_in_executor(None, do_search)

    if results is None:
        return f"Search failed for: {query}. Please try again."

    if not results:
        return f"No results found for: {query}"

    lines = [f"Search results for '{query}':\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        url = r.get("href", r.get("link", r.get("url", "")))
        snippet = r.get("body", r.get("snippet", r.get("text", "")))
        lines.append(f"{i}. {title}")
        if url:
            lines.append(f"   URL: {url}")
        if snippet:
            lines.append(f"   {snippet[:300]}")
        lines.append("")

    return "\n".join(lines)


async def search_news(query: str, max_results: int = 5) -> str:
    """Search for recent news using DuckDuckGo."""
    if not HAS_DDG:
        return "Web search is not available. Install with: pip install ddgs"

    query = query.strip().rstrip("?!.")
    logger.info("News search: '%s'", query)

    loop = asyncio.get_event_loop()

    def do_search():
        try:
            results = DDGS().news(query, max_results=max_results)
            return list(results) if results else []
        except Exception as e:
            logger.error("News search error: %s", e)
            return None

    results = await loop.run_in_executor(None, do_search)

    if results is None:
        return "News search failed."

    if not results:
        return f"No news found for: {query}"

    lines = [f"News results for '{query}':\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        url = r.get("url", r.get("link", ""))
        source = r.get("source", "")
        date = r.get("date", "")
        snippet = r.get("body", "")
        lines.append(f"{i}. {title}")
        if source or date:
            lines.append(f"   Source: {source}  Date: {date}")
        if url:
            lines.append(f"   URL: {url}")
        if snippet:
            lines.append(f"   {snippet[:200]}")
        lines.append("")

    return "\n".join(lines)


async def search_and_read(query: str, max_results: int = 3) -> str:
    """Search the web and fetch the top result's page content."""
    if not HAS_DDG:
        return "Web search is not available. Install with: pip install ddgs"

    query = query.strip().rstrip("?!.")
    logger.info("Search and read: '%s'", query)

    loop = asyncio.get_event_loop()

    def do_search():
        try:
            results = DDGS().text(query, max_results=max_results)
            return list(results) if results else []
        except Exception as e:
            logger.error("Search error: %s", e)
            return []

    results = await loop.run_in_executor(None, do_search)

    if not results:
        return f"No results found for: {query}"

    lines = [f"Results for '{query}':\n"]
    top_url = None
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        url = r.get("href", r.get("link", r.get("url", "")))
        snippet = r.get("body", r.get("snippet", r.get("text", "")))
        if url and url.startswith("http") and top_url is None:
            top_url = url
        lines.append(f"{i}. {title}")
        if snippet:
            lines.append(f"   {snippet[:300]}")
        lines.append("")

    search_text = "\n".join(lines)

    all_urls = []
    for r in results:
        url = r.get("href", r.get("link", r.get("url", "")))
        if url and url.startswith("http"):
            all_urls.append(url)

    if all_urls:
        from jarvis.tools.web_browse import fetch_page_text
        for url in all_urls:
            logger.info("Fetching result: %s", url)
            try:
                page_content = await fetch_page_text(url, max_chars=3000)
                # Check if we actually got useful content (not an error page)
                if page_content and len(page_content) > 100 and "403" not in page_content[:50]:
                    return f"{search_text}\n--- Detailed content from {url} ---\n{page_content}"
                else:
                    logger.warning("Fetch returned minimal or error content, trying next result.")
            except Exception as e:
                logger.warning("Failed to fetch %s: %s. Trying next result.", url, e)

    return search_text
