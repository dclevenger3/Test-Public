from datetime import date, datetime

from school_planner.config import ScheduleConfig
from school_planner.models import Assignment
from school_planner.schedule import build_events, missing_work, render_ics, render_markdown, study_sessions, upcoming_assessments, week_bounds

TODAY = date(2026, 9, 16)  # a Wednesday


def A(id, title, kind, due, status="", student="kid1"):
    return Assignment(id=id, student=student, course_id="c1", course_name="Science", title=title, kind=kind, due=due, status=status)


def test_week_bounds_monday_to_sunday():
    start, end = week_bounds(TODAY)
    assert start == date(2026, 9, 14) and end == date(2026, 9, 20)


def test_study_sessions_skip_past_days():
    cfg = ScheduleConfig(study_days_before=[4, 2, 1])
    test = A("t1", "Unit 1 Test", "test", datetime(2026, 9, 18, 8, 0))
    days = [e.day for e in study_sessions(test, cfg, TODAY)]
    # 4 days before (Sep 14) is in the past; 2 and 1 days before remain.
    assert days == [date(2026, 9, 16), date(2026, 9, 17)]


def test_study_sessions_fall_back_to_today():
    cfg = ScheduleConfig(study_days_before=[4])
    test = A("t1", "Quiz", "quiz", datetime(2026, 9, 17, 8, 0))
    assert [e.day for e in study_sessions(test, cfg, TODAY)] == [TODAY]


def test_homework_gets_no_study_sessions():
    assert study_sessions(A("h", "HW", "homework", datetime(2026, 9, 18)), ScheduleConfig(), TODAY) == []


def test_build_events_includes_next_week_test_study_this_week():
    cfg = ScheduleConfig(study_days_before=[4, 2, 1])
    items = [
        A("t1", "Unit 2 Test", "test", datetime(2026, 9, 22, 8, 0)),  # next Tuesday
        A("h1", "Worksheet", "homework", datetime(2026, 9, 17, 23, 59)),
        A("done", "Old HW", "homework", datetime(2026, 9, 17, 23, 59), status="submitted"),
    ]
    start, end = week_bounds(TODAY)
    events = build_events(items, cfg, start, end, TODAY)
    labels = [(e.day, e.kind) for e in events]
    assert (date(2026, 9, 17), "homework") in labels
    assert (date(2026, 9, 18), "study") in labels  # 4 days before Sep 22
    assert (date(2026, 9, 20), "study") in labels  # 2 days before
    assert all(e.label != "Old HW" for e in events)
    assert all(e.day <= end for e in events)


def test_upcoming_and_missing():
    items = [
        A("t1", "Test", "test", datetime(2026, 9, 25)),
        A("t2", "Far Test", "test", datetime(2026, 11, 1)),
        A("m1", "Late HW", "homework", datetime(2026, 9, 10)),
        A("m2", "Flagged", "homework", datetime(2026, 9, 30), status="missing"),
        A("ok", "Graded old", "homework", datetime(2026, 9, 1), status="graded"),
    ]
    assert [a.id for a in upcoming_assessments(items, 14, TODAY)] == ["t1"]
    assert {a.id for a in missing_work(items, TODAY)} == {"m1", "m2"}


def test_render_markdown_and_ics():
    cfg = ScheduleConfig()
    items = [A("t1", "Unit 1 Test", "test", datetime(2026, 9, 18, 8, 0))]
    start, end = week_bounds(TODAY)
    events = build_events(items, cfg, start, end, TODAY)
    md = render_markdown(events, start, end, {"kid1": "Kid One"})
    assert "Friday, Sep 18" in md and "Unit 1 Test" in md and "Study for Unit 1 Test" in md and "Kid One" in md
    ics = render_ics(events)
    assert ics.startswith("BEGIN:VCALENDAR") and ics.count("BEGIN:VEVENT") == len(events)
    assert "DTSTART;VALUE=DATE:20260918" in ics


def test_duplicate_source_entries_do_not_double_study_sessions():
    cfg = ScheduleConfig(study_days_before=[2, 1])
    items = [A("t1", "Unit 2 Test", "test", datetime(2026, 9, 18, 8)), A("t2", "Unit 2 Test", "test", datetime(2026, 9, 18, 8))]
    start, end = week_bounds(TODAY)
    events = build_events(items, cfg, start, end, TODAY)
    assert sum(1 for e in events if e.kind == "study") == 2
    assert sum(1 for e in events if e.kind == "test") == 1
