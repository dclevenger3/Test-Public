"""Wiring tests for the Claude layer. No network: the SDK client is replaced with a fake."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from school_planner import llm
from school_planner.models import Assignment, Material, Student
from school_planner.store import Store
from school_planner.study_guide import build_prompt, generate_study_guide


class FakeMessages:
    def __init__(self, text, stop_reason="end_turn"):
        self.text, self.stop_reason, self.calls = text, stop_reason, []

    def _msg(self):
        return SimpleNamespace(stop_reason=self.stop_reason, stop_details=None,
                               content=[SimpleNamespace(type="text", text=self.text)])

    def create(self, **kw):
        self.calls.append(kw)
        return self._msg()

    def stream(self, **kw):
        self.calls.append(kw)
        msg = self._msg()

        class Ctx:
            def __enter__(self_inner):
                return SimpleNamespace(get_final_message=lambda: msg)

            def __exit__(self_inner, *a):
                return False

        return Ctx()


@pytest.fixture
def fake(monkeypatch):
    fm = FakeMessages('{"ok": true}')
    monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=fm)))
    monkeypatch.delenv("SCHOOL_PLANNER_NO_FALLBACK", raising=False)
    return fm


def test_generate_json_request_shape(fake):
    out = llm.generate_json("sys", "user", {"type": "object"}, model="claude-opus-5")
    assert out == {"ok": True}
    kw = fake.calls[0]
    assert kw["model"] == "claude-opus-5"
    assert kw["thinking"] == {"type": "adaptive"}
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in kw["betas"]


def test_generate_text_streams_and_returns_text(fake):
    fake.text = "# Study Guide"
    assert llm.generate_text("sys", "user") == "# Study Guide"
    assert fake.calls[0]["output_config"] == {"effort": "high"}


def test_refusal_raises(fake):
    fake.stop_reason = "refusal"
    with pytest.raises(RuntimeError):
        llm.generate_text("sys", "user")


def test_fallback_can_be_disabled(fake, monkeypatch):
    monkeypatch.setenv("SCHOOL_PLANNER_NO_FALLBACK", "1")
    llm.generate_text("sys", "user")
    assert "fallbacks" not in fake.calls[0] and "betas" not in fake.calls[0]


def test_build_prompt_and_generate_guide_writes_file(fake, tmp_path):
    fake.text = "# Study Guide: Unit 2 Test"
    student = Student(name="Kid One", slug="kid1", grade=7)
    a = Assignment(id="canvas-101", student="kid1", course_id="7", course_name="Science", title="Unit 2 Test",
                   kind="test", due=datetime(2026, 9, 22, 8), description="Cells",
                   materials=[Material(title="Notes", url="u", kind="slides", text="Mitochondria make ATP")])
    prompt = build_prompt(student, a, "=== Notes ===\nMitochondria make ATP", today=date(2026, 9, 16))
    assert "6 days away" in prompt and "grade 7" in prompt and "Mitochondria" in prompt
    store = Store("kid1")
    path = generate_study_guide(store, student, a, "claude-opus-5", ctx=None, today=date(2026, 9, 16))
    assert path.endswith("canvas-101.md") and "Study Guide" in open(path).read()
    assert "Mitochondria make ATP" in fake.calls[0]["messages"][0]["content"]
