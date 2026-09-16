import pytest

from school_planner.classify import classify


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Unit 3 Test", "test"),
        ("Chapter 5 Quiz", "quiz"),
        ("Midterm Exam", "exam"),
        ("Final Exam Study Guide", "homework"),
        ("Unit 4 Test Review", "homework"),
        ("Vocabulary Quiz #2", "quiz"),
        ("Science Fair Project", "project"),
        ("Read Chapter 7 pages 120-135", "reading"),
        ("Math HW 4.2", "homework"),
        ("Exit Ticket 9/12", "quiz"),
        ("Field trip permission slip", "other"),
        ("Benchmark Assessment", "test"),
    ],
)
def test_classify_titles(title, expected):
    assert classify(title) == expected


def test_native_kind_wins_for_plain_quiz():
    assert classify("Fractions Check", native_kind="quiz") == "quiz"


def test_native_quiz_titled_test_is_test():
    assert classify("Unit 2 Test", native_kind="quiz") == "test"


def test_description_can_promote_to_test():
    assert classify("Cells", "This is the unit test on cell structure") == "test"
