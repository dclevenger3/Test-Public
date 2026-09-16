"""Generate a study guide for a test or quiz from the class notes attached to it."""

from __future__ import annotations

from datetime import date

from playwright.sync_api import BrowserContext

from .llm import generate_text
from .materials import fetch_text
from .models import Assignment, Student
from .store import Store

SYSTEM = """You are a patient tutor helping a parent get their child ready for an upcoming test.
You are given the test's title, class, date, the teacher's description, and the text of the class notes,
slides, and documents that were attached. Write a study guide grounded ONLY in that material plus
well-established facts that material clearly assumes. Do not invent topics the notes never mention.

Write for the student's grade level. Use plain language and short sentences. Output Markdown with
exactly these sections:

# Study Guide: <test title>
One line: class, test date, and how many days away it is.

## What this test covers
Bulleted list of the 5-10 big ideas, each one sentence.

## Key terms
A two-column Markdown table: Term | Meaning (in the student's words). Include every bolded or defined term in the notes.

## Things to memorize
Formulas, dates, steps, rules, or lists the notes present as must-know. Skip if none.

## Worked examples
2-4 examples of the kind of problem or question the notes practice, fully worked out step by step. Skip for
subjects where that does not apply.

## Practice quiz
10 questions mixing multiple choice, short answer, and one "explain why". Number them. Put the answer key
at the very end of this section under a "### Answer key" heading.

## Flashcards
A Markdown table: Front | Back. 15-25 cards covering terms, facts, and quick questions.

## Study plan
Given the days left, a day-by-day plan (20-30 minutes each). Last day before the test is review only.

## Questions to ask the teacher
2-3 things the notes leave unclear or that seem likely to be on the test but are thin in the material.

If the attached material is empty or unrelated to the test, say so at the top in one sentence and build
the guide from the test title and description alone, clearly labeled as a best guess."""


def gather_materials(ctx: BrowserContext | None, a: Assignment) -> str:
    """Fetch any material text we do not already have, then concatenate it."""
    if ctx is not None:
        for m in a.materials:
            if not m.text:
                fetch_text(ctx, m)
    chunks = []
    for m in a.materials:
        if m.text.strip():
            chunks.append(f"=== {m.title} ({m.kind}) ===\n{m.text.strip()}\n")
    return "\n".join(chunks)


def build_prompt(student: Student, a: Assignment, material_text: str, today: date | None = None) -> str:
    today = today or date.today()
    days_left = (a.due.date() - today).days if a.due else None
    when = f"{a.due:%A, %B %d, %Y}" if a.due else "date not posted"
    left = f"{days_left} days away" if days_left is not None else "unknown"
    grade = f"grade {student.grade}" if student.grade else "grade not specified"
    return (
        f"Student: {student.name} ({grade})\n"
        f"Class: {a.course_name}\n"
        f"Test: {a.title} (type: {a.kind})\n"
        f"Test date: {when} ({left}); today is {today:%A, %B %d, %Y}\n"
        f"Teacher's description:\n{a.description or '(none)'}\n\n"
        f"--- ATTACHED NOTES AND MATERIALS ---\n{material_text or '(nothing attached or nothing could be fetched)'}"
    )


def generate_study_guide(store: Store, student: Student, a: Assignment, model: str,
                         ctx: BrowserContext | None = None, today: date | None = None) -> str:
    material_text = gather_materials(ctx, a)
    if ctx is not None:
        store.merge_assignments([a])  # persist any material text we just fetched
    prompt = build_prompt(student, a, material_text, today)
    guide = generate_text(SYSTEM, prompt, model=model, effort="high")
    path = store.guides_dir / f"{a.id}.md"
    path.write_text(guide)
    return str(path)
