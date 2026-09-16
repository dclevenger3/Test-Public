# School Planner

A small program for parents whose kids' school runs everything through
[ClassLink](https://myapps.classlink.com/home). It logs into each kid's account once, pulls their
classes and assignments, and every week gives you:

1. **A weekly schedule** of everything due, with tests and quizzes flagged and study sessions
   penciled in before each one (Markdown plus an `.ics` file you can drop into Google or Apple Calendar).
2. **A study guide for every upcoming test**, written by Claude from the notes, slides, and docs the
   teacher attached: key terms, worked examples, a practice quiz with answer key, flashcards, and a
   day-by-day study plan.
3. **A parent digest**: what's due this week, what tests are coming in the next two weeks, what is
   missing or past due, and which study guides are ready. Optionally emailed to you.

## How logins work (read this first)

Your kids' passwords are **never** typed into this program or saved by it. Each student gets a
private Chromium browser profile under `data/<slug>/profile/`. You run `school-planner login kid1`,
a real browser window opens on ClassLink, you sign in as that student, and close it. From then on
the saved session is reused, headlessly, until the school makes you log in again.

The whole `data/` folder is git-ignored. It holds sessions, pulled assignments, and study guides,
so keep it on the machine you run this on.

## How Claude is used

By default this runs the `claude` command from [Claude Code](https://code.claude.com) in print
mode, so study guides and page extraction go through **your Claude Code login and subscription**.
There is no API key to manage. If you would rather pay per call, set `backend: api` in
`config.yaml` and put `ANTHROPIC_API_KEY` in `.env`.

## Setup

Requires Python 3.10+ and Claude Code installed and logged in (`claude` on your PATH).

```bash
git clone <this repo> school-planner && cd school-planner
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
playwright install chromium

cp config.example.yaml config.yaml   # one entry per kid
```

Then, for each kid:

```bash
school-planner login kid1       # sign in through ClassLink in the window that opens
school-planner discover kid1    # lists the app tiles on their launchpad
```

`discover` tells you which learning system the school actually uses behind ClassLink. ClassLink
itself is only a launcher; the classes live in Canvas, Google Classroom, Schoology, or similar.
Put what it finds into `config.yaml`:

```yaml
students:
  - name: Kid One
    slug: kid1
    grade: 7
    apps:
      canvas: https://yourdistrict.instructure.com
  - name: Kid Two
    slug: kid2
    grade: 4
    apps:
      google_classroom: https://classroom.google.com
```

If a kid's launchpad has Canvas or Google Classroom, run `login` again and click that tile once so
the single sign-on cookie gets saved into the profile.

## Weekly use

One command does everything:

```bash
school-planner weekly --email
```

That runs, in order:

| Step | Command | What it does |
|---|---|---|
| Sync | `school-planner sync` | Pulls every course and assignment for each kid into `data/<slug>/assignments.json` |
| Schedule | `school-planner schedule` | Prints this week, saves `data/schedules/week-<date>.md` and `.ics` |
| Study guides | `school-planner study-guide` | For each test or quiz in the next 14 days without a guide, fetches the attached notes and writes `data/<slug>/guides/<id>.md` |
| Digest | `school-planner digest` | Writes `data/digests/week-<date>.md` and emails it if SMTP is configured in `.env` |

Useful on their own:

```bash
school-planner list --tests                 # every upcoming test and quiz on file
school-planner schedule --next              # next week instead of this week
school-planner study-guide kid1 "unit 2"    # one specific test, by id or part of the title
school-planner study-guide kid1 --force     # regenerate
school-planner --today 2026-10-01 schedule  # pretend it's another day
```

To run it automatically every Sunday evening: on macOS or Linux add a cron line such as
`0 18 * * 0 cd /path/to/school-planner && .venv/bin/school-planner weekly --email`; on Windows use
Task Scheduler pointing at `.venv\Scripts\school-planner.exe weekly --email`.

## When the school uses something we don't have a connector for

`capture` works with any portal. It opens the kid's browser, you click to a class's assignments
page, press Enter, and Claude reads the page and pulls out the assignments, due dates, and attached
links. Repeat for each class, type `q` when done.

```bash
school-planner capture kid2
```

Google Classroom uses this same approach under the hood because its pages change often. Canvas
uses its JSON API directly, which is faster and also picks up submission status (missing work).

## Canvas without a browser: the calendar feed

Many districts disable personal access tokens for students, but Canvas still gives every user a
private calendar feed. Logged in as the kid, open Canvas, click Calendar, then the "Calendar Feed"
link at the bottom right, and copy the URL ending in `.ics`. Put it in `config.yaml`:

```yaml
    apps:
      canvas_feed: https://yourdistrict.instructure.com/feeds/calendars/user_XXXXXXXX.ics
```

`sync` then needs no browser at all, so it can run on a schedule from any machine. The feed has
every assignment and quiz with a due date and the description's links, but not submission status
or module notes. Use both `canvas` and `canvas_feed` together for the full picture; they share ids
and merge cleanly. Treat the feed URL like a password: anyone with it can read the calendar.

## What gets flagged as a test

Titles and descriptions are classified with simple rules (`school_planner/classify.py`):
"test", "exam", "quiz", "assessment", "benchmark", "exit ticket", and so on. "Unit 4 Test Review" is
treated as homework that points at a test, not the test itself. Canvas quizzes are trusted as
quizzes. If something is mis-tagged, edit `kind` in `data/<slug>/assignments.json` or open an issue
with the title so the rule can be fixed.

## What the study guide looks like

Each guide is Markdown you can print or read on a phone:

- What this test covers
- Key terms table
- Things to memorize
- Worked examples
- 10-question practice quiz with answer key
- Flashcards table (front | back)
- Day-by-day study plan sized to the days left
- Questions to ask the teacher where the notes are thin

Guides are grounded in the attached material. If nothing was attached or nothing could be fetched,
the guide says so at the top and works from the test title and description only.

Material fetching handles Google Docs and Slides (via export), Google Drive files, PDFs, Canvas
pages and files, and plain web pages, all through the kid's logged-in session.

## Other things this can do, or could next

Already in:

- Missing and past-due work in the digest (Canvas reports it directly; other sources infer it from the due date).
- Study sessions scheduled 4, 2, and 1 days before each test (configurable) and never in the past.
- Calendar export, so the schedule shows up on your phone.

Reasonable next steps, in rough order of value:

- **Flashcard export** to Quizlet or Anki from the flashcards table in each guide.
- **Grade tracking** from PowerSchool or Infinite Campus if the launchpad has one (a connector like `canvas.py` using their APIs).
- **Text message digest** via Twilio or an email-to-SMS gateway instead of email.
- **Practice quiz mode**: a tiny web page that asks the practice questions one at a time and scores them.
- **Teacher email drafts** when a kid has missing work, from the digest.
- **Schoology connector** if `discover` shows Schoology; the `capture` path works meanwhile.

## Project layout

```
school_planner/
  cli.py              commands
  config.py           config.yaml and .env loading
  models.py           Student, Course, Assignment, Material
  store.py            JSON files under data/<slug>/
  browser.py          Playwright profiles, ClassLink login and app discovery
  classify.py         test / quiz / homework rules
  extract.py          Claude turns any page's text into assignments (structured output)
  materials.py        fetches the text of attached docs, slides, PDFs
  schedule.py         weekly events, study sessions, Markdown and .ics rendering
  study_guide.py      builds the prompt and writes the guide
  report.py           weekly digest and email
  connectors/
    canvas.py         Canvas REST API through the browser session
    google_classroom.py  page capture plus Claude extraction
tests/                unit tests, no network needed
examples/             sample data to try the scheduler without a login
```

Run the tests with `pip install -e ".[dev]" && pytest`.

## Using it from inside Claude Code

Open Claude Code in this folder and ask in plain words, for example "run the weekly planner for
both kids" or "make a study guide for the science test". `CLAUDE.md` tells Claude Code the
commands and where the files land.

## Limitations to know about

- The Canvas and Google Classroom connectors were written against the documented APIs and page
  layouts but have not been run against your district's instances yet. The first `sync` may need
  a small selector or URL tweak. `capture` is the reliable fallback while that gets sorted.
- Study guides are only as good as what the teacher attaches. If notes live on paper, photograph
  them and drop the text into the assignment's `materials` in `assignments.json`.
- With the default backend, each study guide and each captured page is one Claude Code turn
  against your subscription's usage limits. With `backend: api`, a guide costs well under a dollar.
- The `claude` command is run with tools turned off and a single turn, so it can only write text;
  it never reads or changes files on your machine from inside this program.
