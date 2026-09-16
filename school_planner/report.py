"""Weekly digest for the parent: this week's schedule, upcoming tests, missing work, ready study guides."""

from __future__ import annotations

import os
import smtplib
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from .config import Config, DATA_DIR
from .models import Assignment
from .schedule import build_events, missing_work, render_markdown, upcoming_assessments, week_bounds
from .store import Store


def build_digest(cfg: Config, today: date | None = None) -> str:
    today = today or date.today()
    start, end = week_bounds(today)
    names = {s.slug: s.name for s in cfg.students}
    all_assignments: list[Assignment] = []
    for s in cfg.students:
        all_assignments.extend(Store(s.slug).load_assignments())

    parts = [render_markdown(build_events(all_assignments, cfg.schedule, start, end, today), start, end, names), ""]

    tests = upcoming_assessments(all_assignments, cfg.schedule.lookahead_days, today)
    parts.append(f"## Tests and quizzes in the next {cfg.schedule.lookahead_days} days")
    if not tests:
        parts.append("_none posted_")
    for a in tests:
        guide = Store(a.student).guides_dir / f"{a.id}.md"
        ready = f" · study guide: `{guide}`" if guide.exists() else " · no study guide yet, run `school-planner study-guide " + f"{a.student} {a.id}`"
        parts.append(f"- {a.due:%a %b %d} · **{names.get(a.student, a.student)}** · {a.course_name} · {a.title}{ready}")
    parts.append("")

    missing = missing_work(all_assignments, today)
    parts.append("## Missing or past due")
    if not missing:
        parts.append("_nothing missing_ ✅")
    for a in missing:
        when = f"{a.due:%b %d}" if a.due else "no date"
        parts.append(f"- **{names.get(a.student, a.student)}** · {a.course_name} · {a.title} (due {when})")
    return "\n".join(parts)


def write_digest(text: str, today: date | None = None) -> Path:
    today = today or date.today()
    out = DATA_DIR / "digests"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"week-{today:%Y-%m-%d}.md"
    path.write_text(text)
    return path


def email_digest(text: str, subject: str) -> bool:
    """Send via SMTP if the SMTP_* variables are set. Returns False when email is not configured."""
    host, user, password, to = (os.environ.get(k, "") for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_TO"))
    if not (host and user and password and to):
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(text)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587"))) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
    return True
