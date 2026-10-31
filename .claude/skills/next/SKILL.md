---
name: next
description: What's coming from school in the next few days (default 5), broken down by child and then by Tests, Quizzes, Homework, Projects. Pulls fresh from Canvas first.
---

The parent wants to know what is due soon. Default window is 5 days; use the number they say.

1. Activate `.venv` if it exists.
2. Run `school-planner next --days N`. It syncs Canvas for every child first, then prints each
   child's section with Tests, Quizzes, Homework, Projects, and anything past due. If the sync
   fails on a login, run `school-planner login <slug>`, ask the parent to sign in, and rerun.
   If they only want what is already on file, add `--no-sync`.
3. Show the output as is. Then add two or three plain sentences: the one or two things that
   matter most this week (a test tomorrow, something past due), per child.
