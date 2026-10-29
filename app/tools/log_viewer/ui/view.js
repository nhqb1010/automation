// LEARN: YOU ARE HERE
//   shell.js runs THIS FILE on first open ▶ it registers mount / unmount
//   ▶ every second it asks Python for new lines (bridge call ▶
//   log_viewer/__init__.py ▶ reader.py) ▶ adds them to the list
//   read next → tests/conftest.py

// Logs page: follows logs/app.log live, with level filters and search.
//
// LEARN: the poll loop
//
//   every N s ──▶ call("read_new_log_lines", { cursor, max_lines })
//                   ◀── { lines, cursor, file_found }
//   keep the cursor ──▶ send it back next time (only NEW lines come back)
//
//   tool hidden / window minimised ──▶ timer stops; shown again ──▶ restarts
//
// LEARN: "following" (industry term: "auto-scroll" / "tail mode")
//   following → every new batch scrolls the list to the newest line
//   scroll up (or press Pause) → stop scrolling, keep collecting lines
//   scroll back to the bottom (or press Jump to newest) → follow again
//
// LEARN: (() => { … })() = run once now, keep names private (see icons.js)
(() => {
  const I = window.BaoIcons;
  // closer than this many pixels to the bottom counts as "at the bottom"
  const BOTTOM_SLACK_PX = 24;
  // LEARN: level → filter group (the chips: Info, Warn, Error)
  //   DEBUG and odd lines go with Info; CRITICAL goes with Error
  const GROUP_BY_LEVEL = {
    DEBUG: "info",
    INFO: "info",
    OTHER: "info",
    WARNING: "warning",
    ERROR: "error",
    CRITICAL: "error",
  };
  // what the level column shows (WARNING is shortened so it fits)
  const LEVEL_LABEL = { WARNING: "WARN", CRITICAL: "CRIT", OTHER: "" };

  // LEARN: page-wide state for this tool (let = can change)
  //   root / ctx / prefs → same meaning as in system_monitor/ui/view.js
  //   cursor = the bookmark Python gave back last time (null → first read)
  //   entries = every line on the page: { line, el, group, searchText }
  //   counts = how many lines per group (shown on the chips)
  let root = null;
  let ctx = null;
  let prefs = null;
  let cursor = null;
  let entries = [];
  let counts = { all: 0, info: 0, warning: 0, error: 0 };
  let levelFilter = "all";
  let searchText = "";
  let following = true;
  let newWhilePaused = 0;
  let pollTimer = null;
  let running = false;
  let mounted = false;
  // same "stale reply" counters as system_monitor/ui/view.js
  let mountGeneration = 0;
  let pollSession = 0;
  let inFlightSession = null;

  const $ = (selector) => root.querySelector(selector);

  // ---------- building lines ----------

  // LEARN: one entry as page elements, built with textContent only
  //   log text can contain < > " (paths, errors, page errors)
  //   textContent never reads it as HTML → nothing in a log can run on the page
  //   (the safe alternative to innerHTML; see escapeHtml in charts.js)
  //   called by → appendLogLines, once per new entry
  function createLineElement(line) {
    const el = document.createElement("div");
    el.className = `lv-line lv-${GROUP_BY_LEVEL[line.level]}`;
    // full date on hover; the column shows only the time part
    el.title = line.time;
    const time = document.createElement("span");
    time.className = "lv-time";
    // "2026-10-22 22:12:03".slice(11) → "22:12:03"
    time.textContent = line.time.slice(11);
    const level = document.createElement("span");
    level.className = "lv-level";
    // ?? → use the short label if there is one, else the level itself
    level.textContent = LEVEL_LABEL[line.level] ?? line.level;
    const text = document.createElement("span");
    const source = document.createElement("span");
    source.className = "lv-source";
    source.textContent = line.source ? `[${line.source}]` : "";
    const message = document.createElement("span");
    message.className = "lv-message";
    message.textContent = line.message;
    // append(a, b) → put both inside, in order
    text.append(source, message);
    el.append(time, level, text);
    return el;
  }

  // traceback lines → one <pre> block under the entry (made on first need)
  function addExtraLines(entry, extraLines) {
    if (!extraLines.length) return;
    let extra = entry.el.querySelector(".lv-extra");
    if (!extra) {
      extra = document.createElement("pre");
      extra.className = "lv-extra";
      entry.el.appendChild(extra);
    }
    // join with line breaks; add one first when the block already has text
    extra.textContent += (extra.textContent ? "\n" : "") + extraLines.join("\n");
    entry.searchText += `\n${extraLines.join("\n").toLowerCase()}`;
  }

  // ---------- filtering ----------

  // LEARN: does this entry pass the chip AND the search box?
  //   includes(x) → true if the text contains x ≈ Python "x in text"
  //   both sides lower-cased → search ignores upper / lower case
  function isEntryShown(entry) {
    if (levelFilter !== "all" && entry.group !== levelFilter) return false;
    return !searchText || entry.searchText.includes(searchText);
  }

  // re-check every line (called when the chip or the search text changes)
  function applyFilterToAllLines() {
    entries.forEach((entry) => {
      // el.hidden = true → the [hidden] rule in view.css hides it
      entry.el.hidden = !isEntryShown(entry);
    });
    updateEmptyState();
    if (following) scrollToNewest();
  }

  function updateCountChips() {
    // Object.entries({a: 1}) → [["a", 1]] ≈ Python dict.items()
    Object.entries(counts).forEach(([group, count]) => {
      $(`[data-count="${group}"]`).textContent = count;
    });
  }

  // nothing at all / nothing matching → the message instead of the list
  function updateEmptyState() {
    const anyShown = entries.some((entry) => !entry.el.hidden);
    $(".lv-card").classList.toggle("empty", !anyShown);
    if (!anyShown && entries.length) $(".lv-empty").textContent = "No lines match the filter.";
  }

  // ---------- adding lines ----------

  // LEARN: put a batch of new lines on the page
  //   called by → pollLogLines, after every answer
  //   1. join "continues_previous" lines to the last entry
  //   2. one element per new entry, filtered, appended at the bottom
  //   3. drop the oldest entries past the "Lines kept" setting
  //   DocumentFragment = an invisible holder: build many elements in it,
  //   add it to the page once → one redraw instead of one per line
  function appendLogLines(lines) {
    if (!lines.length) return;
    const list = $(".lv-lines");
    const fragment = document.createDocumentFragment();
    let added = 0;
    lines.forEach((line) => {
      const last = entries[entries.length - 1];
      if (line.continues_previous && last) {
        // [a, ...b] → a new array: a, then every item of b
        addExtraLines(last, [line.message, ...line.extra_lines]);
        return;
      }
      const group = GROUP_BY_LEVEL[line.level];
      const entry = {
        line,
        el: createLineElement(line),
        group,
        searchText: `${line.source} ${line.message}`.toLowerCase(),
      };
      addExtraLines(entry, line.extra_lines);
      entry.el.hidden = !isEntryShown(entry);
      entries.push(entry);
      counts.all += 1;
      counts[group] += 1;
      fragment.appendChild(entry.el);
      added += 1;
    });
    list.appendChild(fragment);
    dropOldestLines();
    updateCountChips();
    updateEmptyState();
    if (following) {
      scrollToNewest();
    } else {
      newWhilePaused += added;
      updateFollowControls();
    }
  }

  // LEARN: keep at most "Lines kept" entries
  //   industry term: "ring buffer" / "bounded buffer" (oldest drop off)
  //   .splice(0, n) → remove the first n items and give them back
  function dropOldestLines() {
    const extra = entries.length - prefs.max_lines;
    if (extra <= 0) return;
    entries.splice(0, extra).forEach((entry) => {
      entry.el.remove();
      counts.all -= 1;
      counts[entry.group] -= 1;
    });
  }

  // ---------- following ----------

  // LEARN: scrollTop = how far the box is scrolled down (pixels)
  //   scrollHeight = the full height of everything inside it
  //   setting scrollTop to scrollHeight → scrolled to the very bottom
  function scrollToNewest() {
    const list = $(".lv-lines");
    list.scrollTop = list.scrollHeight;
  }

  function isScrolledToBottom() {
    const list = $(".lv-lines");
    // clientHeight = the visible height of the box
    return list.scrollHeight - list.scrollTop - list.clientHeight <= BOTTOM_SLACK_PX;
  }

  function setFollowing(value) {
    following = value;
    if (following) {
      newWhilePaused = 0;
      scrollToNewest();
    }
    updateFollowControls();
  }

  // header dot + label, and the button's icon + text
  function updateFollowControls() {
    root.querySelector(".lv").classList.toggle("paused", !following);
    $(".lv-status-label").textContent = following
      ? "Following"
      : `Paused${newWhilePaused ? ` · ${newWhilePaused} new` : ""}`;
    $(".lv-follow-icon").innerHTML = I.svg(following ? "pause" : "arrow-down-to-line", 13);
    $(".lv-follow-label").textContent = following ? "Pause" : "Jump to newest";
  }

  // ---------- events ----------
  // one listener per kind on the tool's root ("event delegation", settings.js)

  // chip or Pause / Jump button clicked
  function onLogViewerClick(event) {
    const chip = event.target.closest("[data-level]");
    if (chip) {
      levelFilter = chip.dataset.level;
      root.querySelectorAll("[data-level]").forEach((button) => {
        button.classList.toggle("on", button === chip);
      });
      applyFilterToAllLines();
      return;
    }
    if (event.target.closest(".lv-follow")) setFollowing(!following);
  }

  // LEARN: "input" event → fires on every key press in the text box
  //   .trim() → drop spaces at both ends ≈ Python str.strip()
  function onSearchInput(event) {
    searchText = event.target.value.trim().toLowerCase();
    applyFilterToAllLines();
  }

  // LEARN: "scroll" fires for the user's scrolling AND for ours
  //   ours always lands at the bottom → following stays on
  //   the user scrolls up → following turns off; back down → on again
  function onListScroll() {
    const atBottom = isScrolledToBottom();
    if (atBottom !== following) setFollowing(atBottom);
  }

  // ---------- poll loop ----------

  // LEARN: one poll (same pattern as refreshLiveStats in system_monitor)
  //   called by → the timer, and startPolling
  //   skips while the previous one hasn't answered (no pile-up)
  async function pollLogLines() {
    const session = pollSession;
    if (!running || inFlightSession === session) return;
    inFlightSession = session;
    try {
      const chunk = await ctx.call("read_new_log_lines", { cursor, max_lines: prefs.max_lines });
      // the user left the tool / the window hid while waiting → ignore it
      if (!running || session !== pollSession) return;
      cursor = chunk.cursor;
      if (!chunk.file_found && !entries.length) {
        $(".lv-empty").textContent = "No log file yet.";
      }
      appendLogLines(chunk.lines);
    } finally {
      if (inFlightSession === session) inFlightSession = null;
    }
  }

  // called by → mount, and shell.js resume (window shown again)
  function startPolling() {
    if (running || !mounted || document.hidden) return;
    running = true;
    pollSession += 1;
    pollLogLines();
    pollTimer = setInterval(pollLogLines, prefs.refresh_interval_seconds * 1000);
  }

  // called by → unmount, and shell.js pause (window hidden)
  function stopPolling() {
    running = false;
    clearInterval(pollTimer);
  }

  // LEARN: the tool comes on screen
  //   called by → shell.js openView, right after view.html is put in place
  //   starts empty with no cursor → the first poll shows the end of the log
  async function mount(container, context) {
    mountGeneration += 1;
    const generation = mountGeneration;
    root = container;
    ctx = context;
    cursor = null;
    entries = [];
    counts = { all: 0, info: 0, warning: 0, error: 0 };
    levelFilter = "all";
    searchText = "";
    following = true;
    newWhilePaused = 0;
    root.querySelectorAll("[data-icon]").forEach((el) => {
      el.innerHTML = I.svg(el.dataset.icon, 14);
    });
    $(".lv-card").classList.add("empty");
    prefs = await ctx.getPreferences();
    // the user may have switched away while preferences were loading
    if (generation !== mountGeneration || !root) return;
    updateFollowControls();
    root.addEventListener("click", onLogViewerClick);
    $(".lv-search-input").addEventListener("input", onSearchInput);
    // scroll events don't bubble up → listen on the list itself
    $(".lv-lines").addEventListener("scroll", onListScroll);
    mounted = true;
    startPolling();
  }

  // the tool leaves the screen: stop polling, forget the page
  // called by → shell.js openView, before another view opens
  function unmount() {
    mountGeneration += 1;
    mounted = false;
    stopPolling();
    if (root) {
      root.removeEventListener("click", onLogViewerClick);
      $(".lv-search-input").removeEventListener("input", onSearchInput);
      $(".lv-lines").removeEventListener("scroll", onListScroll);
    }
    root = null;
    entries = [];
  }

  // plug into the shell (see shell.js BaoTools); runs once, when loaded
  window.BaoTools.register("log_viewer", {
    mount,
    unmount,
    pause: stopPolling,
    resume: startPolling,
  });
})();
