"""Weekly digests: one for the parent (all kids) and one per kid, emailed as HTML."""

from __future__ import annotations

import os
import re
import smtplib
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from .config import Config, DATA_DIR
from .models import Assignment, Student
from .schedule import build_events, missing_work, render_markdown, upcoming_assessments, week_bounds
from .store import Store


def _tests_section(cfg: Config, items: list[Assignment], names: dict[str, str], today: date, inline_guides: bool) -> list[str]:
    tests = upcoming_assessments(items, cfg.schedule.lookahead_days, today)
    parts = [f"## Tests and quizzes in the next {cfg.schedule.lookahead_days} days"]
    if not tests:
        parts.append("_none posted_")
    for a in tests:
        guide = Store(a.student).guides_dir / f"{a.id}.md"
        if inline_guides:
            ready = " · study guide below" if guide.exists() else " · no study guide yet"
        else:
            ready = f" · study guide: `{guide}`" if guide.exists() else f" · no study guide yet, run `school-planner study-guide {a.student} {a.id}`"
        who = f"**{names[a.student]}** · " if len(names) > 1 else ""
        parts.append(f"- {a.due:%a %b %d} · {who}{a.course_name} · {a.title}{ready}")
    parts.append("")
    if inline_guides:
        for a in tests:
            guide = Store(a.student).guides_dir / f"{a.id}.md"
            if guide.exists():
                parts += ["---", "", guide.read_text().strip(), ""]
    return parts


def _missing_section(items: list[Assignment], names: dict[str, str], today: date) -> list[str]:
    missing = missing_work(items, today)
    parts = ["## Missing or past due"]
    if not missing:
        parts.append("_nothing missing_ ✅")
    for a in missing:
        when = f"{a.due:%b %d}" if a.due else "no date"
        who = f"**{names[a.student]}** · " if len(names) > 1 else ""
        parts.append(f"- {who}{a.course_name} · {a.title} (due {when})")
    return parts


def build_digest(cfg: Config, today: date | None = None) -> str:
    """Parent view: every kid, this week, upcoming tests, missing work."""
    today = today or date.today()
    start, end = week_bounds(today)
    names = {s.slug: s.name for s in cfg.students}
    items: list[Assignment] = []
    for s in cfg.students:
        items.extend(Store(s.slug).load_assignments())
    parts = [render_markdown(build_events(items, cfg.schedule, start, end, today), start, end, names), ""]
    parts += _tests_section(cfg, items, names, today, inline_guides=False)
    parts += _missing_section(items, names, today)
    return "\n".join(parts)


def build_student_digest(cfg: Config, student: Student, today: date | None = None) -> str:
    """Kid view: her week, her tests, and her study guides in full so she can read them on a phone."""
    today = today or date.today()
    start, end = week_bounds(today)
    names = {student.slug: student.name}
    items = Store(student.slug).load_assignments()
    first = student.name.split()[0]
    parts = [f"Hi {first}, here is your week.", ""]
    parts.append(render_markdown(build_events(items, cfg.schedule, start, end, today), start, end, names).replace(f"**{student.name}** · ", ""))
    parts.append("")
    parts += _tests_section(cfg, items, names, today, inline_guides=True)
    parts += _missing_section(items, names, today)
    return "\n".join(parts)


def write_digest(text: str, today: date | None = None, slug: str = "family") -> Path:
    today = today or date.today()
    out = DATA_DIR / "digests"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"week-{today:%Y-%m-%d}-{slug}.md"
    path.write_text(text)
    return path


def write_outbox(cfg: Config, today: date | None = None) -> list[Path]:
    """One self-contained HTML page per kid (plus one for the family) in data/outbox/week-<date>/.

    These are what you send: attach to a text, AirDrop, or email them. Each kid's page has her
    week, her tests, and her study guides in full.
    """
    today = today or date.today()
    out = DATA_DIR / "outbox" / f"week-{today:%Y-%m-%d}"
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for student in cfg.students:
        path = out / f"{re.sub(r'[^A-Za-z0-9 _-]', '', student.name).strip() or student.slug}.html"
        path.write_text(markdown_to_html(build_student_digest(cfg, student, today)), encoding="utf-8")
        written.append(path)
    family = out / "Family.html"
    family.write_text(markdown_to_html(build_digest(cfg, today)), encoding="utf-8")
    written.append(family)
    return written


# ---------------------------------------------------------------- email

_CSS = """<style>
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:720px;margin:0 auto;padding:16px;line-height:1.45;color:#222}
h1{font-size:1.5em}h2{font-size:1.2em;margin-top:1.4em;border-bottom:1px solid #ddd}h3{font-size:1.05em}
table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #ccc;padding:4px 8px;vertical-align:top}
code{background:#f3f3f3;padding:1px 4px;border-radius:3px}hr{border:0;border-top:2px solid #ddd;margin:24px 0}
</style>"""


_LIST_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def _space_lists(text: str) -> str:
    """Markdown needs a blank line before a list; the model often omits it after a bold lead-in."""
    out: list[str] = []
    for line in text.splitlines():
        if _LIST_LINE.match(line) and out and out[-1].strip() and not _LIST_LINE.match(out[-1]) and not out[-1].lstrip().startswith("|"):
            out.append("")
        out.append(line)
    return "\n".join(out)


def markdown_to_html(text: str) -> str:
    try:
        import markdown

        body = markdown.markdown(_space_lists(text), extensions=["tables", "sane_lists"])
    except ImportError:  # keep it readable even without the markdown package
        import html

        body = f"<pre style='white-space:pre-wrap'>{html.escape(text)}</pre>"
    return f"<!doctype html><html><head><meta charset='utf-8'>{_CSS}</head><body>{body}</body></html>"


def _smtp_settings() -> tuple[str, str, str] | None:
    host, user, password = (os.environ.get(k, "") for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))
    return (host, user, password) if host and user and password else None


def send_email(to: str, subject: str, text: str, html: bool = True) -> bool:
    """Send via SMTP if SMTP_* are set. Returns False when email is not configured."""
    settings = _smtp_settings()
    if not settings or not to:
        return False
    host, user, password = settings
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(text)
    if html:
        msg.add_alternative(markdown_to_html(text), subtype="html")
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587"))) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
    return True


def email_digest(text: str, subject: str) -> bool:
    """Parent digest to DIGEST_TO."""
    return send_email(os.environ.get("DIGEST_TO", ""), subject, text)


def sms_summary(cfg: Config, student: Student, today: date | None = None) -> str:
    """A few lines for a carrier text-message gateway: tests only."""
    today = today or date.today()
    tests = upcoming_assessments(Store(student.slug).load_assignments(), cfg.schedule.lookahead_days, today)
    if not tests:
        return f"{student.name.split()[0]}: no tests or quizzes in the next {cfg.schedule.lookahead_days} days."
    lines = [f"{student.name.split()[0]}, upcoming:"] + [f"{a.due:%a %m/%d} {a.course_name}: {a.title}" for a in tests[:6]]
    return "\n".join(lines)
