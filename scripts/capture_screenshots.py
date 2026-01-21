#!/usr/bin/env python3
"""Capture authentic headless Chromium screenshots of the running Mini SWE-Bench dashboard.

Every image in ``docs/images/`` is produced by this script from a live server
with real recorded evaluation results. Nothing here is mocked or hand-drawn.

Usage:
    bugbench serve --host 127.0.0.1 --port 8000     # in one terminal
    python scripts/capture_screenshots.py            # in another
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "images"
BASE_URL = "http://127.0.0.1:8000"
VIEWPORT = {"width": 1440, "height": 920}


def _shot(page: Page, name: str) -> None:
    path = OUT_DIR / name
    page.screenshot(path=str(path), full_page=False)
    print(f"Captured docs/images/{name}")


def capture_all(base_url: str = BASE_URL) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page = context.new_page()

        errors: list[str] = []
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )

        page.goto(base_url, wait_until="networkidle")
        time.sleep(1.0)

        # 1. Overview dashboard & quality gate telemetry
        _shot(page, "dashboard-overview.png")

        # Dataset quality gate verification matrix (scroll down)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.5)
        _shot(page, "dataset-quality-gates.png")
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.3)

        # 2. Task library & buggy repository inspector
        page.click('button[data-tab="tasks"]')
        page.wait_for_selector("#task-list-container .task-item-card", timeout=15000)
        time.sleep(0.8)
        task_items = page.locator("#task-list-container .task-item-card")
        if task_items.count() > 0:
            task_items.first.click()
            time.sleep(0.8)
        _shot(page, "task-explorer.png")

        # 3. Run inspector: per-task test outcomes & unified diff
        page.click('button[data-tab="results"]')
        # <option> elements are never "visible" to Playwright, so wait for them
        # to be merely attached to the DOM.
        page.wait_for_selector("#results-run-select option", state="attached", timeout=15000)
        time.sleep(1.2)

        # Pick the most substantial run (the one covering the most tasks) so
        # the inspector shows a full per-task table rather than a single task.
        options = page.locator("#results-run-select option")
        best_value, best_total = None, -1
        for i in range(options.count()):
            value = options.nth(i).get_attribute("value")
            label = options.nth(i).inner_text()
            if not value:
                continue
            match = re.search(r"\((\d+)/(\d+) resolved\)", label)
            total = int(match.group(2)) if match else 0
            if total > best_total:
                best_value, best_total = value, total
        if best_value:
            page.select_option("#results-run-select", best_value)
            time.sleep(1.2)

        rows = page.locator("#run-tasks-tbody tr[data-task-id]")
        # Prefer a RESOLVED row so the inspector shows a real unified diff and
        # per-test outcomes rather than an empty submission.
        target = None
        for i in range(rows.count()):
            if "RESOLVED" in rows.nth(i).inner_text():
                target = rows.nth(i)
                break
        if target is None and rows.count() > 0:
            target = rows.first
        if target is not None:
            target.click()
            time.sleep(0.9)
        _shot(page, "run-inspector-diff.png")

        # 4. Run / agent comparison & regression safety matrix
        page.click('button[data-tab="comparison"]')
        time.sleep(1.0)
        _shot(page, "model-comparison.png")

        # 5. Launch evaluation & live execution logs
        page.click('button[data-tab="evaluate"]')
        time.sleep(0.8)
        _shot(page, "launch-evaluation.png")

        # 6. Provider configuration, easy-connect presets & cost controls
        page.click('button[data-tab="providers"]')
        page.wait_for_selector("#provider-presets-container .preset-card", timeout=15000)
        time.sleep(0.8)
        _shot(page, "provider-configuration.png")

        # 7. Provider presets & cost control panel (scrolled)
        page.evaluate(
            "document.getElementById('provider-presets-container')"
            ".scrollIntoView({block: 'center'})"
        )
        time.sleep(0.5)
        _shot(page, "provider-presets-cost.png")

        browser.close()

        if errors:
            print("\nWARNING: browser console errors were recorded:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            raise SystemExit(1)

    print("\nAll screenshots captured from the live dashboard.")


if __name__ == "__main__":
    capture_all(sys.argv[1] if len(sys.argv) > 1 else BASE_URL)
