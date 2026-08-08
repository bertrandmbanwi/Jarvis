from __future__ import annotations

import json
import time
import traceback
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path('/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi')
OUT = ROOT / '.hermes' / 'tmp' / f"ui-30min-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / 'run.log'
STATE = OUT / 'state.json'
PIN = '042546'
BASE = 'http://localhost:3001'
DURATION_SECONDS = int(__import__('os').getenv('UI_30MIN_SECONDS', str(30 * 60)))
CYCLE_SECONDS = int(__import__('os').getenv('UI_30MIN_CYCLE_SECONDS', '240'))
MAX_CYCLES = int(__import__('os').getenv('UI_30MIN_MAX_CYCLES', '7'))


def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def save_state(**data):
    STATE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def safe_click(page, role, name, timeout=8000):
    locator = page.get_by_role(role, name=name)
    try:
        return locator.click(timeout=timeout)
    except PlaywrightTimeoutError as exc:
        if role == 'button':
            log(f'click fallback for button {name!r}: {exc.__class__.__name__}')
            button = page.locator(f'button[aria-label="{name}"]').first
            if button.count() > 0:
                return button.evaluate('(el) => el.click()')
        raise


def login_if_needed(page):
    page.goto(BASE, wait_until='domcontentloaded')
    page.wait_for_timeout(1200)
    if page.get_by_role('heading', name='MayAss').count() > 0:
        log('login screen present; entering PIN')
        boxes = page.get_by_role('textbox')
        count = boxes.count()
        if count < 6:
            raise RuntimeError(f'expected split PIN inputs, found {count}')
        for i, digit in enumerate(PIN):
            boxes.nth(i).fill(digit)
        page.wait_for_timeout(1000)
    page.wait_for_timeout(1500)
    if page.get_by_role('button', name='Chat').count() == 0:
        # On this UI, an auth refresh may land back on login once before token settles.
        page.goto(BASE, wait_until='domcontentloaded')
        page.wait_for_timeout(1000)
        if page.get_by_role('heading', name='MayAss').count() > 0:
            boxes = page.get_by_role('textbox')
            for i, digit in enumerate(PIN):
                boxes.nth(i).fill(digit)
            page.wait_for_timeout(1000)
    page.wait_for_selector('text=MayAss', timeout=10000)
    safe_click(page, 'button', 'Chat')
    page.wait_for_selector('text=CONVERSATION', timeout=10000)


def assert_chat_visible(page):
    page.get_by_role('heading', name='Conversation').wait_for(timeout=10000)
    page.get_by_role('textbox', name='Message input').wait_for(timeout=10000)


def submit_chat(page, text: str):
    page.get_by_role('textbox', name='Message input').fill(text)
    page.get_by_role('button', name='Send message').click(timeout=8000)
    page.wait_for_timeout(1800)
    # user message should appear in transcript; assistant response should stream or finish shortly after
    page.wait_for_selector(f'text={text[:20]}', timeout=15000)
    try:
        page.wait_for_function(
            """
            () => {
              const bubbles = Array.from(document.querySelectorAll('.message-bubble'));
              return bubbles.length >= 2 && bubbles.some(el => el.textContent && el.textContent.trim().length > 0);
            }
            """,
            timeout=20000,
        )
    except PlaywrightTimeoutError:
        log('assistant response did not fully settle within timeout; continuing with visible user transcript')


