"""Load config.yaml and .env. Credentials never live in config; they live in browser profiles."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import Student

ROOT = Path(os.environ.get("SCHOOL_PLANNER_HOME", Path.cwd()))
DATA_DIR = ROOT / "data"
CONFIG_PATH = ROOT / "config.yaml"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader so we don't need python-dotenv."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class ScheduleConfig:
    lookahead_days: int = 14
    study_days_before: list[int] = field(default_factory=lambda: [4, 2, 1])
    study_session_minutes: int = 30


@dataclass
class Config:
    timezone: str = "America/New_York"
    classlink_url: str = "https://myapps.classlink.com/home"
    backend: str = "claude-code"  # claude-code | api
    model: str = "opus"
    students: list[Student] = field(default_factory=list)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)

    def student(self, slug: str) -> Student:
        for s in self.students:
            if s.slug == slug:
                return s
        known = ", ".join(s.slug for s in self.students) or "(none configured)"
        raise SystemExit(f"Unknown student '{slug}'. Known students: {known}")


def load_config(path: Path = CONFIG_PATH) -> Config:
    load_dotenv()
    if not path.exists():
        raise SystemExit(
            f"No config found at {path}. Copy config.example.yaml to config.yaml and edit it."
        )
    raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    students = [
        Student(
            name=s["name"],
            slug=s["slug"],
            grade=s.get("grade"),
            apps={k: v for k, v in (s.get("apps") or {}).items() if v},
        )
        for s in raw.get("students", [])
    ]
    sched = raw.get("schedule") or {}
    return Config(
        timezone=raw.get("timezone", "America/New_York"),
        classlink_url=raw.get("classlink_url", "https://myapps.classlink.com/home"),
        backend=raw.get("backend", "claude-code"),
        model=raw.get("model", "opus"),
        students=students,
        schedule=ScheduleConfig(
            lookahead_days=int(sched.get("lookahead_days", 14)),
            study_days_before=list(sched.get("study_days_before", [4, 2, 1])),
            study_session_minutes=int(sched.get("study_session_minutes", 30)),
        ),
    )
