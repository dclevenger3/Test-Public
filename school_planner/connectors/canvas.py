"""Canvas LMS connector.

Uses the Canvas REST API with the browser session's cookies, which is exactly what the Canvas
web UI itself does. No API token needed. The student reaches Canvas through ClassLink SSO once;
after that the persistent profile carries the session.
"""

from __future__ import annotations

import json
from datetime import datetime

from playwright.sync_api import BrowserContext

from ..classify import classify
from ..materials import looks_like_notes
from ..tz import to_local
from ..models import Assignment, Course, Material
from .base import Connector


class CanvasConnector(Connector):
    name = "canvas"

    def _get(self, ctx: BrowserContext, path: str, **params) -> list | dict:
        params.setdefault("per_page", 100)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.base_url}/api/v1/{path.lstrip('/')}?{query}"
        out: list = []
        while url:
            r = ctx.request.get(url, headers={"Accept": "application/json"})
            if r.status == 401 or r.status == 302:
                raise SystemExit("Canvas session expired. Run `school-planner login` again and open Canvas once.")
            if not r.ok:
                raise RuntimeError(f"Canvas API {r.status} for {url}")
            body = r.text()
            if body.startswith("while(1);"):  # Canvas anti-JSON-hijacking prefix on cookie auth
                body = body[9:]
            data = json.loads(body)
            if isinstance(data, dict):
                return data
            out.extend(data)
            url = _next_link(r.headers.get("link", ""))
        return out

    def _ensure_session(self, ctx: BrowserContext) -> None:
        page = ctx.new_page()
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        if "login" in page.url.lower():
            raise SystemExit(
                f"Canvas at {self.base_url} is asking for a login. Run `school-planner login {self.student.slug}`, "
                "then click the Canvas tile in ClassLink once so the SSO cookie is saved."
            )
        page.close()

    def sync(self, ctx: BrowserContext) -> tuple[list[Course], list[Assignment]]:
        self._ensure_session(ctx)
        raw_courses = self._get(ctx, "courses", enrollment_state="active", **{"include[]": "teachers"})
        courses: list[Course] = []
        assignments: list[Assignment] = []
        for c in raw_courses:
            if not c.get("name"):
                continue
            course = Course(
                id=str(c["id"]),
                name=c["name"],
                source="canvas",
                teacher=", ".join(t.get("display_name", "") for t in c.get("teachers", [])),
                url=f"{self.base_url}/courses/{c['id']}",
            )
            courses.append(course)
            assignments.extend(self._course_assignments(ctx, course))
        return courses, assignments

    def _course_assignments(self, ctx: BrowserContext, course: Course) -> list[Assignment]:
        items = self._get(ctx, f"courses/{course.id}/assignments", **{"include[]": "submission", "order_by": "due_at"})
        out: list[Assignment] = []
        for a in items:
            if not a.get("published", True):
                continue
            native = "quiz" if a.get("is_quiz_assignment") or "online_quiz" in (a.get("submission_types") or []) else None
            sub = a.get("submission") or {}
            status = ""
            if sub.get("missing"):
                status = "missing"
            elif sub.get("workflow_state") == "graded":
                status = "graded"
            elif sub.get("submitted_at"):
                status = "submitted"
            out.append(
                Assignment(
                    id=f"canvas-{a['id']}",
                    student=self.student.slug,
                    course_id=course.id,
                    course_name=course.name,
                    title=a["name"],
                    kind=classify(a["name"], a.get("description") or "", native_kind=native),
                    due=_parse_iso(a.get("due_at")),
                    description=_strip_html(a.get("description") or ""),
                    url=a.get("html_url", ""),
                    source="canvas",
                    status=status,
                    points=a.get("points_possible"),
                    materials=_materials_from_html(a.get("description") or ""),
                )
            )
        # Modules hold the class notes and slides that usually are not attached to the test itself.
        try:
            modules = self._get(ctx, f"courses/{course.id}/modules", **{"include[]": "items"})
        except RuntimeError:
            modules = []
        notes = [
            Material(title=i.get("title", ""), url=i.get("html_url") or i.get("external_url") or "", kind=i.get("type", "link").lower())
            for m in modules for i in m.get("items", [])
            if i.get("type") in {"Page", "File", "ExternalUrl"} and looks_like_notes(i.get("title", ""), i.get("html_url") or "")
        ]
        for a in out:
            if a.is_assessment and notes:
                a.materials.extend(n for n in notes if n.url and n.url not in {m.url for m in a.materials})
        return out


def _next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return to_local(datetime.fromisoformat(s.replace("Z", "+00:00")))


def _strip_html(html: str) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _materials_from_html(html: str) -> list[Material]:
    import re

    found: list[Material] = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S):
        url, title = m.group(1), _strip_html(m.group(2)) or m.group(1)
        if looks_like_notes(title, url):
            found.append(Material(title=title, url=url))
    return found
