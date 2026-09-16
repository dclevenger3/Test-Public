---
name: practice
description: Make a fresh practice test right now for one of the kids, either for a test on file ("the cells test") or any topic ("adding fractions"), and open it. Self-grading on a phone, printable with an answer key.
---

The parent wants a practice test now. Work out from their words: which child (slug from
config.yaml), whether it is for a test on file or a free topic, how many questions (default 15),
and difficulty (easier / normal / harder, default normal).

1. Activate `.venv` if it exists.
2. If it is a test on file, find it with `school-planner list <slug> --tests` and use part of its
   title. Run:
   `school-planner practice <slug> "<part of title>" --questions N --level L --open`
   For a free topic run:
   `school-planner practice <slug> --topic "<topic>" --questions N --level L --open`
3. Tell the parent in one or two sentences what was made and where the file is
   (`data/<slug>/practice/...html`). It grades itself in the browser; "Print with answer key" makes
   a paper copy. Each run makes new questions and avoids repeating earlier ones for the same test.
4. Offer: another one harder, or a printable version, or a different topic.
