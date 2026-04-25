"""Capture full-page screenshots of the running app for the README/landing page.

Outputs (overwrites):
- assets/images/page-long.png    (EN)
- assets/images/page-long-cn.png (CN)

Usage:
    # Make sure the app is running (e.g. `python launcher.py`).
    .venv/bin/python assets/images/screenshot.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

IMAGES_DIR = Path(__file__).resolve().parent
ROOT = IMAGES_DIR.parent.parent
URL = "http://127.0.0.1:8000/"
OUT_EN = IMAGES_DIR / "page-long.png"
OUT_CN = IMAGES_DIR / "page-long-cn.png"

VIEWPORT = {"width": 1440, "height": 900}

# Override `background-attachment: fixed` so the gradient covers the full
# document height when Chromium does a full-page screenshot.
FIX_BG_CSS = "html, body { background-attachment: scroll !important; }"


def capture(locale: str, out_path: Path) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=2,
        )
        page = context.new_page()
        page.add_init_script(
            f"window.localStorage.setItem('arpm-locale', '{locale}');"
            "window.localStorage.setItem('arpm-theme', 'light');"
        )
        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector("#root > *", state="attached", timeout=15000)
        page.add_style_tag(content=FIX_BG_CSS)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out_path), full_page=True)
        size = out_path.stat().st_size
        print(f"[{locale}] wrote {out_path.relative_to(ROOT)} ({size/1024:.0f} KB)")
        browser.close()


def main() -> int:
    capture("en", OUT_EN)
    capture("cn", OUT_CN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
