"""Free public data APIs for deterministic lookups.

These tools intentionally use no API keys. They give JARVIS a cheap first path
for factual data questions before falling back to web search or an LLM.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger("jarvis.tools.public_data")

HTTP_TIMEOUT_S = 10.0
USER_AGENT = "JarvisAssistant/0.3 (local personal assistant; https://github.com/public-apis/public-apis)"
SEC_USER_AGENT = os.getenv("JARVIS_SEC_USER_AGENT", "JarvisAssistant/0.3 local-user@example.com")

COUNTRY_ALIASES = {
    "america": "US",
    "england": "GB",
    "great britain": "GB",
    "uk": "GB",
    "united kingdom": "GB",
    "united states": "US",
    "united states of america": "US",
    "us": "US",
    "usa": "US",
}

CURRENCY_ALIASES = {
    "$": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "gbp": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
    "sterling": "GBP",
    "yen": "JPY",
    "yuan": "CNY",
}

CRYPTO_IDS = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "sol": "solana",
    "solana": "solana",
    "ada": "cardano",
    "cardano": "cardano",
    "doge": "dogecoin",
    "dogecoin": "dogecoin",
    "xrp": "ripple",
    "ripple": "ripple",
    "matic": "matic-network",
    "polygon": "matic-network",
    "bnb": "binancecoin",
    "binance": "binancecoin",
}

COMMON_SEC_COMPANIES: dict[str, dict[str, Any]] = {
    "AAPL": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "APPLE": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "MSFT": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp."},
    "MICROSOFT": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp."},
    "GOOG": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
    "GOOGL": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
    "ALPHABET": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
    "AMZN": {"cik_str": 1018724, "ticker": "AMZN", "title": "Amazon.com Inc."},
    "AMAZON": {"cik_str": 1018724, "ticker": "AMZN", "title": "Amazon.com Inc."},
    "META": {"cik_str": 1326801, "ticker": "META", "title": "Meta Platforms Inc."},
    "NVDA": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corp."},
    "NVIDIA": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corp."},
    "TSLA": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla Inc."},
    "TESLA": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla Inc."},
}


def _normalize_currency(value: str) -> str:
    cleaned = value.strip().lower()
    return CURRENCY_ALIASES.get(cleaned, cleaned.upper())


def _normalize_country_code(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        return "US"
    if cleaned in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[cleaned]
    if re.fullmatch(r"[a-zA-Z]{2}", cleaned):
        return cleaned.upper()
    return cleaned.upper()


def _format_number(value: Any, *, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}".rstrip("0").rstrip(".")


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


async def _get_json(url: str, params: dict[str, Any] | None = None, *, headers: dict[str, str] | None = None) -> Any:
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S, headers=request_headers, follow_redirects=True) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def _sec_headers() -> dict[str, str]:
    return {
        "User-Agent": SEC_USER_AGENT,
        "Accept": "application/json",
    }


async def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert money using Frankfurter, with Fawaz Currency API as a no-key fallback."""
    base = _normalize_currency(from_currency)
    target = _normalize_currency(to_currency)
    if amount <= 0:
        return "Please provide an amount greater than zero."
    if base == target:
        return f"{_format_number(amount)} {base} is still {_format_number(amount)} {target}."

    try:
        data = await _get_json(
            "https://api.frankfurter.dev/v1/latest",
            {"amount": amount, "from": base, "to": target},
        )
        rate_value = data.get("rates", {}).get(target)
        if rate_value is not None:
            date_value = data.get("date", "latest available")
            return (
                f"{_format_number(amount)} {base} is {_format_number(rate_value)} {target} "
                f"using Frankfurter rates from {date_value}."
            )
    except Exception as exc:
        logger.info("Frankfurter currency lookup failed for %s/%s: %s", base, target, exc)

    try:
        fawaz_base = base.lower()
        fawaz_target = target.lower()
        data = await _get_json(
            f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{fawaz_base}.json"
        )
        rates = data.get(fawaz_base, {})
        rate = rates.get(fawaz_target)
        if rate is not None:
            converted = amount * float(rate)
            date_value = data.get("date", "latest available")
            return (
                f"{_format_number(amount)} {base} is {_format_number(converted)} {target} "
                f"using Fawaz Currency API rates from {date_value}."
            )
    except Exception as exc:
        logger.info("Fawaz currency fallback failed for %s/%s: %s", base, target, exc)

    return f"Could not convert {base} to {target} from the free currency APIs right now."


