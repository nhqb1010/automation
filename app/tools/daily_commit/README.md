<!-- LEARN-README -->
start here → [repo_template/.github/workflows/daily.yml](repo_template/.github/workflows/daily.yml), then follow each file's "read next"

# Daily Commit

One small commit a day, in your own notes repo, made by GitHub itself.
The app is the control panel; GitHub runs the schedule.

## Who does what

```
 your Mac (this app)                  GitHub (your notes repo)
 ───────────────────                  ────────────────────────
 [ Set up / update repo ] ─ diff ───▶ .github/workflows/daily.yml
   (you confirm, one commit)          daily.py
                                      content.txt

 (app can be closed)                  every day 03:00 UTC (10:00 VN)
                                        runner ▶ daily.py ▶ days/2026/11-03.md
                                               ▶ commit as you ▶ push
                                                                │
 [ Run now ] ─────── asks GitHub ───▶ same run, right away      ▼
 [ Pause ] / [ Resume ] ────────────▶ GitHub's on/off switch  green square ✓
 [ Edit content ] ──────────────────▶ content.txt (one commit)
 page reads ◀──── posts, runs, minutes ─────────┘
```

## First-time setup

```
1. a private repo on GitHub (empty is fine)
2. a fine-grained token for that one repo:
     Contents   read and write   (files, commits)
     Actions    read and write   (run now, pause, run history)
     Workflows  read and write   (allowed to add daily.yml)
3. connect
     dev copy   → .env: BAO_DAILY_COMMIT_REPOSITORY / BAO_DAILY_COMMIT_TOKEN, restart
     installed  → Daily Commit page → Connection card → Connect (→ Keychain)
4. Daily Commit page → [ Set up / update repo… ] → check the diff → [ Apply ]
5. the next 10:00 run posts; or press [ Run now ]
```

## The files

```
daily_commit/
├─ repo_template/                what lands in your notes repo
│  ├─ .github/workflows/daily.yml   WHEN + HOW: schedule and 3 steps
│  ├─ daily.py                      WHAT: writes today's post
│  └─ content.txt                   your lines to pick from
├─ __init__.py       DailyCommitTool: the actions the page may call
├─ models.py         the shapes sent to the page
├─ github_client.py  GitHub's REST API, standard library only
├─ connection.py     the token: .env (dev) or the Keychain (installed)
├─ streak_stats.py   streak, calendar, minutes (pure sums, tested)
├─ template_sync.py  template vs repo → diff → what to commit
└─ ui/               the Daily Commit page
```

## One page refresh

```
view.js ── 1. read_daily_commit_repo ──▶ repo + branch (+ empty or not)
        ├─ 2. read_daily_commit_posts ────▶ days/ → streaks, calendar   ┐ all
        ├─ 3. read_daily_commit_workflow ─▶ state, runs, minutes        ├ at
        └─ 4. read_daily_commit_files ────▶ 3 files + today's line      ┘ once
view.js ◀── one drawing of the whole page
```

On open, these four are the checklist on the loading screen.

The loaded data is kept in memory until you quit, so coming back to the tab
is instant:

```
first visit       → loading screen, 4 steps
back within 1 min → the kept data, no calls
back later        → the kept data at once + "updating…", fresh data swaps in
```

A GitHub problem (bad token, offline) comes back as a plain sentence in the
answer, shown in a red banner; the page never breaks.

## One day's file

```
days/2026/11-03.md
  # Tue 3 Nov 2026 🌱        ← first run of the day
  > Honey never spoils 🍯

  ---                        ← each extra run that day adds a block
  **10:42 UTC** · your message
```

The same date always picks the same line and emoji (seeded random), so
a second run that day matches the first.

## Glossary

| Term | One line |
|---|---|
| GitHub Actions | GitHub's system for running steps on its own computers |
| workflow | One .yml file in .github/workflows/ describing what to run and when |
| runner | The lent computer a workflow runs on, thrown away afterwards |
| trigger | What starts a run: a schedule, a button, a push, … |
| cron | A 5-part time pattern for "run at this time" (minute hour day month weekday) |
| workflow_dispatch | The trigger for starting a run by hand, with an optional small form |
| GITHUB_TOKEN | The temporary key each run gets; here it may only write the repo's files |
| least privilege | Give a key only the permissions it needs, nothing more |
| script injection | Typed text turning into a command; avoided by passing it as an environment variable |
| seeded random | Random choices that repeat exactly for the same seed (here: the date) |
| noreply email | Your private GitHub address; commits with it count as yours |
| UTC | The world clock GitHub uses for contribution days (Vietnam = UTC+7) |
| REST API | A website for programs: addresses for things, methods for actions, JSON answers |
| fine-grained token | A GitHub token limited to chosen repos and chosen permissions |
| Keychain | macOS's encrypted password store; the installed app keeps the token there |
| sha | Git's fingerprint of a commit or file version |
| Git Data API | GitHub's low-level API (blobs, trees, commits, refs) used to make one commit with several files |
| unified diff | The "- old / + new" text format for showing changes |
| optimistic concurrency | Save only if nothing changed since you read it (the sha check) |
| test double | A fake stand-in (fake GitHub, fake Keychain) so tests stay offline |
