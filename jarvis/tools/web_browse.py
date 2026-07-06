"""JARVIS Web Browsing: fetch and extract text from web pages using httpx and BeautifulSoup."""
import ipaddress
import logging
import re
import socket
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


def _is_url_safe(url: str) -> tuple[bool, str]:
    """Block requests to private/reserved IPs, localhost, and metadata endpoints."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Explicit blocklist, not a bind address.
    blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}  # nosec
    if hostname.lower() in blocked_hosts:
        return False, f"Blocked: requests to {hostname} not allowed"

    # Block cloud metadata endpoints
    if hostname in ("169.254.169.254", "metadata.google.internal"):
        return False, "Blocked: cloud metadata endpoint"

    try:
        resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _family, _, _, _, addr in resolved:
            ip = ipaddress.ip_address(addr[0])
            if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local:
                return False, f"Blocked: {hostname} resolves to private/reserved IP {ip}"
    except (socket.gaierror, ValueError):
        pass

    return True, "OK"


class _UnsafeURLError(Exception):
    """Raised when a URL — or a redirect target — fails SSRF validation."""


async def _fetch_html(
    url: str,
    *,
    user_agent: str,
    timeout: float = 15.0,
    max_redirects: int = 5,
) -> tuple[str, str]:
    """Fetch HTML, re-checking SSRF safety on the initial URL and each redirect hop.

    Redirects are followed manually (follow_redirects=False) so a benign-looking
    URL that 3xx-redirects to an internal address (e.g. 169.254.169.254 or a
    private IP) is blocked — httpx's built-in redirect following would not re-run
    _is_url_safe on the new location. Returns (html, final_url).
    """
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": user_agent},
    ) as client:
        current = url
        for _ in range(max_redirects + 1):
            safe, reason = _is_url_safe(current)
            if not safe:
                raise _UnsafeURLError(reason)
            resp = await client.get(current)
            if resp.next_request is not None:
                current = str(resp.next_request.url)
                continue
            resp.raise_for_status()
            return resp.text, current
    raise _UnsafeURLError(f"Too many redirects fetching {url}")


async def fetch_page_text(url: str, max_chars: int = 5000) -> str:
    """Fetch a web page and extract its readable text content."""
    if not HAS_HTTPX:
        return "httpx not installed. Cannot fetch web pages."

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    logger.info("Fetching page: %s", url)

    try:
        html, final_url = await _fetch_html(
            url,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
        )
    except _UnsafeURLError as e:
        return str(e)
    except httpx.TimeoutException:
        return f"Timeout fetching {url}"
    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code} fetching {url}"
    except Exception as e:
        return f"Error fetching {url}: {e}"

    if HAS_BS4:
        return _extract_text_bs4(html, final_url, max_chars)
    else:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return f"Content from {final_url}:\n{text}"


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
        html, final_url = await _fetch_html(url, user_agent="Mozilla/5.0")
    except _UnsafeURLError as e:
        return str(e)
    except Exception as e:
        return f"Error fetching {url}: {e}"

    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = str(a_tag.get("href", ""))
        text = a_tag.get_text(strip=True)[:80]

        if href.startswith("/"):
            href = urljoin(final_url, href)

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
