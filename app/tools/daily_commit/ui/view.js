// LEARN: YOU ARE HERE
//   shell.js runs THIS FILE on first open ▶ it registers mount / unmount
//   ▶ asks Python for the overview (bridge call ▶ daily_commit/__init__.py
//   ▶ GitHub) ▶ fills the boxes view.html already drew
//   read next → app/tools/log_viewer/ui/view.html

// Daily Commit page: today, streak, calendar, workflow, minutes, and the buttons.
//
// LEARN: when the page asks Python for the overview
//
//   open the tool ─────────────┐
//   [ Refresh ] ───────────────┤
//   every 5 minutes ───────────┼──▶ 4 steps (repo, posts, workflow, files) ──▶ fill in
//   after an action ───────────┤
//   after Run now: +8 s +25 s +60 s (GitHub starts the run a bit later)
//
// LEARN: NO-JUMP RULE (app/ui/README.md, "Pages must never jump")
//   every box is in view.html from the start, with its height reserved
//   → an answer only changes text, classes and widths, never the layout
//   only YOUR clicks open panels (the diff, the editor)
//
// LEARN: everything shown comes from GitHub or from you → set with
//   textContent (never innerHTML) → no text can run as code on the page
//
// LEARN: (() => { … })() = run once now, keep names private (see icons.js)
(() => {
  const I = window.BaoIcons;
  const AUTO_REFRESH_MS = 5 * 60 * 1000;
  // coming back within this time → the kept data is fresh enough, no calls
  const FRESH_FOR_MS = 60 * 1000;
  // GitHub starts a run a few seconds after Run now; finishing takes ~20 s
  const AFTER_RUN_REFRESH_DELAYS_MS = [8000, 25000, 60000];
  const RUN_ROWS = 5;
  const CALENDAR_DAYS = 12 * 7;
  // the second click on Disconnect must come within this time
  const DISCONNECT_CONFIRM_MS = 4000;
  // file status → [text, badge colour]
  const FILE_STATUS = {
    new: ["Not in the repo yet", "warn"],
    changed: ["Update available", "warn"],
    same: ["Up to date", "good"],
    kept: ["Yours, kept as is", "muted"],
  };
  // LEARN: streak milestones; the hero ring fills up toward the next one
  //   12 days → next goal 14 → ring 12 / 14 = 86 %
  const STREAK_MILESTONES = [3, 7, 14, 30, 50, 100, 200, 365, 500, 1000];
  // only every other day is named, like GitHub's graph
  const WEEKDAY_LABELS = ["Mon", "", "Wed", "", "Fri", "", ""];
  // buttons that CHANGE something on GitHub → "writing to your repo"
  const WRITE_ACTIONS = new Set(["run", "run-message", "pause", "apply-sync", "save-content", "runs-per-day"]);
  const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const EVENT_TEXT = { schedule: "Daily schedule", workflow_dispatch: "Started by hand" };
  const C = window.BaoCharts;

  // LEARN: page-wide state for this tool (let = can change)
  //   overview = the last answer from Python (null until the first one)
  //   busy = an action is running → every button waits
  //   generation = bumped on mount / unmount → late answers are ignored
  //     (same "stale reply" idea as the other tools)
  let root = null;
  let ctx = null;
  let overview = null;
  // LEARN: the last loaded page data, KEPT between visits to this tab
  //   this file runs once per app start → these names live until you quit
  //   (unlike root / ctx, which mount / unmount set and clear)
  //   industry term: "stale-while-revalidate" = show the kept copy at once,
  //   fetch a fresh one in the background, then swap it in
  let keptOverview = null;
  let busy = false;
  let mounted = false;
  let generation = 0;
  let refreshTimer = null;
  let followUpTimers = [];
  let disconnectArmedUntil = 0;
  // content.txt's version when the editor opened (sent back on save)
  let contentSha = null;
  // the two rings (charts.js), made once per visit in mount
  let goalRing = null;
  let minutesRing = null;

  const $ = (selector) => root.querySelector(selector);

  // ---------- small helpers ----------

  // LEARN: errors from Python arrive as an object with .message
  //   (or sometimes plain text) → always give back readable text
  function readErrorText(error) {
    if (!error) return "Something went wrong";
    return error.message || String(error);
  }

  // "2026-11-03T03:00:12Z" → "5 min ago" / "3 h ago" / "2 days ago"
  function formatTimeAgo(isoText) {
    // Date.now() → milliseconds since 1970; new Date(text) → a time
    const seconds = Math.max(0, (Date.now() - new Date(isoText).getTime()) / 1000);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
    const days = Math.floor(seconds / 86400);
    return `${days} day${days === 1 ? "" : "s"} ago`;
  }

  // LEARN: "01:17" (a UTC time from Python) → that moment TODAY (UTC)
  //   Date.UTC(y, m, d, h, min) → that moment in UTC (months count from 0!)
  //   called by → formatLocalRunTime, describeNextDailyRun
  function findTodaysUtcMoment(utcTime, now) {
    const [hour, minute] = utcTime.split(":").map(Number);
    return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hour, minute));
  }

  // "13:17" UTC → "20:17" on a Mac in Vietnam (the Mac's own time zone)
  //   toLocaleTimeString → the time in the Mac's own time zone
  function formatLocalRunTime(utcTime) {
    return findTodaysUtcMoment(utcTime, new Date()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // LEARN: the next scheduled run, shown in YOUR time ("20:17 today")
  //   runTimesUtc → ["01:17", "13:17"] from the repo's daily.yml
  //   every time today already passed → the first one, tomorrow
  //   empty (a schedule this app didn't write) → no time, just "on schedule"
  //   called by → renderHero (the pill under the streak)
  function describeNextDailyRun(runTimesUtc) {
    if (!runTimesUtc.length) return "on schedule";
    const now = new Date();
    const today = runTimesUtc.map((time) => findTodaysUtcMoment(time, now));
    // 86400000 ms = 24 hours → the same time tomorrow
    const next = today.find((moment) => moment > now) || new Date(today[0].getTime() + 86400000);
    const sameLocalDay = next.toDateString() === now.toDateString();
    const time = next.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return `${time} ${sameLocalDay ? "today" : "tomorrow"}`;
  }

  // LEARN: one status line (each action card has its own)
  //   state → how it looks:
  //     "working" small spinner      "writing" spinner, amber (your repo)
  //     "done"    green ✓            "error"   red
  //   target → which card's line; none given → the Controls card's
  function setActionStatus(text, state = "", target = null) {
    const status = target || $(".dc-action-status");
    // "\u00a0" = &nbsp; → keeps the line's height when empty
    status.textContent = text || "\u00a0";
    status.classList.remove("working", "writing", "done", "error");
    if (text && state) status.classList.add(state);
  }

  // ---------- built once per visit ----------

  // LEARN: the calendar grid, built once (CSS fills it column by column)
  //   column 1: an empty corner, then the day names
  //   then per week: a month-name slot, then its 7 day squares
  //   called by → mount; renderCalendar only colours / names them later
  function buildCalendarSquares() {
    const calendar = $(".dc-calendar");
    const addCell = (className, text = "") => {
      const cell = document.createElement(className === "dc-day" ? "div" : "span");
      cell.className = className;
      cell.textContent = text;
      calendar.appendChild(cell);
    };
    addCell("dc-month");
    WEEKDAY_LABELS.forEach((label) => addCell("dc-weekday", label));
    for (let week = 0; week < CALENDAR_DAYS / 7; week += 1) {
      addCell("dc-month");
      for (let day = 0; day < 7; day += 1) addCell("dc-day");
    }
  }

  // LEARN: 5 empty run rows, filled later by renderRuns
  //   each row: badge · what · when · how long · link
  function buildRunRows() {
    const runs = $(".dc-runs");
    for (let index = 0; index < RUN_ROWS; index += 1) {
      const row = document.createElement("div");
      row.className = "dc-run";
      ["dc-badge", "dc-run-what", "dc-run-when num", "dc-run-took num"].forEach((name) => {
        const cell = document.createElement("span");
        cell.className = name;
        row.appendChild(cell);
      });
      const link = document.createElement("a");
      link.target = "_blank";
      link.rel = "noopener";
      row.appendChild(link);
      runs.appendChild(row);
    }
  }

  // a badge = a small rounded label; colour = good / bad / warn / info / muted
  function setBadge(el, text, colour, extraClass = "") {
    el.className = `dc-badge ${colour} ${extraClass}`.trim();
    el.textContent = text;
  }

  // ---------- filling in an overview ----------

  // LEARN: one answer from Python → every box updated in place
  //   called by → refreshOverview
  function renderOverview(data) {
    overview = data;
    renderHeader(data);
    renderHero(data);
    renderTiles(data);
    renderCalendar(data);
    renderMinutes(data);
    renderRuns(data);
    renderFiles(data);
    renderNextPost(data);
    renderSchedule(data);
    renderConnection(data);
    updateButtons();
  }

  // the header line: repo · when this data was fetched
  //   fetched_at is set by refreshOverview → a kept copy shows its real age
  //   the repo name is a highlighted pill (shell.js BaoUi.createRepoPill)
  function renderHeader(data) {
    const time = new Date(data.fetched_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const meta = $(".dc-meta");
    if (data.connection.repository) {
      const updated = document.createElement("span");
      updated.className = "dc-meta-time";
      updated.innerHTML = I.svg("clock", 12);
      updated.append(`updated ${time}`);
      meta.replaceChildren(window.BaoUi.createRepoPill(data.connection.repository), updated);
    } else {
      meta.textContent = "Not connected";
    }
    const problem = $(".dc-problem");
    problem.hidden = !data.problem;
    $(".dc-problem-detail").textContent = data.problem || "";
    const link = $(".dc-repo-link");
    link.hidden = !data.repo;
    if (data.repo) link.href = data.repo.html_url;
  }

  // LEARN: the next milestone above the streak, and how far along it is
  //   .find(f) → the first item where f is true (undefined if none)
  //   ?? → past the last milestone → keep the last one (ring full)
  function findNextMilestone(streak) {
    const next = STREAK_MILESTONES.find((goal) => goal > streak) ?? STREAK_MILESTONES.at(-1);
    return { next, percent: Math.min(100, (streak / next) * 100) };
  }

  // LEARN: the hero card
  //   streak > 0 → class "lit": coloured flame, glow, gradient number
  //   the pill → today's state; the ring → progress to the next milestone
  function renderHero(data) {
    const streak = data.current_streak;
    root.querySelector(".dc-hero").classList.toggle("lit", streak > 0);
    $(".dc-streak").textContent = data.repo ? streak : "—";

    const pill = $(".dc-today");
    pill.classList.remove("good", "warn");
    const workflowState = data.workflow ? data.workflow.state : null;
    if (!data.repo) {
      pill.textContent = data.connection.source === "none" ? "Not connected yet" : "Can't reach the repo";
    } else if (data.today_posted) {
      pill.classList.add("good");
      pill.textContent = "✓ Today's post is in";
    } else if (workflowState === "active") {
      const times = data.run_schedule ? data.run_schedule.run_times_utc : [];
      pill.textContent = `◷ Next post ${describeNextDailyRun(times)}`;
    } else {
      pill.classList.add("warn");
      pill.textContent = workflowState === "paused" ? "Paused: no post today" : "Set up the repo to start";
    }

    const goal = findNextMilestone(streak);
    // the ring's colour follows the flame: orange when lit, grey otherwise
    goalRing.update(goal.percent, streak > 0 ? "var(--flame-2)" : "var(--text-muted)", `${streak}/${goal.next}`, "");
    $(".dc-goal-label").textContent = `next goal: ${goal.next} days`;
  }

  // the three tiles: total posts, best streak, workflow state
  function renderTiles(data) {
    $(".dc-total").textContent = data.repo ? data.total_posts : "—";
    $(".dc-best").textContent = data.repo ? `${data.longest_streak} d` : "—";
    const workflow = data.workflow;
    const box = $(".dc-workflow");
    box.classList.remove("active", "paused", "missing");
    if (!workflow) {
      $(".dc-workflow-text").textContent = "—";
      $(".dc-workflow-sub").textContent = "Workflow";
      return;
    }
    box.classList.add(workflow.state);
    const names = { active: "Active", paused: "Paused", missing: "Not set up" };
    $(".dc-workflow-text").textContent = names[workflow.state];
    const last = workflow.recent_runs[0];
    $(".dc-workflow-sub").textContent = last
      ? `Last run ${formatTimeAgo(last.created_at)}`
      : workflow.state === "missing"
        ? "Set up the repo below"
        : "No runs yet";
  }

  // LEARN: colour the 84 squares (built once) from data.calendar
  //   classList.toggle(name, true / false) → add / remove a class
  //   month names: a column whose week holds the 1st of a month (or the
  //   very first column) gets that month's name above it
  function renderCalendar(data) {
    const squares = root.querySelectorAll(".dc-day");
    let postedCount = 0;
    data.calendar.forEach((day, index) => {
      const square = squares[index];
      if (!square) return;
      if (day.posted) postedCount += 1;
      square.classList.toggle("posted", day.posted);
      square.classList.toggle("future", day.is_future);
      square.classList.toggle("today", day.day === data.today);
      // title = the hover tooltip
      square.title = day.is_future ? day.day : `${day.day} · ${day.posted ? "posted ✓" : "no post"}`;
    });
    // [1, …] → skip the corner slot above the day names
    [...root.querySelectorAll(".dc-month")].slice(1).forEach((label, week) => {
      const days = data.calendar.slice(week * 7, week * 7 + 7);
      // "2026-11-03".slice(8) → "03"; .slice(5, 7) → "11"
      const firstOfMonth = days.find((day) => day.day.slice(8) === "01");
      const shown = firstOfMonth || (week === 0 ? days[0] : null);
      label.textContent = shown ? MONTH_NAMES[Number(shown.day.slice(5, 7)) - 1] : "";
    });
    $(".dc-calendar-count").textContent = data.repo ? `${postedCount} of the last 84 days` : "";
    $(".dc-calendar-note").textContent = `UTC days · today ${data.today}`;
  }

  // LEARN: the minutes ring
  //   private repo → how much of the ~2,000 monthly minutes is used,
  //     green / yellow / red (charts.js statusColor at 75 % and 90 %)
  //   public repo → free → a full, faint blue ring that says "free"
  function renderMinutes(data) {
    const minutes = data.minutes;
    if (!minutes) {
      minutesRing.update(0, "var(--track)", "—", "");
      $(".dc-minutes-big").textContent = "—";
      $(".dc-minutes-sub").textContent = " ";
      $(".dc-minutes-note").textContent = " ";
      return;
    }
    const runs = `${minutes.run_count} run${minutes.run_count === 1 ? "" : "s"} this month`;
    if (minutes.limit_minutes === null) {
      minutesRing.update(100, "rgba(57, 135, 229, 0.45)", "free", "");
      $(".dc-minutes-big").textContent = `${minutes.used_minutes} min`;
      $(".dc-minutes-sub").textContent = runs;
      $(".dc-minutes-note").textContent = "Public repo → Actions are free";
      return;
    }
    minutesRing.update(Math.max(minutes.percent, 1), C.statusColor(minutes.percent, 75, 90), `${Math.round(minutes.percent)}%`, "");
    $(".dc-minutes-big").textContent = `${minutes.used_minutes} / ${minutes.limit_minutes.toLocaleString()} min`;
    $(".dc-minutes-sub").textContent = runs;
    $(".dc-minutes-note").textContent = "Estimated · warns at 75 % and 90 %";
  }

  // one run → badge text + colour
  function describeRunResult(run) {
    if (run.status === "queued") return { text: "Queued", colour: "info", extra: "running" };
    if (run.status !== "completed") return { text: "Running", colour: "info", extra: "running" };
    if (run.conclusion === "success") return { text: "✓ Success", colour: "good", extra: "" };
    if (run.conclusion === "failure" || run.conclusion === "timed_out") {
      return { text: "✗ Failed", colour: "bad", extra: "" };
    }
    return { text: run.conclusion || "Done", colour: "muted", extra: "" };
  }

  // fill the 5 fixed rows; rows without a run stay empty (same height)
  function renderRuns(data) {
    const runs = data.workflow ? data.workflow.recent_runs : [];
    root.querySelectorAll(".dc-run").forEach((row, index) => {
      const run = runs[index];
      const [badge, what, when, took] = row.querySelectorAll("span");
      const link = row.querySelector("a");
      if (!run) {
        setBadge(badge, "", "muted");
        what.textContent = index === 0 ? "No runs yet" : "";
        what.className = "dc-run-what dc-muted";
        when.textContent = "";
        took.textContent = "";
        link.textContent = "";
        link.removeAttribute("href");
        return;
      }
      const result = describeRunResult(run);
      setBadge(badge, result.text, result.colour, result.extra);
      what.className = "dc-run-what";
      what.textContent = EVENT_TEXT[run.event] ?? run.event;
      when.textContent = formatTimeAgo(run.created_at);
      took.textContent = run.duration_seconds === null ? "" : `${run.duration_seconds} s`;
      link.textContent = "View ↗";
      link.href = run.html_url;
    });
  }

  // LEARN: the template files: icon · path · status badge
  //   the badge in the card title sums them up (3 rows; space reserved)
  function renderFiles(data) {
    const list = $(".dc-files");
    // replaceChildren(…) → swap all children in one step
    list.replaceChildren(
      ...data.files.map((file) => {
        const row = document.createElement("div");
        row.className = "dc-file";
        const name = document.createElement("span");
        name.className = "dc-file-name";
        const icon = document.createElement("span");
        icon.className = "dc-file-icon";
        icon.innerHTML = I.svg("file-code", 15);
        const path = document.createElement("span");
        path.className = "dc-file-path";
        path.textContent = file.path;
        name.append(icon, path);
        const status = document.createElement("span");
        const [text, colour] = FILE_STATUS[file.status];
        setBadge(status, text, colour);
        row.append(name, status);
        return row;
      }),
    );
    // .filter(f).length → how many items pass f
    const pending = data.files.filter((file) => file.status === "new" || file.status === "changed").length;
    const summary = $(".dc-files-summary");
    if (!data.files.length) {
      setBadge(summary, "", "muted", "dc-files-summary");
    } else if (pending) {
      setBadge(summary, `${pending} to update`, "warn", "dc-files-summary");
    } else {
      setBadge(summary, "✓ All up to date", "good", "dc-files-summary");
    }
  }

  // LEARN: the "Today's line" quote card + the line count in the title
  //   next_post → which line the next post will use (from Python)
  //   is_today false → today is done, so it's tomorrow's line
  function renderNextPost(data) {
    const next = data.next_post;
    $(".dc-next-label").textContent = next && !next.is_today ? "Tomorrow's line" : "Today's line";
    $(".dc-next-line").textContent = next ? next.line : "—";
    $(".dc-next-emoji").textContent = next ? next.emoji : "";
    const total = $(".dc-line-total");
    total.textContent = next ? `${next.line_count} lines` : "";
    total.hidden = !next;
  }

  // LEARN: the Runs per day row (Controls card)
  //   picker → the repo's count lit blue ("selected")
  //   "Now" → what daily.yml says RIGHT NOW: the count + one chip per time,
  //     in YOUR time; also for an older schedule ("0 3 * * *" → 1 run, 10:00)
  //   no daily.yml yet → "—" and a hint
  //   a schedule the picker didn't write → amber count, nothing lit,
  //     "pick a number to switch"
  function renderSchedule(data) {
    const schedule = data.run_schedule;
    const chosen = schedule ? schedule.runs_per_day : null;
    root.querySelectorAll(".dc-step").forEach((button) => {
      button.classList.toggle("selected", Number(button.dataset.runs) === chosen);
    });
    const count = $(".dc-schedule-count");
    const chips = $(".dc-schedule-chips");
    const note = $(".dc-schedule-note");
    count.classList.toggle("custom", Boolean(schedule && schedule.is_custom));
    if (!schedule) {
      count.textContent = "—";
      chips.replaceChildren();
      note.textContent = data.repo ? "Set up the repo first" : "";
      return;
    }
    const times = schedule.run_times_utc;
    if (!times.length) {
      count.textContent = "Custom schedule";
      chips.replaceChildren();
      note.textContent = "too complex to show · pick a number to switch";
      return;
    }
    count.textContent = `${times.length} run${times.length === 1 ? "" : "s"} a day`;
    chips.replaceChildren(
      ...times.map((time) => {
        const chip = document.createElement("span");
        chip.className = "dc-time-chip num";
        chip.innerHTML = I.svg("clock", 11);
        chip.append(formatLocalRunTime(time));
        // hover → the same time in UTC (GitHub's clock)
        chip.title = `${time} UTC`;
        return chip;
      }),
    );
    note.textContent = schedule.is_custom ? "your time · old schedule, pick a number to switch" : "your time";
  }

  // LEARN: the Connection card has three looks
  //   dev copy              → repo chip + "from .env" badge
  //   installed, connected  → repo chip + "Keychain" badge + Disconnect
  //   installed, not yet    → a hint + the Connect form
  //   the repo name is split: owner (muted) / name (bold)
  function renderConnection(data) {
    const connection = data.connection;
    const form = $(".dc-connect-form");
    const disconnect = $('[data-action="disconnect"]');
    form.hidden = !(connection.can_edit && connection.source === "none");
    disconnect.hidden = !(connection.can_edit && connection.source !== "none");

    const connected = connection.source !== "none";
    // the repo as a large pill; not connected → plain words
    const nameBox = $(".dc-repo-name");
    if (connected) {
      nameBox.replaceChildren(window.BaoUi.createRepoPill(connection.repository, "large"));
    } else {
      nameBox.textContent = "Not connected";
    }

    const visibility = $(".dc-visibility");
    visibility.hidden = !data.repo;
    if (data.repo) {
      visibility.className = `dc-chip dc-visibility ${data.repo.private ? "gold" : "blue"}`;
      visibility.querySelector("[data-icon]").innerHTML = I.svg(data.repo.private ? "lock" : "globe", 12);
      visibility.querySelector(".dc-chip-text").textContent = data.repo.private ? "Private" : "Public";
    }

    const source = $(".dc-source");
    source.hidden = !connected;
    source.className = "dc-chip dc-source purple";
    source.querySelector(".dc-chip-text").textContent =
      connection.source === "keychain" ? "Token in Keychain" : "Token from .env · dev copy";

    const hint = $(".dc-connection-hint");
    hint.hidden = connected;
    $(".dc-connection-hint-text").textContent = connection.can_edit
      ? "Enter your notes repo and a fine-grained token (Contents, Actions, Workflows: read and write)"
      : "Add BAO_DAILY_COMMIT_REPOSITORY and BAO_DAILY_COMMIT_TOKEN to .env, then restart";
  }

  // LEARN: which buttons may be pressed right now
  //   data-needs="connection" → a repo is reachable
  //   data-needs="workflow"   → daily.yml is on GitHub
  //   data-needs="files"      → a repo is reachable (same as connection)
  //   busy → everything waits for the running action
  function updateButtons() {
    const hasRepo = Boolean(overview && overview.repo);
    const workflowState = overview && overview.workflow ? overview.workflow.state : "missing";
    const allowed = {
      connection: Boolean(overview && overview.connection.source !== "none"),
      workflow: hasRepo && workflowState !== "missing",
      files: hasRepo,
    };
    root.querySelectorAll("button[data-action]").forEach((button) => {
      const need = button.dataset.needs;
      button.disabled = busy || (need ? !allowed[need] : false);
    });
    const paused = workflowState === "paused";
    $(".dc-pause-label").textContent = paused ? "Resume" : "Pause";
    $(".dc-pause [data-icon]").innerHTML = I.svg(paused ? "play" : "pause", 13);
  }

  // ---------- asking Python ----------

  // LEARN: the page's data comes in 4 steps (see streak/__init__.py)
  //
  //   1. repo ─┬─▶ 2. posts     ┐
  //            ├─▶ 3. workflow  ├─ at the same time (Promise.allSettled)
  //            └─▶ 4. files     ┘
  //   then ONE drawing of the whole page (renderOverview)
  //
  //   report(stepId, state) → the loading screen's checklist (on open);
  //     a refresh passes nothing → no checklist
  //   one failed step → the others still show; its reason → problem banner
  const LOADING_STEPS = [
    { id: "repo", label: "Connecting to GitHub" },
    { id: "posts", label: "Reading your posts" },
    { id: "workflow", label: "Checking the workflow" },
    { id: "files", label: "Comparing repo files" },
  ];
  // what a step shows when it couldn't load (keeps every box drawable)
  const EMPTY_PARTS = {
    posts: { today_posted: false, current_streak: 0, longest_streak: 0, total_posts: 0, calendar: [] },
    workflow: { workflow: null, minutes: null },
    files: { files: [], next_post: null, run_schedule: null },
  };

  // one step: mark it working → call Python → mark done / error
  async function loadDailyCommitStep(stepId, action, params, report) {
    report(stepId, "working");
    try {
      const part = await ctx.call(action, params);
      report(stepId, "done");
      return part;
    } catch (error) {
      report(stepId, "error");
      throw error;
    }
  }

  // LEARN: called by → mount (with the checklist), the timer, Refresh,
  //   and after actions
  //   gen check → the user left the tool while waiting → do nothing
  //   { ...a, ...b } → one object with the fields of both (≈ Python {**a, **b})
  async function refreshOverview(report = () => {}) {
    if (!mounted) return;
    const gen = generation;
    const repoPart = await loadDailyCommitStep("repo", "read_daily_commit_repo", {}, report);
    if (gen !== generation || !root) return;

    const repo = repoPart.repo;
    // not connected / unreachable → only the empty calendar is needed
    const params = repo ? { branch: repo.default_branch, has_commits: repo.has_commits } : {};
    const [posts, workflow, files] = await Promise.allSettled([
      loadDailyCommitStep("posts", "read_daily_commit_posts", params, report),
      repo
        ? loadDailyCommitStep("workflow", "read_daily_commit_workflow", { is_private: repo.private }, report)
        : Promise.resolve(EMPTY_PARTS.workflow),
      repo ? loadDailyCommitStep("files", "read_daily_commit_files", params, report) : Promise.resolve(EMPTY_PARTS.files),
    ]);
    if (gen !== generation || !root) return;

    // .status "fulfilled" → .value is the answer; "rejected" → .reason is the error
    const pick = (result, empty) => (result.status === "fulfilled" ? result.value : empty);
    const failed = [posts, workflow, files].find((result) => result.status === "rejected");
    keptOverview = {
      ...repoPart,
      ...pick(posts, EMPTY_PARTS.posts),
      ...pick(workflow, EMPTY_PARTS.workflow),
      ...pick(files, EMPTY_PARTS.files),
      problem: repoPart.problem || (failed ? readErrorText(failed.reason) : null),
      // Date.now() → milliseconds since 1970: when this data was fetched
      fetched_at: Date.now(),
    };
    renderOverview(keptOverview);
  }

  // LEARN: refresh in the background, with "updating…" in the header
  //   called by → mount, when the kept copy is older than a minute
  //   the page stays usable meanwhile; the fresh data swaps in when ready
  function refreshKeptOverviewInBackground() {
    // the time next to the repo pill says "updating…" until fresh data is in
    const updated = $(".dc-meta-time");
    if (updated) {
      updated.innerHTML = I.svg("refresh-cw", 12);
      updated.append("updating…");
      updated.classList.add("updating");
    }
    refreshOverviewQuietly();
  }

  // LEARN: run one button's work, with a TOAST for the call to GitHub
  //   the toast (shell.js) is the one place that shows progress:
  //     blue spinner  → reading from GitHub
  //     amber spinner → WRITING to your repo / workflow
  //     then ✓ green (with a link) or ✗ red with GitHub's reason
  //   the pressed button glows while it waits; every button waits
  //   work → an async function giving back the "done" text, or
  //     { text, link } when there's something to open on GitHub
  //   try / catch / finally ≈ Python try / except / finally
  async function runDailyCommitAction(button, startText, work) {
    if (busy) return;
    busy = true;
    const writes = WRITE_ACTIONS.has(button.dataset.action);
    // the repo shows as a highlighted pill in the toast (shell.js)
    const repository = overview && overview.connection.repository;
    const toast = window.BaoToast.show({
      tone: writes ? "writing" : "working",
      title: startText,
      detail: repository ? (writes ? "Writing to" : "Talking to") : "Talking to GitHub",
      repo: repository || null,
    });
    button.classList.add("is-busy");
    updateButtons();
    const gen = generation;
    try {
      const result = await work();
      // a plain text answer → { text }; otherwise it already is { text, link }
      const done = typeof result === "string" ? { text: result } : result;
      toast.update({ tone: "done", title: done.text || "Done", detail: "", link: done.link || null });
    } catch (error) {
      toast.update({ tone: "error", title: `${startText.replace("…", "")} didn't work`, detail: readErrorText(error) });
    } finally {
      busy = false;
      button.classList.remove("is-busy");
      if (gen === generation && root) updateButtons();
    }
  }

  // the repo's Actions tab on GitHub (where runs are listed), or null
  function findActionsPageLink() {
    return overview && overview.repo ? `${overview.repo.html_url}/actions` : null;
  }

  // LEARN: timer refreshes → a failure goes to the status line
  //   (.catch(f) = "if this Promise fails, call f" ≈ Python except)
  //   without it, a failed timer refresh would be an "unhandled" page error
  function refreshOverviewQuietly() {
    refreshOverview().catch((error) => {
      if (root) setActionStatus(readErrorText(error), "error");
    });
  }

  // after Run now: look again a few times while GitHub runs it
  function scheduleFollowUpRefreshes() {
    followUpTimers.forEach(clearTimeout);
    followUpTimers = AFTER_RUN_REFRESH_DELAYS_MS.map((delay) => setTimeout(refreshOverviewQuietly, delay));
  }

  // LEARN: the update preview, line by line
  //   each file → a header, then its diff lines coloured by the first
  //   character: + added · - removed · @@ where in the file
  //   "+++" / "---" lines only repeat the file names → skipped
  function renderTemplatePlan(plan) {
    const diff = $(".dc-diff");
    const nodes = [];
    plan.changes.forEach((change) => {
      const header = document.createElement("div");
      header.className = "dc-diff-file";
      header.textContent = `${change.path} · ${FILE_STATUS[change.status][0]}`;
      nodes.push(header);
      change.diff.split("\n").forEach((text) => {
        if (!text || text.startsWith("+++") || text.startsWith("---")) return;
        const line = document.createElement("div");
        line.className = "dc-diff-line";
        if (text.startsWith("+")) line.classList.add("add");
        else if (text.startsWith("-")) line.classList.add("remove");
        else if (text.startsWith("@@")) line.classList.add("hunk");
        line.textContent = text;
        nodes.push(line);
      });
    });
    diff.replaceChildren(...nodes);
    $('[data-action="apply-sync"]').hidden = plan.up_to_date;
  }

  // "39 lines to pick from" under the editor (# notes and blanks skipped)
  function updateContentLineCount() {
    const lines = $(".dc-textarea").value.split("\n").map((line) => line.trim());
    const usable = lines.filter((line) => line && !line.startsWith("#")).length;
    $(".dc-line-count").textContent = `${usable} line${usable === 1 ? "" : "s"} to pick from`;
  }

  // ---------- button clicks ----------

  // LEARN: one click listener for the whole tool ("event delegation")
  //   data-action on each button says which branch below runs
  //   switch (x) { case "a": … } ≈ Python match x: case "a": …
  function onDailyCommitClick(event) {
    const button = event.target.closest("button[data-action]");
    if (!button || button.disabled) return;
    switch (button.dataset.action) {
      case "refresh":
        runDailyCommitAction(button, "Refreshing from GitHub…", async () => {
          await refreshOverview();
          return "Up to date";
        });
        break;
      case "run":
        runDailyCommitAction(button, "Starting today's run…", async () => {
          const result = await ctx.call("run_daily_commit_now", { message: "" });
          scheduleFollowUpRefreshes();
          return { text: result.message, link: findActionsPageLink() };
        });
        break;
      case "run-message": {
        const input = $(".dc-message");
        const message = input.value.trim();
        if (!message) {
          setActionStatus("Type your line first, then press the send button.", "error");
          input.focus();
          break;
        }
        runDailyCommitAction(button, "Posting your line…", async () => {
          const result = await ctx.call("run_daily_commit_now", { message });
          input.value = "";
          scheduleFollowUpRefreshes();
          return { text: result.message, link: findActionsPageLink() };
        });
        break;
      }
      case "pause": {
        const paused = overview.workflow.state === "active";
        runDailyCommitAction(button, paused ? "Pausing…" : "Resuming…", async () => {
          const result = await ctx.call("set_daily_commit_paused", { paused });
          await refreshOverview();
          return { text: result.message, link: findActionsPageLink() };
        });
        break;
      }
      case "runs-per-day": {
        // the number on the button; the one already chosen → nothing to do
        const runsPerDay = Number(button.dataset.runs);
        const current = overview.run_schedule ? overview.run_schedule.runs_per_day : null;
        if (runsPerDay === current) break;
        const plural = runsPerDay === 1 ? "run" : "runs";
        runDailyCommitAction(button, `Setting ${runsPerDay} ${plural} a day…`, async () => {
          const result = await ctx.call("set_daily_commit_runs_per_day", { runs_per_day: runsPerDay });
          await refreshOverview();
          const link = overview.repo
            ? `${overview.repo.html_url}/blob/${overview.repo.default_branch}/.github/workflows/daily.yml`
            : null;
          return { text: result.message, link };
        });
        break;
      }
      case "preview-sync":
        runDailyCommitAction(button, "Comparing with the repo…", async () => {
          const plan = await ctx.call("preview_template_sync");
          renderTemplatePlan(plan);
          $(".dc-sync-panel").hidden = false;
          return plan.up_to_date ? "The repo is up to date." : "Check the changes below, then Apply.";
        });
        break;
      case "apply-sync":
        runDailyCommitAction(button, "Committing the workflow files…", async () => {
          const result = await ctx.call("apply_template_sync");
          $(".dc-sync-panel").hidden = true;
          await refreshOverview();
          const count = result.committed_paths.length;
          return {
            text: count ? `Committed ${count} file${count === 1 ? "" : "s"}` : "Nothing to commit",
            link: result.commit_url,
          };
        });
        break;
      case "cancel-sync":
        $(".dc-sync-panel").hidden = true;
        setActionStatus("", "", button.closest(".card").querySelector(".dc-status"));
        break;
      case "edit-content":
        runDailyCommitAction(button, "Opening content.txt…", async () => {
          const file = await ctx.call("read_content_file");
          contentSha = file.sha;
          $(".dc-textarea").value = file.text;
          updateContentLineCount();
          $(".dc-editor").hidden = false;
          return file.sha ? "content.txt opened" : "content.txt isn't in the repo yet; saving creates it";
        });
        break;
      case "save-content":
        runDailyCommitAction(button, "Committing content.txt…", async () => {
          const result = await ctx.call("save_content_file", { text: $(".dc-textarea").value, sha: contentSha });
          $(".dc-editor").hidden = true;
          await refreshOverview();
          const link = overview.repo ? `${overview.repo.html_url}/blob/${overview.repo.default_branch}/content.txt` : null;
          return { text: result.message, link };
        });
        break;
      case "cancel-content":
        $(".dc-editor").hidden = true;
        setActionStatus("", "", button.closest(".card").querySelector(".dc-status"));
        break;
      case "test":
        runDailyCommitAction(button, "Testing the connection…", async () => {
          const report = await ctx.call("test_daily_commit_connection");
          const list = $(".dc-checks");
          list.replaceChildren(
            ...report.checks.map(([text, ok]) => {
              const item = document.createElement("li");
              item.className = ok ? "good" : "bad";
              item.textContent = `${ok ? "✓" : "✗"} ${text}`;
              return item;
            }),
          );
          if (!report.ok) throw new Error("Something needs fixing, see the list on the page.");
          return "Connection works";
        });
        break;
      case "connect": {
        const repository = $(".dc-repo-input").value;
        const tokenInput = $(".dc-token-input");
        const token = tokenInput.value;
        // the token leaves the page right away; the box is emptied
        tokenInput.value = "";
        runDailyCommitAction(button, "Connecting…", async () => {
          await ctx.call("connect_daily_commit_repository", { repository, token });
          await refreshOverview();
          return "Connected. The token is in the macOS Keychain.";
        });
        break;
      }
      case "disconnect":
        // LEARN: two clicks within 4 s → a safety catch, no pop-up needed
        if (Date.now() > disconnectArmedUntil) {
          disconnectArmedUntil = Date.now() + DISCONNECT_CONFIRM_MS;
          setActionStatus(
            "Press Disconnect again to remove the token from the Keychain. GitHub keeps posting either way.",
            "",
            button.closest(".card").querySelector(".dc-status"),
          );
          break;
        }
        disconnectArmedUntil = 0;
        runDailyCommitAction(button, "Disconnecting…", async () => {
          await ctx.call("disconnect_daily_commit_repository");
          await refreshOverview();
          return "Disconnected. The repo and its daily workflow are unchanged.";
        });
        break;
      default:
        break;
    }
  }

  // ---------- timers ----------

  // called by → mount, and shell.js resume (window shown again)
  function startAutoRefresh() {
    if (refreshTimer || !mounted || document.hidden) return;
    refreshTimer = setInterval(refreshOverviewQuietly, AUTO_REFRESH_MS);
  }

  // called by → unmount, and shell.js pause (window hidden)
  function stopAutoRefresh() {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }

  // window shown again → catch up now, then every 5 minutes
  function resumeDailyCommitPage() {
    if (!mounted) return;
    refreshOverviewQuietly();
    startAutoRefresh();
  }

  // LEARN: the tool comes on screen
  //   called by → shell.js openView, right after view.html is put in place
  async function mount(container, context) {
    generation += 1;
    root = container;
    ctx = context;
    overview = null;
    busy = false;
    contentSha = null;
    root.querySelectorAll("[data-icon]").forEach((el) => {
      // the flame and the tile icons are drawn bigger by view.css
      el.innerHTML = I.svg(el.dataset.icon, 18);
    });
    buildCalendarSquares();
    buildRunRows();
    // LEARN: two rings from charts.js (the same helper System Monitor uses)
    //   built once; every overview only calls .update(…) on them
    goalRing = C.createRing($(".dc-goal-ring"), { size: 92, stroke: 9 });
    minutesRing = C.createRing($(".dc-minutes-ring"), { size: 84, stroke: 9 });
    root.addEventListener("click", onDailyCommitClick);
    $(".dc-textarea").addEventListener("input", updateContentLineCount);
    mounted = true;
    updateButtons();
    // LEARN: been here before → draw the kept copy NOW (no loading screen)
    //   older than a minute → also fetch a fresh one in the background
    //   first visit → the loading screen with the 4 steps
    if (keptOverview) {
      renderOverview(keptOverview);
      if (Date.now() - keptOverview.fetched_at > FRESH_FOR_MS) refreshKeptOverviewInBackground();
      startAutoRefresh();
      return;
    }

    ctx.loading.steps(LOADING_STEPS);
    try {
      await refreshOverview(ctx.loading.mark);
    } catch (error) {
      if (root) setActionStatus(readErrorText(error), "error");
    }
    startAutoRefresh();
  }

  // the tool leaves the screen: stop every timer, forget the page
  // called by → shell.js openView, before another view opens
  function unmount() {
    generation += 1;
    mounted = false;
    stopAutoRefresh();
    followUpTimers.forEach(clearTimeout);
    followUpTimers = [];
    if (root) {
      root.removeEventListener("click", onDailyCommitClick);
      $(".dc-textarea").removeEventListener("input", updateContentLineCount);
    }
    root = null;
  }

  // plug into the shell (see shell.js BaoTools); runs once, when loaded
  window.BaoTools.register("daily_commit", {
    mount,
    unmount,
    pause: stopAutoRefresh,
    resume: resumeDailyCommitPage,
  });
})();
