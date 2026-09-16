---
name: setup
description: First-time setup of the school planner on this computer. Installs dependencies, creates config.yaml, logs the first student into ClassLink, runs the first sync, and verifies the weekly cycle end to end.
---

You are setting up the school planner for a parent on their own computer. Do the steps yourself
with the terminal; ask the parent only for the things listed under "Ask the parent". Keep each
message to them short and plain, no jargon. Stop and explain if a step fails; do not guess.

## 1. Check tools

Run `python --version` (or `python3 --version`), `git --version`, and `claude --version`.
Python must be 3.10 or newer. If anything is missing, tell the parent exactly what to install and
where (python.org, git-scm.com, https://code.claude.com), then stop until it is installed.

## 2. Install the planner

From this folder:

- Create a virtual environment if `.venv` does not exist: `python -m venv .venv`.
- Activate it (`source .venv/bin/activate` on Mac/Linux, `.venv\Scripts\activate` on Windows).
- `pip install -e .`
- `playwright install chromium`
- `pytest -q` must pass. If it does not, fix the cause before continuing.

## 3. Config

If `config.yaml` does not exist, copy `config.example.yaml` to `config.yaml`. Then ask the parent:

- Which time zone they are in (default America/New_York).
- Each child's first name and grade. Add one `students:` entry per child with a lowercase slug and
  `apps: {canvas: https://forsyth.instructure.com}` unless they say the school uses something else.

Never put passwords in config.yaml.

## 4. Log each child in

For each student slug, run `school-planner login <slug>` and tell the parent: "A browser window
opened. Sign in as <name>, click the Canvas tile once so it opens, then come back here and press
Enter in the terminal." Wait for them. The command prints "Session saved." on success.

If the parent prefers automatic logins, they may put `CLASSLINK_USER_<SLUG>` and
`CLASSLINK_PASS_<SLUG>` in `.env` (git-ignored) and you run `school-planner login <slug> --auto`
instead. Do not ask for the password yourself; let them type it into the browser or into `.env`.

## 5. First sync and check

- `school-planner sync <slug>` for each student.
- `school-planner list <slug> --tests` and show the parent the result.
- If sync fails on the Canvas step, read the error, look at `school_planner/connectors/canvas.py`,
  and fix it. The connector had not been run against this district before; small URL or field
  differences are expected. Add or update a test for any fix.

## 6. First full week

Run `school-planner weekly`. It writes `data/outbox/week-<date>/<Name>.html` for each child. Open
the folder for the parent (`open` on Mac, `start` on Windows) and tell them: send each child her
page by text, AirDrop, or email; run `/weekly` here any time to regenerate.

Offer to schedule it for Sunday evenings (cron on Mac/Linux, Task Scheduler on Windows) using
`scripts/weekly.sh` or `scripts/weekly.bat`, and set it up if they say yes.
