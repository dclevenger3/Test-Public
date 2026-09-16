"""Playwright session management.

Each student gets a persistent Chromium profile under data/<slug>/profile/. The parent logs
in once through ClassLink in a real browser window; cookies and SSO state persist between runs,
so no password is ever typed into this program or stored on disk by it.
"""

from __future__ import annotations

import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .store import Store

LAUNCHPAD_READY_SELECTORS = [
    "[data-testid*='app']",
    ".app-tile",
    "[class*='AppTile']",
    "[class*='app-card']",
    "a[href*='launchpad']",
]


@contextmanager
def browser_session(store: Store, headless: bool = False) -> Iterator[BrowserContext]:
    """Open the student's persistent profile. Headful by default so the parent can log in."""
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(store.profile_dir),
            headless=headless,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            yield context
        finally:
            context.close()


def _wait_for_enter(prompt: str) -> None:
    print(prompt, file=sys.stderr)
    try:
        input()
    except EOFError:
        pass


def login(store: Store, classlink_url: str) -> None:
    """Open ClassLink and wait for the parent to finish logging in."""
    with browser_session(store, headless=False) as ctx:
        page = ctx.new_page()
        page.goto(classlink_url, wait_until="domcontentloaded")
        _wait_for_enter(
            "\nA browser window is open. Log into ClassLink as this student.\n"
            "If the school also asks you to open Canvas / Google Classroom once, do that too\n"
            "so the SSO cookies are saved. Then come back here and press Enter."
        )
        page.goto(classlink_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        ok = "classlink.com" in page.url and "login" not in page.url.lower()
        print("Session saved." if ok else "Warning: still on a login page. Run login again.")


def discover_apps(store: Store, classlink_url: str) -> list[dict]:
    """List the app tiles on the ClassLink launchpad and save them to data/<slug>/apps.json.

    ClassLink's DOM changes, so this collects every clickable element with a name and an
    outbound link or launch id rather than relying on one selector.
    """
    with browser_session(store, headless=False) as ctx:
        page = ctx.new_page()
        page.goto(classlink_url, wait_until="domcontentloaded")
        for sel in LAUNCHPAD_READY_SELECTORS:
            try:
                page.wait_for_selector(sel, timeout=4000)
                break
            except Exception:
                continue
        page.wait_for_timeout(1500)
        if "login" in page.url.lower():
            raise SystemExit("Not logged in. Run `school-planner login <slug>` first.")

        apps = page.evaluate(
            """() => {
              const seen = new Map();
              const els = document.querySelectorAll('a, button, [role=button], [role=link]');
              for (const el of els) {
                const name = (el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || '').trim();
                if (!name || name.length > 80) continue;
                const href = el.href || el.getAttribute('data-url') || '';
                const img = el.querySelector('img');
                const key = name.toLowerCase();
                if (!seen.has(key)) seen.set(key, {name, href, icon: img ? img.src : ''});
              }
              return Array.from(seen.values());
            }"""
        )
        page.screenshot(path=str(store.dir / "launchpad.png"), full_page=True)
        store.write_json("apps", apps)
        return apps


KNOWN_APPS = {
    "canvas": re.compile(r"canvas|instructure", re.I),
    "google_classroom": re.compile(r"google\s*classroom|classroom", re.I),
    "schoology": re.compile(r"schoology", re.I),
    "powerschool": re.compile(r"powerschool", re.I),
    "infinite_campus": re.compile(r"infinite\s*campus", re.I),
    "clever": re.compile(r"clever", re.I),
}


def guess_lms(apps: list[dict]) -> dict[str, str]:
    """Map known app types to the tile name/link that matched, for the user to confirm."""
    found: dict[str, str] = {}
    for app in apps:
        label = f"{app.get('name','')} {app.get('href','')}"
        for key, pat in KNOWN_APPS.items():
            if key not in found and pat.search(label):
                found[key] = app.get("href") or app.get("name", "")
    return found


def click_app(page: Page, name_pattern: str, timeout_ms: int = 15000) -> Page:
    """Click a launchpad tile by name and return the page it opened (new tab or same tab)."""
    pat = re.compile(name_pattern, re.I)
    with page.context.expect_page(timeout=timeout_ms) as popup:
        page.get_by_role("link", name=pat).or_(page.get_by_role("button", name=pat)).first.click()
    new_page = popup.value
    new_page.wait_for_load_state("domcontentloaded")
    return new_page


def page_text(page: Page) -> str:
    """Visible text of the page plus every link, which is what the LLM extractor reads."""
    return page.evaluate(
        """() => {
          const text = document.body.innerText;
          const links = Array.from(document.querySelectorAll('a[href]'))
            .map(a => `${(a.innerText||'').trim().replace(/\\s+/g,' ')} -> ${a.href}`)
            .filter(s => !s.startsWith(' ->'))
            .slice(0, 400);
          return text + '\\n\\n--- LINKS ---\\n' + links.join('\\n');
        }"""
    )


def save_capture(store: Store, page: Page, label: str) -> Path:
    safe = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:60] or "page"
    path = store.captures_dir / f"{safe}.json"
    path.write_text(json.dumps({"url": page.url, "title": page.title(), "text": page_text(page)}, indent=2))
    return path
