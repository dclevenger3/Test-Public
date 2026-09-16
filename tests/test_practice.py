import json
from datetime import date, datetime

from school_planner.models import Assignment, Material, Student
from school_planner.practice import build_prompt, generate_practice_test, render_html
from school_planner.store import Store

QUESTIONS = [
    {"type": "multiple_choice", "question": "Which organelle makes ATP?", "choices": ["Nucleus", "Mitochondria", "Ribosome", "Vacuole"], "answer": "Mitochondria", "explanation": "Mitochondria are the powerhouse."},
    {"type": "true_false", "question": "Animal cells have cell walls.", "choices": ["True", "False"], "answer": "False", "explanation": "Only plant cells do."},
    {"type": "short_answer", "question": "Name the three parts of cell theory.", "choices": [], "answer": "All living things are made of cells; cells are the basic unit of life; cells come from cells.", "explanation": "These are the three rules."},
]


def test_render_html_is_self_contained_and_grades_itself():
    html = render_html(Student(name="Madison", slug="madison", grade=8), "Cells practice", QUESTIONS, "normal")
    assert html.count("class='q'") == 3 and "function check()" in html
    assert "type='radio'" in html and "type='text'" in html
    assert "data-answer='Mitochondria'" in html
    assert "<script src" not in html  # no network needed on a phone


def test_prompt_lists_already_asked_questions():
    s = Student(name="Madison", slug="madison", grade=8)
    p = build_prompt(s, "Science: Unit 2 Test", "notes", 10, "harder", ["Old question?"], due=datetime(2026, 9, 22))
    assert "grade 8" in p and "Old question?" in p and "Difficulty: harder" in p and "Number of questions: 10" in p


def test_generate_practice_test_writes_html_and_history(monkeypatch, tmp_path):
    calls = []

    def fake_json(system, user, schema, **kw):
        calls.append(user)
        return {"title": "Cells practice", "questions": QUESTIONS}

    monkeypatch.setattr("school_planner.practice.generate_json", fake_json)
    store = Store("madison")
    s = Student(name="Madison", slug="madison", grade=8)
    a = Assignment(id="canvas-1", student="madison", course_id="7", course_name="Science", title="Unit 2 Test", kind="test",
                   due=datetime(2026, 9, 22, 8), materials=[Material(title="Notes", url="u", text="cells notes")])
    path = generate_practice_test(store, s, "opus", "claude-code", assignment=a, n=3, today=date(2026, 9, 16))
    assert path.exists() and path.suffix == ".html" and "cells notes" in calls[0]
    # a second test on the same assignment is told not to repeat the first one's questions
    generate_practice_test(store, s, "opus", "claude-code", assignment=a, n=3, today=date(2026, 9, 16))
    assert "Which organelle makes ATP?" in calls[1]
    history = json.loads((store.dir / "practice" / "canvas-1.json").read_text())
    assert len(history) == 6


def test_topic_mode_needs_no_assignment(monkeypatch):
    monkeypatch.setattr("school_planner.practice.generate_json", lambda *a, **k: {"title": "Fractions", "questions": QUESTIONS[:1]})
    store = Store("lily")
    path = generate_practice_test(store, Student(name="Lily", slug="lily", grade=6), "opus", "claude-code", topic="adding fractions", n=1)
    assert path.name.startswith("topic-adding-fractions")
