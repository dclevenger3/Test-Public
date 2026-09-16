from datetime import datetime

from school_planner.connectors.canvas_feed import parse_events, parse_feed

ICS = "\r\n".join([
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "BEGIN:VEVENT",
    "DTSTAMP:20260901T120000Z",
    "UID:event-assignment-4455@forsyth.instructure.com",
    "DTSTART;VALUE=DATE:20260922",
    "SUMMARY:Unit 2 Test: Cells and Organelles [7th Grade Science]",
    "DESCRIPTION:Covers cell theory\\, organelles\\, and plant vs animal cells.",
    "X-ALT-DESC;FMTTYPE=text/html:<p>Covers cell theory. <a href=\"https://docs.google.com/presentation/d/abc/edit\">Cells slides</a></p>",
    "URL:https://forsyth.instructure.com/courses/123/assignments/4455",
    "END:VEVENT",
    "BEGIN:VEVENT",
    "UID:event-assignment-4456@forsyth.instructure.com",
    "DTSTART:20260918T035900Z",
    "SUMMARY:Integers Check [Math 7]",
    "DESCRIPTION:",
    "URL:https://forsyth.instructure.com/courses/124/quizzes/4456",
    "END:VEVENT",
    "BEGIN:VEVENT",
    "UID:event-calendar-event-9@forsyth.instructure.com",
    "DTSTART;VALUE=DATE:20260925",
    "SUMMARY:Teacher workday",
    "URL:https://forsyth.instructure.com/calendar?event_id=9",
    "END:VEVENT",
    "END:VCALENDAR",
    "",
])


def test_parse_events_handles_folding_and_params():
    ics = "BEGIN:VEVENT\r\nSUMMARY:A very long\r\n  title\r\nDTSTART;VALUE=DATE:20260901\r\nEND:VEVENT\r\n"
    ev = parse_events(ics)[0]
    assert ev["SUMMARY"] == "A very long title"
    assert ev["DTSTART"] == "20260901" and ev["DTSTART_PARAMS"] == "VALUE=DATE"


def test_parse_feed_extracts_assignments_and_courses():
    courses, items = parse_feed(ICS, "kid1")
    assert {c.name for c in courses} == {"7th Grade Science", "Math 7"}
    assert [a.id for a in items] == ["canvas-4455", "canvas-4456"]  # calendar event skipped
    test = items[0]
    assert test.title == "Unit 2 Test: Cells and Organelles" and test.kind == "test"
    assert test.due == datetime(2026, 9, 22, 23, 59)
    assert "cell theory, organelles" in test.description
    assert test.materials and "docs.google.com/presentation" in test.materials[0].url
    quiz = items[1]
    assert quiz.kind == "quiz" and quiz.course_name == "Math 7" and quiz.due is not None
    assert quiz.due.year == 2026 and quiz.due.month == 9


def test_feed_ids_match_browser_connector_ids():
    _, items = parse_feed(ICS, "kid1")
    assert all(a.id.startswith("canvas-") for a in items)
