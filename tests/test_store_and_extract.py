from datetime import datetime

from school_planner.extract import parse_due, stable_id
from school_planner.models import Assignment, Material
from school_planner.store import Store


def test_store_roundtrip_and_merge_keeps_material_text():
    s = Store("kid1")
    a = Assignment(id="x1", student="kid1", course_id="c", course_name="Math", title="Quiz 1", kind="quiz",
                   due=datetime(2026, 9, 20, 23, 59), materials=[Material(title="Notes", url="u1", text="fetched text")])
    s.save_assignments([a])
    fresh = Assignment(id="x1", student="kid1", course_id="c", course_name="Math", title="Quiz 1 (updated)", kind="quiz",
                       due=datetime(2026, 9, 21, 23, 59), materials=[Material(title="Notes", url="u1")])
    merged = s.merge_assignments([fresh])
    assert len(merged) == 1
    assert merged[0].title == "Quiz 1 (updated)"
    assert merged[0].materials[0].text == "fetched text"
    assert s.load_assignments()[0].due == datetime(2026, 9, 21, 23, 59)


def test_find_assignment_by_title_fragment():
    s = Store("kid1")
    s.save_assignments([Assignment(id="a", student="kid1", course_id="c", course_name="Sci", title="Unit 3 Test", kind="test")])
    assert s.find_assignment("unit 3").id == "a"


def test_parse_due_variants():
    today = datetime(2026, 9, 16)
    assert parse_due("Due Sep 24, 11:59 PM", today) == datetime(2026, 9, 24, 23, 59)
    assert parse_due("Sep 24", today) == datetime(2026, 9, 24, 23, 59)
    assert parse_due("", today) is None
    assert parse_due("No due date", today) is None


def test_stable_id_is_deterministic():
    assert stable_id("k", "Math", "Quiz", "Sep 1") == stable_id("k", "Math", "Quiz", "Sep 1")
    assert stable_id("k", "Math", "Quiz", "Sep 1") != stable_id("k", "Math", "Quiz", "Sep 2")
