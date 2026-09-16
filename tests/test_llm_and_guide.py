"""Wiring tests for the Claude layer. No network: both backends are faked."""

import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from school_planner import llm
from school_planner.models import Assignment, Material, Student
from school_planner.store import Store
from school_planner.study_guide import build_prompt, generate_study_guide


# ---------------- claude-code backend ----------------

class FakeProc:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


@pytest.fixture
def fake_cli(monkeypatch):
    calls = []
    envelope = {"is_error": False, "subtype": "success", "result": "# Study Guide", "structured_output": None}

    def run(cmd, **kw):
        calls.append((cmd, kw))
        return FakeProc(json.dumps(envelope))

    monkeypatch.setattr(llm.subprocess, "run", run)
    monkeypatch.setattr(llm, "claude_bin", lambda: "/usr/bin/claude")
    return calls, envelope


def test_cli_text_generation_flags(fake_cli):
    calls, _ = fake_cli
    assert llm.generate_text("SYS", "USER", model="opus", effort="high") == "# Study Guide"
    cmd, kw = calls[0]
    assert cmd[:2] == ["/usr/bin/claude", "-p"]
    assert kw["input"] == "USER"
    for flag, value in (("--model", "opus"), ("--effort", "high"), ("--system-prompt", "SYS"), ("--output-format", "json"), ("--tools", "")):
        assert cmd[cmd.index(flag) + 1] == value
    assert "--no-session-persistence" in cmd and "--json-schema" not in cmd


def test_cli_json_uses_structured_output(fake_cli):
    calls, envelope = fake_cli
    envelope["structured_output"] = {"assignments": []}
    out = llm.generate_json("SYS", "USER", {"type": "object"}, model="sonnet")
    assert out == {"assignments": []}
    cmd, _ = calls[0]
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == {"type": "object"}


def test_cli_error_envelope_raises(fake_cli):
    _, envelope = fake_cli
    envelope.update(is_error=True, result="Not logged in")
    with pytest.raises(llm.LLMError, match="Not logged in"):
        llm.generate_text("s", "u")


def test_cli_missing_binary(monkeypatch):
    monkeypatch.setattr(llm.shutil, "which", lambda *_: None)
    monkeypatch.delenv("CLAUDE_BIN", raising=False)
    with pytest.raises(SystemExit):
        llm.claude_bin()


# ---------------- api backend ----------------

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
def fake_api(monkeypatch):
    fm = FakeMessages('{"ok": true}')
    monkeypatch.setattr(llm, "_api_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=fm)))
    monkeypatch.delenv("SCHOOL_PLANNER_NO_FALLBACK", raising=False)
    return fm


def test_api_json_request_shape(fake_api):
    out = llm.generate_json("sys", "user", {"type": "object"}, model="opus", backend="api")
    assert out == {"ok": True}
    kw = fake_api.calls[0]
    assert kw["model"] == "claude-opus-5"  # alias mapped to a full id
    assert kw["thinking"] == {"type": "adaptive"}
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in kw["betas"]


def test_api_refusal_raises(fake_api):
    fake_api.stop_reason = "refusal"
    with pytest.raises(llm.LLMError):
        llm.generate_text("sys", "user", backend="api")


def test_api_fallback_can_be_disabled(fake_api, monkeypatch):
    monkeypatch.setenv("SCHOOL_PLANNER_NO_FALLBACK", "1")
    llm.generate_text("sys", "user", backend="api")
    assert "fallbacks" not in fake_api.calls[0]


# ---------------- study guide ----------------

def test_build_prompt_and_generate_guide_writes_file(fake_cli, tmp_path):
    calls, envelope = fake_cli
    envelope["result"] = "# Study Guide: Unit 2 Test"
    student = Student(name="Kid One", slug="kid1", grade=7)
    a = Assignment(id="canvas-101", student="kid1", course_id="7", course_name="Science", title="Unit 2 Test",
                   kind="test", due=datetime(2026, 9, 22, 8), description="Cells",
                   materials=[Material(title="Notes", url="u", kind="slides", text="Mitochondria make ATP")])
    prompt = build_prompt(student, a, "=== Notes ===\nMitochondria make ATP", today=date(2026, 9, 16))
    assert "6 days away" in prompt and "grade 7" in prompt and "Mitochondria" in prompt
    store = Store("kid1")
    path = generate_study_guide(store, student, a, "opus", ctx=None, today=date(2026, 9, 16))
    assert path.endswith("canvas-101.md") and "Study Guide" in open(path).read()
    assert "Mitochondria make ATP" in calls[0][1]["input"]


def test_write_outbox_produces_one_page_per_kid(tmp_path):
    from school_planner.config import Config, ScheduleConfig
    from school_planner.report import write_outbox

    cfg = Config(students=[Student(name="Madison", slug="madison", grade=8), Student(name="Lily", slug="lily", grade=6)],
                 schedule=ScheduleConfig())
    Store("madison").save_assignments([Assignment(id="t", student="madison", course_id="c", course_name="Science",
                                                  title="Unit 2 Test", kind="test", due=datetime(2026, 9, 22, 8))])
    files = write_outbox(cfg, today=date(2026, 9, 16))
    assert [f.name for f in files] == ["Madison.html", "Lily.html", "Family.html"]
    assert files[0].parent.name == "week-2026-09-16"
    html = files[0].read_text()
    assert "<html" in html and "Unit 2 Test" in html and "Hi Madison" in html


def test_markdown_lists_after_bold_lead_in_render_as_lists():
    from school_planner.report import markdown_to_html

    html = markdown_to_html("**Steps:**\n1. First\n2. Second\n**Words:**\n- a\n- b\n")
    assert html.count("<li>") == 4
