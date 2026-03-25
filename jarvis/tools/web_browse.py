"""JARVIS Web Browsing: fetch and extract text from web pages using httpx and BeautifulSoup."""
import logging
import re
from urllib.parse import urljoin

logger = logging.getLogger("jarvis.tools.web_browse")

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    logger.warning("beautifulsoup4 not installed. Web page reading limited.")


async def fetch_page_text(url: str, max_chars: int = 5000) -> str:
    """Fetch a web page and extract its readable text content."""
    if not HAS_HTTPX:
        return "httpx not installed. Cannot fetch web pages."

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    logger.info("Fetching page: %s", url)

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36"
            }
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

    except httpx.TimeoutException:
        return f"Timeout fetching {url}"
    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code} fetching {url}"
    except Exception as e:
        return f"Error fetching {url}: {e}"

    if HAS_BS4:
        return _extract_text_bs4(html, url, max_chars)
    else:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return f"Content from {url}:\n{text}"


def _extract_text_bs4(html: str, url: str, max_chars: int) -> str:
    """Extract readable text from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    main = (
        soup.find("main") or
        soup.find("article") or
        soup.find(id="content") or
        soup.find(class_="content") or
        soup.body or
        soup
    )

    title = soup.title.string if soup.title else ""
    text = main.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    text = "\n".join(lines)

    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"

    result = f"Page: {title}\nURL: {url}\n\n{text}"
    return result


async def fetch_page_links(url: str, max_links: int = 20) -> str:
    """Fetch a web page and extract all links."""
    if not HAS_HTTPX or not HAS_BS4:
        return "Required libraries not installed (httpx, beautifulsoup4)."

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        return f"Error fetching {url}: {e}"

    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        text = a_tag.get_text(strip=True)[:80]

        if href.startswith("/"):
            href = urljoin(url, href)

        if href.startswith(("#", "javascript:", "mailto:")):
            continue

        if text:
            links.append(f"  {text}: {href}")
        else:
            links.append(f"  {href}")

        if len(links) >= max_links:
            break

    if not links:
        return f"No links found on {url}"

    return f"Links from {url}:\n" + "\n".join(links)
