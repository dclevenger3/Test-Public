"""Google Classroom connector.

Google Classroom has no cookie-friendly JSON API and its DOM changes often, so this connector
visits the pages a student sees, grabs the visible text and links, and hands them to Claude for
structured extraction (see extract.py). It is slower than the Canvas connector but robust.
"""

from __future__ import annotations

import re

from playwright.sync_api import BrowserContext

from ..browser import page_text, save_capture
from ..extract import extract_assignments
from ..models import Assignment, Course
from ..store import Store
from .base import Connector

COURSE_LINK = re.compile(r"https://classroom\.google\.com/(?:u/\d+/)?c/([\w-]+)$")


class GoogleClassroomConnector(Connector):
    name = "google_classroom"

    def __init__(self, student, base_url: str, model: str, store: Store | None = None):
        super().__init__(student, base_url or "https://classroom.google.com", model)
        self.store = store or Store(student.slug)

    def sync(self, ctx: BrowserContext) -> tuple[list[Course], list[Assignment]]:
        page = ctx.new_page()
        page.goto(f"{self.base_url}/h", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        if "accounts.google.com" in page.url:
            raise SystemExit(
                f"Google Classroom needs a login. Run `school-planner login {self.student.slug}` and open the "
                "Google Classroom tile in ClassLink once."
            )
        hrefs = page.evaluate("() => Array.from(document.querySelectorAll('a[href]')).map(a => [a.href, (a.innerText||'').trim()])")
        seen: dict[str, str] = {}
        for href, text in hrefs:
            m = COURSE_LINK.match(href.split("?")[0])
            if m and m.group(1) not in seen and text:
                seen[m.group(1)] = text.split("\n")[0]

        courses: list[Course] = []
        assignments: list[Assignment] = []
        for cid, name in seen.items():
            url = f"{self.base_url}/c/{cid}"
            courses.append(Course(id=cid, name=name, source="google_classroom", url=url))
            # Classwork tab lists everything with due dates and attached materials.
            page.goto(f"{url}/a", wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            _expand_all(page)
            save_capture(self.store, page, f"classroom-{name}")
            course_name, items = extract_assignments(
                self.student.slug, page_text(page), page.url, self.model, course_hint=name
            )
            for a in items:
                a.source = "google_classroom"
                a.course_id = cid
                a.course_name = name
            assignments.extend(items)
        page.close()
        return courses, assignments


def _expand_all(page) -> None:
    """Classwork items are collapsed; click each one so the description and links are visible."""
    try:
        items = page.locator("[role=button][aria-expanded=false]")
        for i in range(min(items.count(), 80)):
            try:
                items.nth(i).click(timeout=500)
            except Exception:
                pass
        page.wait_for_timeout(500)
    except Exception:
        pass
