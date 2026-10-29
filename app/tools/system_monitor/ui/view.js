// LEARN: YOU ARE HERE
//   shell.js runs THIS FILE on first open ▶ it registers mount / unmount
//   ▶ on a timer it calls Python (bridge call ▶ system_monitor/__init__.py)
//   ▶ redraws the cards with charts.js
//   read next → app/tools/log_viewer/ui/view.html

// System Monitor page: polls Python on a timer and redraws the cards.
//
// LEARN: the refresh loop.
//
//   every N s (Settings) ──▶ call("get_live_stats") ──▶ rings, cores, gauges
//   every N s (Settings) ──▶ call("get_power")       ──▶ Power card (default 10 s)
//        └─ if a top apps list is open ──▶ call("get_top_apps") ──▶ rows
//   every N s (Settings) ──▶ call("get_storage")     ──▶ donuts (default 30 s)
//
//   window not in front + "Slow down in the background" on
//     ──▶ every timer waits at least 10 s (industry term: "throttling")
//   once per visit      ──▶ call("get_mac_info")   ──▶ This Mac card
//                           (its uptime line ticks on with every live refresh)
//
//   tool hidden / window minimised ──▶ timers stop; back on screen ──▶ restart
//
//   polling (industry term) = asking again and again on a timer
//
// LEARN: (() => { … })() = run once now, keep names private (see icons.js)
(() => {
  // short names for the shared helpers (charts.js, icons.js)
  const C = window.BaoCharts;
  const I = window.BaoIcons;
  // WARN / CRITICAL = where colours turn yellow / red
  // window not in front → no timer runs more often than this
  const BACKGROUND_MIN_SECONDS = 10;
  const CPU_WARN = 60;
  const CPU_CRITICAL = 85;
  const TEMP_WARN = 70;
  const TEMP_CRITICAL = 90;
  const TEMP_SCALE = { min: 30, max: 100 };
  const DISK_WARN = 75;
  const DISK_CRITICAL = 90;
  // charge state (from power.py) → the word inside the ring
  //   the colours live in view.css (data-state rules)
  const RING_LABEL_BY_STATE = {
    charging: "charging",
    charged: "charged",
    on_hold: "on hold",
    on_battery: "on battery",
    low: "low",
    very_low: "very low",
  };
  // fixed scale for the Mac power sparkline (watts)
  const POWER_SCALE = { min: 0, max: 100 };
  // matches the 60 s of recent values kept in Python (recent_values.py)
  const HISTORY_SECONDS = 60;
  // drive kind → [icon name, tag text] shown under the drive
  const DRIVE_TAGS = {
    external: ["usb", "External"],
    network: ["network", "Network"],
    image: ["disc", "Disk image"],
  };

  // LEARN: page-wide state for this tool (let = can change)
  //   root = the content area we draw in; ctx = shell.js's tool context
  //   prefs = this tool's settings; parts = rings / gauges built at mount
  //   liveTimer / storageTimer = ids from setInterval, to stop them later
  let root = null;
  let ctx = null;
  let prefs = null;
  let parts = null;
  let liveTimer = null;
  let powerTimer = null;
  let storageTimer = null;
  // true while another app's window is in front of ours
  // LEARN: document.hasFocus() → is our window the active one right now?
  let inBackground = !document.hasFocus();
  let running = false;
  // true only once mount has fully finished (preferences loaded)
  let mounted = false;
  // LEARN: counters instead of plain true/false flags. Each mount and each
  // start of the timers gets a new number; a reply that comes back carrying an
  // old number belongs to a previous visit and is ignored, so it can neither
  // draw on the new page nor block the new page's first refresh.
  let mountGeneration = 0;
  let refreshSession = 0;
  let liveInFlightSession = null;
  let storageInFlightSession = null;
  let powerInFlightSession = null;
  // LEARN: rows and donuts are built once and then only updated, so values
  // animate instead of the whole list being redrawn (which made it jump).
  // Rebuilt on every mount, because the shell gives the tool fresh markup.
  // LEARN: Map = key → value store ≈ Python dict (keys can be anything)
  //   here: app key → that app's row on screen
  let topRows = { cpu: new Map(), memory: new Map() };
  let storageView = null;
  // the This Mac answer, kept so the uptime line can tick on
  let macInfo = null;
  // set once a GPU reading has been seen, so one missed reading does not
  // collapse the card to a single gauge and back
  let gpuSeen = false;

  // LEARN: $ is just a short function name (allowed in JS)
  //   $(".sm-load") = the first element inside this tool with class sm-load
  const $ = (selector) => root.querySelector(selector);

  // LEARN: keeps the page still while cards redraw. Reading layout in the
  // middle of a redraw (sparklines measure their width) can make the browser
  // move the scroll position; if it moved, it is put back before the screen
  // is painted. The first correction per part is written to the log, so the
  // cause can be traced.
  // LEARN: Set = a collection with no duplicates ≈ Python set
  const reportedScrollMoves = new Set();

  // called by → the refresh functions, around every redraw
  //   render = the drawing function to run (passed in, run here)
  function renderKeepingScrollPosition(part, render) {
    const before = root.scrollTop;
    render();
    const after = root.scrollTop;
    if (after === before) return;
    root.scrollTop = before;
    if (reportedScrollMoves.has(part)) return;
    reportedScrollMoves.add(part);
    window.pywebview.api.log_client_error(
      `Scroll position moved during ${part} redraw (${before} to ${after}), restored`,
      "system_monitor",
      0,
    );
  }

  // how many points each line chart holds (see charts.js sparklineSlots)
  function historySlots() {
    return C.sparklineSlots(HISTORY_SECONDS, prefs.refresh_interval_seconds);
  }

  // first data arrived → stop the shimmer on that card
  function markCardLoaded(selector) {
    $(selector).classList.remove("loading");
  }

  // ---------- CPU and memory ----------
  // the render functions below: called by → refreshLiveStats, every refresh
  //   input → one part of the Python answer (models.py shapes)
  //   output → that card redrawn

  function renderCpuCard(cpu) {
    const color = C.statusColor(cpu.percent, CPU_WARN, CPU_CRITICAL);
    parts.cpuRing.update(cpu.percent, color, `${Math.round(cpu.percent)}%`, "in use");
    // [1.234, 2.5, 3] → "1.23 · 2.50 · 3.00"  (toFixed(2) = 2 decimals)
    $(".sm-load").textContent = cpu.load_average.map((v) => v.toFixed(2)).join(" · ");
    const hasLayout = cpu.performance_cores + cpu.efficiency_cores > 0;
    $(".sm-core-summary").innerHTML = hasLayout
      ? `<b>${cpu.performance_cores}P + ${cpu.efficiency_cores}E</b> cores`
      : `<b>${cpu.cores.length}</b> cores`;
    // display "none" → hidden; "" → back to the CSS default (shown)
    $(".sm-core-legend").style.display = hasLayout ? "" : "none";
    C.drawSparkline($(".sm-cpu-spark"), cpu.history, { min: 0, max: 100, color: "var(--accent)", slots: historySlots() });
    renderCoreColumns(cpu.cores);
    markCardLoaded(".sm-cpu");
  }

  function renderCoreColumns(cores) {
    const container = $(".sm-cores");
    // build the columns only when the core count changes (first time)
    //   children = the elements directly inside; !== = not equal
    if (container.children.length !== cores.length) {
      container.innerHTML = cores
        .map(
          (core) => `<div class="sm-core" title="Core ${core.index}">
            <div class="col"><div class="fill"></div></div><div class="tag">${core.kind === "?" ? "" : core.kind}</div></div>`,
        )
        .join("");
    }
    // update heights in place so the CSS transition animates them
    cores.forEach((core, i) => {
      const fill = container.children[i].querySelector(".fill");
      fill.style.height = `${core.percent}%`;
      fill.style.background = core.kind === "E" ? "var(--e-core)" : "var(--p-core)";
      // hover text, e.g. "Core 3 Efficiency 42%" (nested ? : picks the word)
      container.children[i].title = `Core ${core.index} ${core.kind === "E" ? "Efficiency" : core.kind === "P" ? "Performance" : ""} ${Math.round(core.percent)}%`;
    });
  }

  function renderMemoryCard(memory) {
    const color = C.statusColor(memory.percent, CPU_WARN, CPU_CRITICAL);
    parts.memoryRing.update(memory.percent, color, `${Math.round(memory.percent)}%`, "used");
    $(".sm-memory-used").textContent = C.formatBytes(memory.used_bytes);
    $(".sm-memory-total").textContent = C.formatBytes(memory.total_bytes, 0);
    $(".sm-swap").textContent = C.formatBytes(memory.swap_used_bytes);
    C.drawSparkline($(".sm-memory-spark"), memory.history, {
      min: 0,
      max: 100,
      color: "var(--accent)",
      slots: historySlots(),
    });
    markCardLoaded(".sm-memory");
  }

  // ---------- temperature ----------

  function renderTemperatureCard(temperature) {
    const card = $(".sm-temperature");
    card.classList.toggle("unavailable", !temperature.available);
    markCardLoaded(".sm-temperature");
    if (!temperature.available) {
      $(".sm-unavailable-reason").textContent = temperature.reason || "";
      return;
    }
    // "chip" = only one whole-chip sensor (fallback) → no separate GPU
    const isChip = temperature.source === "chip";
    if (!isChip && temperature.gpu_hottest != null) gpuSeen = true;
    const showGpu = !isChip && gpuSeen;
    const cpuName = isChip ? "Chip" : "CPU";
    parts.cpuGauge.update(
      temperature.cpu_hottest,
      C.statusColor(temperature.cpu_hottest, TEMP_WARN, TEMP_CRITICAL),
      cpuName,
      `avg ${Math.round(temperature.cpu_average)}°C`,
    );
    $(".sm-gauges").classList.toggle("single", !showGpu);
    $(".sm-gpu-gauge").style.display = showGpu ? "" : "none";
    if (showGpu) {
      const gpu = temperature.gpu_hottest;
      parts.gpuGauge.update(
        gpu,
        gpu == null ? "var(--text-muted)" : C.statusColor(gpu, TEMP_WARN, TEMP_CRITICAL),
        "GPU",
        gpu == null ? "no reading" : "hottest",
      );
    }
    $(".sm-temp-legend").textContent = cpuName;
    $(".sm-legend-gpu").style.display = showGpu ? "" : "none";
    C.drawSparklines(
      $(".sm-temp-spark"),
      [
        { name: cpuName, values: temperature.cpu_history, color: "var(--series-1)" },
        { name: "GPU", values: showGpu ? temperature.gpu_history : [], color: "var(--series-2)" },
      ],
      // { ...TEMP_SCALE, slots } = { min: 30, max: 100, slots }
      { ...TEMP_SCALE, slots: historySlots() },
    );
  }

  // ---------- power ----------

  // 75 → "1 h 15 min", 40 → "40 min"
  function formatMinutes(minutes) {
    // Math.floor → round down; % → remainder ≈ Python // and %
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    return hours ? `${hours} h ${rest} min` : `${rest} min`;
  }

  // 12.3 → "12.3 W", null → "—"; signed adds + for charging ("+48.9 W")
  function formatWatts(watts, signed = false) {
    if (watts == null) return "—";
    const sign = signed && watts > 0 ? "+" : "";
    return `${sign}${watts.toFixed(1)} W`;
  }

  // LEARN: the status line for each charge state → [bold part, grey part]
  //   switch (x) { case "a": … } = pick the block matching x
  //   ≈ Python match x: case "a": …
  function describePowerState(power) {
    const time = power.minutes_remaining == null ? "estimating…" : formatMinutes(power.minutes_remaining);
    switch (power.charge_state) {
      case "charging":
        return ["Charging", `${time} to full`];
      case "charged":
        return ["Charged", ""];
      case "on_hold":
        return ["Plugged in", "holding to protect the battery"];
      case "low":
        return ["Low battery", `${time} left`];
      case "very_low":
        return ["Very low", "plug in soon"];
      default:
        return ["On battery", `${time} left`];
    }
  }

  // LEARN: one box of the charger ▶ Mac ▶ battery row
  //   shown false → the box (and the arrow before it) is hidden
  function setFlowBox(name, text, shown) {
    const box = $(`[data-flow="${name}"]`);
    box.hidden = !shown;
    box.querySelector("b").textContent = text;
    // previousElementSibling = the element right before it (its ▶ arrow)
    const arrow = box.previousElementSibling;
    if (arrow && arrow.classList.contains("sm-flow-arrow")) arrow.hidden = !shown;
  }

  // called by → refreshLiveStats; input → PowerStats (models.py)
  function renderPowerCard(power) {
    const card = $(".sm-power");
    card.classList.toggle("unavailable", !power.available);
    markCardLoaded(".sm-power");
    if (!power.available) {
      card.querySelector(".sm-unavailable-reason").textContent = power.reason || "";
      return;
    }
    // dataset.state = "charging" → data-state="charging" → view.css colours
    card.dataset.state = power.charge_state;
    const [status, time] = describePowerState(power);
    // the ring reads the card's colour variable straight from CSS
    parts.batteryRing.update(
      power.percent,
      "var(--power-color)",
      `${power.percent}%`,
      RING_LABEL_BY_STATE[power.charge_state] ?? "",
    );
    $(".sm-power-status").textContent = status;
    $(".sm-power-time").textContent = time;
    $(".sm-low-power-tag").hidden = !power.low_power_mode;
    setFlowBox("charger", power.charger_watts == null ? "—" : `${power.charger_watts} W`, power.plugged_in);
    setFlowBox("in", formatWatts(power.power_in_watts), power.plugged_in);
    setFlowBox("mac", formatWatts(power.mac_watts), true);
    setFlowBox("battery", formatWatts(power.battery_watts, true), true);
    $('[data-flow="battery"]').classList.toggle("gaining", power.battery_watts > 0);
    C.drawSparkline($(".sm-power-spark"), power.history, {
      ...POWER_SCALE,
      color: "var(--accent)",
      slots: powerHistorySlots(),
    });
    $(".sm-battery-health").textContent = power.health_percent == null ? "—" : `${Math.round(power.health_percent)}%`;
    $(".sm-battery-cycles").textContent = power.cycle_count ?? "—";
    $(".sm-battery-temp").textContent =
      power.temperature_celsius == null ? "—" : `${Math.round(power.temperature_celsius)}°C`;
  }

  // ---------- this mac ----------

  // 38 → "3 yrs 2 mo", 5 → "5 mo", 12 → "1 yr"
  function formatMonths(months) {
    const years = Math.floor(months / 12);
    const rest = months % 12;
    const yearText = years ? `${years} yr${years === 1 ? "" : "s"}` : "";
    const monthText = rest || !years ? `${rest} mo` : "";
    // filter(Boolean) → drop the empty parts; join → "3 yrs 2 mo"
    return [yearText, monthText].filter(Boolean).join(" ");
  }

  // seconds → "3 days 4 h", "5 h 12 min", "8 min"
  function formatUptime(seconds) {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (days) return `${days} day${days === 1 ? "" : "s"} ${hours} h`;
    if (hours) return `${hours} h ${minutes} min`;
    return `${minutes} min`;
  }

  // LEARN: place the timeline dots by date
  //   start = 1 Jan of the model year, end = today
  //   a date's spot = (date − start) ÷ (today − start) × 100 %
  //   new Date(…) → a date; subtracting two dates → milliseconds between
  function placeTimelinePoints(info) {
    const model = $('[data-point="model"]');
    const setup = $('[data-point="setup"]');
    const today = $('[data-point="today"]');
    const timeline = $(".sm-timeline");
    // no model year → no timeline at all
    timeline.hidden = info.model_year == null;
    if (info.model_year == null) return;
    const start = new Date(info.model_year, 0, 1);
    const now = new Date();
    model.style.left = "0%";
    model.querySelector("b").textContent = info.model_year;
    today.style.left = "100%";
    setup.hidden = !info.setup_date;
    if (!info.setup_date) return;
    const setupDate = new Date(info.setup_date);
    // clamp between 0 and 100 in case the dates are odd
    const share = Math.min(1, Math.max(0, (setupDate - start) / (now - start)));
    setup.style.left = `${share * 100}%`;
    // toLocaleDateString(…) → "Aug 2023"
    setup.querySelector("b").textContent = setupDate.toLocaleDateString("en-GB", { month: "short", year: "numeric" });
  }

  // "Up 3 days 4 h since last restart" — called on mount and every live refresh
  function updateUptimeLine() {
    if (!macInfo || macInfo.boot_time == null) return;
    // Date.now() → milliseconds since 1970; boot_time is in seconds
    const seconds = Date.now() / 1000 - macInfo.boot_time;
    $(".sm-mac-uptime").textContent = `Up ${formatUptime(seconds)} since last restart`;
  }

  // called by → mount, once per visit; input → MacInfo (models.py)
  function renderMacCard(info) {
    macInfo = info;
    $(".sm-mac-name").textContent = info.model_name ?? "—";
    $(".sm-mac-specs").textContent =
      [info.chip, info.memory, info.macos_version && `macOS ${info.macos_version}`].filter(Boolean).join(" · ") || "—";
    placeTimelinePoints(info);
    const ages = [];
    if (info.model_age_years != null) ages.push(`Model ~${info.model_age_years} yrs old`);
    if (info.months_since_setup != null) ages.push(`set up ${formatMonths(info.months_since_setup)} ago`);
    $(".sm-mac-ages").textContent = ages.join(" · ");
    updateUptimeLine();
    markCardLoaded(".sm-mac");
  }

  // ask once; a failure leaves "—" and is logged by the shell
  async function loadMacInfo(generation) {
    const info = await ctx.call("get_mac_info");
    if (generation !== mountGeneration || !root) return;
    renderMacCard(info);
  }

  // ---------- top apps ----------

  // one new row element + handles to its parts (updated later)
  // called by → renderAppRows, when an app first appears in the list

  function createAppRow(app) {
    const el = document.createElement("div");
    el.className = "app-row entering";
    el.title = app.name;
    el.innerHTML = `
      <div class="app-icon">${app.icon ? `<img src="${app.icon}" alt="">` : I.svg("terminal", 16)}</div>
      <div class="app-name">${C.escapeHtml(app.name)}</div>
      <div><div class="bar"><div></div></div><div class="mini-ring"></div></div>
      <div class="app-val num"></div>
      <svg class="app-spark"></svg>`;
    // after the fade-in finishes, drop the class (so it can't replay)
    el.addEventListener("animationend", () => el.classList.remove("entering"), { once: true });
    return {
      el,
      bar: el.querySelector(".bar > div"),
      ring: C.createRing(el.querySelector(".mini-ring"), { size: 22, stroke: 4, label: false }),
      value: el.querySelector(".app-val"),
      spark: el.querySelector(".app-spark"),
    };
  }

  // new numbers into an existing row; kind = "cpu" or "memory"
  function updateAppRow(row, app, kind, memoryTotal) {
    const share = kind === "cpu" ? app.cpu_percent : (app.memory_bytes / memoryTotal) * 100;
    const color = C.statusColor(share, CPU_WARN, CPU_CRITICAL);
    row.bar.style.width = `${Math.min(100, share)}%`;
    row.bar.style.background = color;
    row.ring.update(share, color);
    row.value.textContent = kind === "cpu" ? `${share.toFixed(share < 10 ? 1 : 0)}%` : C.formatBytes(app.memory_bytes);
    // fixed scale (whole CPU, or all of RAM) so the line never rescales between refreshes
    C.drawSparkline(row.spark, app.history, {
      min: 0,
      max: kind === "cpu" ? 100 : memoryTotal,
      color: "var(--text-secondary)",
      fill: false,
      slots: historySlots(),
    });
  }

  // LEARN: where each row is on screen now (first step of FLIP below)
  //   [...list.querySelectorAll(…)] → turn the result into a real array
  //   getBoundingClientRect().top → distance from the top of the window
  //   new Map([[el, top], …]) → row element → its top
  function measureRowTops(list) {
    return new Map([...list.querySelectorAll(".app-row")].map((el) => [el, el.getBoundingClientRect().top]));
  }

  // LEARN: a FLIP animation. Note where each row was (First), put the rows in
  // their new order (Last), shift each one back to where it was (Invert),
  // then let the CSS transition slide it home (Play). Nothing moves unless
  // the ranking actually changed.
  function placeRowsInOrder(list, ordered, topsBefore) {
    const current = [...list.children];
    // same rows, same order → nothing to do
    //   .every(f) → true if f is true for all items ≈ Python all(…)
    if (current.length === ordered.length && current.every((el, i) => el === ordered[i])) return;
    // appendChild on an element already in the list MOVES it to the end
    //   → doing it for each row in order = the rows are now sorted
    ordered.forEach((el) => list.appendChild(el));
    ordered.forEach((el) => {
      const before = topsBefore.get(el);
      if (before === undefined) return;
      const delta = before - el.getBoundingClientRect().top;
      if (!delta) return;
      el.style.transition = "none";
      el.style.transform = `translateY(${delta}px)`;
      // reading the layout applies the shift before the transition is restored
      el.getBoundingClientRect();
      el.style.transition = "";
      el.style.transform = "";
    });
  }

  // LEARN: keep the list in step with the newest top apps
  //   called by → refreshLiveStats, when a list is open
  //   rows gone from the top → removed; new apps → new rows
  //   kept rows are reused (only numbers change) → no flicker
  //   industry term: "keyed list reconciliation" (what React / Vue do)
  function renderAppRows(list, rows, apps, kind, memoryTotal) {
    if (!apps.length) {
      rows.clear();
      list.innerHTML = '<div class="top-empty">Collecting…</div>';
      return;
    }
    const topsBefore = measureRowTops(list);
    // ?. → only call remove() if something was found ("optional chaining")
    list.querySelector(".top-empty")?.remove();
    const keys = new Set(apps.map((app) => app.key));
    rows.forEach((row, key) => {
      if (!keys.has(key)) {
        row.el.remove();
        rows.delete(key);
      }
    });
    const ordered = apps.map((app) => {
      if (!rows.has(app.key)) rows.set(app.key, createAppRow(app));
      const row = rows.get(app.key);
      updateAppRow(row, app, kind, memoryTotal);
      return row.el;
    });
    placeRowsInOrder(list, ordered, topsBefore);
  }

  function isTopListOpen(kind) {
    return kind === "cpu" ? prefs.cpu_top_apps_open : prefs.memory_top_apps_open;
  }

  // show / hide both lists to match the saved settings
  function applyTopListOpenState() {
    root.querySelectorAll(".top-toggle").forEach((button) => {
      const open = isTopListOpen(button.dataset.list);
      button.classList.toggle("open", open);
      $(`.sm-${button.dataset.list}-top`).classList.toggle("open", open);
    });
  }

  // "Top apps ▸" clicked → flip and SAVE that setting, then redraw
  // one listener for the whole tool ("event delegation", see settings.js)
  async function onTopToggleClick(event) {
    const button = event.target.closest(".top-toggle");
    if (!button) return;
    const kind = button.dataset.list;
    const field = kind === "cpu" ? "cpu_top_apps_open" : "memory_top_apps_open";
    const generation = mountGeneration;
    const updated = await ctx.setPreference(field, !isTopListOpen(kind));
    // the user may have left the tool while the preference was saving
    if (generation !== mountGeneration || !root) return;
    prefs = updated;
    applyTopListOpenState();
    refreshLiveStats();
  }

  // ---------- storage ----------

  // network drives and disk images → drawn muted (dotted ring, grey)

  function isSecondaryDrive(drive) {
    return drive.kind === "network" || drive.kind === "image";
  }

  // one drive: ring + name + sizes; bigger for the main disk
  // called by → renderStorageCard, when the set of drives changes
  function createDriveView(drive) {
    const isMain = drive.kind === "main";
    const isSecondary = isSecondaryDrive(drive);
    const tag = DRIVE_TAGS[drive.kind];
    const el = document.createElement("div");
    el.className = "drive";
    el.classList.toggle("main", isMain);
    el.classList.toggle("secondary", isSecondary);
    el.innerHTML = `<div class="drive-ring"></div>
      <div class="drive-text"><div class="d-name"></div>
        <div class="d-meta num"></div>
        ${tag ? `<span class="d-tag">${I.svg(tag[0], 11)}${tag[1]}</span>` : ""}</div>`;
    return {
      el,
      ring: C.createRing(el.querySelector(".drive-ring"), {
        size: isMain ? 120 : drive.kind === "external" ? 76 : 52,
        stroke: isMain ? 14 : drive.kind === "external" ? 10 : 7,
        dashed: isSecondary,
      }),
      name: el.querySelector(".d-name"),
      meta: el.querySelector(".d-meta"),
    };
  }

  // new numbers into an existing drive view
  function updateDriveView(view, drive) {
    const percent = drive.used_percent ?? 0;
    const color =
      !drive.responding || isSecondaryDrive(drive) ? "var(--text-muted)" : C.statusColor(percent, DISK_WARN, DISK_CRITICAL);
    view.ring.update(percent, color, drive.responding ? `${Math.round(percent)}%` : "—");
    view.name.textContent = drive.name;
    // built only from formatted numbers, never from system names
    // nested a ? b : c ? d : e = if / else if / else
    //   not responding → "Not responding"
    //   main disk      → "X free · Y of Z"
    //   any other      → "X free of Z"
    view.meta.innerHTML = !drive.responding
      ? "Not responding"
      : drive.kind === "main"
        ? `<b>${C.formatBytes(drive.free_bytes)}</b> free · ${C.formatBytes(drive.used_bytes)} of ${C.formatBytes(drive.total_bytes)}`
        : `${C.formatBytes(drive.free_bytes)} free of ${C.formatBytes(drive.total_bytes)}`;
    view.el.classList.toggle("not-responding", !drive.responding);
  }

  // the donuts are rebuilt only when drives are plugged in or removed;
  // otherwise each one just animates to its new value
  function renderStorageCard(storage) {
    const drives = storage.drives;
    // signature = one text naming every drive; it changes only when drives
    //   are added / removed → "main:/|external:/Volumes/USB"
    const signature = drives.map((drive) => `${drive.kind}:${drive.mountpoint}`).join("|");
    if (!storageView || storageView.signature !== signature) {
      const container = $(".sm-drives");
      container.innerHTML = "";
      storageView = { signature, views: drives.map(createDriveView) };
      storageView.views.forEach((view, i) => {
        // a thin line between the main disk and the rest
        if (i === 1 && drives[0].kind === "main") container.insertAdjacentHTML("beforeend", '<div class="drives-divider"></div>');
        container.appendChild(view.el);
      });
    }
    drives.forEach((drive, i) => updateDriveView(storageView.views[i], drive));
    markCardLoaded(".sm-storage");
  }

  // ---------- refresh loop ----------

  // is this reply still wanted? (see the counters near the top)

  function isRefreshSessionCurrent(session) {
    return running && session === refreshSession;
  }

  // LEARN: one live refresh
  //   called by → the timer, startRefreshTimers, onTopToggleClick
  //   skips if the previous one hasn't answered yet (no pile-up)
  //   try / finally → the "in flight" mark is always cleared, even on error
  async function refreshLiveStats() {
    const session = refreshSession;
    if (!running || liveInFlightSession === session) return;
    liveInFlightSession = session;
    try {
      const stats = await ctx.call("get_live_stats");
      if (!isRefreshSessionCurrent(session)) return;
      renderKeepingScrollPosition("live stats", () => {
        renderCpuCard(stats.cpu);
        renderMemoryCard(stats.memory);
        renderTemperatureCard(stats.temperature);
        updateUptimeLine();
      });
      if (prefs.cpu_top_apps_open || prefs.memory_top_apps_open) {
        const top = await ctx.call("get_top_apps", { limit: prefs.top_apps_count });
        if (!isRefreshSessionCurrent(session)) return;
        renderKeepingScrollPosition("top apps", () => {
          if (prefs.cpu_top_apps_open) {
            renderAppRows($(".sm-cpu-top"), topRows.cpu, top.by_cpu, "cpu", top.memory_total_bytes);
          }
          if (prefs.memory_top_apps_open) {
            renderAppRows($(".sm-memory-top"), topRows.memory, top.by_memory, "memory", top.memory_total_bytes);
          }
        });
      }
    } finally {
      if (liveInFlightSession === session) liveInFlightSession = null;
    }
  }

  // one battery refresh (same pattern as refreshLiveStats)
  async function refreshPower() {
    const session = refreshSession;
    if (!running || powerInFlightSession === session) return;
    powerInFlightSession = session;
    try {
      const power = await ctx.call("get_power");
      if (isRefreshSessionCurrent(session)) renderKeepingScrollPosition("power", () => renderPowerCard(power));
    } finally {
      if (powerInFlightSession === session) powerInFlightSession = null;
    }
  }

  // one storage refresh (same pattern as refreshLiveStats)
  async function refreshStorage() {
    const session = refreshSession;
    if (!running || storageInFlightSession === session) return;
    storageInFlightSession = session;
    try {
      const storage = await ctx.call("get_storage");
      if (isRefreshSessionCurrent(session)) renderKeepingScrollPosition("storage", () => renderStorageCard(storage));
    } finally {
      if (storageInFlightSession === session) storageInFlightSession = null;
    }
  }

  // LEARN: setInterval(f, ms) → call f every ms milliseconds until stopped
  //   gives back an id; clearInterval(id) stops it
  //   called by → mount, and shell.js resume (window shown again)
  function startRefreshTimers() {
    if (running || !mounted || document.hidden) return;
    running = true;
    refreshSession += 1;
    refreshLiveStats();
    refreshPower();
    refreshStorage();
    liveTimer = setInterval(refreshLiveStats, effectiveSeconds(prefs.refresh_interval_seconds) * 1000);
    powerTimer = setInterval(refreshPower, effectiveSeconds(prefs.battery_refresh_seconds) * 1000);
    storageTimer = setInterval(refreshStorage, effectiveSeconds(prefs.storage_refresh_seconds) * 1000);
    updateRefreshLabel();
  }

  // called by → unmount, and shell.js pause (window hidden)
  function stopRefreshTimers() {
    running = false;
    clearInterval(liveTimer);
    clearInterval(powerTimer);
    clearInterval(storageTimer);
  }

  // LEARN: the interval a timer really uses
  //   in front, or slowing down switched off → the setting as chosen
  //   in the background → at least 10 s (Math.max picks the larger)
  function effectiveSeconds(seconds) {
    const slowed = prefs.slow_down_in_background && inBackground;
    return slowed ? Math.max(seconds, BACKGROUND_MIN_SECONDS) : seconds;
  }

  // the battery chart's point count follows the battery's own interval
  function powerHistorySlots() {
    return C.sparklineSlots(HISTORY_SECONDS, effectiveSeconds(prefs.battery_refresh_seconds));
  }

  // 30 → "30s", 60 → "1 min", 300 → "5 min"
  function formatInterval(seconds) {
    return seconds < 60 ? `${seconds}s` : `${seconds / 60} min`;
  }

  // LEARN: every "how often" text comes from the settings, never typed in
  //   the HTML → a label can't drift from what the timer really does
  //   "Live · every 2s", or "Live · every 10s (background)" while slowed
  //   Storage card: "updates every 5 min"
  function updateRefreshLabel() {
    const seconds = effectiveSeconds(prefs.refresh_interval_seconds);
    const slowed = seconds !== prefs.refresh_interval_seconds;
    $(".sm-refresh-label").textContent = `Live · every ${formatInterval(seconds)}${slowed ? " (background)" : ""}`;
    $(".sm-storage-note").textContent = `updates every ${formatInterval(effectiveSeconds(prefs.storage_refresh_seconds))}`;
  }

  // LEARN: the window moved to the back / came to the front
  //   "blur" = our window stopped being the active one; "focus" = it's back
  //   → restart the timers with the new intervals (only if they're running)
  function onWindowFocusChange(event) {
    inBackground = event.type === "blur";
    if (!running) return;
    stopRefreshTimers();
    startRefreshTimers();
  }

  // LEARN: the tool comes on screen
  //   called by → shell.js openView, right after view.html is put in place
  //   container = the content area; context = { call, getPreferences, … }
  //   builds rings / gauges, loads settings, starts the timers
  async function mount(container, context) {
    mountGeneration += 1;
    const generation = mountGeneration;
    root = container;
    ctx = context;
    topRows = { cpu: new Map(), memory: new Map() };
    storageView = null;
    macInfo = null;
    root.querySelectorAll("[data-icon]").forEach((el) => {
      el.innerHTML = I.svg(el.dataset.icon, el.classList.contains("sm-unavailable-icon") ? 28 : 14);
    });
    parts = {
      cpuRing: C.createRing($(".sm-cpu-ring"), { size: 108, stroke: 12 }),
      memoryRing: C.createRing($(".sm-memory-ring"), { size: 108, stroke: 12 }),
      cpuGauge: C.createArcGauge($(".sm-cpu-gauge"), TEMP_SCALE),
      gpuGauge: C.createArcGauge($(".sm-gpu-gauge"), TEMP_SCALE),
      batteryRing: C.createRing($(".sm-battery-ring"), { size: 96, stroke: 11 }),
    };
    prefs = await ctx.getPreferences();
    // the user may have switched away (unmount) while preferences were loading
    if (generation !== mountGeneration || !root) return;
    inBackground = !document.hasFocus();
    updateRefreshLabel();
    // an open list reserves room for every row up front, so it never grows as rows arrive
    // setProperty("--x", v) → set a CSS variable from JS (used in view.css)
    $(".sm").style.setProperty("--sm-top-count", prefs.top_apps_count);
    applyTopListOpenState();
    loadMacInfo(generation);
    root.addEventListener("click", onTopToggleClick);
    window.addEventListener("focus", onWindowFocusChange);
    window.addEventListener("blur", onWindowFocusChange);
    mounted = true;
    // LEARN: if the window was hidden while mount was waiting, the timers stay
    // off; the shell's next "shown" event calls resume and starts them.
    startRefreshTimers();
  }

  // the tool leaves the screen: stop everything, forget the page
  // called by → shell.js openView, before another view opens
  function unmount() {
    mountGeneration += 1;
    mounted = false;
    stopRefreshTimers();
    if (root) root.removeEventListener("click", onTopToggleClick);
    window.removeEventListener("focus", onWindowFocusChange);
    window.removeEventListener("blur", onWindowFocusChange);
    root = null;
  }

  // plug into the shell (see shell.js BaoTools); runs once, when loaded
  //   pause: stopRefreshTimers → "use this function for pause"
  window.BaoTools.register("system_monitor", {
    mount,
    unmount,
    pause: stopRefreshTimers,
    resume: startRefreshTimers,
  });
})();
