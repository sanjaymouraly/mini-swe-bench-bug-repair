"""Playwright browser smoke and UI navigation tests for the Mini SWE-Bench dashboard."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest
import uvicorn

from bugbench.api.app import create_app
from bugbench.config import AppConfig


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def live_dashboard_url(test_config: AppConfig) -> Generator[str, None, None]:
    app = create_app(test_config)
    port = _find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(40):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=3.0)


def _playwright_browsers_available() -> bool:
    """Return True when a Chromium binary is actually installed for Playwright.

    The browser is installed in several places depending on how Playwright was
    provisioned, so this asks Playwright itself rather than guessing a path.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
            return bool(path) and Path(path).exists()
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False


def test_playwright_dashboard_navigation_and_task_inspection(
    live_dashboard_url: str,
) -> None:
    if not _playwright_browsers_available():
        pytest.skip(
            "Playwright Chromium is not installed. Run `playwright install chromium` "
            "to enable the dashboard browser smoke test."
        )

    from playwright.sync_api import sync_playwright

    console_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text()) if msg.type == "error" else None,
        )

        page.goto(live_dashboard_url, wait_until="networkidle")

        # Verify title and official SWE-bench independence disclaimer
        assert "Mini SWE-Bench" in page.title()
        disclaimer = page.locator("#disclaimer-text").inner_text()
        assert "independent SWE-bench-inspired practice benchmark" in disclaimer

        # Verify KPI total tasks = 12
        assert page.locator("#kpi-total-tasks").inner_text().strip() == "12"

        # Navigate to Task Library and filter by difficulty=easy
        page.click('button[data-tab="tasks"]')
        page.wait_for_selector("#task-list-container .task-item-card")
        assert page.locator("#task-list-container .task-item-card").count() == 12

        page.select_option("#task-difficulty-filter", "easy")
        time.sleep(0.3)
        assert page.locator("#task-list-container .task-item-card").count() == 4

        # Click a task to inspect issue details and source code
        page.locator("#task-list-container .task-item-card").first.click()
        detail_text = page.locator("#task-detail-panel").inner_text()
        assert "Issue Report" in detail_text
        assert "Allowed Modifiable Files" in detail_text

        # Navigate across remaining tabs
        for tab_name in ("evaluate", "results", "comparison", "providers"):
            page.click(f'button[data-tab="{tab_name}"]')
            assert page.locator(f"#tab-{tab_name}").is_visible()

        # The provider tab must render the easy-connect presets.
        page.wait_for_selector("#provider-presets-container .preset-card")
        assert page.locator("#provider-presets-container .preset-card").count() >= 7

        browser.close()

    assert console_errors == []
