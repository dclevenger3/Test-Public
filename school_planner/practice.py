"""On-demand practice tests: fresh questions each time, self-grading in the browser or printable."""

from __future__ import annotations

import html
import json
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import BrowserContext

from .llm import generate_json
from .models import Assignment, Student
from .store import Store
from .study_guide import gather_materials

SYSTEM = """You write practice tests for a parent to give their child before a real test.
Ground every question in the material provided (class notes, slides, the teacher's description). If a
topic is given instead of material, write grade-appropriate questions on that topic.

Rules:
- Match the grade level in wording and difficulty. "easier" means mostly recall; "harder" means mostly
  application and explain-why.
- Mix types: about 60% multiple_choice, 20% true_false, 20% short_answer. Multiple choice has exactly 4
  choices with one correct; make the wrong choices plausible, not silly.
- Every question has a one or two sentence explanation a student could learn from.
- Do not repeat or lightly reword any question listed under "Already asked".
- For short_answer, `answer` is a model answer of one sentence or a few words; `choices` is empty.
- For true_false, choices are exactly ["True", "False"]."""

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["multiple_choice", "true_false", "short_answer"]},
                    "question": {"type": "string"},
                    "choices": {"type": "array", "items": {"type": "string"}},
                    "answer": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["type", "question", "choices", "answer", "explanation"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "questions"],
    "additionalProperties": False,
}


def _history_path(store: Store, key: str) -> Path:
    d = store.dir / "practice"
    d.mkdir(exist_ok=True)
    return d / f"{key}.json"


def _load_history(store: Store, key: str) -> list[str]:
    p = _history_path(store, key)
    return json.loads(p.read_text()) if p.exists() else []


def _save_history(store: Store, key: str, questions: list[str]) -> None:
    _history_path(store, key).write_text(json.dumps(questions, indent=2))


def build_prompt(student: Student, subject: str, material_text: str, n: int, level: str, already: list[str],
                 description: str = "", due: datetime | None = None) -> str:
    grade = f"grade {student.grade}" if student.grade else "grade not specified"
    when = f"{due:%A, %B %d}" if due else "not posted"
    asked = "\n".join(f"- {q}" for q in already[-60:]) or "(none)"
    return (
        f"Student: {student.name} ({grade})\nSubject / test: {subject}\nTest date: {when}\n"
        f"Number of questions: {n}\nDifficulty: {level}\n"
        f"Teacher's description:\n{description or '(none)'}\n\n"
        f"Already asked (do not repeat):\n{asked}\n\n"
        f"--- MATERIAL ---\n{material_text or '(no material attached; use the subject and grade level)'}"
    )


def generate_practice_test(store: Store, student: Student, model: str, backend: str, *, assignment: Assignment | None = None,
                           topic: str = "", n: int = 15, level: str = "normal", ctx: BrowserContext | None = None,
                           today: date | None = None) -> Path:
    """Write data/<slug>/practice/<key>-<stamp>.html and return its path."""
    if assignment is None and not topic:
        raise ValueError("need an assignment or a topic")
    key = assignment.id if assignment else "topic-" + "".join(c if c.isalnum() else "-" for c in topic.lower())[:40].strip("-")
    subject = f"{assignment.course_name}: {assignment.title}" if assignment else topic
    material = gather_materials(ctx, assignment) if assignment else ""
    if assignment is not None and ctx is not None:
        store.merge_assignments([assignment])
    already = _load_history(store, key)
    prompt = build_prompt(student, subject, material, n, level, already,
                          description=assignment.description if assignment else "", due=assignment.due if assignment else None)
    data = generate_json(SYSTEM, prompt, SCHEMA, model=model, effort="high", backend=backend)
    questions = data["questions"][:n]
    _save_history(store, key, already + [q["question"] for q in questions])
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = store.dir / "practice" / f"{key}-{stamp}.html"
    path.write_text(render_html(student, data.get("title") or subject, questions, level), encoding="utf-8")
    (store.dir / "practice" / f"{key}-{stamp}.json").write_text(json.dumps(data, indent=2))
    return path


# ---------------------------------------------------------------- rendering

_CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:720px;margin:0 auto;padding:16px;line-height:1.45;color:#222;background:#fff}
h1{font-size:1.4em;margin-bottom:0}.sub{color:#666;margin-top:4px}
.q{border:1px solid #ddd;border-radius:10px;padding:12px 14px;margin:14px 0}
.q p.t{font-weight:600;margin:0 0 8px}
label{display:block;padding:6px 8px;border-radius:6px;cursor:pointer}label:hover{background:#f5f5f5}
input[type=text]{width:100%;padding:8px;font-size:1em;border:1px solid #ccc;border-radius:6px;box-sizing:border-box}
.exp{display:none;margin-top:8px;padding:8px 10px;border-radius:6px;background:#f6f8fa;font-size:.95em}
.q.right{border-color:#2e9e5b;background:#f2fbf5}.q.wrong{border-color:#d9534f;background:#fdf4f4}
.q.right .exp,.q.wrong .exp,.show .exp{display:block}
button{font-size:1em;padding:10px 16px;border-radius:8px;border:0;background:#2563eb;color:#fff;cursor:pointer;margin-right:8px}
button.alt{background:#6b7280}#score{font-weight:700;font-size:1.2em;margin:12px 0}
.selfmark{margin-top:6px;font-size:.95em}
@media print{button,.selfmark{display:none}.q{break-inside:avoid}body.key .exp{display:block}}
"""

_JS = """
function check(){
  let right=0,total=0;
  document.querySelectorAll('.q').forEach(q=>{
    total++; q.classList.remove('right','wrong');
    const ans=q.dataset.answer.trim().toLowerCase();
    let got=null;
    if(q.dataset.type==='short_answer'){
      got = q.querySelector('.selfmark input').checked ? ans : '';
    } else {
      const sel=q.querySelector('input[type=radio]:checked'); got = sel ? sel.value.trim().toLowerCase() : '';
    }
    if(got===ans){right++;q.classList.add('right')} else {q.classList.add('wrong')}
  });
  document.getElementById('score').textContent = `Score: ${right} / ${total}` + (right===total ? '  Perfect!' : right>=total*0.8 ? '  Nice work.' : '  Keep going; read the explanations below.');
  window.scrollTo({top:0,behavior:'smooth'});
}
function reveal(){document.body.classList.toggle('show')}
function printKey(){document.body.classList.add('key');window.print();document.body.classList.remove('key')}
function reset(){document.querySelectorAll('input').forEach(i=>{if(i.type==='radio'||i.type==='checkbox')i.checked=false;else i.value=''});document.querySelectorAll('.q').forEach(q=>q.classList.remove('right','wrong'));document.getElementById('score').textContent='';document.body.classList.remove('show')}
"""


def render_html(student: Student, title: str, questions: list[dict], level: str) -> str:
    e = html.escape
    parts = ["<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
             f"<title>{e(title)}</title><style>{_CSS}</style></head><body>",
             f"<h1>{e(title)}</h1><p class='sub'>Practice test for {e(student.name)} · {len(questions)} questions · {e(level)}</p>",
             "<div id='score'></div>",
             "<p><button onclick='check()'>Check my answers</button><button class='alt' onclick='reveal()'>Show explanations</button>"
             "<button class='alt' onclick='printKey()'>Print with answer key</button><button class='alt' onclick='reset()'>Start over</button></p>"]
    for i, q in enumerate(questions, 1):
        parts.append(f"<div class='q' data-type='{e(q['type'])}' data-answer='{e(q['answer'])}'>")
        parts.append(f"<p class='t'>{i}. {e(q['question'])}</p>")
        if q["type"] in {"multiple_choice", "true_false"}:
            for c in q["choices"]:
                parts.append(f"<label><input type='radio' name='q{i}' value='{e(c)}'> {e(c)}</label>")
        else:
            parts.append("<input type='text' placeholder='Your answer'>")
            parts.append("<div class='selfmark'><label><input type='checkbox'> I got this right (compare with the answer after checking)</label></div>")
        parts.append(f"<div class='exp'><b>Answer:</b> {e(q['answer'])}<br>{e(q['explanation'])}</div></div>")
    parts.append(f"<script>{_JS}</script></body></html>")
    return "\n".join(parts)
