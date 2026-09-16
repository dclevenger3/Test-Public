from __future__ import annotations

from abc import ABC, abstractmethod

from playwright.sync_api import BrowserContext

from ..models import Assignment, Course, Student


class Connector(ABC):
    name = "base"

    def __init__(self, student: Student, base_url: str, model: str):
        self.student = student
        self.base_url = base_url.rstrip("/")
        self.model = model

    @abstractmethod
    def sync(self, ctx: BrowserContext) -> tuple[list[Course], list[Assignment]]:
        """Return every current course and its assignments for this student."""