async def get_crypto_price(asset: str, vs_currency: str = "usd") -> str:
    """Get a cryptocurrency spot price from CoinGecko's free simple price API."""
    cleaned = asset.strip().lower()
    coin_id = CRYPTO_IDS.get(cleaned, cleaned.replace(" ", "-"))
    quote = _normalize_currency(vs_currency).lower()

    try:
        data = await _get_json(
            "https://api.coingecko.com/api/v3/simple/price",
            {"ids": coin_id, "vs_currencies": quote},
        )
        price = data.get(coin_id, {}).get(quote)
        if price is None:
            return f"CoinGecko did not return a price for {asset} in {quote.upper()}."
        return f"{coin_id.replace('-', ' ').title()} is {_format_number(price)} {quote.upper()} on CoinGecko."
    except Exception as exc:
        logger.error("CoinGecko lookup failed for %s/%s: %s", coin_id, quote, exc)
        return f"Could not retrieve the crypto price for {asset} right now."


async def get_public_holidays(country_code: str = "US", year: int | None = None) -> str:
    """List public holidays for a country and year using Nager.Date."""
    resolved_year = year or datetime.now().year
    country = _normalize_country_code(country_code)

    try:
        data = await _get_json(f"https://date.nager.at/api/v3/PublicHolidays/{resolved_year}/{country}")
    except Exception as exc:
        logger.error("Nager.Date holiday lookup failed for %s/%s: %s", country, resolved_year, exc)
        return f"Could not retrieve {country} public holidays for {resolved_year} right now."

    if not data:
        return f"No public holidays were returned for {country} in {resolved_year}."

    lines = [f"Public holidays in {country} for {resolved_year}:"]
    for item in data[:20]:
        lines.append(f"- {item.get('date')}: {item.get('name') or item.get('localName')}")
    if len(data) > 20:
        lines.append(f"...and {len(data) - 20} more.")
    return "\n".join(lines)


async def get_next_public_holiday(country_code: str = "US") -> str:
    """Return the next public holiday for a country using Nager.Date."""
    country = _normalize_country_code(country_code)
    today = datetime.now().date()

    holidays: list[dict[str, Any]] = []
    for year in (today.year, today.year + 1):
        try:
            data = await _get_json(f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country}")
            if isinstance(data, list):
                holidays.extend(data)
        except Exception as exc:
            logger.error("Nager.Date next holiday lookup failed for %s/%s: %s", country, year, exc)
            return f"Could not retrieve upcoming {country} public holidays right now."

    future = []
    for item in holidays:
        holiday_date = _parse_date(str(item.get("date", "")))
        if holiday_date and holiday_date >= today:
            future.append((holiday_date, item))

    if not future:
        return f"I could not find an upcoming public holiday for {country}."

    holiday_date, item = sorted(future, key=lambda pair: pair[0])[0]
    days = (holiday_date - today).days
    day_text = "today" if days == 0 else f"in {days} days"
    return f"The next public holiday in {country} is {item.get('name') or item.get('localName')} on {holiday_date.isoformat()} ({day_text})."


async def is_public_holiday(country_code: str = "US", check_date: str = "") -> str:
    """Check whether a date is a public holiday using Nager.Date."""
    country = _normalize_country_code(country_code)
    target_date = _parse_date(check_date) if check_date else datetime.now().date()
    if target_date is None:
        return "Please provide the date in YYYY-MM-DD format."

    try:
        data = await _get_json(f"https://date.nager.at/api/v3/PublicHolidays/{target_date.year}/{country}")
    except Exception as exc:
        logger.error("Nager.Date holiday check failed for %s/%s: %s", country, target_date, exc)
        return f"Could not check public holidays for {country} right now."

    for item in data:
        if item.get("date") == target_date.isoformat():
            return f"Yes. {target_date.isoformat()} is {item.get('name') or item.get('localName')} in {country}."
    return f"No. {target_date.isoformat()} is not listed as a public holiday in {country}."


