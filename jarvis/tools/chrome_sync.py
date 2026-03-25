"""Extract and inject Chrome cookies into Playwright browser context via macOS Keychain."""

import logging
import os
import platform
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.tools.chrome_sync")

_pycookiecheat_available = False
try:
    from pycookiecheat import BrowserType, get_cookies  # noqa: F401
    _pycookiecheat_available = True
except ImportError:
    logger.warning(
        "pycookiecheat is not installed. Chrome cookie sync will be disabled. "
        "To enable it, run: pip install pycookiecheat"
    )

CHROME_COOKIE_DB = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "Cookies"

DEFAULT_SYNC_DOMAINS = [
    ".google.com",
    ".github.com",
    ".linkedin.com",
    ".twitter.com",
    ".x.com",
    ".youtube.com",
    ".reddit.com",
    ".amazon.com",
    ".microsoft.com",
    ".outlook.com",
    ".live.com",
    ".stackoverflow.com",
    ".notion.so",
    ".slack.com",
    ".discord.com",
    ".facebook.com",
    ".instagram.com",
    ".chatgpt.com",
    ".openai.com",
    ".anthropic.com",
    ".claude.ai",
    ".trello.com",
    ".atlassian.com",
    ".jira.com",
    ".figma.com",
    ".vercel.app",
    ".netlify.app",
]


def _get_chrome_cookie_db() -> Optional[Path]:
    """Locate Chrome's Cookies database file on macOS."""
    if platform.system() != "Darwin":
        logger.warning("Chrome cookie sync is only supported on macOS.")
        return None

    if not CHROME_COOKIE_DB.exists():
        logger.warning("Chrome cookie database not found at: %s", CHROME_COOKIE_DB)
        return None

    return CHROME_COOKIE_DB


def _read_raw_cookies(
    domains: list[str] | None = None,
) -> list[dict]:
    """Read cookies from Chrome's SQLite database with Keychain decryption."""
    db_path = _get_chrome_cookie_db()
    if not db_path:
        return []

    target_domains = domains or DEFAULT_SYNC_DOMAINS

    if not _pycookiecheat_available:
        return []

    tmp_db = tempfile.mktemp(suffix=".db")
    try:
        shutil.copy2(str(db_path), tmp_db)
    except (PermissionError, OSError) as e:
        logger.error("Cannot copy Chrome cookie DB: %s", e)
        return []

    playwright_cookies = []
    seen = set()  # Dedup cookies by (name, domain, path)

    for domain in target_domains:
        url = f"https://{domain.lstrip('.')}"
        try:
            from pycookiecheat import BrowserType, get_cookies
            cookies = get_cookies(url, browser=BrowserType.CHROMIUM, as_cookies=True)

            for cookie in cookies:
                key = (cookie.name, cookie.domain, cookie.path)
                if key in seen:
                    continue
                seen.add(key)

                pw_cookie = {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path or "/",
                    "secure": cookie.secure,
                    "httpOnly": bool(
                        getattr(cookie, "has_nonstandard_attr", lambda x: False)(
                            "HttpOnly"
                        )
                    ),
                }

                if cookie.expires:
                    pw_cookie["expires"] = cookie.expires

                same_site = getattr(cookie, "get_nonstandard_attr", lambda x: None)(
                    "SameSite"
                )
                if same_site:
                    pw_cookie["sameSite"] = same_site
                else:
                    pw_cookie["sameSite"] = "Lax"

                playwright_cookies.append(pw_cookie)

        except Exception as e:
            logger.debug("No cookies for %s: %s", domain, e)
            continue

    try:
        os.unlink(tmp_db)
    except OSError:
        pass

    logger.info(
        "Extracted %d cookies from Chrome for %d domain(s).",
        len(playwright_cookies),
        len(target_domains),
    )
    return playwright_cookies


async def sync_chrome_cookies(
    context,
    domains: list[str] | None = None,
) -> str:
    """Sync cookies from Chrome into a Playwright browser context."""
    if context is None:
        return "Error: no browser context available. Start the browser first."

    cookies = _read_raw_cookies(domains)

    if not cookies:
        return (
            "No cookies found to sync. Make sure Chrome is installed and "
            "you've visited the target sites at least once."
        )

    try:
        await context.add_cookies(cookies)
    except Exception as e:
        return f"Error injecting cookies into Playwright: {e}"

    # Summarize which domains got cookies
    domain_counts: dict[str, int] = {}
    for c in cookies:
        d = c["domain"].lstrip(".")
        parts = d.split(".")
        if len(parts) > 2:
            d = ".".join(parts[-2:])
        domain_counts[d] = domain_counts.get(d, 0) + 1

    summary_parts = []
    for d, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        summary_parts.append(f"  {d}: {count} cookies")

    summary = (
        f"Synced {len(cookies)} cookies from Chrome into JARVIS browser.\n"
        f"Domains synced:\n" + "\n".join(summary_parts[:15])
    )
    if len(summary_parts) > 15:
        summary += f"\n  ... and {len(summary_parts) - 15} more domains"

    logger.info("Chrome cookie sync complete: %d cookies injected.", len(cookies))
    return summary


async def sync_chrome_for_url(context, url: str) -> str:
    """Sync Chrome cookies for a specific URL's domain."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    domain = parsed.hostname
    if not domain:
        return f"Error: could not parse domain from URL: {url}"

    # Build domain variants to match (e.g., ".github.com" and "github.com")
    domain_variants = [f".{domain}", domain]

    # Also try the parent domain (e.g., for "api.github.com", also sync ".github.com")
    parts = domain.split(".")
    if len(parts) > 2:
        parent = ".".join(parts[-2:])
        domain_variants.extend([f".{parent}", parent])

    return await sync_chrome_cookies(context, domains=domain_variants)
