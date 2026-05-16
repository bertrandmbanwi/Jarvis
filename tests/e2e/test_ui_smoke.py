"""Playwright smoke test for the Next.js UI."""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("JARVIS_E2E_BASE_URL"),
    reason="Set JARVIS_E2E_BASE_URL to run UI smoke tests.",
)


def test_login_screen_renders():
    from playwright.sync_api import expect, sync_playwright

    base_url = os.environ["JARVIS_E2E_BASE_URL"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(base_url, wait_until="networkidle")
        expect(page).to_have_title("J.A.R.V.I.S.")
        expect(page.get_by_text("J.A.R.V.I.S.").first).to_be_visible()
        browser.close()