async def get_country_info(country: str) -> str:
    """Get country facts from REST Countries."""
    if not country.strip():
        return "Please provide a country name."

    encoded = quote(country.strip())
    urls = [
        f"https://restcountries.com/v3.1/name/{encoded}",
        f"https://restcountries.com/v3.1/alpha/{encoded}",
    ]
    data: Any = None
    for url in urls:
        try:
            data = await _get_json(url, {"fullText": "true"} if "/name/" in url else None)
            break
        except Exception as exc:
            logger.debug("REST Countries lookup variant failed for %s: %s", country, exc)
    if not data:
        return f"Could not find country information for {country}."

    item = data[0] if isinstance(data, list) else data
    name = item.get("name", {}).get("common", country)
    official = item.get("name", {}).get("official", "")
    capital = ", ".join(item.get("capital", [])) or "not listed"
    region = item.get("region", "not listed")
    subregion = item.get("subregion", "")
    population = _format_number(item.get("population"), digits=0)
    currencies = item.get("currencies", {})
    currency_text = ", ".join(
        f"{code} ({details.get('name', 'currency')})" for code, details in currencies.items()
    ) or "not listed"
    languages = item.get("languages", {})
    language_text = ", ".join(languages.values()) or "not listed"

    lines = [f"{name}"]
    if official and official != name:
        lines.append(f"Official name: {official}")
    lines.append(f"Capital: {capital}")
    lines.append(f"Region: {region}{f' / {subregion}' if subregion else ''}")
    lines.append(f"Population: {population}")
    lines.append(f"Currency: {currency_text}")
    lines.append(f"Languages: {language_text}")
    return "\n".join(lines)


async def get_sec_company_filings(ticker_or_cik: str, limit: int = 5) -> str:
    """Get recent SEC filings for a public company by ticker, name, or CIK."""
    company = await _resolve_sec_company(ticker_or_cik)
    if company is None:
        return f"Could not resolve '{ticker_or_cik}' to a public company in SEC EDGAR."

    cik = f"{int(company['cik_str']):010d}"
    try:
        data = await _get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=_sec_headers())
    except Exception as exc:
        logger.error("SEC submissions lookup failed for CIK %s: %s", cik, exc)
        return f"Could not retrieve SEC filings for {company['title']} right now."

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    documents = recent.get("primaryDocument", [])

    lines = [f"Recent SEC filings for {data.get('name', company['title'])} ({company['ticker']}):"]
    for index, form in enumerate(forms[: max(1, min(limit, 10))]):
        filing_date = dates[index] if index < len(dates) else "unknown date"
        accession = accessions[index] if index < len(accessions) else ""
        document = documents[index] if index < len(documents) else ""
        lines.append(f"- {filing_date}: {form} {document}".rstrip())
        if accession:
            accession_path = accession.replace("-", "")
            lines.append(f"  https://www.sec.gov/Archives/edgar/data/{int(company['cik_str'])}/{accession_path}/{document}")
    return "\n".join(lines)


async def _resolve_sec_company(ticker_or_cik: str) -> dict[str, Any] | None:
    query = ticker_or_cik.strip()
    if not query:
        return None
    if re.fullmatch(r"\d{1,10}", query):
        return {"cik_str": int(query), "ticker": f"CIK{query}", "title": f"CIK {query}"}

    common = COMMON_SEC_COMPANIES.get(query.upper())
    if common is not None:
        return common

    try:
        data = await _get_json("https://www.sec.gov/files/company_tickers.json", headers=_sec_headers())
    except Exception as exc:
        logger.error("SEC company ticker map lookup failed: %s", exc)
        return None

    records: list[dict[str, Any]] = [record for record in data.values() if isinstance(record, dict)] if isinstance(data, dict) else []
    lowered = query.lower()
    for record in records:
        if str(record.get("ticker", "")).lower() == lowered:
            return record
    for record in records:
        if lowered in str(record.get("title", "")).lower():
            return record
    return None


