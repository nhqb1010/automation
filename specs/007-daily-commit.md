# 007: Daily Commit: one small commit a day, run by GitHub

- **Status:** steps 1–6 implemented, waiting for test run
- **Created:** 2026-10-31

## Requirement
Keep a daily contribution streak with a small, honest post each day in your own private notes repo. GitHub runs the schedule, so the Mac can be off. The app is the control panel. No backdating, no co-author lines, no queue or images.

## Plan
1. **Repo template:** The workflow, the post-writing script and the list of lines that get copied into the notes repo.
2. **GitHub client:** Read and write repo files, start and pause the workflow, read run history.
3. **Token storage:** The dev copy reads .env; the installed app uses the macOS Keychain.
4. **Daily Commit page:** Set up and update the repo (with a diff), today ✓/✗, streak, a 12-week calendar, workflow health, Run now (with a message), Pause/Resume, Actions minutes, Edit content, Test connection, Disconnect.
5. **Colour-coded Logs:** A colour per area with a legend, worked out in Python.
6. **App-wide polish:** A loading screen with steps, toasts for GitHub calls, the repo name highlighted, instant quit.

## Step details

### 1. Repo template
- **Approach:** A GitHub Actions workflow runs daily at 03:00 UTC (10:00 in Vietnam) and can also be started by hand with an optional message. The script picks one line from the content list per day (the same line all day), adds an emoji, and writes days/YYYY/MM-DD.md; a second run on the same day appends. The commit is made under the owner's private GitHub address, so it counts on their graph. A typed message reaches the script as an environment variable, never inside a shell command. The script uses only Python 3.12 and the standard library, which matches GitHub's runner; Ruff is told so for that folder.
- **Files:** app/tools/daily_commit/repo_template/.github/workflows/daily.yml, app/tools/daily_commit/repo_template/daily.py, app/tools/daily_commit/repo_template/content.txt, app/tools/daily_commit/README.md, tests/test_daily_commit_daily.py, ruff.toml, cspell.json, README.md
- **Concerns:** GitHub may start scheduled runs late on busy days. Private repos use Actions minutes (about 30 a month here, out of 2,000 free).

### 2. GitHub client
- **Approach:** A small client on Python's own web library, so nothing new ships with the app. It reads the repo, files and folders, writes single files, commits several files at once, and starts, pauses and lists workflow runs. GitHub's error text is passed on in plain words; "not found" answers that are expected (an empty repo, a missing file) are not treated as problems.
- **Files:** app/tools/daily_commit/github_client.py, tests/test_daily_commit_github_client.py

### 3. Token storage
- **Approach:** The dev copy reads the repository and token from .env (the DAILY_COMMIT names, or the earlier STREAK or DAILY_LOG names) and never touches the Keychain. The installed app keeps both in one macOS Keychain item, set from the page's Connect form; Disconnect removes it. The token is never logged or sent back to the page.
- **Files:** app/tools/daily_commit/connection.py, app/config.py, example.env, tests/test_daily_commit_connection.py
- **Concerns:** macOS asks once after each reinstall whether the app may read the item (Always Allow). A stable signing certificate is on the roadmap.

### 4. Daily Commit page
- **Approach:** The page loads in four steps (repo first, then posts, workflow and files at the same time), shown as a checklist on the loading screen, and draws everything in one go: a hero card (a flame that lights up while the streak runs, the streak number, today's status, and a ring toward the next milestone), tiles for total posts, best streak and workflow state, a 12-week calendar with month names, workflow state with the last runs, an Actions minutes ring (each run rounded up to a minute; public repos free; marks at 75 % and 90 %), and each template file's status. Set up and update are one flow: compare, show the diff, commit only after Apply, in a single commit; content.txt is never overwritten once it exists. Run now (optionally with your own line), Pause/Resume, Edit content (saved only if it didn't change on GitHub meanwhile) with a "Today's line" preview worked out by the same picker GitHub runs, Test connection, Open on GitHub. The page refreshes on open, every 5 minutes, and a few times after Run now. Drawn once and updated in place (no jumping).
- **Files:** app/tools/daily_commit/__init__.py, app/tools/daily_commit/models.py, app/tools/daily_commit/streak_stats.py, app/tools/daily_commit/template_sync.py, app/tools/daily_commit/ui/view.html, app/tools/daily_commit/ui/view.css, app/tools/daily_commit/ui/view.js, app/tools/__init__.py, app/main.py, app/ui/icons.js, mac_app/bao_internal_apps.spec, tests/test_daily_commit_streak_stats.py, tests/test_daily_commit_template_sync.py, tests/test_daily_commit_tool.py

### 5. Colour-coded Logs
- **Approach:** Python works out each line's area from where it was logged: Monitor blue, Daily Commit green, Logs purple, Page orange, App grey, libraries dim grey. A new tool gets its own name and a colour that stays the same every time. Each line shows a coloured tag, and a legend lists the areas seen.
- **Files:** app/tools/log_viewer/log_areas.py, app/tools/log_viewer/models.py, app/tools/log_viewer/ui/view.html, app/tools/log_viewer/ui/view.css, app/tools/log_viewer/ui/view.js, tests/test_log_viewer_log_areas.py

### 6. App-wide polish
- **Approach:** The tool was renamed from Streak to Daily Commit; older settings names still work and the saved Keychain item keeps its original label. Every tab opens behind one loading screen: the page stays hidden with no animations until all its first data is in, a spinner appears after 150 ms with a checklist of the tab's real loading steps, then the finished page fades in at once. Daily Commit keeps its loaded data between visits, so coming back is instant, with a quiet background refresh after a minute. Every call to GitHub shows a toast (blue reading, amber writing, then green with a link or red with GitHub's reason), and the repo name always appears as a highlighted pill. Closing the window quits right away instead of waiting for GitHub calls still running.
- **Files:** app/ui/shell.js, app/ui/style.css, app/ui/index.html, app/ui/settings.js, app/ui/icons.js, app/ui/README.md, app/tools/system_monitor/ui/view.js, app/tools/log_viewer/ui/view.js, app/tools/daily_commit/ui/view.js, app/main.py
- **Concerns:** If a tab's first data never arrives, its loading screen stays up; GitHub calls give up after 15 seconds each, so it can't hang forever.
