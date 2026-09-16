# School Planner

Python CLI that pulls kids' school assignments from the systems behind ClassLink, builds a weekly
schedule, and writes study guides for tests. The parent runs it on their own machine.

## Commands (run from this folder, inside the venv)

- `school-planner login <slug>` opens a browser so the parent logs a kid into ClassLink once. Never ask for or store passwords.
- `school-planner discover <slug>` lists the launchpad tiles; use it to find which LMS to put under `apps:` in config.yaml.
- `school-planner sync [slug] --headless` pulls courses and assignments into `data/<slug>/assignments.json`. Connectors: `canvas` (browser session), `canvas_feed` (private .ics URL, no browser), `google_classroom` (page capture).
- `school-planner capture <slug>` manual page capture for any LMS; Claude extracts the assignments.
- `school-planner list [slug] [--tests]` shows what is on file.
- `school-planner schedule [slug] [--next]` prints the week and writes `data/schedules/week-*.md` and `.ics`.
- `school-planner study-guide [slug] [assignment] [--force] [--no-browser]` writes `data/<slug>/guides/<id>.md`.
- `school-planner digest [--email]` writes `data/digests/week-*.md`.
- `school-planner weekly [--email]` does sync, schedule, study guides, digest.
- Add `--today YYYY-MM-DD` before the subcommand to pretend it is another day.

## Rules

- `data/`, `config.yaml`, and `.env` hold the family's private data and are git-ignored. Never commit them or paste their contents into a PR or issue.
- Study guides and extraction call Claude through `school_planner/llm.py`. Default backend runs `claude -p` with tools off; `backend: api` uses the SDK.
- Tests: `pytest`. They need no network and no login.
- Classification rules for test vs quiz vs homework live in `school_planner/classify.py`; add a test in `tests/test_classify.py` when changing them.
