"""Build the weekly schedule: what is due each day, plus study sessions before every test."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .config import ScheduleConfig
from .models import Assignment

KIND_ICON = {"exam": "🔴", "test": "🔴", "quiz": "🟠", "project": "🟣", "homework": "📝", "reading": "📖", "other": "•"}


@dataclass
class Event:
    day: date
    student: str
    label: str
    kind: str  # assignment kind, or "study"
    course: str
    assignment: Assignment | None = None
    minutes: int | None = None

    @property
    def icon(self) -> str:
        return "📚" if self.kind == "study" else KIND_ICON.get(self.kind, "•")


def week_bounds(anchor: date | None = None) -> tuple[date, date]:
    """Monday..Sunday containing `anchor` (default today)."""
    anchor = anchor or date.today()
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=6)


def study_sessions(a: Assignment, cfg: ScheduleConfig, today: date) -> list[Event]:
    """Study blocks before an assessment: N days before, but never in the past."""
    if not a.is_assessment or not a.due:
        return []
    due = a.due.date()
    days = sorted(set(cfg.study_days_before), reverse=True)
    out: list[Event] = []
    for d in days:
        day = due - timedelta(days=d)
        if day < today or day >= due:
            continue
        out.append(Event(day=day, student=a.student, label=f"Study for {a.title}", kind="study",
                         course=a.course_name, assignment=a, minutes=cfg.study_session_minutes))
    # If every planned day is already gone and the test is still ahead, study today.
    if not out and due > today:
        out.append(Event(day=today, student=a.student, label=f"Study for {a.title}", kind="study",
                         course=a.course_name, assignment=a, minutes=cfg.study_session_minutes))
    return out


def build_events(assignments: list[Assignment], cfg: ScheduleConfig, start: date, end: date,
                 today: date | None = None) -> list[Event]:
    today = today or date.today()
    events: list[Event] = []
    for a in assignments:
        if not a.due or a.status in {"submitted", "graded"}:
            continue
        if start <= a.due.date() <= end:
            events.append(Event(day=a.due.date(), student=a.student, label=a.title, kind=a.kind, course=a.course_name, assignment=a))
        # Tests due after this week still create study sessions inside this week.
        for ev in study_sessions(a, cfg, today):
            if start <= ev.day <= end:
                events.append(ev)
    order = {"exam": 0, "test": 0, "quiz": 1, "project": 2, "study": 3, "homework": 4, "reading": 5, "other": 6}
    events.sort(key=lambda e: (e.day, e.student, order.get(e.kind, 9), e.label))
    return events


def upcoming_assessments(assignments: list[Assignment], days: int, today: date | None = None) -> list[Assignment]:
    today = today or date.today()
    horizon = today + timedelta(days=days)
    return sorted(
        (a for a in assignments if a.is_assessment and a.due and today <= a.due.date() <= horizon),
        key=lambda a: a.due,
    )


def missing_work(assignments: list[Assignment], today: date | None = None) -> list[Assignment]:
    today = today or date.today()
    return sorted(
        (a for a in assignments if a.status == "missing" or (a.due and a.due.date() < today and a.status == "")),
        key=lambda a: a.due or datetime.max,
    )


# ---------- rendering ----------

def render_markdown(events: list[Event], start: date, end: date, students: dict[str, str]) -> str:
    lines = [f"# Week of {start:%b %d} to {end:%b %d, %Y}", ""]
    if not events:
        lines.append("Nothing due this week. 🎉")
        return "\n".join(lines)
    for i in range(7):
        day = start + timedelta(days=i)
        todays = [e for e in events if e.day == day]
        lines.append(f"## {day:%A, %b %d}")
        if not todays:
            lines.append("_nothing_")
        for e in todays:
            who = students.get(e.student, e.student)
            extra = f" ({e.minutes} min)" if e.minutes else ""
            due_time = f" at {e.assignment.due:%I:%M %p}" if e.assignment and e.assignment.due and e.kind != "study" and e.assignment.due.time() != datetime.max.time() and (e.assignment.due.hour, e.assignment.due.minute) != (23, 59) else ""
            lines.append(f"- {e.icon} **{who}** · {e.course} · {e.label}{extra}{due_time}")
        lines.append("")
    lines.append("Legend: 🔴 test/exam · 🟠 quiz · 🟣 project · 📝 homework · 📖 reading · 📚 study session")
    return "\n".join(lines)


def render_ics(events: list[Event], calendar_name: str = "School Planner") -> str:
    """Minimal iCalendar file, importable into Google/Apple/Outlook calendars."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//school-planner//EN", f"X-WR-CALNAME:{esc(calendar_name)}"]
    for n, e in enumerate(events):
        uid = f"{e.day:%Y%m%d}-{n}-{abs(hash((e.student, e.label))) % 10**8}@school-planner"
        out += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}"]
        if e.kind == "study":
            start_dt = datetime.combine(e.day, datetime.min.time()).replace(hour=16)
            end_dt = start_dt + timedelta(minutes=e.minutes or 30)
            out += [f"DTSTART:{start_dt:%Y%m%dT%H%M%S}", f"DTEND:{end_dt:%Y%m%dT%H%M%S}"]
        else:
            out += [f"DTSTART;VALUE=DATE:{e.day:%Y%m%d}", f"DTEND;VALUE=DATE:{e.day + timedelta(days=1):%Y%m%d}"]
        out += [f"SUMMARY:{esc(f'{e.icon} {e.student}: {e.label}')}", f"DESCRIPTION:{esc(e.course)}"]
        if e.assignment and e.assignment.url:
            out.append(f"URL:{e.assignment.url}")
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"
