"""Decide whether an assignment is a test, quiz, exam, or regular work from its title and text."""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("exam", re.compile(r"\b(final|midterm|semester)\b.*\b(exam|test)\b|\bexam\b", re.I)),
    ("test", re.compile(r"\b(test|assessment|unit\s*check|checkpoint|benchmark|summative)\b", re.I)),
    ("quiz", re.compile(r"\bquiz(zes)?\b|\bpop\s*quiz\b|\bcheck[- ]?in\b|\bexit\s*ticket\b", re.I)),
    ("project", re.compile(r"\bproject\b|\bpresentation\b|\bposter\b|\bessay\b|\breport\b", re.I)),
    ("reading", re.compile(r"\bread(ing)?\b|\bchapter\b|\bpages?\s*\d", re.I)),
    ("homework", re.compile(r"\bhomework\b|\bhw\b|\bworksheet\b|\bpractice\b|\bproblem\s*set\b", re.I)),
]

# Words that mean "this is about a test but is not the test itself".
_NOT_THE_TEST = re.compile(r"\b(review|study\s*guide|practice\s*(test|quiz)|prep|retake\s*form)\b", re.I)


def classify(title: str, description: str = "", native_kind: str | None = None) -> str:
    """Return one of: exam, test, quiz, project, reading, homework, other.

    native_kind is what the LMS itself says (e.g. Canvas "quiz"), which wins when present.
    """
    if native_kind in {"quiz", "test", "exam"}:
        # A Canvas "quiz" titled "Unit 3 Test" is a test.
        for kind, pat in _PATTERNS[:2]:
            if pat.search(title):
                return kind
        return native_kind

    text = f"{title}\n{description[:300]}"
    if _NOT_THE_TEST.search(title):
        # "Unit 4 Test Review" is homework that hints at a test, not the test.
        for kind, pat in _PATTERNS[3:]:
            if pat.search(text):
                return kind
        return "homework"
    for kind, pat in _PATTERNS:
        if pat.search(title) or (kind in {"exam", "test", "quiz"} and pat.search(text)):
            return kind
    return "other"
