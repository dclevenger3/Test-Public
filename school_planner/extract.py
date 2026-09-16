"""Turn the visible text of any LMS page into structured assignments using Claude.

This is the LMS-agnostic path: it works for Google Classroom, Schoology, or any portal we do
not have a dedicated connector for, and it is the fallback when a connector's selectors break.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from dateutil import parser as dateparser

from .classify import classify
from .llm import generate_json
from .models import Assignment, Material

SYSTEM = """You extract school assignments from the visible text of a learning-management-system page
(Google Classroom, Canvas, Schoology, etc.) that a parent captured for their child.

Rules:
- Only list real, dated or undated pieces of work: assignments, homework, quizzes, tests, projects, readings.
- Skip announcements, navigation, teacher chatter, and anything without a title.
- kind must be one of: test, quiz, exam, homework, project, reading, other. Use test/quiz/exam only when the
  item itself is the assessment. "Unit 3 Test Review" is homework.
- due is the due date/time as written on the page, or "" if none is shown. Copy it as written; do not guess.
- materials are links on the page that appear attached to that item (docs, slides, PDFs, files, pages).
- Return an empty list if the page has no assignments."""

SCHEMA = {
    "type": "object",
    "properties": {
        "course_name": {"type": "string"},
        "teacher": {"type": "string"},
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "kind": {"type": "string", "enum": ["test", "quiz", "exam", "homework", "project", "reading", "other"]},
                    "due": {"type": "string"},
                    "description": {"type": "string"},
                    "url": {"type": "string"},
                    "status": {"type": "string", "enum": ["", "submitted", "missing", "graded"]},
                    "materials": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                            "required": ["title", "url"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "kind", "due", "description", "url", "status", "materials"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["course_name", "teacher", "assignments"],
    "additionalProperties": False,
}


def parse_due(text: str, today: datetime | None = None) -> datetime | None:
    """Parse "Due Sep 24, 11:59 PM" style strings. Returns None when unparseable."""
    text = text.strip()
    if not text:
        return None
    text = text.replace("Due", "").replace("due", "").strip(" :,-")
    try:
        return dateparser.parse(text, default=(today or datetime.now()).replace(hour=23, minute=59, second=0, microsecond=0))
    except (ValueError, OverflowError):
        return None


def stable_id(student: str, course: str, title: str, due: str) -> str:
    return "x-" + hashlib.sha1(f"{student}|{course}|{title}|{due}".encode()).hexdigest()[:12]


def extract_assignments(student: str, page_text: str, page_url: str, model: str,
                        course_hint: str = "", today: datetime | None = None) -> tuple[str, list[Assignment]]:
    """Return (course_name, assignments) extracted from a captured page."""
    user = f"Page URL: {page_url}\nCourse hint: {course_hint or '(unknown)'}\n\n--- PAGE TEXT ---\n{page_text[:120_000]}"
    data = generate_json(SYSTEM, user, SCHEMA, model=model)
    course = data.get("course_name") or course_hint or "Unknown course"
    out: list[Assignment] = []
    for item in data["assignments"]:
        due_raw = item["due"]
        out.append(
            Assignment(
                id=stable_id(student, course, item["title"], due_raw),
                student=student,
                course_id=course.lower().replace(" ", "-"),
                course_name=course,
                title=item["title"],
                kind=classify(item["title"], item["description"], native_kind=item["kind"] if item["kind"] in {"test", "quiz", "exam"} else None),
                due=parse_due(due_raw, today),
                description=item["description"],
                url=item["url"] or page_url,
                source="capture",
                status=item["status"],
                materials=[Material(title=m["title"], url=m["url"]) for m in item["materials"]],
            )
        )
    return course, out