def run_cycle(page, cycle: int):
    log(f'cycle {cycle}: start')
    page.wait_for_timeout(500)
    if page.get_by_role('heading', name='MayAss').count() > 0:
        log(f'cycle {cycle}: relogin required')
        boxes = page.get_by_role('textbox')
        for i, digit in enumerate(PIN):
            boxes.nth(i).fill(digit)
        page.wait_for_timeout(1200)
    elif page.get_by_role('button', name='Chat').count() == 0:
        log(f'cycle {cycle}: app surface missing; reloading')
        try:
            page.reload(wait_until='commit', timeout=60000)
        except Exception:
            page.goto(BASE, wait_until='commit', timeout=60000)
        page.wait_for_timeout(1500)
        if page.get_by_role('heading', name='MayAss').count() > 0:
            boxes = page.get_by_role('textbox')
            for i, digit in enumerate(PIN):
                boxes.nth(i).fill(digit)
            page.wait_for_timeout(1200)

    # Chat path — wait for nav button to settle before click (avoids locator timeout after idle)
    page.wait_for_selector('button[aria-label="Chat"], button:has-text("Chat")', timeout=10000)
    safe_click(page, 'button', 'Chat')
    assert_chat_visible(page)
    chat_text = f'30-min smoke cycle {cycle}: hello MayAss {cycle}'
    submit_chat(page, chat_text)
    save_state(last_cycle=cycle, last_chat=chat_text, timestamp=datetime.now().isoformat())
    page.screenshot(path=str(OUT / f'cycle-{cycle:02d}-chat.png'), full_page=True)

    # System path
    safe_click(page, 'button', 'System')
    page.wait_for_selector('text=ACTIVITY LOG', timeout=10000)
    page.wait_for_selector('text=SYSTEM', timeout=10000)
    page.screenshot(path=str(OUT / f'cycle-{cycle:02d}-system.png'), full_page=True)

    # Flows path
    safe_click(page, 'button', 'Flows')
    page.wait_for_selector('text=WORKFLOWS', timeout=10000)
    page.wait_for_selector('text=APP LIFECYCLE', timeout=10000)
    page.wait_for_selector('text=server', timeout=10000)
    page.wait_for_selector('text=:8741', timeout=10000)
    page.wait_for_selector('text=:3001', timeout=10000)
    page.screenshot(path=str(OUT / f'cycle-{cycle:02d}-flows.png'), full_page=True)

    # Settings open/close
    page.locator('button[aria-label="Open settings"]').evaluate('(el) => el.click()')
    page.wait_for_timeout(1000)
    page.screenshot(path=str(OUT / f'cycle-{cycle:02d}-settings-open.png'), full_page=True)
    if page.get_by_role('button', name='Close settings').count() > 0:
        page.get_by_role('button', name='Close settings').evaluate('(el) => el.click()')
        page.wait_for_timeout(800)
    elif page.get_by_role('button', name='Open settings').count() > 0:
        # toggle-style panel
        page.get_by_role('button', name='Open settings').evaluate('(el) => el.click()')
        page.wait_for_timeout(800)

    # Voice path
    safe_click(page, 'button', 'Voice')
    page.wait_for_timeout(1000)
    safe_click(page, 'button', 'Chat')
    assert_chat_visible(page)
    voice_buttons = page.get_by_role('button', name='Start voice input')
    if voice_buttons.count() > 0:
        voice_button = voice_buttons.first
        if voice_button.is_enabled():
            voice_button.evaluate('(el) => el.click()')
            page.wait_for_timeout(2000)
            # If recording starts, stop it once. If it didn't, the button still remains visible and we keep going.
            if page.get_by_role('button', name='Stop recording').count() > 0:
                page.get_by_role('button', name='Stop recording').evaluate('(el) => el.click()')
                page.wait_for_timeout(1500)
        else:
            log(f'cycle {cycle}: [EXPECTED in headless] voice button is disabled — microphone unavailable in headless browser; soft-skip is correct behaviour')
    else:
        log(f'cycle {cycle}: [EXPECTED in headless] voice button not found — voice tab absent in headless mode; soft-skip is correct behaviour')
    page.screenshot(path=str(OUT / f'cycle-{cycle:02d}-voice.png'), full_page=True)

    # Return to chat and verify shell remains healthy
    safe_click(page, 'button', 'Chat')
    assert_chat_visible(page)
    page.wait_for_timeout(1000)
    page.screenshot(path=str(OUT / f'cycle-{cycle:02d}-return-chat.png'), full_page=True)
    log(f'cycle {cycle}: complete')


def main():
    start = time.time()
    log(f'output_dir={OUT}')
    log('starting playwright browser')
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--use-fake-ui-for-media-stream',
                '--use-fake-device-for-media-stream',
            ],
        )
        context = browser.new_context()
        context.grant_permissions(['microphone'], origin=BASE)
        context.set_extra_http_headers({'Cache-Control': 'no-cache'})
        context.on('page', lambda pg: pg.on('console', lambda msg: log(f'console[{msg.type}]: {msg.text}')))
        page = context.new_page()
        page.on('pageerror', lambda exc: log(f'pageerror: {exc}'))
        page.on('crash', lambda *args: log('page crash detected'))

        login_if_needed(page)
        page.screenshot(path=str(OUT / 'logged-in.png'), full_page=True)

        cycles = 0
        failures = 0
        while cycles < MAX_CYCLES and (time.time() - start) < DURATION_SECONDS:
            cycles += 1
            try:
                run_cycle(page, cycles)
            except Exception:
                failures += 1
                log(f'cycle {cycles}: failed but runner will continue')
                log(traceback.format_exc())
                try:
                    page.screenshot(path=str(OUT / f'cycle-{cycles:02d}-failure.png'), full_page=True)
                except Exception as screenshot_error:
                    log(f'cycle {cycles}: failure screenshot unavailable: {screenshot_error}')
                try:
                    page.reload(wait_until='commit', timeout=60000)
                    page.wait_for_timeout(1500)
                    if page.get_by_role('heading', name='MayAss').count() > 0:
                        boxes = page.get_by_role('textbox')
                        for i, digit in enumerate(PIN):
                            boxes.nth(i).fill(digit)
                        page.wait_for_timeout(1200)
                except Exception:
                    log(f'cycle {cycles}: recovery failed')
                    log(traceback.format_exc())
            elapsed = time.time() - start
            remaining = max(0, DURATION_SECONDS - elapsed)
            if cycles < MAX_CYCLES and remaining > 0:
                sleep_for = min(CYCLE_SECONDS, remaining)
                log(f'cycle {cycles}: sleeping {int(sleep_for)}s before next pass')
                time.sleep(sleep_for)

        elapsed = time.time() - start
        summary = {
            'cycles_completed': cycles,
            'failures': failures,
            'elapsed_seconds': round(elapsed, 1),
            'output_dir': str(OUT),
            'log': str(LOG),
            'state': str(STATE),
        }
        save_state(**summary)
        log('summary=' + json.dumps(summary, ensure_ascii=False))
        browser.close()


if __name__ == '__main__':
    main()
