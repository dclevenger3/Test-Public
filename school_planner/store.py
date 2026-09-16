"""JSON storage under data/<student>/. Everything here is git-ignored."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .config import DATA_DIR
from .models import Assignment, Course


class Store:
    def __init__(self, slug: str, data_dir: Path = DATA_DIR):
        self.slug = slug
        self.dir = data_dir / slug
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "guides").mkdir(exist_ok=True)
        (self.dir / "captures").mkdir(exist_ok=True)

    # ----- paths -----
    @property
    def profile_dir(self) -> Path:
        p = self.dir / "profile"
        p.mkdir(exist_ok=True)
        return p

    @property
    def guides_dir(self) -> Path:
        return self.dir / "guides"

    @property
    def captures_dir(self) -> Path:
        return self.dir / "captures"

    def _path(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    # ----- generic -----
    def write_json(self, name: str, obj) -> Path:
        p = self._path(name)
        p.write_text(json.dumps(obj, indent=2, default=str))
        return p

    def read_json(self, name: str, default=None):
        p = self._path(name)
        if not p.exists():
            return default
        return json.loads(p.read_text())

    # ----- courses -----
    def save_courses(self, courses: list[Course]) -> None:
        self.write_json("courses", [asdict(c) for c in courses])

    def load_courses(self) -> list[Course]:
        return [Course(**c) for c in self.read_json("courses", [])]

    # ----- assignments -----
    def save_assignments(self, assignments: list[Assignment]) -> None:
        self.write_json("assignments", [a.to_dict() for a in assignments])

    def load_assignments(self) -> list[Assignment]:
        return [Assignment.from_dict(a) for a in self.read_json("assignments", [])]

    def merge_assignments(self, new: list[Assignment]) -> list[Assignment]:
        """Upsert by id, keeping any materials text we already fetched."""
        existing = {a.id: a for a in self.load_assignments()}
        for a in new:
            old = existing.get(a.id)
            if old:
                old_text = {m.url: m.text for m in old.materials if m.text}
                for m in a.materials:
                    if not m.text and m.url in old_text:
                        m.text = old_text[m.url]
            existing[a.id] = a
        merged = sorted(existing.values(), key=lambda a: (a.due is None, a.due or 0))
        self.save_assignments(merged)
        return merged

    def find_assignment(self, needle: str) -> Assignment:
        """Find by exact id, or by case-insensitive substring of the title."""
        items = self.load_assignments()
        for a in items:
            if a.id == needle:
                return a
        matches = [a for a in items if needle.lower() in a.title.lower()]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise SystemExit(f"No assignment matching '{needle}' for {self.slug}.")
        listing = "\n".join(f"  {a.id}  {a.title}" for a in matches)
        raise SystemExit(f"'{needle}' matches several assignments, use the id:\n{listing}")
