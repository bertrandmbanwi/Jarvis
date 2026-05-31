"""Tests for free public-data tools."""
import pytest

from jarvis.tools import public_data


@pytest.mark.asyncio
async def test_convert_currency_uses_frankfurter(monkeypatch):
    async def fake_get_json(url, params=None, *, headers=None):
        assert url == "https://api.frankfurter.dev/v1/latest"
        assert params == {"amount": 100, "from": "USD", "to": "EUR"}
        return {"amount": 100, "base": "USD", "date": "2026-05-28", "rates": {"EUR": 86.08}}

    monkeypatch.setattr(public_data, "_get_json", fake_get_json)

    result = await public_data.convert_currency(100, "usd", "eur")

    assert "100 USD is 86.08 EUR" in result
    assert "Frankfurter" in result


@pytest.mark.asyncio
async def test_convert_currency_falls_back_to_fawaz(monkeypatch):
    calls = []

    async def fake_get_json(url, params=None, *, headers=None):
        calls.append(url)
        if "frankfurter" in url:
            raise RuntimeError("primary down")
        return {"date": "2026-05-28", "usd": {"cad": 1.37}}

    monkeypatch.setattr(public_data, "_get_json", fake_get_json)

    result = await public_data.convert_currency(10, "USD", "CAD")

    assert len(calls) == 2
    assert "10 USD is 13.7 CAD" in result
    assert "Fawaz" in result


@pytest.mark.asyncio
async def test_get_crypto_price_formats_common_ticker(monkeypatch):
    async def fake_get_json(url, params=None, *, headers=None):
        assert params == {"ids": "bitcoin", "vs_currencies": "usd"}
        return {"bitcoin": {"usd": 73022}}

    monkeypatch.setattr(public_data, "_get_json", fake_get_json)

    result = await public_data.get_crypto_price("BTC")

    assert "Bitcoin is 73,022 USD" in result


@pytest.mark.asyncio
async def test_get_next_public_holiday(monkeypatch):
    async def fake_get_json(url, params=None, *, headers=None):
        return [
            {"date": "2026-01-01", "name": "New Year's Day"},
            {"date": "2999-12-25", "name": "Christmas Day"},
        ]

    monkeypatch.setattr(public_data, "_get_json", fake_get_json)

    result = await public_data.get_next_public_holiday("US")

    assert "Christmas Day" in result
    assert "2999-12-25" in result


@pytest.mark.asyncio
async def test_country_info_formats_rest_countries_payload(monkeypatch):
    async def fake_get_json(url, params=None, *, headers=None):
        return [
            {
                "name": {"common": "Cameroon", "official": "Republic of Cameroon"},
                "capital": ["Yaounde"],
                "region": "Africa",
                "subregion": "Middle Africa",
                "population": 26545864,
                "currencies": {"XAF": {"name": "Central African CFA franc"}},
                "languages": {"eng": "English", "fra": "French"},
            }
        ]

    monkeypatch.setattr(public_data, "_get_json", fake_get_json)

    result = await public_data.get_country_info("Cameroon")

    assert "Cameroon" in result
    assert "Capital: Yaounde" in result
    assert "XAF" in result
    assert "English, French" in result


@pytest.mark.asyncio
async def test_sec_company_filings_resolves_ticker(monkeypatch):
    async def fake_get_json(url, params=None, *, headers=None):
        if url.endswith("company_tickers.json"):
            return {"0": {"cik_str": 999999, "ticker": "FAKE", "title": "Fake Corp."}}
        return {
            "name": "Fake Corp.",
            "filings": {
                "recent": {
                    "form": ["10-Q"],
                    "filingDate": ["2026-05-01"],
                    "accessionNumber": ["0000320193-26-000001"],
                    "primaryDocument": ["aapl-20260501.htm"],
                }
            },
        }

    monkeypatch.setattr(public_data, "_get_json", fake_get_json)

    result = await public_data.get_sec_company_filings("FAKE")

    assert "Recent SEC filings for Fake Corp. (FAKE)" in result
    assert "10-Q" in result
    assert "sec.gov/Archives" in result


@pytest.mark.asyncio
async def test_lookup_ip_formats_ipapi_payload(monkeypatch):
    async def fake_get_json(url, params=None, *, headers=None):
        return {
            "city": "Mountain View",
            "region": "California",
            "country_name": "United States",
            "org": "Google LLC",
        }

    monkeypatch.setattr(public_data, "_get_json", fake_get_json)

    result = await public_data.lookup_ip("8.8.8.8")

    assert "Mountain View" in result
    assert "Google LLC" in result


@pytest.mark.asyncio
async def test_public_api_status_returns_structured_provider_health(monkeypatch):
    monkeypatch.setattr(public_data, "_STATUS_CACHE", {"checked_at": 0.0, "payload": None})
    monkeypatch.setattr(
        public_data,
        "_public_api_checks",
        lambda: [
            {"name": "Provider One", "category": "test", "url": "https://example.test/one"},
            {"name": "Provider Two", "category": "test", "url": "https://example.test/two"},
        ],
    )

    async def fake_get_json(url, params=None, *, headers=None):
        if url.endswith("/two"):
            raise RuntimeError("provider down")
        return {"ok": True}

    monkeypatch.setattr(public_data, "_get_json", fake_get_json)

    status = await public_data.get_public_api_status(force=True)

    assert status["provider_count"] == 2
    assert status["healthy_count"] == 1
    assert status["degraded_count"] == 1
    assert status["providers"][0]["status"] == "ok"
    assert status["providers"][1]["status"] == "unavailable"
