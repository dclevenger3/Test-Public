"""Canvas calendar-feed connector.

Canvas gives every user a private calendar feed URL (Calendar page, "Calendar Feed" link, bottom
right). It lists every assignment and quiz with a due date across all courses and needs no login,
so it works from anywhere, including a cloud scheduler. Districts that disable personal access
tokens generally leave this on.

What it cannot see: submission status (missing work) and attached files beyond links in the
assignment description. Pair it with the browser-based `canvas` connector for those.
"""

from __future__ import annotations

import re
import urllib.request
from datetime import datetime, timezone

from ..classify import classify
from ..models import Assignment, Course
from .base import Connector
from .canvas import _materials_from_html, _strip_html

SUMMARY_RE = re.compile(r"^(?P<title>.*?)\s*\[(?P<course>[^\]]+)\]\s*$")
ASSIGNMENT_URL = re.compile(r"/courses/(\d+)/(assignments|quizzes)/(\d+)")


class CanvasFeedConnector(Connector):
    name = "canvas_feed"
    needs_browser = False

    def fetch(self) -> str:
        if not self.base_url.lower().endswith(".ics"):
            raise SystemExit(
                "canvas_feed must be the private .ics URL from Canvas: Calendar page, 'Calendar Feed' link at the bottom right."
            )
        req = urllib.request.Request(self.base_url, headers={"User-Agent": "school-planner"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8", errors="replace")

    def sync(self, ctx=None) -> tuple[list[Course], list[Assignment]]:
        return parse_feed(self.fetch(), self.student.slug)


# ---------------------------------------------------------------- parsing

def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(s: str) -> str:
    return s.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\;", ";").replace("\\\\", "\\")


def _parse_dt(value: str, params: str) -> datetime | None:
    value = value.strip()
    try:
        if "VALUE=DATE" in params or len(value) == 8:
            return datetime.strptime(value, "%Y%m%d").replace(hour=23, minute=59)
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        return datetime.strptime(value, "%Y%m%dT%H%M%S")
    except ValueError:
        return None


def parse_events(ics: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    for line in _unfold(ics):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, _, value = line.partition(":")
            name, _, params = key.partition(";")
            cur[name] = value
            if params:
                cur[name + "_PARAMS"] = params
    return events


def parse_feed(ics: str, student: str) -> tuple[list[Course], list[Assignment]]:
    courses: dict[str, Course] = {}
    assignments: list[Assignment] = []
    for ev in parse_events(ics):
        summary = _unescape(ev.get("SUMMARY", "")).strip()
        url = ev.get("URL", "").strip()
        m = ASSIGNMENT_URL.search(url)
        if not m:
            continue  # plain calendar events (holidays, class meetings) are not work
        course_id, url_kind, item_id = m.groups()
        sm = SUMMARY_RE.match(summary)
        title = sm.group("title") if sm else summary
        course_name = sm.group("course") if sm else f"Course {course_id}"
        if course_id not in courses:
            base = url.split("/courses/")[0]
            courses[course_id] = Course(id=course_id, name=course_name, source="canvas", url=f"{base}/courses/{course_id}")
        html = _unescape(ev.get("X-ALT-DESC", "")) or ""
        description = _unescape(ev.get("DESCRIPTION", "")) or _strip_html(html)
        native = "quiz" if url_kind == "quizzes" else None
        assignments.append(
            Assignment(
                id=f"canvas-{item_id}",  # same id the browser connector uses, so they merge
                student=student,
                course_id=course_id,
                course_name=course_name,
                title=title,
                kind=classify(title, description, native_kind=native),
                due=_parse_dt(ev.get("DTSTART", ""), ev.get("DTSTART_PARAMS", "")),
                description=description.strip(),
                url=url,
                source="canvas_feed",
                materials=_materials_from_html(html),
            )
        )
    return list(courses.values()), assignments