async def lookup_ip(ip_address: str) -> str:
    """Look up public IP location data using ipapi.co."""
    ip = ip_address.strip()
    if not re.fullmatch(r"[0-9a-fA-F:.]{3,45}", ip):
        return "Please provide a valid IPv4 or IPv6 address."

    try:
        data = await _get_json(f"https://ipapi.co/{ip}/json/")
    except Exception as exc:
        logger.error("IP lookup failed for %s: %s", ip, exc)
        return f"Could not look up IP address {ip} right now."

    if data.get("error"):
        return f"Could not look up IP address {ip}: {data.get('reason', 'unknown error')}."

    city = data.get("city") or "unknown city"
    region = data.get("region") or "unknown region"
    country = data.get("country_name") or data.get("country") or "unknown country"
    org = data.get("org") or "unknown network"
    return f"{ip} appears to be in {city}, {region}, {country}. Network: {org}."


async def get_spaceflight_news(query: str = "", limit: int = 5) -> str:
    """Get recent spaceflight news from Spaceflight News API."""
    params: dict[str, Any] = {"limit": max(1, min(limit, 10))}
    if query.strip():
        params["search"] = query.strip()

    try:
        data = await _get_json("https://api.spaceflightnewsapi.net/v4/articles/", params)
    except Exception as exc:
        logger.error("Spaceflight News lookup failed: %s", exc)
        return "Could not retrieve spaceflight news right now."

    results = data.get("results", [])
    if not results:
        return "No matching spaceflight news found."

    lines = ["Recent spaceflight news:"]
    for item in results[: params["limit"]]:
        title = item.get("title", "Untitled")
        site = item.get("news_site", "unknown source")
        url = item.get("url", "")
        lines.append(f"- {title} ({site})")
        if url:
            lines.append(f"  {url}")
    return "\n".join(lines)


async def get_citybike_networks(city: str = "", country: str = "", limit: int = 10) -> str:
    """Find bike-share networks from CityBikes."""
    try:
        data = await _get_json("https://api.citybik.es/v2/networks")
    except Exception as exc:
        logger.error("CityBikes lookup failed: %s", exc)
        return "Could not retrieve bike-share networks right now."

    city_filter = city.strip().lower()
    country_filter = country.strip().lower()
    matches = []
    for network in data.get("networks", []):
        location = network.get("location", {})
        if city_filter and city_filter not in str(location.get("city", "")).lower():
            continue
        if country_filter and country_filter not in str(location.get("country", "")).lower():
            continue
        matches.append(network)

    if not matches:
        filter_text = ", ".join(part for part in [city or "", country or ""] if part).strip()
        return f"No CityBikes networks found{f' for {filter_text}' if filter_text else ''}."

    display_limit = max(1, min(limit, 20))
    lines = ["CityBikes networks:"]
    for network in matches[:display_limit]:
        location = network.get("location", {})
        lines.append(
            f"- {network.get('name', network.get('id', 'Unknown'))}: "
            f"{location.get('city', 'unknown city')}, {location.get('country', 'unknown country')}"
        )
    if len(matches) > display_limit:
        lines.append(f"...and {len(matches) - display_limit} more.")
    return "\n".join(lines)


async def check_public_api_status() -> str:
    """Run a lightweight health check against the selected no-key public APIs."""
    checks = [
        ("Nager.Date", "https://date.nager.at/api/v3/PublicHolidays/2026/US", None),
        ("Frankfurter", "https://api.frankfurter.dev/v1/latest", {"amount": 1, "from": "USD", "to": "EUR"}),
        ("CoinGecko", "https://api.coingecko.com/api/v3/simple/price", {"ids": "bitcoin", "vs_currencies": "usd"}),
        ("REST Countries", "https://restcountries.com/v3.1/name/cameroon", {"fullText": "true"}),
        ("SEC EDGAR", "https://www.sec.gov/files/company_tickers.json", None),
        ("Spaceflight News", "https://api.spaceflightnewsapi.net/v4/articles/", {"limit": 1}),
        ("CityBikes", "https://api.citybik.es/v2/networks", None),
    ]

    lines = ["Public API status:"]
    for name, url, params in checks:
        try:
            await _get_json(url, params, headers=_sec_headers() if name == "SEC EDGAR" else None)
            lines.append(f"- {name}: OK")
        except Exception as exc:
            lines.append(f"- {name}: unavailable ({str(exc)[:80]})")
    return "\n".join(lines)
