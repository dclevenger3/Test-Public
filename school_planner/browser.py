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


def credentials_from_env(slug: str) -> tuple[str, str] | None:
    """CLASSLINK_USER_<SLUG> / CLASSLINK_PASS_<SLUG> environment variables, for unattended runs.

    Set these in the environment (or a local .env that is never committed), not in config.yaml.
    """
    import os

    key = slug.upper().replace("-", "_")
    user, pw = os.environ.get(f"CLASSLINK_USER_{key}"), os.environ.get(f"CLASSLINK_PASS_{key}")
    return (user, pw) if user and pw else None


def _first_visible(page: Page, selectors: list[str]):
    for sel in selectors:
        loc = page.locator(sel)
        for i in range(min(loc.count(), 5)):
            if loc.nth(i).is_visible():
                return loc.nth(i)
    return None


def auto_login(store: Store, classlink_url: str, username: str, password: str, headless: bool = True) -> bool:
    """Fill the ClassLink (or the district SSO it redirects to) sign-in form. Best effort.

    Returns True when the launchpad loads. On failure a screenshot is left at data/<slug>/login-failed.png.
    Districts that require a code sent to a phone cannot be automated; use `login` interactively instead.
    """
    with browser_session(store, headless=headless) as ctx:
        page = ctx.new_page()
        page.goto(classlink_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        for _ in range(3):  # ClassLink -> district SSO -> back, at most a few hops
            if "classlink.com" in page.url and "login" not in page.url.lower() and "launchpad" not in page.url.lower():
                return True
            user_box = _first_visible(page, ["input[type=email]", "input[name*=user i]", "input[id*=user i]", "input[name=loginfmt]", "input[type=text]"])
            pass_box = _first_visible(page, ["input[type=password]"])
            if user_box and user_box.input_value() == "":
                user_box.fill(username)
                if not pass_box:  # two-step forms (Microsoft): submit the username first
                    user_box.press("Enter")
                    page.wait_for_timeout(2500)
                    pass_box = _first_visible(page, ["input[type=password]"])
            if pass_box:
                pass_box.fill(password)
                pass_box.press("Enter")
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(4000)
                stay = _first_visible(page, ["input[value='Yes']", "button:has-text('Yes')", "input[value='No']"])
                if stay:  # Microsoft "Stay signed in?"
                    stay.click()
                    page.wait_for_timeout(2500)
            else:
                sso = _first_visible(page, ["button:has-text('Microsoft')", "a:has-text('Microsoft')", "button:has-text('Google')", "a:has-text('Google')", "button:has-text('Sign in')"])
                if not sso:
                    break
                sso.click()
                page.wait_for_timeout(3000)
            if "classlink.com" in page.url and "login" not in page.url.lower():
                page.goto(classlink_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                return True
        page.screenshot(path=str(store.dir / "login-failed.png"), full_page=True)
        return False


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
