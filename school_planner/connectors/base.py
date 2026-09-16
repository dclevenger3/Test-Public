from __future__ import annotations

from abc import ABC, abstractmethod

from playwright.sync_api import BrowserContext

from ..models import Assignment, Course, Student


class Connector(ABC):
    name = "base"
    needs_browser = True  # False for connectors that work over plain HTTPS (calendar feeds)

    def __init__(self, student: Student, base_url: str, model: str, backend: str = "claude-code"):
        self.student = student
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.backend = backend

    @abstractmethod
    def sync(self, ctx: BrowserContext | None) -> tuple[list[Course], list[Assignment]]:
        """Return every current course and its assignments for this student. ctx is None when needs_browser is False."""
