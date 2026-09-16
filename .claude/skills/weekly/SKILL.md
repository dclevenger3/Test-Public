---
name: weekly
description: Run this week's cycle for the school planner. Syncs Canvas, builds the schedule, writes study guides for upcoming tests, and opens the outbox folder with one page per child to send.
---

Run the weekly cycle for the parent and hand them the pages to send.

1. Activate `.venv` if it exists. If `config.yaml` is missing, tell the parent to run `/setup` first and stop.
2. Run `school-planner weekly`. If it stops at a login error, run `school-planner login <slug>` and
   ask the parent to sign in again, then rerun.
3. Run `school-planner list --tests` and summarize in two or three plain sentences: which tests
   are coming up for which child, and which study guides were written.
4. Open `data/outbox/week-<today>/` for the parent and list the files by name. Tell them each
   child's `.html` page opens on a phone and can be sent by text, AirDrop, or email.
5. If anything looked wrong (a test classified as homework, a due date off, a guide with no
   material), say so and offer to fix it.
