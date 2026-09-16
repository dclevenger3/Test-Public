"""Command-line entry point. Run `school-planner --help`."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from . import __version__
from .config import Config, load_config
from .models import Assignment
from .store import Store


def _today(args) -> date:
    return date.fromisoformat(args.today) if getattr(args, "today", None) else date.today()


# ---------------- commands ----------------

def cmd_login(cfg: Config, args) -> None:
    from .browser import auto_login, credentials_from_env, login

    student = cfg.student(args.student)
    store = Store(student.slug)
    if args.auto:
        creds = credentials_from_env(student.slug)
        if not creds:
            key = student.slug.upper().replace("-", "_")
            raise SystemExit(f"--auto needs CLASSLINK_USER_{key} and CLASSLINK_PASS_{key} in the environment.")
        ok = auto_login(store, cfg.classlink_url, *creds, headless=not args.show)
        print("Logged in and session saved." if ok else f"Automatic login failed; see {store.dir/'login-failed.png'}. Try `login {student.slug}` without --auto.")
        if not ok:
            raise SystemExit(1)
    else:
        login(store, cfg.classlink_url)


def cmd_discover(cfg: Config, args) -> None:
    from .browser import discover_apps, guess_lms

    student = cfg.student(args.student)
    store = Store(student.slug)
    apps = discover_apps(store, cfg.classlink_url)
    print(f"Found {len(apps)} tiles on the ClassLink launchpad (saved to {store.dir/'apps.json'}, screenshot launchpad.png):")
    for app in apps:
        print(f"  - {app['name']}  {app.get('href','')}")
    guesses = guess_lms(apps)
    if guesses:
        print("\nLooks like these known apps are present. Add the ones you want to config.yaml under apps:")
        for k, v in guesses.items():
            print(f"  {k}: {v}")
    else:
        print("\nNo Canvas / Google Classroom tile recognised. Use `school-planner capture` on any class page instead.")


def cmd_sync(cfg: Config, args) -> None:
    from .browser import browser_session
    from .connectors import REGISTRY

    for student in _students(cfg, args):
        store = Store(student.slug)
        if not student.apps:
            print(f"{student.name}: no apps configured. Run discover, then fill apps: in config.yaml.")
            continue
        conns = []
        for app, url in student.apps.items():
            conn_cls = REGISTRY.get(app)
            if not conn_cls:
                print(f"{student.name}: no connector for '{app}', skipping (use capture).")
                continue
            kwargs = {"store": store} if app == "google_classroom" else {}
            conns.append(conn_cls(student, url, cfg.model, cfg.backend, **kwargs))

        def run_all(ctx):
            for conn in conns:
                print(f"{student.name}: syncing {conn.name} ...")
                courses, assignments = conn.sync(ctx if conn.needs_browser else None)
                if courses:
                    store.save_courses(courses)
                merged = store.merge_assignments(assignments)
                tests = sum(1 for a in assignments if a.is_assessment)
                print(f"  {len(courses)} courses, {len(assignments)} assignments ({tests} tests/quizzes). {len(merged)} total on file.")

        if any(c.needs_browser for c in conns):
            from .browser import auto_login, credentials_from_env

            creds = credentials_from_env(student.slug)
            if creds and not (store.profile_dir / "Default").exists():
                print(f"{student.name}: no saved session, logging in from environment credentials ...")
                if not auto_login(store, cfg.classlink_url, *creds, headless=True):
                    raise SystemExit(f"Automatic login failed; see {store.dir/'login-failed.png'}")
            with browser_session(store, headless=args.headless) as ctx:
                run_all(ctx)
        else:
            run_all(None)


def cmd_capture(cfg: Config, args) -> None:
    """Manual path for any LMS: parent navigates to a class page, presses Enter, Claude extracts."""
    from .browser import browser_session, page_text, save_capture
    from .extract import extract_assignments

    student = cfg.student(args.student)
    store = Store(student.slug)
    with browser_session(store, headless=False) as ctx:
        page = ctx.new_page()
        page.goto(args.url or cfg.classlink_url, wait_until="domcontentloaded")
        print("Navigate to a class's assignments / classwork page. Press Enter to capture it, or type q to finish.", file=sys.stderr)
        n = 0
        while True:
            try:
                answer = input("> ").strip().lower()
            except EOFError:
                break
            if answer == "q":
                break
            page = ctx.pages[-1]
            path = save_capture(store, page, page.title() or f"capture-{n}")
            course, items = extract_assignments(student.slug, page_text(page), page.url, cfg.model, today=datetime.combine(_today(args), datetime.min.time()), backend=cfg.backend)
            store.merge_assignments(items)
            n += 1
            print(f"Captured '{course}': {len(items)} assignments ({sum(a.is_assessment for a in items)} tests/quizzes). Raw page saved to {path}")


def cmd_list(cfg: Config, args) -> None:
    for student in _students(cfg, args):
        items = Store(student.slug).load_assignments()
        if args.tests:
            items = [a for a in items if a.is_assessment]
        print(f"\n{student.name} ({len(items)} items)")
        for a in items:
            due = f"{a.due:%a %b %d}" if a.due else "no date  "
            flag = {"missing": " ❌", "submitted": " ✓", "graded": " ✓"}.get(a.status, "")
            print(f"  {a.id:<18} {due}  [{a.kind:<8}] {a.course_name[:22]:<22} {a.title}{flag}")


def cmd_schedule(cfg: Config, args) -> None:
    from .schedule import build_events, render_ics, render_markdown, week_bounds
    from .config import DATA_DIR

    today = _today(args)
    start, end = week_bounds(today)
    if args.next:
        from datetime import timedelta
        start, end = start + timedelta(days=7), end + timedelta(days=7)
    all_items: list[Assignment] = []
    for s in _students(cfg, args):
        all_items.extend(Store(s.slug).load_assignments())
    events = build_events(all_items, cfg.schedule, start, end, today)
    md = render_markdown(events, start, end, {s.slug: s.name for s in cfg.students})
    print(md)
    out = DATA_DIR / "schedules"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"week-{start:%Y-%m-%d}.md").write_text(md)
    (out / f"week-{start:%Y-%m-%d}.ics").write_text(render_ics(events))
    print(f"\nSaved to {out}/week-{start:%Y-%m-%d}.md and .ics (import the .ics into your calendar).")


def cmd_study_guide(cfg: Config, args) -> None:
    from .schedule import upcoming_assessments
    from .study_guide import generate_study_guide

    today = _today(args)
    for student in _students(cfg, args):
        store = Store(student.slug)
        if args.assignment:
            targets = [store.find_assignment(args.assignment)]
        else:
            targets = [a for a in upcoming_assessments(store.load_assignments(), cfg.schedule.lookahead_days, today)
                       if args.force or not (store.guides_dir / f"{a.id}.md").exists()]
        if not targets:
            print(f"{student.name}: no upcoming tests without a study guide.")
            continue
        if args.no_browser:
            for a in targets:
                print(f"{student.name}: writing study guide for '{a.title}' ...")
                print("  ->", generate_study_guide(store, student, a, cfg.model, ctx=None, today=today, backend=cfg.backend))
        else:
            from .browser import browser_session

            with browser_session(store, headless=True) as ctx:
                for a in targets:
                    print(f"{student.name}: fetching notes and writing study guide for '{a.title}' ...")
                    print("  ->", generate_study_guide(store, student, a, cfg.model, ctx=ctx, today=today, backend=cfg.backend))


def cmd_digest(cfg: Config, args) -> None:
    from .report import build_digest, build_student_digest, email_digest, send_email, sms_summary, write_digest

    today = _today(args)
    text = build_digest(cfg, today)
    path = write_digest(text, today)
    if not args.quiet:
        print(text)
    print(f"Parent digest saved to {path}")
    for student in cfg.students:
        kid_text = build_student_digest(cfg, student, today)
        kid_path = write_digest(kid_text, today, student.slug)
        print(f"{student.name}'s digest saved to {kid_path}")
        if args.email and student.email:
            sent = send_email(student.email, f"{student.name.split()[0]}, your school week of {today:%b %d}", kid_text)
            print(f"  emailed to {student.email}" if sent else "  email not configured (set SMTP_* in .env)")
        if args.email and student.sms_email:
            sent = send_email(student.sms_email, "", sms_summary(cfg, student, today), html=False)
            print(f"  texted via {student.sms_email}" if sent else "  text not sent (SMTP not configured)")
    if args.email:
        sent = email_digest(text, f"School week of {today:%b %d} (all kids)")
        print("Parent digest emailed." if sent else "Parent digest not emailed (set SMTP_* and DIGEST_TO in .env).")


def cmd_weekly(cfg: Config, args) -> None:
    """The one command to run every Sunday: sync, schedule, study guides, digest."""
    args.headless = True
    cmd_sync(cfg, args)
    args.next = False
    cmd_schedule(cfg, args)
    args.assignment, args.force, args.no_browser = None, False, False
    cmd_study_guide(cfg, args)
    args.quiet = True
    cmd_digest(cfg, args)


# ---------------- plumbing ----------------

def _students(cfg: Config, args):
    slug = getattr(args, "student", None)
    return [cfg.student(slug)] if slug else cfg.students


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="school-planner", description="Weekly schedules, test tracking, and study guides for kids behind ClassLink.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--today", help="Pretend today is this date (YYYY-MM-DD). Useful for testing.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("login", help="Open a browser to log a student into ClassLink once."); s.add_argument("student"); s.add_argument("--auto", action="store_true", help="Fill the form from CLASSLINK_USER_<SLUG> / CLASSLINK_PASS_<SLUG> env vars"); s.add_argument("--show", action="store_true", help="With --auto, show the browser window"); s.set_defaults(fn=cmd_login)
    s = sub.add_parser("discover", help="List the app tiles on the ClassLink launchpad."); s.add_argument("student"); s.set_defaults(fn=cmd_discover)
    s = sub.add_parser("sync", help="Pull courses and assignments from the configured apps."); s.add_argument("student", nargs="?"); s.add_argument("--headless", action="store_true"); s.set_defaults(fn=cmd_sync)
    s = sub.add_parser("capture", help="Manually capture class pages and let Claude extract the assignments."); s.add_argument("student"); s.add_argument("--url"); s.set_defaults(fn=cmd_capture)
    s = sub.add_parser("list", help="Show assignments on file."); s.add_argument("student", nargs="?"); s.add_argument("--tests", action="store_true", help="Only tests and quizzes"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("schedule", help="Print and save this week's schedule (Markdown + .ics)."); s.add_argument("student", nargs="?"); s.add_argument("--next", action="store_true", help="Next week instead of this week"); s.set_defaults(fn=cmd_schedule)
    s = sub.add_parser("study-guide", help="Write study guides for upcoming tests (or one assignment)."); s.add_argument("student", nargs="?"); s.add_argument("assignment", nargs="?", help="Assignment id or part of its title"); s.add_argument("--force", action="store_true", help="Regenerate even if a guide exists"); s.add_argument("--no-browser", action="store_true", help="Use only material text already on file"); s.set_defaults(fn=cmd_study_guide)
    s = sub.add_parser("digest", help="Weekly digests: one for you, one per kid with her study guides."); s.add_argument("--email", action="store_true", help="Email each kid hers and you the combined one"); s.add_argument("--quiet", action="store_true"); s.set_defaults(fn=cmd_digest)
    s = sub.add_parser("weekly", help="sync + schedule + study guides + digest in one go."); s.add_argument("student", nargs="?"); s.add_argument("--email", action="store_true"); s.set_defaults(fn=cmd_weekly)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    cfg = load_config()
    from .tz import set_timezone

    set_timezone(cfg.timezone)
    args.fn(cfg, args)


if __name__ == "__main__":
    main()
