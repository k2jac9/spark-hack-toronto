"""Opt-in end-to-end browser check of the click-to-verify interaction.

NOT part of the pytest/CI suite (needs Chrome + a running server). Run locally:

    pip install playwright
    DATA_DIR=demo_data uvicorn civic_analyst.api.server:app --port 8022 --app-dir src &
    python scripts/e2e_click.py http://localhost:8022/

Loads the map page, runs an analysis (equivalent to clicking a pin), then performs a
real DOM click on a "✓ verify" control and asserts the source record is revealed.
Uses the system Chrome (channel="chrome") — no browser download.
"""
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8022/"
ADDRESS = sys.argv[2] if len(sys.argv) > 2 else "500 BLOOR ST W"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader",
                  "--enable-unsafe-swiftshader"],
        )
        page = browser.new_page()
        page.goto(URL, wait_until="load")

        # analyze() is a hoisted global; calling it is equivalent to clicking a map pin.
        page.wait_for_function("typeof window.analyze === 'function'", timeout=10000)
        page.evaluate("async (a) => { await window.analyze(a); }", ADDRESS)
        page.wait_for_selector(".verify", timeout=10000)

        claims = page.locator("#claims li").count()
        verify = page.locator(".verify").count()
        before = page.locator(".srcline:visible").count()
        page.locator(".verify").first.click()
        page.wait_for_timeout(200)
        after = page.locator(".srcline:visible").count()
        revealed = page.locator(".srcline:visible").first.inner_text() if after else ""

        print(f"claims={claims} verify_links={verify} visible_before={before} visible_after={after}")
        print(f"revealed source: {revealed}")
        ok = claims > 0 and verify > 0 and before == 0 and after >= 1
        print("RESULT:", "PASS" if ok else "FAIL")
        browser.close()
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
