"""Data model shared by every connector, the scheduler, and the study-guide generator."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

# Assignment kinds. "test", "quiz", and "exam" are assessments; the rest are regular work.
ASSESSMENT_KINDS = {"test", "quiz", "exam"}
ALL_KINDS = ASSESSMENT_KINDS | {"homework", "project", "reading", "other"}


@dataclass
class Student:
    name: str
    slug: str
    grade: Optional[int] = None
    apps: dict[str, str] = field(default_factory=dict)


@dataclass
class Course:
    id: str
    name: str
    source: str  # canvas | google_classroom | capture
    teacher: str = ""
    url: str = ""


@dataclass
class Material:
    """A note, slide deck, document, or link attached to an assignment."""

    title: str
    url: str = ""
    kind: str = "link"  # doc | slides | pdf | page | link
    text: str = ""  # extracted text, filled in by materials.fetch_text


@dataclass
class Assignment:
    id: str
    student: str
    course_id: str
    course_name: str
    title: str
    kind: str = "other"
    due: Optional[datetime] = None
    description: str = ""
    url: str = ""
    source: str = ""
    status: str = ""  # submitted | missing | graded | "" (unknown)
    points: Optional[float] = None
    materials: list[Material] = field(default_factory=list)

    @property
    def is_assessment(self) -> bool:
        return self.kind in ASSESSMENT_KINDS

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["due"] = self.due.isoformat() if self.due else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Assignment":
        d = dict(d)
        d["due"] = datetime.fromisoformat(d["due"]) if d.get("due") else None
        d["materials"] = [Material(**m) for m in d.get("materials", [])]
        return cls(**d)
